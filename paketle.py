"""Claude Base.exe üretir: logoyu (logo.py) yeniden çizer, PyInstaller ile tek dosya paketler.

Kullanım:  python paketle.py
Çıktı:     Claude Base.exe (bu klasörde; veri/ klasörünü yanında kullanır)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent


def main():
    import logo
    logo.hepsini_yaz()
    ikon = KOK / "veri" / "ikon.ico"
    komut = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
             "--name", "Claude Base", "--icon", str(ikon),
             "--add-data", f"{KOK / 'web'};web",
             "--distpath", str(KOK), "--workpath", str(KOK / "build"), "--specpath", str(KOK / "build"),
             str(KOK / "server.py")]
    r = subprocess.run(komut, cwd=str(KOK))
    if r.returncode != 0:
        sys.exit(r.returncode)
    shutil.rmtree(KOK / "build", ignore_errors=True)
    print("Hazır:", KOK / "Claude Base.exe")


if __name__ == "__main__":
    main()
