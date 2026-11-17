"""Token azaltma önerileri: yerel verilere bakan kural motoru. Model çağırmaz, veri göndermez."""
from __future__ import annotations

import config
import indexer
import bant_ops


def _tok(chars: int) -> int:
    return round(chars / 3.2)


def _fiyat_girdi(model: str = "claude-opus-5-5") -> float:
    p = config.fiyat(model)
    return p[0] if p else 4.0


def uret(gun: int = 30) -> dict:
    oturumlar = indexer.ozetler(gun)
    bant = bant_ops.bant(gun)
    n_oturum = max(1, len(oturumlar))
    toplam_cost = sum(o.get("cost") or 0 for o in oturumlar)
    toplam_cagri = sum(o.get("calls") or 0 for o in oturumlar)
    oneriler = []

    def ekle(oncelik, baslik, neden, tasarruf, eylem, hedef=None, kanit=None):
        oneriler.append({"oncelik": oncelik, "baslik": baslik, "neden": neden, "tasarruf": tasarruf,
                         "eylem": eylem, "hedef": hedef, "kanit": kanit or []})

    # 1) Her araç çağrısına eklenen hook bağlamı
    for h in bant["hook_ctx"]:
        if h["olay"] in ("PreToolUse", "PostToolUse", "UserPromptSubmit") and h["token"] > 20000:
            ort = h["ortalama"]
            ekle(1 if h["token"] > 150000 else 2,
                 f"{h['olay']} hook'u her çağrıya bağlam ekliyor",
                 f"Son {gun} günde {h['kez']} kez, ortalama {ort} karakter (~{_tok(ort)} token) eklendi; "
                 f"toplam ~{h['token']:,} token. Bu metin bağlamda kalıp sonraki her model çağrısında yeniden okunur.",
                 f"~{h['token']:,} token bağlam (sonraki çağrılarda önbellekten tekrar okunur)",
                 "Hook'un eşleştiricisini daralt (ör. yalnız belirli dosya türleri) ya da Bant sekmesinden kapat.",
                 {"sekme": "bant", "tur": "hook", "olay": h["olay"]})

    # 2) Hiç kullanılmayan skill'ler: her oturumun başında açıklamaları listelenir
    kullanilmayan = [s for s in bant["skills"] if s["acik"] and not s.get("kilitli") and s["kullanim"] == 0]
    if kullanilmayan:
        tok = sum(s["liste_token"] for s in kullanilmayan)
        ekle(2 if tok > 1500 else 3,
             f"{len(kullanilmayan)} skill son {gun} günde hiç çağrılmadı",
             "Skill açıklamaları her oturumun başında modele listelenir. Kullanılmayanlar her oturumda boşuna yer kaplar.",
             f"oturum başına ~{tok:,} token, {gun} günde ~{tok * n_oturum:,} token",
             "Bant sekmesinde bu skill'leri kapat; gerektiğinde tek tıkla geri açılır.",
             {"sekme": "bant", "tur": "skill", "filtre": "kullanilmayan"},
             [s["ad"] for s in kullanilmayan][:40])

    # 3) Kullanılmayan MCP sunucuları
    bos_mcp = [m for m in bant["mcp"] if m["acik"] and not m.get("kilitli") and m["kullanim"] == 0]
    if bos_mcp:
        ekle(2, f"{len(bos_mcp)} MCP sunucusu hiç kullanılmadı",
             "Açık MCP sunucularının araç tanımları oturumlara yüklenir; bağlanamayanlar her açılışta zaman da kaybettirir.",
             "araç tanımı kadar bağlam ve açılış süresi",
             "Bant sekmesinde kapat; kayıtları panoda saklanır, tek tıkla geri eklenir.",
             {"sekme": "bant", "tur": "mcp"}, [m["ad"] for m in bos_mcp])

    # 4) Gereksiz okumalar
    gereksiz = sorted(((o.get("redundant") or 0, o) for o in oturumlar), key=lambda x: -x[0])
    top_g = sum(x[0] for x in gereksiz)
    if top_g > 20:
        ekle(2, f"{top_g} gereksiz dosya okuması",
             "Aynı ajan, arada değişmemiş bir dosyayı yeniden okumuş. Her okuma dosyanın tamamını yeniden bağlama ekler.",
             f"{top_g} okuma", "Brif'lere 'okuduğun dosyayı değişmediyse yeniden okuma, notlarından devam et' kuralı ekle; "
                               "büyük dosyalarda offset/limit kullan.",
             {"sekme": "oturumlar"}, [f"{o['title'][:40]}: {n}" for n, o in gereksiz[:5] if n])

    # 5) Opus ile yapılan kısa ve basit alt ajan işleri
    adaylar = []
    for o in oturumlar:
        for a in o.get("subagent_summary") or []:
            m = (a.get("model") or "")
            if ("opus" in m or "fable" in m) and (a.get("calls") or 0) <= 25 and (a.get("out") or 0) < 15000:
                adaylar.append((a, o))
    if len(adaylar) >= 3:
        harcanan = sum(a.get("cost") or 0 for a, _ in adaylar)
        sonnet_oran = config.fiyat("claude-sonnet-5-5")[0] / config.fiyat("claude-opus-5-5")[0]
        ekle(2, f"{len(adaylar)} kısa alt ajan işi Opus/Fable ile çalışmış",
             "25 çağrıdan kısa ve az çıktılı işler genelde Sonnet ile aynı kalitede biter.",
             f"~{harcanan * (1 - sonnet_oran):.2f} $ API karşılığı ({harcanan:.2f} $ → {harcanan * sonnet_oran:.2f} $)",
             "Ajanlar sekmesinde bu iş türlerini 'hizli-isci' (Sonnet, medium) ajanına yönlendir.",
             {"sekme": "ajanlar"}, [f"{a.get('label', '')[:45]} ({a.get('calls')} çağrı)" for a, _ in adaylar[:8]])

    # 6) Çok uzun oturumlar ve sıkıştırmalar
    uzun = [o for o in oturumlar if (o.get("compacts") or 0) >= 2 or (o.get("calls") or 0) > 1500]
    if uzun:
        ekle(2, f"{len(uzun)} oturum çok uzun sürmüş",
             "Uzun oturumda bağlam büyür; her çağrı tüm geçmişi önbellekten tekrar okur ve sıkıştırma (compact) bilgi kaybettirir.",
             "çağrı başına okunan bağlam",
             "Her yeni iş için yeni oturum aç; kalınan yeri kısa bir devir notu ya da hafıza dosyası taşısın.",
             {"sekme": "oturumlar"},
             [f"{o['title'][:40]}: {o.get('calls')} çağrı, {o.get('compacts', 0)} sıkıştırma" for o in uzun[:6]])

    # 7) Hata ve tekrarlar
    hata = sum(o.get("errors") or 0 for o in oturumlar)
    tekrar = sum(o.get("retries") or 0 for o in oturumlar)
    if hata > 30:
        ekle(3, f"{hata} başarısız araç çağrısı, {tekrar} aynı çağrının tekrarı",
             "Her hata bir model turu ve hata metni kadar bağlam harcar; aynı hatanın tekrarı daha da pahalı.",
             f"~{hata} model turu", "Geçmiş sekmesinde hata veren adımlara bak; tekrar eden hatayı ders hafızasına yaz.",
             {"sekme": "gecmis", "filtre": "hata"})

    # 8) Büyük hafıza dosyaları
    for h in bant["hafiza"]:
        if h["acik"] and h["token"] > 2500 and not h.get("kilitli"):
            ekle(3, f"{h['yol'].split(chr(92))[-1]} her oturumda ~{h['token']:,} token",
                 "Bu dosya ilgili klasörde açılan her oturuma otomatik yüklenir.",
                 f"oturum başına ~{h['token']:,} token",
                 "Eskimiş satırları Bant sekmesinden banttan çıkar ya da dosyayı kısalt.",
                 {"sekme": "bant", "tur": "hafiza", "id": h["id"]})

    # 9) Hook hataları
    hatali = [h for h in bant["hooks"] if h.get("hata")]
    if hatali:
        ekle(2, f"{len(hatali)} hook hata veriyor",
             "Hata veren hook her çalıştığında süre kaybettirir, işini de yapmıyor olabilir.",
             "çalışma süresi", "Bant sekmesinde hook'un komutuna bak; gerekirse kapat.",
             {"sekme": "bant", "tur": "hook"}, [f"{h['ad']} @{h['olay']}: {h['hata']} hata" for h in hatali])

    oneriler.sort(key=lambda x: x["oncelik"])
    return {"gun": gun, "oturum": len(oturumlar), "toplam_cost": round(toplam_cost, 2),
            "toplam_cagri": toplam_cagri, "oneriler": oneriler}
