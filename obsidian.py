"""Günlük özeti Obsidian kasasına (notes/bant/YYYY-MM-DD.md) yazar.

Kasa yolu veri/ayarlar.json içindeki "obsidian_kasa" alanından gelir; boşsa hiçbir şey yazılmaz.
Yalnız başlık, proje, süre, token, maliyet ve dosya adları yazılır; emir metinleri yazılmaz.
"obsidian_sonra" doluysa not yazıldıktan sonra o komut kasa klasöründe çalıştırılır.
"""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timedelta

import config
import indexer


def _sure(sn: float) -> str:
    sn = int(sn or 0)
    if sn < 3600:
        return f"{sn // 60} dk"
    return f"{sn // 3600} sa {sn % 3600 // 60} dk"


def _tok(n: int) -> str:
    return f"{n / 1e6:.1f} M" if n >= 1e6 else f"{n / 1e3:.0f} B"


def gun_yaz(gun: str | None = None) -> str:
    kasa = config.kasa()
    if not kasa:
        raise ValueError("Obsidian kasası ayarlanmadı: veri/ayarlar.json içinde \"obsidian_kasa\" alanını doldur")
    gun = gun or datetime.now().strftime("%Y-%m-%d")
    bas = datetime.strptime(gun, "%Y-%m-%d").timestamp()
    bit = bas + 86400
    oturumlar = [o for o in indexer.ozetler(None) if (o.get("end") or 0) >= bas and (o.get("start") or 0) < bit]
    if not oturumlar:
        return f"{gun}: o gün etkinlik yok, not yazılmadı"
    toplam = sum(o["cost"] for o in oturumlar)
    satirlar = [
        "---", json.dumps({"kind": "note", "project": "bant", "visibility": "internal"}, ensure_ascii=False), "---",
        f"# Bant günlüğü {gun}", "",
        "**Ana terim:** bant · **Diğer adlar:** Claude oturumları, ajan, token, maliyet, günlük, pano",
        f"Kaynak: {config.APP_NAME} ({time.strftime('%Y-%m-%d %H:%M')}). Değerler yerel kayıtlardan hesaplandı; "
        "API karşılığı abonelikte faturalanmaz.", "",
        f"**{len(oturumlar)} oturum** · API karşılığı **{toplam:.2f} $** · "
        f"{sum(o['agents'] - 1 for o in oturumlar)} alt ajan · {sum(o['errors'] for o in oturumlar)} hata", "",
        "| Oturum | Proje | Kategori | Aktif süre | Ajan | Token | API karşılığı | Hata |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for o in sorted(oturumlar, key=lambda x: -x["cost"]):
        tok = o["in"] + o["out"] + o["cr"] + o["cw"]
        satirlar.append(f"| {o['title'][:60].replace('|', '/')} | {o['project']} | {o['category']} | "
                        f"{_sure(o.get('active', o['duration']))} | {o['agents']} | {_tok(tok)} | {o['cost']:.2f} $ | {o['errors']} |")
    satirlar += ["", "## Yazılan dosyalar", ""]
    for o in oturumlar:
        d = indexer.detay(o["id"]) or {}
        yazilan = [f for f in d.get("files", []) if f["w"]][:12]
        if yazilan:
            satirlar.append(f"**{o['title'][:60]}**")
            satirlar += [f"- `{f['path']}` ({f['w']} yazım)" for f in yazilan]
            satirlar.append("")
    satirlar.append(f"İlgili: [[projeler]], [[claude-oturumlari-{gun[:7]}]]")
    hedef = kasa / "notes" / "bant" / f"{gun}.md"
    hedef.parent.mkdir(parents=True, exist_ok=True)
    hedef.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    sonra = config.ayarlar().get("obsidian_sonra") or []
    if sonra:
        subprocess.run([str(x) for x in sonra], cwd=str(kasa), capture_output=True, timeout=120,
                       creationflags=config.PENCERESIZ)
    return f"{hedef} yazıldı ({len(oturumlar)} oturum)"


def son_gunler(n: int = 7) -> list[str]:
    out = []
    for i in range(n):
        g = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        out.append(gun_yaz(g))
    return out


if __name__ == "__main__":
    import sys
    print("\n".join(son_gunler(int(sys.argv[1]) if len(sys.argv) > 1 else 1)))
