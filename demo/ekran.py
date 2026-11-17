"""Demo verisiyle docs/screenshots/ altına ekran görüntüleri alır (Windows, Microsoft Edge).

Kullanım:  python demo/ekran.py
Önce demo verisini üretir, demo sunucusunu ayrı bir portta açar, Edge'i başsız çalıştırır, sunucuyu kapatır.
Gerçek kayıtlarına dokunmaz; görüntülerde yalnız uydurma projeler görünür.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
DEMO = KOK / "demo"
CIKTI = KOK / "docs" / "screenshots"
PORT = 4399
SEKMELER = ["genel", "projeler", "oturumlar", "bant", "ajanlar", "oneriler"]


def edge() -> str:
    for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        p = Path(os.environ.get(k, "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if p.is_file():
            return str(p)
    sys.exit("Microsoft Edge bulunamadı")


def main() -> None:
    subprocess.run([sys.executable, str(DEMO / "demo_veri.py")], check=True)
    env = dict(os.environ, CLAUDE_BASE_HOME=str(DEMO / "ev"), CLAUDE_BASE_DATA=str(DEMO / "veri"),
               CLAUDE_BASE_PORT=str(PORT), CLAUDE_BASE_HIDE_HOME="1")
    sunucu = subprocess.Popen([sys.executable, str(KOK / "server.py"), "--tarayicisiz"], cwd=str(KOK), env=env)
    try:
        for _ in range(60):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/durum", timeout=2) as r:
                    if b'"calisiyor": false' in r.read() :
                        break
            except OSError:
                pass
            time.sleep(1)
        CIKTI.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as profil:
            isler = [(s, f"?sekme={s}") for s in SEKMELER] + [("genel-acik", "?sekme=genel&tema=acik")]
            for ad, sorgu in isler:
                subprocess.run([edge(), "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-prefers-reduced-motion",
                                f"--user-data-dir={profil}", "--window-size=1500,950", "--virtual-time-budget=8000",
                                f"--screenshot={CIKTI / (ad + '.png')}", f"http://127.0.0.1:{PORT}/{sorgu}"],
                               capture_output=True, timeout=120)
                print("yazıldı:", CIKTI / (ad + ".png"))
    finally:
        sunucu.terminate()


if __name__ == "__main__":
    main()
