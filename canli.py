"""Şu an açık Claude Code oturumları (~/.claude/sessions/<pid>.json) ve süreç kontrolü."""
from __future__ import annotations

import ctypes
import json
import os
import sys

import config


def _pid_canli(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        k32 = ctypes.windll.kernel32
        h = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return False
        try:
            kod = ctypes.c_ulong()
            if k32.GetExitCodeProcess(h, ctypes.byref(kod)):
                return kod.value == 259  # STILL_ACTIVE
            return False
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acik_oturumlar() -> list[dict]:
    d = config.CLAUDE_DIR / "sessions"
    out = []
    if not d.exists():
        return out
    for f in d.glob("*.json"):
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pid = int(s.get("pid") or 0)
        if not _pid_canli(pid):
            continue
        out.append({
            "pid": pid, "id": s.get("sessionId"), "cwd": s.get("cwd"), "ad": s.get("name"),
            "durum": s.get("status") or "?", "durum_zaman": (s.get("statusUpdatedAt") or 0) / 1000,
            "baslangic": (s.get("startedAt") or 0) / 1000, "giris": s.get("entrypoint"),
            "tur": s.get("kind"), "surum": s.get("version"),
        })
    out.sort(key=lambda x: -x["baslangic"])
    return out
