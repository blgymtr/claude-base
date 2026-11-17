"""Claude Base yerel sunucusu. Yalnız 127.0.0.1'de dinler; dışarıya hiçbir istek atmaz."""
from __future__ import annotations

import json
import mimetypes
import os
import sys
import threading
import time
import traceback
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import ajanlar
import bant_ops
import canli
import canli_akis
import config
import indexer
import obsidian
import oneriler

IZINLI_HOST = {f"127.0.0.1:{config.PORT}", f"localhost:{config.PORT}"}


# ----------------------------------------------------------------------------- veri derleyiciler

def _tok(o):
    return (o.get("in") or 0) + (o.get("out") or 0) + (o.get("cr") or 0) + (o.get("cw") or 0)


def _sinir_gun(gun):
    if not gun:
        return None
    return datetime.fromtimestamp(time.time() - (gun - 1) * 86400).strftime("%Y-%m-%d")


def _pencere(o, sinir):
    """Oturumun yalnız seçili dönemdeki günlerine düşen (maliyet, token, çağrı)."""
    g = o.get("gunluk")
    if not g:
        return o["cost"], _tok(o), o["calls"]
    c = t = n = 0
    for gk, (gc, gt, gn) in g.items():
        if sinir is None or gk >= sinir:
            c += gc
            t += gt
            n += gn
    return c, t, n


def _canli_harita():
    acik = canli.acik_oturumlar()
    return acik, {a["id"]: a for a in acik if a.get("id")}


def genel(gun: float) -> dict:
    oz = indexer.ozetler(gun)
    sinir = _sinir_gun(gun)
    acik, harita = _canli_harita()
    kat, modeller, gunluk, projeler = {}, {}, {}, {}
    toplam_c = toplam_t = toplam_n = 0
    for o in oz:
        pc, pt, pn = _pencere(o, sinir)
        toplam_c += pc
        toplam_t += pt
        toplam_n += pn
        k = kat.setdefault(o["category"], {"cost": 0.0, "tok": 0, "oturum": 0})
        k["cost"] += pc
        k["tok"] += pt
        k["oturum"] += 1
        for gk, (gc, gt, gn) in (o.get("gunluk") or {}).items():
            if sinir is None or gk >= sinir:
                gg = gunluk.setdefault(gk, {"cost": 0.0, "tok": 0, "oturum": 0})
                gg["cost"] += gc
                gg["tok"] += gt
                gg["oturum"] += 1
        for m, v in (o.get("models") or {}).items():
            mm = modeller.setdefault(m, {"calls": 0, "cost": 0.0, "tok": 0, "out": 0})
            mm["calls"] += v["calls"]
            mm["cost"] += v["cost"]
            mm["tok"] += v["in"] + v["out"] + v["cr"] + v["cw"]
            mm["out"] += v["out"]
        p = projeler.setdefault(o["project"], {"cost": 0.0, "tok": 0, "kategori": o["category"]})
        p["cost"] += pc
        p["tok"] += pt
    canli_ozet = []
    for a in acik:
        o = next((x for x in oz if x["id"] == a["id"]), None)
        canli_ozet.append(a | {"baslik": (o or {}).get("title") or a.get("ad"), "proje": (o or {}).get("project"),
                               "kategori": (o or {}).get("category"), "cost": (o or {}).get("cost"),
                               "ajan": (o or {}).get("agents")})
    return {
        "gun": gun, "oturum": len(oz), "cost": round(toplam_c, 2),
        "tok": toplam_t, "calls": toplam_n,
        "out": sum(o["out"] for o in oz), "cr": sum(o["cr"] for o in oz), "cw": sum(o["cw"] for o in oz),
        "inp": sum(o["in"] for o in oz),
        "ajan": sum(max(0, o["agents"] - 1) for o in oz), "hata": sum(o["errors"] for o in oz),
        "kategoriler": kat, "modeller": modeller,
        "gunluk": [{"gun": k} | v for k, v in sorted(gunluk.items())],
        "projeler": sorted(({"ad": k} | v for k, v in projeler.items()), key=lambda x: -x["cost"])[:12],
        "acik": canli_ozet, "kategori_listesi": config.KATEGORILER,
    }


def projeler_listesi(gun: float | None) -> dict:
    oz = indexer.ozetler(gun)
    sinir = _sinir_gun(gun)
    acik, harita = _canli_harita()
    out = {}
    for o in oz:
        pc, pt, _ = _pencere(o, sinir)
        p = out.setdefault(o["project"], {
            "ad": o["project"], "kok": o.get("root"), "kategori": o["category"], "oturum": 0, "cost": 0.0,
            "tok": 0, "inp": 0, "out": 0, "cr": 0, "cw": 0, "ajan": 0, "hata": 0, "aktif": 0,
            "son": 0, "ilk": None, "modeller": {}, "oturumlar": [], "acik": False})
        p["oturum"] += 1
        p["cost"] += pc
        p["tok"] += pt
        for a, b in (("inp", "in"), ("out", "out"), ("cr", "cr"), ("cw", "cw")):
            p[a] += o.get(b) or 0
        p["ajan"] += max(0, o["agents"] - 1)
        p["hata"] += o["errors"]
        p["aktif"] += o.get("active") or 0
        p["son"] = max(p["son"], o["end"] or 0)
        p["ilk"] = o["start"] if p["ilk"] is None else min(p["ilk"], o["start"] or p["ilk"])
        for m, v in (o.get("models") or {}).items():
            p["modeller"][m] = p["modeller"].get(m, 0) + v["cost"]
        canli_o = harita.get(o["id"])
        if canli_o:
            p["acik"] = True
        p["oturumlar"].append({"id": o["id"], "title": o["title"], "end": o["end"], "cost": o["cost"],
                               "acik": bool(canli_o), "durum": (canli_o or {}).get("durum")})
    liste = sorted(out.values(), key=lambda x: (not x["acik"], -x["son"]))
    for p in liste:
        p["cost"] = round(p["cost"], 2)
    return {"projeler": liste, "kategoriler": config.KATEGORILER}


def gecmis(saat: float) -> dict:
    sinir = time.time() - saat * 3600
    oz = [o for o in indexer.ozetler(saat / 24 + 1) if (o["end"] or 0) >= sinir]
    akis = []
    for o in oz:
        d = indexer.detay(o["id"]) or {}
        tl = d.get("timeline", [])
        emirler = [i for i, e in enumerate(tl) if e["k"] == "prompt"]
        for j, i in enumerate(emirler):
            e = tl[i]
            if (e["t"] or 0) < sinir:
                continue
            son = emirler[j + 1] if j + 1 < len(emirler) else len(tl)
            adimlar = tl[i + 1:son]
            akis.append({"oturum": o["id"], "baslik": o["title"], "proje": o["project"], "t": e["t"],
                         "emir": e["h"], "adim": len(adimlar),
                         "ajan": len({a["a"] for a in adimlar} - {"main"}),
                         "hata": sum(1 for a in adimlar if a.get("err")),
                         "yazilan": len({a["h"] for a in adimlar if a["k"] == "write"}),
                         "bitis": adimlar[-1]["t"] if adimlar else e["t"]})
    akis.sort(key=lambda x: -x["t"])
    return {"saat": saat, "akis": akis[:300]}


# ----------------------------------------------------------------------------- sunucu

def _tarayici():
    while True:
        try:
            indexer.tara()
        except Exception:
            traceback.print_exc()
        time.sleep(45)


class Isleyici(BaseHTTPRequestHandler):
    server_version = "BantPanosu/1"

    def log_message(self, fmt, *args):  # sessiz
        pass

    def _host_ok(self) -> bool:
        return self.headers.get("Host", "") in IZINLI_HOST

    def _json(self, data, kod=200):
        s = json.dumps(data, ensure_ascii=False, default=str)
        if config.EVI_GIZLE:
            # Ekran görüntüsü modu: ev klasörünün tam yolu yerine "~" gösterilir.
            for ev in {str(config.HOME), str(config.HOME.resolve())}:
                s = s.replace(json.dumps(ev, ensure_ascii=False)[1:-1], "~")
        b = s.encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _statik(self, yol: str):
        if yol in ("", "/"):
            yol = "/index.html"
        hedef = (config.WEB_DIR / yol.lstrip("/")).resolve()
        if not str(hedef).startswith(str(config.WEB_DIR.resolve())) or not hedef.is_file():
            self.send_error(404)
            return
        b = hedef.read_bytes()
        self.send_response(200)
        tip = mimetypes.guess_type(str(hedef))[0] or "application/octet-stream"
        if tip.startswith("text/") or tip in ("application/javascript",):
            tip += "; charset=utf-8"
        self.send_header("Content-Type", tip)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        # Dışarıya hiçbir kaynak yüklenmesin
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self'; connect-src 'self'; font-src 'self' data:")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if not self._host_ok():
            self.send_error(403)
            return
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        gun = float(q["gun"]) if q.get("gun") not in (None, "", "0") else None
        try:
            if not u.path.startswith("/api/"):
                return self._statik(u.path)
            p = u.path[5:]
            if p == "durum":
                return self._json(indexer.DURUM)
            if p == "genel":
                return self._json(genel(gun or 30))
            if p == "oturumlar":
                acik, harita = _canli_harita()
                oz = indexer.ozetler(gun)
                for o in oz:
                    o["acik"] = o["id"] in harita
                    o["durum"] = (harita.get(o["id"]) or {}).get("durum")
                return self._json({"oturumlar": oz, "kategoriler": config.KATEGORILER})
            if p.startswith("oturum/"):
                d = indexer.detay(p.split("/", 1)[1])
                return self._json(d or {"hata": "bulunamadı"}, 200 if d else 404)
            if p == "projeler":
                return self._json(projeler_listesi(gun))
            if p == "bant":
                return self._json(bant_ops.bant(int(gun or 30)))
            if p == "ajanlar":
                return self._json(ajanlar.hepsi(int(gun or 30)))
            if p == "oneriler":
                return self._json(oneriler.uret(int(gun or 30)))
            if p == "gecmis":
                return self._json(gecmis(float(q.get("saat") or 48)))
            if p == "acik":
                acik = canli.acik_oturumlar()
                oz = {o["id"]: o for o in indexer.ozetler(None)}
                for a in acik:
                    o = oz.get(a["id"]) or {}
                    a.update(baslik=o.get("title") or a.get("ad"), proje=o.get("project"), kategori=o.get("category"))
                return self._json({"acik": acik})
            if p.startswith("canli/"):
                return self._json(canli_akis.akis(p.split("/", 1)[1], int(q.get("seq") or 0)))
            self.send_error(404)
        except Exception as e:
            traceback.print_exc()
            self._json({"hata": str(e)}, 500)

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Bant") != "1":
            self.send_error(403)
            return
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{config.PORT}", f"http://localhost:{config.PORT}"):
            self.send_error(403)
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return self._json({"hata": "geçersiz JSON"}, 400)
        p = urlparse(self.path).path[5:]
        try:
            if p == "tara":
                threading.Thread(target=indexer.tara, kwargs={"zorla": bool(body.get("zorla"))}, daemon=True).start()
                return self._json({"mesaj": "Tarama başladı"})
            if p == "kategori":
                a = config.ayarlar()
                kat = body.get("kategori")
                if kat not in config.KATEGORILER:
                    raise ValueError("Geçersiz kategori")
                if body.get("oturum"):
                    a["oturumlar"][body["oturum"]] = kat
                else:
                    a["projeler"][body["proje"]] = kat
                config.ayar_kaydet({k: v for k, v in a.items()})
                indexer.kategorileri_yenile()
                return self._json({"mesaj": "Kategori kaydedildi"})
            if p == "bant":
                return self._json({"mesaj": bant_ops.degistir(body["tur"], body["id"], bool(body["ac"]), body.get("satir"))})
            if p == "ajan/kaydet":
                return self._json({"mesaj": ajanlar.tanim_kaydet(body["ad"], body.get("aciklama", ""), body.get("model", "inherit"),
                                                                 body.get("effort", ""), body.get("govde", ""), body.get("tools", ""))})
            if p == "ajan/degistir":
                return self._json({"mesaj": ajanlar.tanim_degistir(body["ad"], bool(body["ac"]))})
            if p == "ajan/onerilenler":
                return self._json({"mesaj": "; ".join(ajanlar.onerilenleri_kur())})
            if p == "yonlendirme":
                return self._json({"mesaj": ajanlar.yonlendirme_kaydet(body.get("satirlar", []), body.get("varsayilan_model"),
                                                                         bool(body.get("bagla", True)))})
            if p == "yonlendirme/kopar":
                return self._json({"mesaj": ajanlar.yonlendirme_kopar()})
            if p == "obsidian":
                gunler = int(body.get("gunler") or 1)
                return self._json({"mesaj": "\n".join(obsidian.son_gunler(gunler))})
            if p == "kapat":
                self._json({"mesaj": "Claude Base kapanıyor"})
                threading.Timer(0.3, self.server.shutdown).start()
                return
            self.send_error(404)
        except (ValueError, KeyError) as e:
            self._json({"hata": str(e)}, 400)
        except Exception as e:
            traceback.print_exc()
            self._json({"hata": str(e)}, 500)


def _pencere_ac(url: str):
    """Edge'in uygulama modunda (sekmesiz, kendi penceresi) aç; yoksa varsayılan tarayıcı."""
    adaylar = [os.path.join(os.environ.get(k, ""), r"Microsoft\Edge\Application\msedge.exe")
               for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for exe in adaylar:
        if os.path.isfile(exe):
            import subprocess
            subprocess.Popen([exe, f"--app={url}", "--window-size=1500,950"], creationflags=config.PENCERESIZ)
            return
    webbrowser.open(url)


def main():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if sys.stderr is None or sys.stdout is None:
        # Konsolsuz .exe: hatalar dosyaya yazılsın
        log = open(config.DATA_DIR / "hata.log", "a", encoding="utf-8", buffering=1)
        sys.stderr = sys.stderr or log
        sys.stdout = sys.stdout or log
    url = f"http://127.0.0.1:{config.PORT}/"
    tarayicisiz = "--tarayicisiz" in sys.argv
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", config.PORT), Isleyici)
    except OSError:
        # Pano zaten çalışıyor: yalnız pencereyi aç.
        print(f"Claude Base zaten açık: {url}")
        if not tarayicisiz:
            _pencere_ac(url)
        return
    threading.Thread(target=_tarayici, daemon=True).start()
    print(f"Claude Base: {url}")
    if not tarayicisiz:
        threading.Timer(0.8, lambda: _pencere_ac(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()  # .exe içinde paralel tarama için şart
    main()
