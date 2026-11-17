"""Claude Base logosu: bir bant (konveyör) ve üstünde büyüyen üç sütun.

Bant, kapatılıp açılan skill/hook/MCP hattını; sütunlar panodaki token ölçümünü anlatır.
Tek geometri iki çıktıya gider: web/logo.svg (pencere, sekme, başlık) ve veri/ikon.ico (exe).
Küçük boylarda (32 px ve altı) çizgiler kalınlaşır, makaralar düşer; yoksa 16 px'te bant kaybolur.

Kullanım:  python logo.py      (ikisini de yeniden üretir)
"""
from __future__ import annotations

from pathlib import Path

KOK = Path(__file__).resolve().parent

ZEMIN = "#17181a"
KENAR = "#2e3034"
VURGU = "#e2725b"
ACIK = "#e8e8e6"
SOLUK = "#8e9095"


def _geometri(kucuk: bool) -> dict:
    """256 birimlik ızgarada parçalar."""
    if kucuk:
        return {
            "kose": 52,
            "bant": (40, 152, 216, 204), "bant_kalin": 22,
            "makara": None,
            "sutunlar": [(60, 104, 94), (111, 74, 145), (162, 40, 196)],  # (sol, üst, sağ)
            "sutun_alt": 132, "sutun_kose": 7,
        }
    return {
        "kose": 56,
        "bant": (48, 150, 208, 192), "bant_kalin": 12,
        "makara": 7,
        "sutunlar": [(80, 108, 106), (115, 86, 141), (150, 62, 176)],
        "sutun_alt": 136, "sutun_kose": 5,
    }


def svg(kucuk: bool = False) -> str:
    g = _geometri(kucuk)
    x0, y0, x1, y1 = g["bant"]
    t = g["bant_kalin"]
    r = (y1 - y0) / 2
    renkler = [SOLUK, ACIK, VURGU]
    parca = [
        f'<rect x="8" y="8" width="240" height="240" rx="{g["kose"]}" fill="{ZEMIN}" stroke="{KENAR}" stroke-width="4"/>',
        f'<rect x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="{r}" fill="none" stroke="{VURGU}" stroke-width="{t}"/>',
    ]
    if g["makara"]:
        cy = (y0 + y1) / 2
        for cx in (x0 + r, x1 - r):
            parca.append(f'<circle cx="{cx}" cy="{cy}" r="{g["makara"]}" fill="{SOLUK}"/>')
    for (sol, ust, sag), renk in zip(g["sutunlar"], renkler):
        parca.append(f'<rect x="{sol}" y="{ust}" width="{sag - sol}" height="{g["sutun_alt"] - ust}" '
                     f'rx="{g["sutun_kose"]}" fill="{renk}"/>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
            + "".join(parca) + "</svg>\n")


def _renk(h: str) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _ciz(boy: int, kucuk: bool):
    """Pillow ile 4 kat büyük çizip küçültür (kenar yumuşatma)."""
    from PIL import Image, ImageDraw
    k = boy * 4 / 256
    img = Image.new("RGBA", (boy * 4, boy * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    g = _geometri(kucuk)
    s = lambda v: round(v * k)

    d.rounded_rectangle((s(8), s(8), s(248), s(248)), radius=s(g["kose"]), fill=_renk(ZEMIN),
                        outline=_renk(KENAR), width=max(1, s(4)))
    x0, y0, x1, y1 = g["bant"]
    t = g["bant_kalin"]
    # SVG'deki çizgi kenarın ortasından geçer; Pillow içe doğru çizer, bu yüzden yarım kalınlık dışa taşı.
    d.rounded_rectangle((s(x0 - t / 2), s(y0 - t / 2), s(x1 + t / 2), s(y1 + t / 2)),
                        radius=s((y1 - y0) / 2 + t / 2), outline=_renk(VURGU), width=s(t))
    if g["makara"]:
        r = (y1 - y0) / 2
        cy = (y0 + y1) / 2
        for cx in (x0 + r, x1 - r):
            m = g["makara"]
            d.ellipse((s(cx - m), s(cy - m), s(cx + m), s(cy + m)), fill=_renk(SOLUK))
    for (sol, ust, sag), renk in zip(g["sutunlar"], [SOLUK, ACIK, VURGU]):
        d.rounded_rectangle((s(sol), s(ust), s(sag), s(g["sutun_alt"])), radius=s(g["sutun_kose"]),
                            fill=_renk(renk))
    return img.resize((boy, boy), Image.LANCZOS)


def ico_yaz(hedef: Path) -> None:
    boylar = [16, 24, 32, 48, 64, 128, 256]
    resimler = [_ciz(b, b <= 32) for b in boylar]
    hedef.parent.mkdir(exist_ok=True)
    resimler[-1].save(hedef, format="ICO", sizes=[(b, b) for b in boylar], append_images=resimler[:-1])


def png_yaz(hedef: Path, boy: int = 256) -> None:
    _ciz(boy, boy <= 32).save(hedef)


def hepsini_yaz() -> None:
    (KOK / "web" / "logo.svg").write_text(svg(), encoding="utf-8")
    (KOK / "web" / "logo-kucuk.svg").write_text(svg(kucuk=True), encoding="utf-8")
    ico_yaz(KOK / "veri" / "ikon.ico")


if __name__ == "__main__":
    hepsini_yaz()
    print("Yazıldı: web/logo.svg, web/logo-kucuk.svg, veri/ikon.ico")
