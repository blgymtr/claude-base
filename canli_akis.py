"""Canlı akış: açık bir oturumun kayıt dosyalarının yalnız yeni eklenen satırlarını okur.

Her yoklamada ana oturum ve alt ajan dosyalarının sonuna eklenen baytlar okunur, olaylara
çevrilir ve sıra numarasıyla bir halka belleğe eklenir. İstemci son gördüğü sıra numarasını
gönderir, yalnız yenilerini alır. Dosyanın tamamı hiçbir zaman yeniden okunmaz.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import config
import indexer

ILK_OKUMA = 3_000_000    # açılışta her dosyanın son ~3 MB'ı (yakın geçmiş)
HALKA = 3000             # bellekte tutulan son olay sayısı
_DURUMLAR: dict[str, "AkisDurumu"] = {}
_KILIT = threading.Lock()


def _ana_yol(sid: str) -> Path | None:
    for p in config.PROJECTS_DIR.glob(f"*/{sid}.jsonl"):
        return p
    return None


class AkisDurumu:
    def __init__(self, sid: str, ana: Path):
        self.sid = sid
        self.ana = ana
        self.ofset: dict[str, int] = {}
        self.etiket: dict[str, str] = {"main": "Ana oturum"}
        self.tur: dict[str, str] = {"main": "main"}
        self.model: dict[str, str] = {}
        self.olaylar: list[dict] = []
        self.seq = 0
        self.tool_ajan: dict[str, str] = {}
        self.son_yazan: dict[str, str] = {}
        self.toplam = {"cost": 0.0, "out": 0, "tok": 0, "calls": 0}
        self.gorulen_mesaj: set[str] = set()
        self.kilit = threading.Lock()
        self.son_erisim = time.time()

    # ------------------------------------------------------------------ dosyalar
    def _dosyalar(self):
        out = [("main", self.ana)]
        sub = self.ana.with_suffix("") / "subagents"
        if sub.exists():
            for f in sub.glob("agent-*.jsonl"):
                aid = f.stem.replace("agent-", "")
                if aid not in self.etiket:
                    m = f.with_name(f.stem + ".meta.json")
                    try:
                        meta = json.loads(m.read_text(encoding="utf-8")) if m.exists() else {}
                    except (OSError, ValueError):
                        meta = {}
                    self.etiket[aid] = meta.get("description") or aid[:8]
                    self.tur[aid] = meta.get("agentType") or "alt ajan"
                    if meta.get("model"):
                        self.model[aid] = meta["model"]
                out.append((aid, f))
        return out

    def _ekle(self, o: dict):
        self.seq += 1
        o["s"] = self.seq
        self.olaylar.append(o)
        if len(self.olaylar) > HALKA:
            del self.olaylar[: len(self.olaylar) - HALKA]

    # ------------------------------------------------------------------ okuma
    def yokla(self):
        with self.kilit:
            self.son_erisim = time.time()
            yeni = []
            for ajan, yol in self._dosyalar():
                key = str(yol)
                try:
                    boyut = yol.stat().st_size
                except OSError:
                    continue
                bas = self.ofset.get(key)
                if bas is None:
                    bas = max(0, boyut - ILK_OKUMA)
                    ilk = True
                else:
                    ilk = False
                if boyut <= bas:
                    self.ofset[key] = boyut
                    continue
                with open(yol, "rb") as fh:
                    fh.seek(bas)
                    veri = fh.read(boyut - bas)
                # yarım son satırı bir sonraki yoklamaya bırak
                son_nl = veri.rfind(b"\n")
                if son_nl < 0:
                    continue
                parca = veri[: son_nl + 1]
                self.ofset[key] = bas + son_nl + 1
                satirlar = parca.split(b"\n")
                if ilk and bas > 0:
                    satirlar = satirlar[1:]  # ortadan başlayan ilk satır yarım
                for ham in satirlar:
                    if not ham.strip():
                        continue
                    yeni.extend(self._satir(ajan, ham))
            yeni.sort(key=lambda o: o.get("t") or 0)
            for o in yeni:
                self._ekle(o)

    def _satir(self, ajan: str, ham: bytes):
        head = ham[:600].decode("utf-8", "replace")
        mt = indexer._TYPE_RE.search(head)
        if mt and mt.group(1).startswith(indexer.ATLA_TURLER):
            return []
        try:
            r = json.loads(ham)
        except ValueError:
            return []
        t = r.get("type")
        ts = indexer._ts(r.get("timestamp"))
        out = []
        if t == "assistant":
            m = r.get("message") or {}
            mid = m.get("id")
            model = m.get("model")
            if model and model != "<synthetic>":
                self.model.setdefault(ajan, model)
                if mid and mid not in self.gorulen_mesaj:
                    self.gorulen_mesaj.add(mid)
                    u = m.get("usage") or {}
                    cost = indexer._maliyet(model, u)
                    tok = sum((u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                       "cache_creation_input_tokens"))
                    self.toplam["cost"] += cost
                    self.toplam["out"] += u.get("output_tokens") or 0
                    self.toplam["tok"] += tok
                    self.toplam["calls"] += 1
                    out.append({"t": ts, "a": ajan, "k": "model", "n": model, "h": "", "out": u.get("output_tokens") or 0,
                                "c": round(cost, 5), "tok": tok})
            for c in m.get("content") or []:
                if not isinstance(c, dict) or c.get("type") != "tool_use":
                    continue
                name = c.get("name") or "?"
                inp = c.get("input") if isinstance(c.get("input"), dict) else {}
                tur, hedef = indexer._hedef(name, inp)
                o = {"t": ts, "a": ajan, "k": tur, "n": name, "h": hedef, "id": c.get("id")}
                if tur == "read" and hedef:
                    yazan = self.son_yazan.get(indexer._norm(hedef))
                    if yazan and yazan != ajan:
                        o["devir"] = yazan
                elif tur == "write" and hedef:
                    self.son_yazan[indexer._norm(hedef)] = ajan
                elif tur == "agent":
                    o["model"] = inp.get("model") or ""
                self.tool_ajan[c.get("id")] = ajan
                out.append(o)
        elif t == "user":
            content = (r.get("message") or {}).get("content")
            if isinstance(content, list):
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "tool_result" and c.get("is_error") in (True, "True", "true"):
                        cc = c.get("content")
                        if isinstance(cc, list):
                            cc = " ".join(x.get("text", "") for x in cc if isinstance(x, dict))
                        out.append({"t": ts, "a": ajan, "k": "err", "n": "hata", "h": str(cc or "")[:200],
                                    "ref": c.get("tool_use_id")})
            if ajan == "main" and not r.get("isMeta") and not r.get("isSidechain"):
                txt = indexer._prompt_metni(content)
                if txt:
                    out.append({"t": ts, "a": ajan, "k": "prompt", "n": "Emir", "h": txt[:200]})
        elif t == "attachment":
            a = r.get("attachment") or {}
            if a.get("type") == "queued_command":
                p = a.get("prompt") or ""
                if isinstance(p, str) and "<task-notification>" in p[:40]:
                    import re
                    oz = re.search(r"<summary>(.*?)</summary>", p, re.S)
                    out.append({"t": ts, "a": ajan, "k": "done", "n": "bitti", "h": (oz.group(1) if oz else "")[:160]})
            elif a.get("type") == "hook_additional_context":
                cc = a.get("content")
                n = len("".join(cc) if isinstance(cc, list) else str(cc or ""))
                out.append({"t": ts, "a": ajan, "k": "hookctx", "n": a.get("hookEvent") or "hook", "h": f"{n} karakter bağlam"})
        return out

    def disari(self, son_seq: int) -> dict:
        yeni = [o for o in self.olaylar if o["s"] > son_seq]
        return {
            "sid": self.sid, "seq": self.seq, "olaylar": yeni[-1500:],
            "ajanlar": [{"key": k, "label": v, "type": self.tur.get(k), "model": self.model.get(k)}
                        for k, v in self.etiket.items()],
            "toplam": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.toplam.items()},
        }


def akis(sid: str, son_seq: int = 0) -> dict:
    with _KILIT:
        d = _DURUMLAR.get(sid)
        if d is None:
            ana = _ana_yol(sid)
            if not ana:
                raise ValueError("Oturum kaydı bulunamadı")
            d = _DURUMLAR[sid] = AkisDurumu(sid, ana)
        # 15 dakikadır bakılmayan durumları bellekten at
        for k in [k for k, v in _DURUMLAR.items() if time.time() - v.son_erisim > 900 and k != sid]:
            _DURUMLAR.pop(k, None)
    d.yokla()
    return d.disari(son_seq)
