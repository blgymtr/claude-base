"""Bant: skill, hook, eklenti, MCP ve hafıza dosyalarını listeler, açar ve kapatır.

Kural: hiçbir şey silinmez. Kapatılan öğe kenara taşınır (skill, ajan), ayar dosyasından
çıkarılıp panonun saklama dosyasına yazılır (hook, hafıza satırı) ya da bayrağı değiştirilir
(eklenti). Ayar dosyasına her yazıştan önce zaman damgalı yedek alınır.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import config
import indexer

SAKLA = config.DATA_DIR / "kapali.json"


# ----------------------------------------------------------------------------- dosya yardımcıları

def _oku_json(path: Path, varsayilan=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {} if varsayilan is None else varsayilan


def _yedekle(path: Path) -> str | None:
    if not path.exists():
        return None
    config.YEDEK_DIR.mkdir(parents=True, exist_ok=True)
    hedef = config.YEDEK_DIR / f"{path.name}.{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, hedef)
    return str(hedef)


def _yaz_json(path: Path, data) -> None:
    _yedekle(path)
    tmp = path.with_name(path.name + ".bant-tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))  # geçerli JSON mu?
    os.replace(tmp, path)


def _sakla_oku() -> dict:
    d = _oku_json(SAKLA)
    for k in ("hooks", "hafiza", "mcp"):
        d.setdefault(k, {})
    return d


def _sakla_yaz(d: dict) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SAKLA.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, SAKLA)


def _frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def _token(n_chars: int) -> int:
    return round(n_chars / 3.2)  # Türkçe metin için kaba tahmin


# ----------------------------------------------------------------------------- kullanım istatistiği

def kullanim(gun: int = 30) -> dict:
    """Son N günün oturumlarından skill, MCP, hook ve araç kullanımını topla."""
    out = {"skills": {}, "mcp": {}, "hooks": {}, "hook_ctx": {}, "tools": {}, "oturum": 0, "skill_son": {}}
    for o in indexer.ozetler(gun):
        out["oturum"] += 1
        for k, v in (o.get("skills") or {}).items():
            out["skills"][k] = out["skills"].get(k, 0) + v
            out["skill_son"][k] = max(out["skill_son"].get(k, 0), o.get("end") or 0)
        for k, v in (o.get("mcp") or {}).items():
            out["mcp"][k] = out["mcp"].get(k, 0) + v
        for k, v in (o.get("tools") or {}).items():
            out["tools"][k] = out["tools"].get(k, 0) + v
        for k, v in (o.get("hooks") or {}).items():
            h = out["hooks"].setdefault(k, {"runs": 0, "errors": 0, "event": v.get("event")})
            h["runs"] += v.get("runs", 0)
            h["errors"] += v.get("errors", 0)
        for k, v in (o.get("hook_ctx") or {}).items():
            h = out["hook_ctx"].setdefault(k, {"chars": 0, "times": 0})
            h["chars"] += v.get("chars", 0)
            h["times"] += v.get("times", 0)
    return out


# ----------------------------------------------------------------------------- skill'ler

def skill_listesi(k: dict) -> list[dict]:
    kapali_dir = config.KAPALI_DIR / "skills"
    out = []
    for base, acik in ((config.SKILLS_DIR, True), (kapali_dir, False)):
        if not base.exists():
            continue
        for d in sorted(base.iterdir(), key=lambda x: x.name.lower()):
            sk = d / "SKILL.md"
            if not d.is_dir():
                continue
            if d.name == "synced":
                # claude.ai'dan eşitlenen skill'ler: uygulama yönetir, salt okunur
                for sub in d.rglob("SKILL.md"):
                    fm = _frontmatter(sub.read_text(encoding="utf-8", errors="replace"))
                    ad = fm.get("name") or sub.parent.name
                    out.append({"id": "synced:" + ad, "ad": ad, "aciklama": fm.get("description", "")[:300],
                                "acik": True, "kilitli": "claude.ai'dan eşitlenir; buradan kapatılamaz",
                                "liste_token": _token(len(fm.get("description", "")) + len(ad)),
                                "govde_token": _token(sub.stat().st_size), "kullanim": k["skills"].get(ad, 0),
                                "son": k["skill_son"].get(ad), "yol": str(sub.parent)})
                continue
            if not sk.exists():
                continue
            text = sk.read_text(encoding="utf-8", errors="replace")
            fm = _frontmatter(text)
            ad = fm.get("name") or d.name
            out.append({
                "id": d.name, "ad": ad, "aciklama": fm.get("description", "")[:300], "acik": acik,
                "liste_token": _token(len(fm.get("description", "")) + len(ad)),
                "govde_token": _token(len(text)),
                "kullanim": k["skills"].get(ad, 0) + (k["skills"].get(d.name, 0) if d.name != ad else 0),
                "son": k["skill_son"].get(ad) or k["skill_son"].get(d.name), "yol": str(d),
            })
    # Eklentilerle gelen skill'ler: eklentiyle birlikte açılır/kapanır
    s = _oku_json(config.SETTINGS_PATH)
    acik_eklenti = s.get("enabledPlugins") or {}
    kurulu = _oku_json(config.CLAUDE_DIR / "plugins" / "installed_plugins.json").get("plugins", {})
    for pid, kayitlar in kurulu.items():
        if not kayitlar:
            continue
        kok = Path(kayitlar[0].get("installPath", ""))
        kisa = pid.split("@")[0]
        for sk in sorted((kok / "skills").glob("*/SKILL.md")) if kok.exists() else []:
            text = sk.read_text(encoding="utf-8", errors="replace")
            fm = _frontmatter(text)
            ad = fm.get("name") or sk.parent.name
            tam = f"{kisa}:{ad}"
            out.append({"id": "eklenti:" + tam, "ad": tam, "aciklama": fm.get("description", "")[:300],
                        "acik": bool(acik_eklenti.get(pid)), "kilitli": f"'{kisa}' eklentisiyle açılır/kapanır",
                        "liste_token": _token(len(fm.get("description", "")) + len(tam)),
                        "govde_token": _token(len(text)),
                        "kullanim": k["skills"].get(tam, 0) + k["skills"].get(ad, 0),
                        "son": k["skill_son"].get(tam), "yol": str(sk.parent), "eklenti": pid})
    return out


def skill_degistir(sid: str, ac: bool) -> str:
    if sid.startswith("synced:") or "/" in sid or "\\" in sid or sid in ("", ".", ".."):
        raise ValueError("Bu skill buradan değiştirilemez")
    acik = config.SKILLS_DIR / sid
    kapali = config.KAPALI_DIR / "skills" / sid
    kaynak, hedef = (kapali, acik) if ac else (acik, kapali)
    if not kaynak.exists():
        raise ValueError("Skill bulunamadı")
    if hedef.exists():
        raise ValueError("Hedefte aynı adlı skill var; elle bak")
    hedef.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(kaynak), str(hedef))
    return f"{sid} {'açıldı' if ac else 'kapatıldı (' + str(hedef) + ')'}"


# ----------------------------------------------------------------------------- hook'lar

def _hook_id(event: str, command: str) -> str:
    return hashlib.sha1(f"{event}\n{command}".encode("utf-8")).hexdigest()[:12]


def hook_listesi(k: dict) -> list[dict]:
    s = _oku_json(config.SETTINGS_PATH)
    out = []
    for ev, gruplar in (s.get("hooks") or {}).items():
        for g in gruplar:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                etiket = indexer.hook_etiketi(cmd)
                st = k["hooks"].get(f"{etiket} @{ev}", {})
                out.append({"id": _hook_id(ev, cmd), "olay": ev, "matcher": g.get("matcher", ""), "ad": etiket,
                            "komut": indexer.hook_cozulmus(cmd)[:600], "acik": True, "kapsam": "genel",
                            "calisma": st.get("runs", 0), "hata": st.get("errors", 0),
                            "timeout": h.get("timeout")})
    for hid, kayit in _sakla_oku()["hooks"].items():
        cmd = kayit["hook"].get("command", "")
        etiket = indexer.hook_etiketi(cmd)
        out.append({"id": hid, "olay": kayit["event"], "matcher": kayit.get("matcher", ""), "ad": etiket,
                    "komut": indexer.hook_cozulmus(cmd)[:600], "acik": False, "kapsam": "genel",
                    "calisma": 0, "hata": 0, "timeout": kayit["hook"].get("timeout")})
    # Proje düzeyindeki hook'lar (salt okunur): ayarlanmışsa kasa
    kasa = config.kasa()
    proj = kasa / ".claude" / "settings.local.json" if kasa else None
    if proj and proj.exists():
        kilit = config.ayarlar().get("kasa_kilit") or "kasanın kendi ayarı"
        ps = _oku_json(proj)
        for ev, gruplar in (ps.get("hooks") or {}).items():
            for g in gruplar:
                for h in g.get("hooks", []):
                    cmd = h.get("command", "")
                    out.append({"id": "kasa:" + _hook_id(ev, cmd), "olay": ev, "matcher": g.get("matcher", ""),
                                "ad": indexer.hook_etiketi(cmd), "komut": indexer.hook_cozulmus(cmd)[:600],
                                "acik": True, "kapsam": f"{kasa.name} (salt okunur)", "kilitli": kilit,
                                "calisma": k["hooks"].get(f"{indexer.hook_etiketi(cmd)} @{ev}", {}).get("runs", 0),
                                "hata": 0, "timeout": h.get("timeout")})
    return out


def hook_degistir(hid: str, ac: bool) -> str:
    s = _oku_json(config.SETTINGS_PATH)
    sakla = _sakla_oku()
    if ac:
        kayit = sakla["hooks"].pop(hid, None)
        if not kayit:
            raise ValueError("Kapalı hook bulunamadı")
        grup = {"hooks": [kayit["hook"]]}
        if kayit.get("matcher"):
            grup = {"matcher": kayit["matcher"], "hooks": [kayit["hook"]]}
        s.setdefault("hooks", {}).setdefault(kayit["event"], []).append(grup)
        _yaz_json(config.SETTINGS_PATH, s)
        _sakla_yaz(sakla)
        return "Hook açıldı; yeni oturumlarda çalışır"
    for ev, gruplar in list((s.get("hooks") or {}).items()):
        for gi, g in enumerate(gruplar):
            for hi, h in enumerate(g.get("hooks", [])):
                if _hook_id(ev, h.get("command", "")) == hid:
                    g["hooks"].pop(hi)
                    if not g["hooks"]:
                        gruplar.pop(gi)
                    if not gruplar:
                        s["hooks"].pop(ev)
                    sakla["hooks"][hid] = {"event": ev, "matcher": g.get("matcher", ""), "hook": h,
                                           "kapatildi": time.time()}
                    _sakla_yaz(sakla)
                    _yaz_json(config.SETTINGS_PATH, s)
                    return "Hook kapatıldı; yeni oturumlarda çalışmaz"
    raise ValueError("Hook bulunamadı")


# ----------------------------------------------------------------------------- eklentiler

def eklenti_listesi(k: dict) -> list[dict]:
    s = _oku_json(config.SETTINGS_PATH)
    kurulu = _oku_json(config.CLAUDE_DIR / "plugins" / "installed_plugins.json").get("plugins", {})
    out = []
    for ad, acik in (s.get("enabledPlugins") or {}).items():
        kisa = ad.split("@")[0]
        kullanim = sum(v for kk, v in k["skills"].items() if kk.startswith(kisa + ":"))
        kullanim += sum(v for kk, v in k["tools"].items() if kk.startswith(f"mcp__plugin_{kisa}"))
        bilgi = (kurulu.get(ad) or [{}])[0]
        out.append({"id": ad, "ad": kisa, "kaynak": ad.split("@")[1] if "@" in ad else "", "acik": bool(acik),
                    "surum": bilgi.get("version"), "kullanim": kullanim})
    return out


def eklenti_degistir(pid: str, ac: bool) -> str:
    s = _oku_json(config.SETTINGS_PATH)
    if pid not in (s.get("enabledPlugins") or {}):
        raise ValueError("Eklenti bulunamadı")
    s["enabledPlugins"][pid] = bool(ac)
    _yaz_json(config.SETTINGS_PATH, s)
    return f"{pid} {'açıldı' if ac else 'kapatıldı'}; yeni oturumlarda geçerli"


# ----------------------------------------------------------------------------- MCP sunucuları

def _claude_exe() -> str | None:
    for p in (config.HOME / ".local" / "bin" / "claude.exe", config.HOME / ".local" / "bin" / "claude"):
        if p.exists():
            return str(p)
    return shutil.which("claude")


def mcp_listesi(k: dict) -> list[dict]:
    cj = _oku_json(config.CLAUDE_JSON)
    out = []
    for ad, cfg in (cj.get("mcpServers") or {}).items():
        out.append({"id": ad, "ad": ad, "acik": True, "tur": cfg.get("type", "stdio"),
                    "komut": (cfg.get("command", "") + " " + " ".join(cfg.get("args", [])))[:300] or cfg.get("url", ""),
                    "kullanim": k["mcp"].get(ad, 0)})
    for ad, kayit in _sakla_oku()["mcp"].items():
        cfg = kayit["config"]
        out.append({"id": ad, "ad": ad, "acik": False, "tur": cfg.get("type", "stdio"),
                    "komut": (cfg.get("command", "") + " " + " ".join(cfg.get("args", [])))[:300] or cfg.get("url", ""),
                    "kullanim": 0})
    # Uygulamanın kendi araçları (ccd_*, Claude_Browser vb.): bilgi amaçlı
    yerlesik = {kk: v for kk, v in k["mcp"].items() if kk not in {o["id"] for o in out}}
    for ad, v in sorted(yerlesik.items(), key=lambda x: -x[1]):
        out.append({"id": "yerlesik:" + ad, "ad": ad, "acik": True, "tur": "uygulama", "komut": "",
                    "kullanim": v, "kilitli": "Claude uygulamasının kendi aracı ya da claude.ai bağlantısı"})
    return out


def mcp_degistir(ad: str, ac: bool) -> str:
    """Resmi `claude mcp` komutuyla kullanıcı kapsamında kaldır/ekle (dosya kilidiyle yarışmaz)."""
    exe = _claude_exe()
    if not exe:
        raise ValueError("claude komutu bulunamadı")
    sakla = _sakla_oku()
    if ac:
        kayit = sakla["mcp"].get(ad)
        if not kayit:
            raise ValueError("Kapalı MCP bulunamadı")
        r = subprocess.run([exe, "mcp", "add-json", "-s", "user", ad, json.dumps(kayit["config"])],
                           capture_output=True, text=True, encoding="utf-8", timeout=60, creationflags=config.PENCERESIZ)
        if r.returncode != 0:
            raise ValueError("claude mcp add-json: " + (r.stderr or r.stdout)[-300:])
        sakla["mcp"].pop(ad)
        _sakla_yaz(sakla)
        return f"{ad} açıldı; yeni oturumlarda yüklenir"
    cfg = (_oku_json(config.CLAUDE_JSON).get("mcpServers") or {}).get(ad)
    if not cfg:
        raise ValueError("MCP sunucusu bulunamadı")
    _yedekle(config.CLAUDE_JSON)
    sakla["mcp"][ad] = {"config": cfg, "kapatildi": time.time()}
    _sakla_yaz(sakla)
    r = subprocess.run([exe, "mcp", "remove", "-s", "user", ad], capture_output=True, text=True,
                       encoding="utf-8", timeout=60, creationflags=config.PENCERESIZ)
    if r.returncode != 0:
        sakla["mcp"].pop(ad, None)
        _sakla_yaz(sakla)
        raise ValueError("claude mcp remove: " + (r.stderr or r.stdout)[-300:])
    return f"{ad} kapatıldı; ayarı panoda saklanıyor"


# ----------------------------------------------------------------------------- hafıza dosyaları

def _hafiza_dosyalari() -> list[tuple[str, Path, str | None]]:
    """(id, yol, kilit nedeni)"""
    out = [("global", config.GLOBAL_CLAUDE_MD, None)]
    for p in sorted(config.PROJECTS_DIR.glob("*/memory/MEMORY.md")):
        if any(a in str(p) for a in config.atla_proje()):
            continue
        out.append(("mem:" + p.parent.parent.name, p, None))
    for e in config.ayarlar().get("ek_hafiza") or []:
        if isinstance(e, dict) and e.get("id") and e.get("yol"):
            out.append((str(e["id"]), Path(e["yol"]), e.get("kilit")))
    out.append(("yonlendirme", config.YONLENDIRME_MD, "Ajanlar sekmesinden düzenlenir"))
    return out


def hafiza_listesi() -> list[dict]:
    sakla = _sakla_oku()["hafiza"]
    out = []
    for hid, yol, kilit in _hafiza_dosyalari():
        kapali_yol = yol.with_name(yol.name + ".kapali")
        acik = yol.exists()
        gercek = yol if acik else kapali_yol
        if not gercek.exists():
            continue
        text = gercek.read_text(encoding="utf-8", errors="replace")
        satirlar = []
        if yol.name == "MEMORY.md":
            for i, line in enumerate(text.splitlines()):
                m = re.match(r"^\s*-\s*\[(.+?)\]\((.+?)\)\s*[—-]?\s*(.*)$", line)
                if m:
                    hedef = yol.parent / m.group(2)
                    boyut = hedef.stat().st_size if hedef.exists() else 0
                    satirlar.append({"id": hashlib.sha1(line.encode("utf-8")).hexdigest()[:10], "baslik": m.group(1),
                                     "dosya": m.group(2), "aciklama": m.group(3)[:200], "acik": True,
                                     "token": _token(len(line)), "dosya_token": _token(boyut)})
            for sid, kayit in sakla.items():
                if kayit.get("dosya_id") == hid:
                    m = re.match(r"^\s*-\s*\[(.+?)\]\((.+?)\)\s*[—-]?\s*(.*)$", kayit["satir"])
                    satirlar.append({"id": sid, "baslik": m.group(1) if m else kayit["satir"][:40],
                                     "dosya": m.group(2) if m else "", "aciklama": m.group(3)[:200] if m else "",
                                     "acik": False, "token": _token(len(kayit["satir"])), "dosya_token": 0})
        importlar = re.findall(r"^@(\S+)", text, re.M)
        out.append({"id": hid, "yol": str(yol), "acik": acik, "token": _token(len(text)), "kilitli": kilit,
                    "satirlar": satirlar, "importlar": importlar,
                    "proje": hid[4:] if hid.startswith("mem:") else None})
    return out


def hafiza_degistir(hid: str, ac: bool, satir_id: str | None = None) -> str:
    dosyalar = {i: (y, k) for i, y, k in _hafiza_dosyalari()}
    if hid not in dosyalar:
        raise ValueError("Hafıza dosyası bulunamadı")
    yol, kilit = dosyalar[hid]
    if kilit:
        raise ValueError(f"Bu dosya buradan kapatılamaz: {kilit}")
    if satir_id:
        sakla = _sakla_oku()
        if ac:
            kayit = sakla["hafiza"].pop(satir_id, None)
            if not kayit:
                raise ValueError("Kapalı satır bulunamadı")
            _yedekle(yol)
            text = yol.read_text(encoding="utf-8")
            if not text.endswith("\n"):
                text += "\n"
            yol.write_text(text + kayit["satir"] + "\n", encoding="utf-8")
            _sakla_yaz(sakla)
            return "Hafıza satırı geri eklendi"
        text = yol.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if hashlib.sha1(line.rstrip("\r\n").encode("utf-8")).hexdigest()[:10] == satir_id:
                _yedekle(yol)
                sakla["hafiza"][satir_id] = {"dosya_id": hid, "satir": line.rstrip("\r\n"), "kapatildi": time.time()}
                _sakla_yaz(sakla)
                yol.write_text("".join(lines[:i] + lines[i + 1:]), encoding="utf-8")
                return "Hafıza satırı banttan çıkarıldı (not dosyası duruyor)"
        raise ValueError("Satır bulunamadı")
    kapali = yol.with_name(yol.name + ".kapali")
    if ac:
        if not kapali.exists():
            raise ValueError("Kapalı dosya bulunamadı")
        os.replace(kapali, yol)
        return f"{yol.name} açıldı"
    if not yol.exists():
        raise ValueError("Dosya bulunamadı")
    _yedekle(yol)
    os.replace(yol, kapali)
    return f"{yol.name} kapatıldı ({kapali.name} olarak duruyor)"


# ----------------------------------------------------------------------------- toplu

def bant(gun: int = 30) -> dict:
    k = kullanim(gun)
    hook_ctx = [{"olay": ev, "karakter": v["chars"], "kez": v["times"], "token": _token(v["chars"]),
                 "ortalama": round(v["chars"] / max(1, v["times"]))}
                for ev, v in sorted(k["hook_ctx"].items(), key=lambda x: -x[1]["chars"])]
    return {"gun": gun, "oturum": k["oturum"], "skills": skill_listesi(k), "hooks": hook_listesi(k),
            "hook_ctx": hook_ctx, "eklentiler": eklenti_listesi(k), "mcp": mcp_listesi(k),
            "hafiza": hafiza_listesi()}


def degistir(tur: str, oid: str, ac: bool, satir: str | None = None) -> str:
    if tur == "skill":
        return skill_degistir(oid, ac)
    if tur == "hook":
        return hook_degistir(oid, ac)
    if tur == "eklenti":
        return eklenti_degistir(oid, ac)
    if tur == "mcp":
        return mcp_degistir(oid, ac)
    if tur == "hafiza":
        return hafiza_degistir(oid, ac, satir)
    raise ValueError("Bilinmeyen tür")
