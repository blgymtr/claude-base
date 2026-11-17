"""Demo için tamamen uydurma bir Claude Code geçmişi üretir (ekran görüntüleri ve deneme için).

Gerçek hiçbir kayda dokunmaz. Çıktı:
  demo/ev/.claude/...   sahte ev klasörü (oturumlar, alt ajanlar, ayarlar, skill'ler, hafıza)
  demo/veri/            demo panosunun önbelleği ve ayarları

Kullanım:
  python demo/demo_veri.py
  CLAUDE_BASE_HOME=demo/ev CLAUDE_BASE_DATA=demo/veri CLAUDE_BASE_PORT=4399 python server.py --tarayicisiz
"""
from __future__ import annotations

import json
import random
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

KOK = Path(__file__).resolve().parent
EV = KOK / "ev"
VERI = KOK / "veri"
CLAUDE = EV / ".claude"
SAHTE_KOK = "C:\\Users\\dev\\projects"  # kayıtlarda görünen uydurma proje kökü

rnd = random.Random(42)
SIMDI = datetime.now(timezone.utc).replace(microsecond=0)

PROJELER = {
    # ad: (kategori, dosyalar, emirler)
    "weather-widget": ("Uygulamalar", ["src/App.tsx", "src/api/forecast.ts", "src/components/Chart.tsx", "package.json"],
                       ["Add an hourly forecast chart", "Fix the timezone bug in forecast.ts", "Write tests for the API client"]),
    "pixel-dungeon": ("Oyunlar", ["scripts/player.gd", "scripts/enemy_ai.gd", "scenes/level_01.tscn", "scripts/inventory.gd"],
                      ["Make enemies patrol between waypoints", "Add a dash with cooldown", "Balance the first level"]),
    "orbit-racer": ("Oyunlar", ["Assets/Scripts/ShipController.cs", "Assets/Scripts/Checkpoint.cs", "Assets/Scenes/Track1.unity"],
                    ["Tune the drift handling", "Add a lap timer UI"]),
    "notes-sync": ("Uygulamalar", ["app/sync/engine.py", "app/models.py", "tests/test_sync.py", "README.md"],
                   ["Resolve merge conflicts between devices", "Speed up the initial sync"]),
    "blog-engine": ("Projelerim", ["site/build.py", "site/templates/post.html", "content/hello-world.md"],
                    ["Add RSS feed generation", "Dark mode for the theme"]),
    "data-cleaner": ("Side-projects", ["clean.py", "rules.yaml", "tests/test_rules.py"],
                     ["Deduplicate rows by fuzzy match", "Export a summary report"]),
    "recipe-cards": ("Side-projects", ["cards/render.py", "cards/layout.css", "data/recipes.json"],
                     ["Print-ready PDF layout", "Add nutrition facts"]),
}
SKILLER = ["game-feel", "level-design", "save-systems", "shader-programming", "camera-systems",
           "test-writer", "release-notes", "api-docs", "sql-helper", "pdf", "docx", "xlsx"]
KULLANILAN_SKILLER = ["game-feel", "level-design", "test-writer", "pdf"]
ALT_AJANLAR = [
    ("Explore", "claude-sonnet-5-5", "medium", "Map the codebase (read only)"),
    ("general-purpose", "claude-opus-5-5", "high", "Implement the feature"),
    ("general-purpose", "claude-sonnet-5-5", "medium", "Run tests and report"),
    ("general-purpose", "claude-haiku-5-5", "low", "Rename symbols across files"),
]


def _ts(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _yaz(yol: Path, satirlar: list[dict]) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text("\n".join(json.dumps(s, ensure_ascii=False) for s in satirlar) + "\n", encoding="utf-8")


class Akis:
    """Bir oturumun (ya da alt ajanın) satırlarını üretir."""

    def __init__(self, cwd: str, sid: str, model: str, effort: str, t: datetime, baglam: int):
        self.cwd, self.sid, self.model, self.effort, self.t = cwd, sid, model, effort, t
        self.baglam = baglam
        self.satir: list[dict] = []

    def _ilerle(self, sn: float) -> str:
        self.t += timedelta(seconds=sn)
        return _ts(self.t)

    def emir(self, metin: str) -> None:
        self.satir.append({"type": "user", "timestamp": self._ilerle(rnd.uniform(20, 240)), "cwd": self.cwd,
                           "sessionId": self.sid, "message": {"role": "user", "content": metin}})

    def arac(self, ad: str, girdi: dict, hata: bool = False, sonuc_ek: dict | None = None) -> str:
        tid = "toolu_" + uuid.UUID(int=rnd.getrandbits(128)).hex[:20]
        self.baglam += rnd.randint(1500, 9000)
        usage = {"input_tokens": rnd.randint(2, 40), "output_tokens": rnd.randint(150, 2500),
                 "cache_read_input_tokens": self.baglam, "cache_creation_input_tokens": rnd.randint(800, 7000)}
        self.satir.append({"type": "assistant", "timestamp": self._ilerle(rnd.uniform(3, 30)), "cwd": self.cwd,
                           "sessionId": self.sid, "effort": self.effort,
                           "message": {"id": "msg_" + uuid.UUID(int=rnd.getrandbits(128)).hex[:20], "model": self.model,
                                       "usage": usage,
                                       "content": [{"type": "tool_use", "id": tid, "name": ad, "input": girdi}]}})
        sonuc = {"type": "user", "timestamp": self._ilerle(rnd.uniform(1, 12)), "cwd": self.cwd, "sessionId": self.sid,
                 "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid,
                                                          "content": "Error: file has changed" if hata else "ok",
                                                          "is_error": hata}]}}
        if sonuc_ek:
            sonuc.update(sonuc_ek)
        self.satir.append(sonuc)
        return tid

    def hook_baglami(self, olay: str, karakter: int) -> None:
        self.satir.append({"type": "attachment", "timestamp": self._ilerle(0.2), "attachment": {
            "type": "hook_additional_context", "hookEvent": olay, "content": "x" * karakter}})

    def sikistir(self) -> None:
        self.baglam = rnd.randint(30_000, 60_000)
        self.satir.append({"type": "system", "subtype": "compact_boundary", "timestamp": self._ilerle(5)})


def oturum_uret(proje: str, kategori: str, dosyalar: list[str], emirler: list[str], bas: datetime, uzun: bool) -> None:
    sid = str(uuid.UUID(int=rnd.getrandbits(128)))
    kok = f"{SAHTE_KOK}\\{proje}"
    slug = kok.replace(":", "-").replace("\\", "-")
    model = rnd.choice(["claude-opus-5-5", "claude-opus-5-5", "claude-sonnet-5-5"])
    a = Akis(kok, sid, model, rnd.choice(["high", "medium", "xhigh"]), bas, rnd.randint(25_000, 45_000))
    a.satir.append({"type": "custom-title", "customTitle": f"{proje}: {emirler[0][:40].lower()}", "sessionId": sid})
    alt_satirlar: list[tuple[str, dict, list[dict]]] = []
    tur = len(emirler) * (3 if uzun else 1)
    for i in range(tur):
        a.emir(emirler[i % len(emirler)])
        for _ in range(rnd.randint(6, 22) if uzun else rnd.randint(4, 12)):
            d = f"{kok}\\{rnd.choice(dosyalar).replace('/', chr(92))}"
            r = rnd.random()
            if r < 0.42:
                a.arac("Read", {"file_path": d})
                if rnd.random() < 0.25:
                    a.arac("Read", {"file_path": d})  # değişmemiş dosyayı yeniden okuma
            elif r < 0.62:
                a.arac("Edit", {"file_path": d, "old_string": "a", "new_string": "b"}, hata=rnd.random() < 0.06)
            elif r < 0.75:
                a.arac("Grep", {"pattern": rnd.choice(["TODO", "def ", "class ", "import"]), "path": kok})
            elif r < 0.88:
                a.arac("Bash", {"command": rnd.choice(["npm test", "pytest -q", "git status", "godot --headless --quit"]),
                                "description": "Run checks"}, hata=rnd.random() < 0.08)
            elif r < 0.93 and kategori == "Oyunlar":
                a.arac("Skill", {"skill": rnd.choice(["game-feel", "level-design"])})
            else:
                a.arac("WebSearch", {"query": f"{proje} best practices"})
            if rnd.random() < 0.18:
                a.hook_baglami("PreToolUse", rnd.randint(400, 1400))
        if rnd.random() < 0.55:
            tip, amodel, aeffort, aciklama = rnd.choice(ALT_AJANLAR)
            aid = uuid.UUID(int=rnd.getrandbits(128)).hex[:17]
            tid = a.arac("Agent", {"description": aciklama, "subagent_type": tip, "model": amodel.split("-")[1]},
                         sonuc_ek={"toolUseResult": {"agentId": aid, "resolvedModel": amodel, "status": "completed"}})
            s = Akis(kok, sid, amodel, aeffort, a.t - timedelta(seconds=200), rnd.randint(12_000, 20_000))
            for _ in range(rnd.randint(5, 18)):
                d = f"{kok}\\{rnd.choice(dosyalar).replace('/', chr(92))}"
                if rnd.random() < 0.6:
                    s.arac("Read", {"file_path": d})
                else:
                    s.arac("Write" if rnd.random() < 0.3 else "Edit", {"file_path": d})
            alt_satirlar.append((aid, {"agentType": tip, "description": aciklama, "toolUseId": tid, "model": amodel},
                                 s.satir))
        if uzun and i in (2, 5):
            a.sikistir()
    klasor = CLAUDE / "projects" / slug
    _yaz(klasor / f"{sid}.jsonl", a.satir)
    for aid, meta, satirlar in alt_satirlar:
        _yaz(klasor / sid / "subagents" / f"agent-{aid}.jsonl", satirlar)
        (klasor / sid / "subagents" / f"agent-{aid}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def ayar_dosyalari() -> None:
    (CLAUDE / "skills").mkdir(parents=True, exist_ok=True)
    for s in SKILLER:
        d = CLAUDE / "skills" / s
        d.mkdir(exist_ok=True)
        (d / "SKILL.md").write_text(f"---\nname: {s}\ndescription: Example skill '{s}' for the demo. "
                                    + "Helps with a focused task and explains when to use it. " * 3
                                    + "\n---\n\n# " + s + "\n\nDemo content.\n", encoding="utf-8")
    (CLAUDE / "agents").mkdir(exist_ok=True)
    (CLAUDE / "agents" / "quick-worker.md").write_text(
        "---\nname: quick-worker\ndescription: \"Simple, well defined edits\"\nmodel: sonnet\neffort: medium\n---\n\n"
        "Do the task in the brief and report what changed.\n", encoding="utf-8")
    ayar = {"hooks": {
        "PreToolUse": [{"matcher": "", "hooks": [{"type": "command", "command": "python ~/.claude/hooks/context_hint.py"}]}],
        "Stop": [{"hooks": [{"type": "command", "command": "python ~/.claude/hooks/notify_done.py"}]}]},
        "enabledPlugins": {"example-tools@demo-market": True}}
    (CLAUDE / "settings.json").write_text(json.dumps(ayar, indent=2), encoding="utf-8")
    (EV / ".claude.json").write_text(json.dumps({"mcpServers": {
        "docs-search": {"type": "stdio", "command": "npx", "args": ["docs-search-mcp"]},
        "image-tools": {"type": "stdio", "command": "uvx", "args": ["image-tools-mcp"]}}}, indent=2), encoding="utf-8")
    (CLAUDE / "CLAUDE.md").write_text("# Global notes\n\n- Prefer small commits.\n- Run tests before finishing.\n",
                                      encoding="utf-8")
    mem = CLAUDE / "projects" / f"{SAHTE_KOK}".replace(":", "-").replace("\\", "-") / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    (mem / "MEMORY.md").write_text("\n".join(f"- [Note {i}](note-{i}.md) — example memory line about a project decision"
                                             for i in range(40)) + "\n", encoding="utf-8")


def main() -> None:
    for d in (EV, VERI):
        shutil.rmtree(d, ignore_errors=True)
    ayar_dosyalari()
    for gun in range(27, -1, -1):
        for _ in range(rnd.choice([0, 1, 1, 2, 2, 3])):
            proje = rnd.choice(list(PROJELER))
            kategori, dosyalar, emirler = PROJELER[proje]
            bas = SIMDI - timedelta(days=gun, hours=rnd.uniform(1, 10))
            oturum_uret(proje, kategori, dosyalar, emirler, bas, uzun=rnd.random() < 0.18)
    VERI.mkdir(parents=True, exist_ok=True)
    (VERI / "ayarlar.json").write_text(json.dumps({
        "kaplar": [SAHTE_KOK],
        "projeler": {ad: k for ad, (k, _, _) in PROJELER.items()},
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Demo verisi hazır:", EV)


if __name__ == "__main__":
    main()
