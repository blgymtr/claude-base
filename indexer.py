"""Claude Code oturum kayıtlarını (~/.claude/projects) tarar, özet ve ayrıntıyı önbelleğe yazar.

Her ana oturum ve alt ajan kaydı satır satır okunur; olaylar zamana göre birleştirilir ve
pano metrikleri (maliyet, dosya okuma/yazma, hata, tekrar, gereksiz okuma, devir) çıkarılır.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sqlite3
import threading
import time
import zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import config

READ_TOOLS = {"Read", "NotebookRead"}
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
SEARCH_TOOLS = {"Glob", "Grep"}
CMD_TOOLS = {"Bash", "PowerShell"}
AGENT_TOOLS = {"Agent", "Task"}
# Pano için gereksiz, büyük kayıt türleri: json çözmeden atlanır.
ATLA_TURLER = ("api-request", "file-history", "atis-latch", "queue-operation", "tools-used")
_TYPE_RE = re.compile(r'"type"\s*:\s*"([a-z\-]+)"')


# ----------------------------------------------------------------------------- yardımcılar

def _norm(p: str) -> str:
    try:
        return os.path.normcase(os.path.normpath(p))
    except Exception:
        return p


def _ts(s: str | None) -> float:
    if not s:
        return 0.0
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def hook_etiketi(command: str) -> str:
    """Hook komutunu okunur bir ada çevir (PowerShell EncodedCommand çözülür)."""
    text = command or ""
    if "-EncodedCommand " in text:
        try:
            text = base64.b64decode(text.split("-EncodedCommand ")[1].strip()).decode("utf-16le")
        except Exception:
            pass
    m = re.findall(r"[\w\-.]+\.(?:py|js|mjs|ps1|sh|cmd|bat)", text)
    if m:
        name = m[-1] if m[-1] != "python.exe" else m[0]
        extra = re.search(r"--harness'?\s*'?(\w+)", text)
        return name
    return text.strip()[:60] or "?"


def hook_cozulmus(command: str) -> str:
    text = command or ""
    if "-EncodedCommand " in text:
        try:
            return base64.b64decode(text.split("-EncodedCommand ")[1].strip()).decode("utf-16le")
        except Exception:
            return text
    return text


def _maliyet(model, usage) -> float:
    pr = config.fiyat(model)
    if not pr or not usage:
        return 0.0
    pin, pout, pread = pr
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    cr = usage.get("cache_read_input_tokens") or 0
    cc = usage.get("cache_creation") or {}
    c5 = cc.get("ephemeral_5m_input_tokens")
    c1 = cc.get("ephemeral_1h_input_tokens")
    if c5 is None and c1 is None:
        c5, c1 = usage.get("cache_creation_input_tokens") or 0, 0
    return (inp * pin + (c5 or 0) * pin * 1.25 + (c1 or 0) * pin * 2 + cr * pread + out * pout) / 1e6


def _hedef(name: str, inp: dict) -> tuple[str, str]:
    """Araç çağrısını (tür, hedef) olarak sınıfla."""
    if not isinstance(inp, dict):
        inp = {}
    if name in READ_TOOLS:
        return "read", inp.get("file_path") or inp.get("notebook_path") or ""
    if name in WRITE_TOOLS:
        return "write", inp.get("file_path") or inp.get("notebook_path") or ""
    if name in SEARCH_TOOLS:
        return "search", inp.get("pattern") or inp.get("path") or ""
    if name in CMD_TOOLS:
        desc = inp.get("description") or ""
        cmd = (inp.get("command") or "").replace("\n", " ")
        return "command", (desc + " · " if desc else "") + cmd[:160]
    if name == "Skill":
        return "skill", inp.get("skill") or ""
    if name in AGENT_TOOLS:
        return "agent", inp.get("description") or ""
    if name.startswith("mcp__"):
        parts = name.split("__")
        return "mcp", (parts[1] if len(parts) > 1 else name)
    if name in ("WebFetch", "WebSearch"):
        return "web", inp.get("url") or inp.get("query") or ""
    return "tool", name


def _prompt_metni(content) -> str | None:
    if isinstance(content, str):
        t = content
    elif isinstance(content, list):
        parts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        if not parts or any(isinstance(c, dict) and c.get("type") == "tool_result" for c in content):
            return None
        t = "\n".join(parts)
    else:
        return None
    t = t.strip()
    if not t or t.startswith("<") and ("system-reminder" in t[:80] or "local-command" in t[:80]
                                        or "command-name" in t[:80] or "task-notification" in t[:80]
                                        or "side-sessions-event" in t[:80]):
        return None
    # baştaki sistem hatırlatmalarını ve yapıştırma etiketlerini kırp
    t = re.sub(r"<system-reminder>.*?</system-reminder>", "", t, flags=re.S)
    t = re.sub(r"</?pasted_content[^>]*>", "", t).strip()
    return t or None


# ----------------------------------------------------------------------------- akış ayrıştırma

def _akis_oku(path: Path, ajan: str):
    """Bir kayıt dosyasını oku; olay listesi ve ajan istatistiği döndür."""
    olaylar = []
    istat = {
        "models": {}, "efforts": {}, "calls": 0, "in": 0, "out": 0, "cr": 0, "cw": 0, "cost": 0.0,
        "tools": {}, "skills": {}, "mcp": {}, "first": None, "last": None,
        "gun": {},  # "YYYY-MM-DD" -> [maliyet, token, çağrı]  (yerel saat)
    }
    meta = {"title": None, "cwd": None, "prompts": [], "spawns": {}, "agent_ids": {},
            "hooks": {}, "compacts": 0}
    mesaj_kullanim = {}  # message.id -> (model, usage, effort, ts)
    tool_index = {}  # tool_use_id -> olay index
    try:
        fh = open(path, encoding="utf-8", errors="replace")
    except OSError:
        return olaylar, istat, meta
    with fh:
        for line in fh:
            head = line[:600]
            mt = _TYPE_RE.search(head)
            if mt and mt.group(1).startswith(ATLA_TURLER):
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            t = r.get("type")
            if t in ATLA_TURLER or (t and t.startswith(ATLA_TURLER)):
                continue
            ts = _ts(r.get("timestamp"))
            if ts:
                istat["first"] = ts if istat["first"] is None else min(istat["first"], ts)
                istat["last"] = ts if istat["last"] is None else max(istat["last"], ts)
            if r.get("cwd") and not meta["cwd"]:
                meta["cwd"] = r["cwd"]
            if t == "custom-title" and r.get("customTitle"):
                meta["title"] = r["customTitle"]
            elif t == "system":
                st = r.get("subtype")
                if st == "compact_boundary":
                    meta["compacts"] += 1
                elif st == "stop_hook_summary":
                    infos = r.get("hookInfos") or []
                    errs = r.get("hookErrors") or []
                    for h in infos:
                        cmd = h.get("command") if isinstance(h, dict) else str(h)
                        key = hook_etiketi(cmd) + " @Stop"
                        hk = meta["hooks"].setdefault(key, {"event": "Stop", "runs": 0, "errors": 0, "ctx": 0, "cmd": cmd})
                        hk["runs"] += 1
                    if errs:
                        for e in errs:
                            meta["hooks"].setdefault("Stop hatası", {"event": "Stop", "runs": 0, "errors": 0, "ctx": 0, "cmd": ""})
                            meta["hooks"]["Stop hatası"]["errors"] += 1
            elif t == "attachment":
                a = r.get("attachment") or {}
                at = a.get("type") or ""
                if at == "hook_additional_context":
                    # Bağlam hook'a değil olaya bağlı gelir: olay başına topla.
                    ev = a.get("hookEvent") or (a.get("hookName") or "").split(":")[0] or "?"
                    c = a.get("content")
                    n = len("".join(c) if isinstance(c, list) else str(c or ""))
                    ctx = meta.setdefault("hook_ctx", {})
                    e = ctx.setdefault(ev, {"chars": 0, "times": 0})
                    e["chars"] += n
                    e["times"] += 1
                elif at.startswith("hook_"):
                    ev = a.get("hookEvent") or (a.get("hookName") or "").split(":")[0]
                    cmd = a.get("command") or ""
                    key = (hook_etiketi(cmd) if cmd else (a.get("hookName") or "hook")) + " @" + str(ev)
                    hk = meta["hooks"].setdefault(key, {"event": ev, "runs": 0, "errors": 0, "ctx": 0, "cmd": cmd})
                    hk["runs"] += 1
                    if "error" in at or str(a.get("exitCode", "0")) not in ("0", "None"):
                        hk["errors"] += 1
                        olaylar.append({"t": ts, "a": ajan, "k": "hook", "n": key, "h": str(a.get("stderr") or "")[:200], "err": True})
                elif at == "queued_command":
                    p = a.get("prompt") or ""
                    if isinstance(p, str) and p.lstrip().startswith("<task-notification>"):
                        ozet = re.search(r"<summary>(.*?)</summary>", p, re.S)
                        durum = re.search(r"<status>(.*?)</status>", p)
                        olaylar.append({"t": ts, "a": ajan, "k": "done", "n": "Ajan bildirimi",
                                        "h": (ozet.group(1) if ozet else "")[:160],
                                        "st": durum.group(1) if durum else ""})
                    elif ajan == "main":
                        txt = _prompt_metni(p)
                        if txt:
                            meta["prompts"].append({"t": ts, "x": txt[:400], "q": True})
                            olaylar.append({"t": ts, "a": ajan, "k": "prompt", "n": "Emir (sırada)", "h": txt[:160]})
                elif at == "invoked_skills":
                    for s in a.get("skills") or []:
                        n = s.get("name") if isinstance(s, dict) else str(s)
                        if n:
                            istat["skills"][n] = istat["skills"].get(n, 0)
            elif t == "assistant":
                m = r.get("message") or {}
                mid = m.get("id") or r.get("uuid")
                model = m.get("model")
                if model and model != "<synthetic>":
                    mesaj_kullanim[mid] = (model, m.get("usage") or {}, r.get("effort"), ts)
                for c in m.get("content") or []:
                    if not isinstance(c, dict) or c.get("type") != "tool_use":
                        continue
                    name = c.get("name") or "?"
                    inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                    tur, hedef = _hedef(name, inp)
                    istat["tools"][name] = istat["tools"].get(name, 0) + 1
                    if tur == "skill" and hedef:
                        istat["skills"][hedef] = istat["skills"].get(hedef, 0) + 1
                    if tur == "mcp":
                        istat["mcp"][hedef] = istat["mcp"].get(hedef, 0) + 1
                    olay = {"t": ts, "a": ajan, "k": tur, "n": name, "h": hedef, "id": c.get("id")}
                    if tur == "read" and (inp.get("offset") or inp.get("limit") or inp.get("pages")):
                        olay["rk"] = f"{inp.get('offset')}:{inp.get('limit')}:{inp.get('pages')}"
                    if tur == "agent":
                        meta["spawns"][c.get("id")] = {
                            "description": inp.get("description") or "",
                            "model": inp.get("model") or "",
                            "type": inp.get("subagent_type") or "general-purpose",
                            "background": str(inp.get("run_in_background")).lower() == "true",
                            "t": ts,
                        }
                    tool_index[c.get("id")] = len(olaylar)
                    olaylar.append(olay)
            elif t == "user":
                m = r.get("message") or {}
                content = m.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "tool_result":
                            idx = tool_index.get(c.get("tool_use_id"))
                            if idx is not None:
                                o = olaylar[idx]
                                o["ok"] = ts
                                if c.get("is_error") in (True, "True", "true"):
                                    o["err"] = True
                                    cc = c.get("content")
                                    if isinstance(cc, list):
                                        cc = " ".join(x.get("text", "") for x in cc if isinstance(x, dict))
                                    o["e"] = str(cc or "")[:240]
                tur = r.get("toolUseResult")
                if isinstance(tur, dict) and tur.get("agentId"):
                    src = r.get("sourceToolAssistantUUID")
                    for c in content if isinstance(content, list) else []:
                        if isinstance(c, dict) and c.get("type") == "tool_result":
                            meta["agent_ids"][tur["agentId"]] = {
                                "tool_use_id": c.get("tool_use_id"),
                                "resolvedModel": tur.get("resolvedModel"),
                                "status": tur.get("status"),
                            }
                if ajan == "main" and not r.get("isMeta") and not r.get("isSidechain"):
                    txt = _prompt_metni(content)
                    if txt:
                        meta["prompts"].append({"t": ts, "x": txt[:400]})
                        olaylar.append({"t": ts, "a": ajan, "k": "prompt", "n": "Emir", "h": txt[:160]})
    for mid, (model, usage, effort, ts) in mesaj_kullanim.items():
        md = istat["models"].setdefault(model, {"calls": 0, "in": 0, "out": 0, "cr": 0, "cw": 0, "cost": 0.0})
        cw = usage.get("cache_creation_input_tokens") or 0
        cost = _maliyet(model, usage)
        for d in (md, istat):
            d["calls"] += 1
            d["in"] += usage.get("input_tokens") or 0
            d["out"] += usage.get("output_tokens") or 0
            d["cr"] += usage.get("cache_read_input_tokens") or 0
            d["cw"] += cw
            d["cost"] += cost
        if effort:
            istat["efforts"][effort] = istat["efforts"].get(effort, 0) + 1
        if ts:
            gk = time.strftime("%Y-%m-%d", time.localtime(ts))
            g = istat["gun"].setdefault(gk, [0.0, 0, 0])
            g[0] += cost
            g[1] += (usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0) \
                + (usage.get("cache_read_input_tokens") or 0) + cw
            g[2] += 1
    return olaylar, istat, meta


def oturum_ayristir(main_path: str, sub_paths: list[str], ayar: dict) -> dict:
    """Bir ana oturumu ve alt ajanlarını tam ayrıntıyla ayrıştır."""
    main_path = Path(main_path)
    olaylar, istat, meta = _akis_oku(main_path, "main")
    ajanlar = {"main": {"key": "main", "label": "Ana oturum", "type": "main", "desc": "Seninle konuşan ana oturum",
                        "stat": istat, "model_req": None, "effort": _top(istat["efforts"])}}
    spawn_by_tool = meta["spawns"]
    for sp in sorted(sub_paths):
        sp = Path(sp)
        aid = sp.stem.replace("agent-", "")
        mfile = sp.with_name(sp.stem + ".meta.json")
        m = {}
        if mfile.exists():
            try:
                m = json.loads(mfile.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                m = {}
        so, si, smeta = _akis_oku(sp, aid)
        if not so and not si["calls"]:
            continue
        olaylar.extend(so)
        spawn = spawn_by_tool.get(m.get("toolUseId")) or {}
        if not spawn:
            link = meta["agent_ids"].get(aid) or {}
            spawn = spawn_by_tool.get(link.get("tool_use_id")) or {}
        ajanlar[aid] = {
            "key": aid,
            "label": m.get("description") or spawn.get("description") or aid[:8],
            "type": m.get("agentType") or spawn.get("type") or "alt ajan",
            "desc": spawn.get("description") or m.get("description") or "",
            "stat": si,
            "model_req": m.get("model") or spawn.get("model") or None,
            "effort": _top(si["efforts"]),
            "background": spawn.get("background", m.get("requestShape") == "background"),
            "finished": m.get("finished"),
        }
    olaylar.sort(key=lambda o: o.get("t") or 0)

    # ---- dosya akışı, gereksiz okuma, tekrar, devir
    dosyalar = {}
    son_yazan = {}
    yazma_sayaci = {}
    okuma_durumu = {}
    hata_son = {}
    gereksiz = tekrar = devir = 0
    devirler = []
    for o in olaylar:
        a = o["a"]
        k = o["k"]
        if k in ("read", "write") and o.get("h"):
            key = _norm(o["h"])
            d = dosyalar.setdefault(key, {"path": o["h"], "r": 0, "w": 0, "by": {}})
            by = d["by"].setdefault(a, {"r": 0, "w": 0})
            if k == "read":
                d["r"] += 1
                by["r"] += 1
                surum = yazma_sayaci.get(key, 0)
                okey = (a, key, o.get("rk"))  # aynı dosyanın farklı bölümü ayrı okuma sayılır
                if okuma_durumu.get(okey) == surum:
                    gereksiz += 1
                    o["redundant"] = True
                okuma_durumu[okey] = surum
                yazan = son_yazan.get(key)
                if yazan and yazan != a:
                    devir += 1
                    devirler.append({"from": yazan, "to": a, "path": o["h"], "t": o["t"]})
                    son_yazan[key] = None  # aynı yazımı bir kez say
            else:
                d["w"] += 1
                by["w"] += 1
                yazma_sayaci[key] = yazma_sayaci.get(key, 0) + 1
                son_yazan[key] = a
        if k not in ("prompt",):
            sig = (o["n"], _norm(o.get("h") or "")[:120])
            prev = hata_son.get(a)
            if prev and prev == sig:
                tekrar += 1
                o["retry"] = True
            hata_son[a] = sig if o.get("err") else None

    hatalar = sum(1 for o in olaylar if o.get("err"))
    for aj in ajanlar.values():
        s = aj["stat"]
        evs = [o for o in olaylar if o["a"] == aj["key"]]
        aj["reads"] = sum(1 for o in evs if o["k"] == "read")
        aj["writes"] = sum(1 for o in evs if o["k"] == "write")
        aj["cmds"] = sum(1 for o in evs if o["k"] == "command")
        aj["web"] = sum(1 for o in evs if o["k"] == "web")
        aj["searches"] = sum(1 for o in evs if o["k"] == "search")
        aj["subagents"] = sum(1 for o in evs if o["k"] == "agent")
        aj["errors"] = sum(1 for o in evs if o.get("err"))
        aj["toolcount"] = sum(1 for o in evs if o["k"] not in ("prompt",))
        aj["files"] = sorted(
            ({"path": d["path"], "r": d["by"][aj["key"]]["r"], "w": d["by"][aj["key"]]["w"]}
             for d in dosyalar.values() if aj["key"] in d["by"]),
            key=lambda x: (-(x["w"] * 3 + x["r"]), x["path"]))
        aj["models"] = s["models"]

    first = min((a["stat"]["first"] for a in ajanlar.values() if a["stat"]["first"]), default=0)
    last = max((a["stat"]["last"] for a in ajanlar.values() if a["stat"]["last"]), default=0)
    # Aktif süre: 10 dakikadan uzun sessizlikler sayılmaz.
    aktif = 0.0
    zamanlar = sorted(o["t"] for o in olaylar if o.get("t"))
    for x, y in zip(zamanlar, zamanlar[1:]):
        aktif += min(y - x, 600)
    toplam = {"calls": 0, "in": 0, "out": 0, "cr": 0, "cw": 0, "cost": 0.0}
    modeller = {}
    skills, mcp, tools = {}, {}, {}
    gunluk = {}
    for aj in ajanlar.values():
        s = aj["stat"]
        for gk, (c, tk, n) in s["gun"].items():
            g = gunluk.setdefault(gk, [0.0, 0, 0])
            g[0] += c
            g[1] += tk
            g[2] += n
        for kk in toplam:
            toplam[kk] += s[kk]
        for mdl, md in s["models"].items():
            t = modeller.setdefault(mdl, {"calls": 0, "in": 0, "out": 0, "cr": 0, "cw": 0, "cost": 0.0})
            for kk in t:
                t[kk] += md[kk]
        for src, dst in ((s["skills"], skills), (s["mcp"], mcp), (s["tools"], tools)):
            for kk, v in src.items():
                dst[kk] = dst.get(kk, 0) + v

    proje, kok = proje_bul(meta["cwd"], dosyalar, ayar)
    kategori = kategori_bul(proje, kok, ayar, main_path.stem)
    ozet = {
        "id": main_path.stem,
        "title": meta["title"] or (meta["prompts"][0]["x"][:70] if meta["prompts"] else main_path.stem[:8]),
        "cwd": meta["cwd"],
        "project": proje, "root": kok, "category": kategori,
        "start": first, "end": last, "duration": max(0, last - first), "active": round(aktif),
        "agents": len(ajanlar), "prompts": len(meta["prompts"]),
        "calls": toplam["calls"], "in": toplam["in"], "out": toplam["out"], "cr": toplam["cr"], "cw": toplam["cw"],
        "cost": round(toplam["cost"], 4),
        "errors": hatalar, "retries": tekrar, "redundant": gereksiz, "handoffs": devir,
        "files_read": sum(1 for d in dosyalar.values() if d["r"]),
        "files_written": sum(1 for d in dosyalar.values() if d["w"]),
        "models": modeller, "skills": skills, "mcp": mcp, "tools": tools,
        "hooks": meta["hooks"], "hook_ctx": meta.get("hook_ctx", {}), "compacts": meta["compacts"],
        "gunluk": {k: [round(v[0], 4), v[1], v[2]] for k, v in sorted(gunluk.items())},
        "subagent_summary": [
            {"type": a["type"], "model": (list(a["models"]) or [a["model_req"]])[0] if (a["models"] or a["model_req"]) else None,
             "model_req": a["model_req"], "effort": a["effort"], "cost": round(a["stat"]["cost"], 4),
             "out": a["stat"]["out"], "calls": a["stat"]["calls"],
             "duration": max(0, (a["stat"]["last"] or 0) - (a["stat"]["first"] or 0)),
             "errors": a["errors"], "label": a["label"]}
            for k, a in ajanlar.items() if k != "main"],
    }
    detay = {
        "ozet": ozet,
        "prompts": meta["prompts"],
        "agents": [
            {k: v for k, v in a.items() if k != "stat"} | {
                "calls": a["stat"]["calls"], "in": a["stat"]["in"], "out": a["stat"]["out"],
                "cr": a["stat"]["cr"], "cw": a["stat"]["cw"], "cost": round(a["stat"]["cost"], 4),
                "first": a["stat"]["first"], "last": a["stat"]["last"],
                "efforts": a["stat"]["efforts"], "tools": a["stat"]["tools"]}
            for a in ajanlar.values()],
        "files": sorted(({"path": d["path"], "r": d["r"], "w": d["w"], "by": d["by"]} for d in dosyalar.values()),
                        key=lambda x: (-(x["w"] * 3 + x["r"]), x["path"])),
        "handoffs": devirler[:400],
        "timeline": olaylar[-6000:],
        "timeline_kirpildi": max(0, len(olaylar) - 6000),
    }
    return {"ozet": ozet, "detay": detay}


def _top(d: dict):
    return max(d, key=d.get) if d else None


# ----------------------------------------------------------------------------- proje ve kategori

def _kok_bul(path: str, kaplar: list[str], haric: tuple = ()):
    r = _kok_bul_ham(path, kaplar)
    if r and r[0].lower() in haric:
        return None
    return r


def _kok_bul_ham(path: str, kaplar: list[str]):
    p = _norm(path)
    en_iyi = None
    for k in kaplar:
        kn = _norm(k).rstrip("\\/")
        if p.startswith(kn + os.sep) and (en_iyi is None or len(kn) > len(_norm(en_iyi).rstrip("\\/"))):
            en_iyi = k.rstrip("\\/")
    if en_iyi is None:
        return None
    rest = os.path.normpath(path)[len(en_iyi):].lstrip("\\/")
    parca = rest.split(os.sep)
    ilk = parca[0] if rest else ""
    if not ilk or (len(parca) == 1 and "." in ilk):
        return None  # kabın içindeki tek bir dosya
    return ilk, os.path.join(en_iyi + (os.sep if en_iyi.endswith(":") else ""), ilk)


GECICI = ("\\appdata\\local\\temp\\", "\\.claude\\", "\\appdata\\roaming\\", "\\scratchpad\\")


def proje_bul(cwd: str | None, dosyalar: dict, ayar: dict):
    kaplar = ayar.get("kaplar", [])
    haric = tuple(x.lower() for x in ayar.get("proje_degil", []))
    puan = {}
    kokler = {}
    kasa_yolu = config.kasa()
    vault = _norm(str(kasa_yolu)) if kasa_yolu else None
    for key, d in dosyalar.items():
        if any(g in key for g in GECICI):
            continue
        agirlik = d["w"] * 3 + d["r"]
        if vault and key.startswith(vault):
            ad, kok = kasa_yolu.name, str(kasa_yolu)
        else:
            r = _kok_bul(d["path"], kaplar, haric)
            if not r:
                continue
            ad, kok = r
        puan[ad] = puan.get(ad, 0) + agirlik
        kokler[ad] = kok
    if puan:
        ad = max(puan, key=puan.get)
        return ad, kokler[ad]
    if cwd:
        if _norm(cwd).rstrip("\\/") == _norm(str(config.HOME)):
            return "Ev klasörü", cwd
        r = _kok_bul(cwd, kaplar, haric)
        if r:
            return r
        return os.path.basename(cwd.rstrip("\\/")) or cwd, cwd
    return "?", ""


def kategori_bul(proje: str, kok: str, ayar: dict, sid: str | None = None) -> str:
    if sid and sid in ayar.get("oturumlar", {}):
        return ayar["oturumlar"][sid]
    atanmis = ayar.get("projeler", {})
    if proje in atanmis:
        return atanmis[proje]
    for anahtar in ayar.get("kural_oyun", []):
        if anahtar.lower() in (kok or "").lower():
            return "Oyunlar"
    return "Sınıflanmadı"


# ----------------------------------------------------------------------------- önbellek

def _db():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS oturum (
        id TEXT PRIMARY KEY, yol TEXT, imza TEXT, ozet TEXT, detay BLOB,
        baslangic REAL, bitis REAL, guncel REAL)""")
    con.execute("CREATE INDEX IF NOT EXISTS oturum_bitis ON oturum(bitis)")
    return con


def dosyalari_topla():
    """{oturum_id: (ana_yol, [alt_ajan_yolları], imza)}"""
    out = {}
    if not config.PROJECTS_DIR.exists():
        return out
    atla = config.atla_proje()
    for proj in config.PROJECTS_DIR.iterdir():
        if not proj.is_dir() or any(a in proj.name for a in atla):
            continue
        for f in proj.glob("*.jsonl"):
            sid = f.stem
            subdir = proj / sid / "subagents"
            subs = sorted(str(s) for s in subdir.glob("agent-*.jsonl")) if subdir.exists() else []
            parcalar = []
            for p in [str(f)] + subs:
                try:
                    st = os.stat(p)
                    parcalar.append(f"{st.st_size}:{int(st.st_mtime)}")
                except OSError:
                    pass
            out[sid] = (str(f), subs, "|".join(parcalar))
    return out


DURUM = {"calisiyor": False, "toplam": 0, "biten": 0, "son": None, "hata": None, "basladi": None}
_KILIT = threading.Lock()


def _isci(args):
    sid, main_path, subs, imza, ayar = args
    try:
        sonuc = oturum_ayristir(main_path, subs, ayar)
        return sid, main_path, imza, sonuc, None
    except Exception as e:  # tek bozuk dosya taramayı durdurmasın
        return sid, main_path, imza, None, repr(e)


def tara(zorla: bool = False, isci_sayisi: int | None = None):
    """Değişen oturumları yeniden ayrıştır. Arka plan iş parçacığından çağrılır."""
    if not _KILIT.acquire(blocking=False):
        return
    try:
        DURUM.update(calisiyor=True, biten=0, hata=None, basladi=time.time())
        ayar = config.ayarlar()
        con = _db()
        mevcut = {r[0]: r[1] for r in con.execute("SELECT id, imza FROM oturum")}
        dosyalar = dosyalari_topla()
        isler = [(sid, m, s, imza, ayar) for sid, (m, s, imza) in dosyalar.items()
                 if zorla or mevcut.get(sid) != imza]
        # büyük dosyalar önce: paralel iş daha dengeli biter
        isler.sort(key=lambda x: -sum(os.path.getsize(p) for p in [x[1]] + x[2] if os.path.exists(p)))
        DURUM["toplam"] = len(isler)
        silinen = set(mevcut) - set(dosyalar)
        for sid in silinen:
            con.execute("DELETE FROM oturum WHERE id=?", (sid,))
        con.commit()
        if isler:
            n = isci_sayisi or max(1, min(8, (os.cpu_count() or 2) - 1))
            with ProcessPoolExecutor(max_workers=n) as ex:
                futs = [ex.submit(_isci, a) for a in isler]
                for fut in as_completed(futs):
                    sid, main_path, imza, sonuc, hata = fut.result()
                    DURUM["biten"] += 1
                    if sonuc is None:
                        DURUM["hata"] = f"{sid}: {hata}"
                        continue
                    o = sonuc["ozet"]
                    con.execute(
                        "REPLACE INTO oturum VALUES (?,?,?,?,?,?,?,?)",
                        (sid, main_path, imza, json.dumps(o, ensure_ascii=False),
                         zlib.compress(json.dumps(sonuc["detay"], ensure_ascii=False).encode("utf-8"), 6),
                         o["start"], o["end"], time.time()))
                    if DURUM["biten"] % 10 == 0:
                        con.commit()
        con.commit()
        con.close()
        DURUM["son"] = time.time()
    except Exception as e:
        DURUM["hata"] = repr(e)
    finally:
        DURUM["calisiyor"] = False
        _KILIT.release()


def kategorileri_yenile():
    """Ayarlar değişince önbellekteki özetlerin kategorisini güncelle (yeniden ayrıştırmadan)."""
    ayar = config.ayarlar()
    con = _db()
    for sid, oz in con.execute("SELECT id, ozet FROM oturum").fetchall():
        o = json.loads(oz)
        k = kategori_bul(o.get("project"), o.get("root"), ayar, sid)
        if k != o.get("category"):
            o["category"] = k
            con.execute("UPDATE oturum SET ozet=? WHERE id=?", (json.dumps(o, ensure_ascii=False), sid))
    con.commit()
    con.close()


def ozetler(gun: float | None = None) -> list[dict]:
    con = _db()
    if gun:
        sinir = time.time() - gun * 86400
        rows = con.execute("SELECT ozet FROM oturum WHERE bitis >= ? ORDER BY bitis DESC", (sinir,)).fetchall()
    else:
        rows = con.execute("SELECT ozet FROM oturum ORDER BY bitis DESC").fetchall()
    con.close()
    return [json.loads(r[0]) for r in rows]


def detay(sid: str) -> dict | None:
    con = _db()
    row = con.execute("SELECT detay FROM oturum WHERE id=?", (sid,)).fetchone()
    con.close()
    if not row:
        return None
    d = json.loads(zlib.decompress(row[0]).decode("utf-8"))
    ayar = config.ayarlar()
    d["ozet"]["category"] = kategori_bul(d["ozet"].get("project"), d["ozet"].get("root"), ayar, sid)
    return d


if __name__ == "__main__":
    import sys
    t0 = time.time()
    tara(zorla="--zorla" in sys.argv)
    print(json.dumps(DURUM, ensure_ascii=False), f"{time.time() - t0:.1f} sn")
