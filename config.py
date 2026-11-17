"""Claude Base: yollar, fiyatlar ve varsayılan ayarlar.

Kişiye özel her şey (proje adları, kasa yolu, ek hafıza dosyaları) koda değil,
git dışındaki veri/ayarlar.json dosyasına yazılır. Örnek: ayarlar.ornek.json.

Ortam değişkenleri (isteğe bağlı):
  CLAUDE_BASE_HOME  Claude kayıtlarının arandığı ev klasörü (varsayılan: kullanıcı ev klasörü)
  CLAUDE_BASE_DATA  önbellek ve ayarların yazıldığı klasör (varsayılan: uygulamanın yanındaki veri/)
  CLAUDE_BASE_PORT  yerel port (varsayılan: 4317)
  CLAUDE_BASE_HIDE_HOME=1  ekranda ev klasörünün tam yolu yerine "~" yazar (ekran görüntüsü için)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "Claude Base"
HOME = Path(os.environ["CLAUDE_BASE_HOME"]) if os.environ.get("CLAUDE_BASE_HOME") else Path.home()
CLAUDE_DIR = HOME / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
SETTINGS_PATH = CLAUDE_DIR / "settings.json"
CLAUDE_JSON = HOME / ".claude.json"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"
KAPALI_DIR = CLAUDE_DIR / "bant-kapali"  # banttan çıkarılan skill ve ajanlar burada bekler
GLOBAL_CLAUDE_MD = CLAUDE_DIR / "CLAUDE.md"
YONLENDIRME_MD = CLAUDE_DIR / "bant-yonlendirme.md"

import sys as _sys

DONMUS = getattr(_sys, "frozen", False)  # PyInstaller ile paketlenmiş .exe mi?
# .exe'de veri klasörü exe'nin yanında, web dosyaları paketin içinde durur.
APP_DIR = Path(_sys.executable).resolve().parent if DONMUS else Path(__file__).resolve().parent
WEB_DIR = (Path(getattr(_sys, "_MEIPASS", APP_DIR)) / "web") if DONMUS else APP_DIR / "web"
PENCERESIZ = 0x08000000 if os.name == "nt" else 0  # alt süreçler siyah pencere açmasın
DATA_DIR = Path(os.environ["CLAUDE_BASE_DATA"]) if os.environ.get("CLAUDE_BASE_DATA") else APP_DIR / "veri"
DB_PATH = DATA_DIR / "onbellek.sqlite"
AYARLAR_PATH = DATA_DIR / "ayarlar.json"
YEDEK_DIR = DATA_DIR / "yedekler"

PORT = int(os.environ.get("CLAUDE_BASE_PORT") or 4317)
# Ekran görüntüsü alırken ev klasörünün tam yolunu "~" ile gizle
EVI_GIZLE = os.environ.get("CLAUDE_BASE_HIDE_HOME") == "1"

# API karşılığı fiyatları, $/milyon token (claude-api skill tablosu, 2026-11-03).
# Önbelleğe yazma: 5 dk = girdi x1,25, 1 sa = girdi x2 (standart çarpan, yaklaşık).
FIYATLAR = {
    "claude-fable-5-2": (8.00, 40.00, 0.20),
    "claude-mythos-5-2": (8.00, 40.00, 0.20),
    "claude-fable-5-1": (10.00, 50.00, 1.00),
    "claude-mythos-5-1": (10.00, 50.00, 1.00),
    "claude-fable-5": (10.00, 50.00, 1.00),
    "claude-opus-5-5": (4.00, 20.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 0.50),
    "claude-opus-4-8": (5.00, 25.00, 0.50),
    "claude-opus-4-7": (5.00, 25.00, 0.50),
    "claude-opus-4-6": (5.00, 25.00, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 0.20),
    "claude-sonnet-4-6": (3.00, 15.00, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4-5": (1.00, 5.00, 0.10),
}


def fiyat(model: str | None):
    """Model kimliğini fiyat satırına eşle; tarih eki veya [1m] gibi son ekleri yok say."""
    if not model:
        return None
    m = model.lower().split("[")[0]
    if m in FIYATLAR:
        return FIYATLAR[m]
    for key in sorted(FIYATLAR, key=len, reverse=True):
        if m.startswith(key):
            return FIYATLAR[key]
    return None


KATEGORILER = ["Projelerim", "Oyunlar", "Uygulamalar", "Side-projects", "Sınıflanmadı"]

VARSAYILAN_AYARLAR = {
    # Proje kökü aranırken "kap" sayılan klasörler: bunların ilk alt klasörü proje adıdır.
    "kaplar": [
        str(HOME / "Desktop"),
        str(HOME / "Documents"),
        str(HOME / "projects"),
        str(HOME / "source" / "repos"),
        str(HOME),
    ],
    # Kabın altında proje sayılmayacak klasörler
    "proje_degil": ["Users", "Windows", "Program Files", "Program Files (x86)", "ProgramData", "AppData",
                    "$Recycle.Bin", "tmp", "temp"],
    # Proje adı -> kategori. Panoda kartı sürükleyince buraya yazılır.
    "projeler": {},
    # Yolunda bu parçalardan biri geçen proje "Oyunlar" sayılır.
    "kural_oyun": [],
    # Tek tek oturum için elle seçilen kategori: {oturum_id: kategori}
    "oturumlar": {},
    # İsteğe bağlı Obsidian kasası; boşsa "Obsidian'a yaz" kapalıdır.
    "obsidian_kasa": "",
    # Not yazıldıktan sonra kasada çalıştırılacak komut (ör. ["git", "add", "-A"]); boşsa hiçbir şey çalışmaz.
    "obsidian_sonra": [],
    # Taramada atlanan proje klasörleri (ad parçası)
    "atla_proje": [],
    # Bant sekmesinde gösterilecek ek CLAUDE.md / AGENTS.md dosyaları: [{"id", "yol", "kilit"?}]
    "ek_hafiza": [],
    # Kasanın kendi hook'ları salt okunur gösterilirken yazılacak not
    "kasa_kilit": "kasanın kendi ayarı",
}


def kasa() -> Path | None:
    """Ayarlanmışsa Obsidian kasası."""
    k = (ayarlar().get("obsidian_kasa") or "").strip()
    return Path(k) if k else None


def atla_proje() -> tuple[str, ...]:
    return tuple(ayarlar().get("atla_proje") or ())


def ayarlar() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if AYARLAR_PATH.exists():
        try:
            data = json.loads(AYARLAR_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
    else:
        data = {}
    out = json.loads(json.dumps(VARSAYILAN_AYARLAR))
    for k, v in data.items():
        if k in ("projeler", "oturumlar") and isinstance(v, dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


def ayar_kaydet(data: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AYARLAR_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, AYARLAR_PATH)
