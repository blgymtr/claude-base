"""Alt ajanlar: gözlenen kullanım, özel ajan tanımları ve yönlendirme tablosu.

Gerçek kontrol noktaları:
- Agent aracı çağrısında yalnız `model` seçilebilir; efor ajanın tanım dosyasından gelir.
  Bu yüzden efor kontrolü ~/.claude/agents/<ad>.md içindeki `model:` ve `effort:` alanlarıyla yapılır.
- Ana ajan hangi işe hangi ajanı/modeli vereceğini ~/.claude/bant-yonlendirme.md tablosundan okur;
  bu dosya ~/.claude/CLAUDE.md içine `@bant-yonlendirme.md` satırıyla bağlanır.
- Varsayılan alt ajan modeli settings.json içindeki env.CLAUDE_CODE_SUBAGENT_MODEL ile verilir.
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import bant_ops
import config
import indexer

MODELLER = ["inherit", "haiku", "sonnet", "opus", "fable"]
EFORLAR = ["low", "medium", "high", "xhigh", "max"]
YONLENDIRME_JSON = config.DATA_DIR / "yonlendirme.json"
IMPORT_SATIRI = "@bant-yonlendirme.md"
_AD_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,40}$")

ONERILEN = [
    {"ad": "hizli-isci", "model": "sonnet", "effort": "medium",
     "aciklama": "Açık, adımları belli işler: brifteki değişikliği uygula, test çalıştır, dosya düzenle. Kısa rapor verir."},
    {"ad": "derin-isci", "model": "opus", "effort": "high",
     "aciklama": "Tasarım, zor hata, mimari ve araştırma gerektiren işler. Kendi planını kurar, bulgularını kanıtla raporlar."},
    {"ad": "toplu-veri", "model": "haiku", "effort": "low",
     "aciklama": "Çok sayıda dosyayı tarama, sınıflama, veri temizleme ve özetleme gibi hacimli, basit işler."},
]

VARSAYILAN_YONLENDIRME = {
    "varsayilan_model": "",
    "satirlar": [
        {"is": "Brifi belli kod değişikliği, test, düzeltme", "ajan": "hizli-isci", "model": "sonnet", "effort": "medium"},
        {"is": "Tasarım, mimari, zor hata, araştırma", "ajan": "derin-isci", "model": "opus", "effort": "high"},
        {"is": "Toplu dosya tarama, veri temizleme, özet", "ajan": "toplu-veri", "model": "haiku", "effort": "low"},
    ],
}


# ----------------------------------------------------------------------------- gözlenen kullanım

def gozlenen(gun: int = 30) -> dict:
    gruplar = {}
    toplam = {"ajan": 0, "cost": 0.0}
    for o in indexer.ozetler(gun):
        for a in o.get("subagent_summary") or []:
            model = a.get("model") or a.get("model_req") or "?"
            key = (a.get("type") or "?", model, a.get("effort") or "?")
            g = gruplar.setdefault(key, {"tur": key[0], "model": key[1], "effort": key[2], "adet": 0, "cost": 0.0,
                                         "out": 0, "calls": 0, "sure": 0, "hata": 0, "ornek": []})
            g["adet"] += 1
            g["cost"] += a.get("cost") or 0
            g["out"] += a.get("out") or 0
            g["calls"] += a.get("calls") or 0
            g["sure"] += a.get("duration") or 0
            g["hata"] += a.get("errors") or 0
            if len(g["ornek"]) < 4:
                g["ornek"].append(a.get("label"))
            toplam["ajan"] += 1
            toplam["cost"] += a.get("cost") or 0
    satirlar = sorted(gruplar.values(), key=lambda g: -g["cost"])
    for g in satirlar:
        g["cost"] = round(g["cost"], 2)
        g["ort_cost"] = round(g["cost"] / max(1, g["adet"]), 3)
        g["ort_sure"] = round(g["sure"] / max(1, g["adet"]))
    toplam["cost"] = round(toplam["cost"], 2)
    return {"gun": gun, "satirlar": satirlar, "toplam": toplam}


# ----------------------------------------------------------------------------- ajan tanımları

def _tanim_oku(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    fm = bant_ops._frontmatter(text)
    govde = re.sub(r"^---\s*\n.*?\n---\s*\n?", "", text, count=1, flags=re.S)
    return {"ad": fm.get("name") or path.stem, "dosya": path.stem, "aciklama": fm.get("description", ""),
            "model": fm.get("model", "inherit"), "effort": fm.get("effort", ""), "tools": fm.get("tools", ""),
            "govde": govde.strip(), "yol": str(path)}


def tanimlar() -> list[dict]:
    out = []
    for base, acik in ((config.AGENTS_DIR, True), (config.KAPALI_DIR / "agents", False)):
        if base.exists():
            for p in sorted(base.glob("*.md")):
                d = _tanim_oku(p)
                d["acik"] = acik
                out.append(d)
    return out


def _tek_satir(s: str) -> str:
    return " ".join((s or "").split()).replace('"', "'")


def tanim_kaydet(ad: str, aciklama: str, model: str, effort: str, govde: str = "", tools: str = "") -> str:
    if not _AD_RE.match(ad or ""):
        raise ValueError("Ajan adı küçük harf, rakam ve tire olmalı (2-41 karakter)")
    if model not in MODELLER:
        raise ValueError("Geçersiz model")
    if effort and effort not in EFORLAR:
        raise ValueError("Geçersiz efor")
    if not (aciklama or "").strip():
        raise ValueError("Açıklama gerekli: ana ajan ne zaman bu ajanı seçeceğini buradan anlar")
    config.AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    yol = config.AGENTS_DIR / f"{ad}.md"
    if yol.exists():
        bant_ops._yedekle(yol)
    satirlar = ["---", f"name: {ad}", f'description: "{_tek_satir(aciklama)}"']
    if model != "inherit":
        satirlar.append(f"model: {model}")
    if effort:
        satirlar.append(f"effort: {effort}")
    if tools.strip():
        satirlar.append(f"tools: {_tek_satir(tools)}")
    satirlar.append("---")
    govde = govde.strip() or (
        "Sen bu projelerde çalışan bir alt ajansın. Sana verilen brifi baştan sona oku ve uygula.\n"
        "Brifin dışına çıkma; belirsiz bir nokta varsa varsayımını raporda açıkça yaz.\n"
        "İşin sonunda kısa bir rapor ver: ne yaptın, hangi dosyaları değiştirdin, neyi doğruladın, ne açık kaldı.")
    yol.write_text("\n".join(satirlar) + "\n\n" + govde + "\n", encoding="utf-8")
    return f"{ad} kaydedildi; yeni oturumlarda kullanılabilir"


def tanim_degistir(ad: str, ac: bool) -> str:
    if not _AD_RE.match(ad or ""):
        raise ValueError("Geçersiz ad")
    acik = config.AGENTS_DIR / f"{ad}.md"
    kapali = config.KAPALI_DIR / "agents" / f"{ad}.md"
    kaynak, hedef = (kapali, acik) if ac else (acik, kapali)
    if not kaynak.exists():
        raise ValueError("Ajan bulunamadı")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(kaynak), str(hedef))
    return f"{ad} {'açıldı' if ac else 'kapatıldı'}"


def onerilenleri_kur() -> list[str]:
    out = []
    for o in ONERILEN:
        if (config.AGENTS_DIR / f"{o['ad']}.md").exists():
            out.append(f"{o['ad']} zaten var, dokunulmadı")
            continue
        out.append(tanim_kaydet(o["ad"], o["aciklama"], o["model"], o["effort"]))
    return out


# ----------------------------------------------------------------------------- yönlendirme

def yonlendirme_oku() -> dict:
    d = bant_ops._oku_json(YONLENDIRME_JSON, None) or {"satirlar": []}
    d["kayitli"] = YONLENDIRME_JSON.exists()
    # Öneri satırları yalnız öneri olarak döner; kullanıcı kaydetmeden tabloya girmez.
    d["oneri_satirlar"] = VARSAYILAN_YONLENDIRME["satirlar"]
    s = bant_ops._oku_json(config.SETTINGS_PATH)
    d["varsayilan_model"] = (s.get("env") or {}).get("CLAUDE_CODE_SUBAGENT_MODEL", "")
    gm = config.GLOBAL_CLAUDE_MD
    gm_text = gm.read_text(encoding="utf-8") if gm.exists() else ""
    d["bagli"] = IMPORT_SATIRI in gm_text and config.YONLENDIRME_MD.exists()
    d["md_yolu"] = str(config.YONLENDIRME_MD)
    return d


def _md_uret(satirlar: list[dict]) -> str:
    tablo = ["| İş türü | Alt ajan (subagent_type) | Model | Efor |", "|---|---|---|---|"]
    for r in satirlar:
        tablo.append(f"| {_tek_satir(r.get('is'))} | {r.get('ajan') or '—'} | {r.get('model') or '—'} | {r.get('effort') or '—'} |")
    return (
        "# Alt ajan yönlendirmesi (Claude Base)\n\n"
        "Bu dosyayı Claude Base üretir; elle değil, panodaki Ajanlar sekmesinden düzenle.\n\n"
        "Alt ajan başlatırken işi aşağıdaki türlerden birine eşle:\n"
        "- Satırda alt ajan adı varsa Agent aracında `subagent_type` olarak onu ver; model ve eforu o ajanın tanımı belirler.\n"
        "- Alt ajan yoksa `model` parametresini tablodaki model yap.\n"
        "- Hiçbir satıra uymayan işte kendi muhakemenle seç ve son raporda hangi modeli neden seçtiğini bir cümleyle yaz.\n"
        "- Kullanıcı o anda açıkça başka bir model ya da efor isterse onun isteği bu tablodan önce gelir.\n\n"
        + "\n".join(tablo) + "\n"
    )


def yonlendirme_kaydet(satirlar: list[dict], varsayilan_model: str | None, bagla: bool = True) -> str:
    temiz = []
    for r in satirlar:
        if not _tek_satir(r.get("is")):
            continue
        ajan = (r.get("ajan") or "").strip()
        if ajan and ajan not in ("general-purpose", "Explore", "Plan"):
            if not _AD_RE.match(ajan):
                raise ValueError(f"Geçersiz ajan adı: {ajan}")
            if not (config.AGENTS_DIR / f"{ajan}.md").exists():
                raise ValueError(f"'{ajan}' adlı ajan tanımlı değil. Önce aşağıdan ajanı kur ya da satırdan ajanı kaldır.")
        model = r.get("model") or ""
        effort = r.get("effort") or ""
        if model and model not in MODELLER:
            raise ValueError(f"Geçersiz model: {model}")
        if effort and effort not in EFORLAR:
            raise ValueError(f"Geçersiz efor: {effort}")
        temiz.append({"is": _tek_satir(r.get("is")), "ajan": ajan, "model": model, "effort": effort})
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    YONLENDIRME_JSON.write_text(json.dumps({"satirlar": temiz}, ensure_ascii=False, indent=2), encoding="utf-8")
    if config.YONLENDIRME_MD.exists():
        bant_ops._yedekle(config.YONLENDIRME_MD)
    config.YONLENDIRME_MD.write_text(_md_uret(temiz), encoding="utf-8")
    mesaj = ["Yönlendirme tablosu kaydedildi"]
    if bagla:
        gm = config.GLOBAL_CLAUDE_MD
        text = gm.read_text(encoding="utf-8") if gm.exists() else ""
        if IMPORT_SATIRI not in text:
            bant_ops._yedekle(gm)
            gm.write_text(text.rstrip("\n") + ("\n\n" if text else "") + "# Alt ajan yönlendirmesi\n\n" + IMPORT_SATIRI + "\n",
                          encoding="utf-8")
            mesaj.append("~/.claude/CLAUDE.md dosyasına bağlandı")
    if varsayilan_model is not None:
        s = bant_ops._oku_json(config.SETTINGS_PATH)
        env = s.setdefault("env", {})
        if varsayilan_model:
            if varsayilan_model not in MODELLER[1:]:
                raise ValueError("Geçersiz varsayılan model")
            if env.get("CLAUDE_CODE_SUBAGENT_MODEL") != varsayilan_model:
                env["CLAUDE_CODE_SUBAGENT_MODEL"] = varsayilan_model
                bant_ops._yaz_json(config.SETTINGS_PATH, s)
                mesaj.append(f"varsayılan alt ajan modeli: {varsayilan_model}")
        elif "CLAUDE_CODE_SUBAGENT_MODEL" in env:
            env.pop("CLAUDE_CODE_SUBAGENT_MODEL")
            if not env:
                s.pop("env")
            bant_ops._yaz_json(config.SETTINGS_PATH, s)
            mesaj.append("varsayılan alt ajan modeli kaldırıldı (ana ajan seçer)")
    return "; ".join(mesaj) + ". Yeni oturumlarda geçerli."


def yonlendirme_kopar() -> str:
    gm = config.GLOBAL_CLAUDE_MD
    if gm.exists():
        text = gm.read_text(encoding="utf-8")
        if IMPORT_SATIRI in text:
            bant_ops._yedekle(gm)
            text = text.replace("# Alt ajan yönlendirmesi\n\n" + IMPORT_SATIRI + "\n", "").replace(IMPORT_SATIRI + "\n", "")
            gm.write_text(text.rstrip("\n") + "\n", encoding="utf-8")
    return "Yönlendirme tablosu CLAUDE.md'den çıkarıldı (dosya duruyor)"


def hepsi(gun: int = 30) -> dict:
    return {"gozlenen": gozlenen(gun), "tanimlar": tanimlar(), "yonlendirme": yonlendirme_oku(),
            "modeller": MODELLER, "eforlar": EFORLAR, "onerilen": ONERILEN}
