"use strict";
// Canlı akış: açık bir oturumda kim kime veri sağlıyor, anlık olarak.
// Ortada ana oturum, iç çemberde alt ajanlar, dış çemberde dosyalar.
// Okuma: dosya → ajan (mavi). Yazma: ajan → dosya (amber). Ajan başlatma: ana → alt (yeşil).
// Devir: bir ajanın yazdığı dosyayı başka ajan okursa (mor).

const CANLI = { timer: null, raf: null, sid: null, seq: 0, olaylar: [], ajanlar: {}, dosyalar: new Map(),
  parcaciklar: [], aktif: new Map(), toplam: null, ilk: true, hover: null, boyut: { w: 0, h: 0 }, otomatik: true };
const CANLI_AJAN_LIMIT = 22, CANLI_DOSYA_LIMIT = 30;

function canliDurdur() {
  clearInterval(CANLI.timer); CANLI.timer = null;
  cancelAnimationFrame(CANLI.raf); CANLI.raf = null;
}

function renk(ad) { return getComputedStyle(document.documentElement).getPropertyValue("--" + ad).trim() || "#888"; }

async function cizCanli(kap) {
  const a = await api("acik");
  const liste = [...a.acik].sort((x, y) => (y.durum === "busy") - (x.durum === "busy") || y.durum_zaman - x.durum_zaman);
  if (!CANLI.sid || !liste.find((x) => x.id === CANLI.sid)) { canliSifirla(liste[0]?.id || null); }
  kap.innerHTML = `
  <div class="bolum-baslik" style="margin-top:14px"><h2>Canlı</h2><span class="aciklama">açık bir oturumu seç · kim kime veri sağlıyor, anlık</span>
    <div class="sag lejant">
      <span><i style="background:var(--mavi)"></i>okuma: dosya → ajan</span>
      <span><i style="background:var(--amber)"></i>yazma: ajan → dosya</span>
      <span><i style="background:var(--yesil)"></i>ajan başlatma</span>
      <span><i style="background:var(--mor)"></i>devir: başka ajanın yazdığını okuma</span>
    </div></div>
  <div class="oturum-secici" id="canliSecici">${liste.map((x) => `
    <button class="oturum-hap ${x.id === CANLI.sid ? "aktif" : ""}" data-sid="${esc(x.id)}">
      <div class="b"><span class="durum-rozet ${esc(x.durum)}">${x.durum === "busy" ? "çalışıyor" : "boşta"}</span>${esc(x.baslik || x.ad || x.id)}</div>
      <div class="m">${esc(x.proje || "")} · ${esc(x.cwd || "")}</div>
    </button>`).join("") || `<div class="bos">Şu an açık oturum yok. Bir Claude Code oturumu açınca burada görünür.</div>`}</div>
  ${CANLI.sid ? `
  <div class="iki-kolon" style="margin-top:10px;grid-template-columns:minmax(0,1fr) 340px">
    <div class="panel" style="position:relative;overflow:hidden">
      <canvas id="canliTuval" style="display:block;width:100%;height:min(620px,calc(100vh - 210px))"></canvas>
      <div id="canliIpucu" class="ipucu gizli" style="position:absolute"></div>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px;min-width:0">
      <div class="kart-izgara" style="grid-template-columns:1fr 1fr" id="canliSayac"></div>
      <div class="panel" style="flex:1;min-height:0;display:flex;flex-direction:column">
        <div class="mini-baslik" style="margin:10px 12px 4px;display:flex;justify-content:space-between">Şimdi <label class="cok-soluk" style="font-weight:400"><input type="checkbox" id="canliOto" ${CANLI.otomatik ? "checked" : ""}> otomatik kaydır</label></div>
        <div id="canliAkis" class="canli-akis" style="overflow:auto;max-height:calc(100vh - 470px);min-height:160px;padding:0 4px 8px 8px"></div>
      </div>
      <div class="panel panel-ic" id="canliIpuclari" style="padding:10px 12px"></div>
    </div>
  </div>` : ""}`;
  $("#canliSecici").onclick = (e) => { const b = e.target.closest("[data-sid]"); if (!b) return; canliSifirla(b.dataset.sid); cizCanli(kap); };
  if (!CANLI.sid) return;
  const oto = $("#canliOto"); oto.onchange = () => (CANLI.otomatik = oto.checked);
  const tuval = $("#canliTuval");
  tuval.onmousemove = (e) => { const r = tuval.getBoundingClientRect(); CANLI.fare = { x: e.clientX - r.left, y: e.clientY - r.top }; };
  tuval.onmouseleave = () => { CANLI.fare = null; };
  canliDurdur();
  await canliYokla();
  CANLI.timer = setInterval(canliYokla, 1500);
  const dongu = () => { canliCiz(); CANLI.raf = requestAnimationFrame(dongu); };
  CANLI.raf = requestAnimationFrame(dongu);
}

function canliSifirla(sid) {
  canliDurdur();
  Object.assign(CANLI, { sid, seq: 0, olaylar: [], ajanlar: {}, dosyalar: new Map(), parcaciklar: [], aktif: new Map(), toplam: null, ilk: true });
}

async function canliYokla() {
  if (!CANLI.sid || D.sekme !== "canli") return;
  let r;
  try { r = await api(`canli/${encodeURIComponent(CANLI.sid)}?seq=${CANLI.seq}`); } catch (e) { return; }
  r.ajanlar.forEach((a) => { CANLI.ajanlar[a.key] = Object.assign(CANLI.ajanlar[a.key] || { ilk: Infinity, son: 0 }, a); });
  const yeni = r.olaylar;
  CANLI.seq = r.seq;
  CANLI.toplam = r.toplam;
  const simdi = performance.now();
  yeni.forEach((o, i) => {
    CANLI.olaylar.push(o);
    const aj = CANLI.ajanlar[o.a] || (CANLI.ajanlar[o.a] = { key: o.a, label: o.a, ilk: Infinity, son: 0 });
    aj.ilk = Math.min(aj.ilk, o.t || Infinity);
    aj.son = Math.max(aj.son, o.t || 0);
    if ((o.k === "read" || o.k === "write") && o.h) {
      const key = o.h.toLowerCase();
      const f = CANLI.dosyalar.get(key) || { yol: o.h, r: 0, w: 0, son: 0, yazan: null };
      f.son = o.t || f.son; o.k === "read" ? f.r++ : f.w++;
      if (o.k === "write") f.yazan = o.a;
      CANLI.dosyalar.delete(key); CANLI.dosyalar.set(key, f); // en sona (en yeni)
    }
    // İlk yüklemede yalnız son 25 olay canlandırılır; sonrakiler yoklama aralığına yayılır.
    const canlandir = !CANLI.ilk || i >= yeni.length - 25;
    if (canlandir) {
      const gecikme = CANLI.ilk ? (i - (yeni.length - 25)) * 60 : (i / Math.max(1, yeni.length)) * 1400;
      CANLI.parcaciklar.push({ o, bas: simdi + gecikme, sure: 1100 });
      CANLI.aktif.set(o.a, simdi + gecikme);
    }
  });
  if (CANLI.olaylar.length > 4000) CANLI.olaylar.splice(0, CANLI.olaylar.length - 4000);
  // dosya halkası: en yeni N dosya
  while (CANLI.dosyalar.size > CANLI_DOSYA_LIMIT) CANLI.dosyalar.delete(CANLI.dosyalar.keys().next().value);
  CANLI.ilk = false;
  canliPanel(yeni);
}

function canliYerlesim() {
  const tuval = $("#canliTuval"); if (!tuval) return null;
  const dpr = devicePixelRatio || 1;
  const w = tuval.clientWidth, h = tuval.clientHeight;
  if (tuval.width !== Math.round(w * dpr) || tuval.height !== Math.round(h * dpr)) { tuval.width = Math.round(w * dpr); tuval.height = Math.round(h * dpr); }
  const cx = w / 2, cy = h / 2;
  const R1 = Math.min(w * 0.3, h * 0.31), R2 = Math.min(w * 0.46, h * 0.45);
  const alt = Object.values(CANLI.ajanlar).filter((a) => a.key !== "main").sort((a, b) => b.son - a.son).slice(0, CANLI_AJAN_LIMIT).sort((a, b) => a.ilk - b.ilk);
  const konum = { main: { x: cx, y: cy, r: 22 } };
  alt.forEach((a, i) => { const ac = -Math.PI / 2 + (i / Math.max(1, alt.length)) * Math.PI * 2; konum[a.key] = { x: cx + Math.cos(ac) * R1, y: cy + Math.sin(ac) * R1, r: 12 }; });
  const dosyalar = [...CANLI.dosyalar.entries()];
  const dk = {};
  dosyalar.forEach(([k, f], i) => { const ac = -Math.PI / 2 + ((i + 0.5) / Math.max(1, dosyalar.length)) * Math.PI * 2; dk[k] = { x: cx + Math.cos(ac) * R2, y: cy + Math.sin(ac) * R2 * 0.92, ac, f }; });
  const sonAltilar = new Set([...alt].sort((a, b) => b.son - a.son).slice(0, 5).map((a) => a.key));
  return { tuval, dpr, w, h, cx, cy, konum, dk, alt, sonAltilar };
}

function egri(a, b, t, buk = 0.18) {
  const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y;
  const kx = mx - dy * buk, ky = my + dx * buk;
  const u = 1 - t;
  return { x: u * u * a.x + 2 * u * t * kx + t * t * b.x, y: u * u * a.y + 2 * u * t * ky + t * t * b.y, kx, ky };
}

function canliCiz() {
  const L = canliYerlesim(); if (!L) return;
  const { tuval, dpr, w, h, konum, dk } = L;
  const c = tuval.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  const R = { metin: renk("metin"), soluk: renk("soluk"), cs: renk("cok-soluk"), cizgi: renk("cizgi2"), panel: renk("panel"), vurgu: renk("vurgu"),
    mavi: renk("mavi"), amber: renk("amber"), yesil: renk("yesil"), mor: renk("mor") };
  const simdi = performance.now();
  // ana → alt ajan bağları
  c.lineWidth = 1;
  Object.entries(konum).forEach(([k, p]) => { if (k === "main") return; c.strokeStyle = R.cizgi; c.globalAlpha = 0.5; c.beginPath(); const e = egri(konum.main, p, 0, 0.08); c.moveTo(konum.main.x, konum.main.y); c.quadraticCurveTo(e.kx, e.ky, p.x, p.y); c.stroke(); });
  c.globalAlpha = 1;
  // dosyalar
  c.font = "11px 'Segoe UI', sans-serif";
  Object.values(dk).forEach((d) => {
    const yeni = (Date.now() / 1000 - d.f.son) < 20;
    c.fillStyle = d.f.w ? R.amber : R.mavi;
    c.globalAlpha = yeni ? 1 : 0.55;
    c.beginPath(); c.arc(d.x, d.y, d.f.w ? 4 : 3, 0, Math.PI * 2); c.fill();
    const ad = d.f.yol.split(/[\\/]/).pop();
    const sag = Math.cos(d.ac) >= 0;
    c.fillStyle = yeni ? R.metin : R.soluk;
    c.textAlign = sag ? "left" : "right"; c.textBaseline = "middle";
    c.fillText(ad.length > 26 ? ad.slice(0, 25) + "…" : ad, d.x + (sag ? 8 : -8), d.y);
  });
  c.globalAlpha = 1;
  // parçacıklar
  CANLI.parcaciklar = CANLI.parcaciklar.filter((p) => simdi < p.bas + p.sure + 600);
  CANLI.parcaciklar.forEach((p) => {
    const t = (simdi - p.bas) / p.sure;
    if (t < 0) return;
    const o = p.o;
    const ajan = konum[o.a] || konum.main;
    let a, b, col;
    const dosya = o.h ? dk[o.h.toLowerCase()] : null;
    if (o.k === "read" && dosya) { a = dosya; b = ajan; col = o.devir ? R.mor : R.mavi; }
    else if (o.k === "write" && dosya) { a = ajan; b = dosya; col = R.amber; }
    else if (o.k === "agent") { a = konum.main; b = ajan; col = R.yesil; }
    else if (o.k === "done") { a = ajan; b = konum.main; col = R.yesil; }
    else if (o.k === "err") { a = ajan; b = { x: ajan.x, y: ajan.y }; col = R.vurgu; }
    else if (o.k === "devir") return;
    else { a = ajan; b = ajan; col = o.k === "command" ? R.mor : o.k === "model" ? R.cs : R.soluk; }
    if (a === b || (a.x === b.x && a.y === b.y)) {
      // yerinde atım: halka
      const tt = Math.min(1, t);
      c.strokeStyle = col; c.globalAlpha = (1 - tt) * 0.8; c.lineWidth = 1.5;
      c.beginPath(); c.arc(a.x, a.y, (a.r || 10) + tt * 16, 0, Math.PI * 2); c.stroke();
      c.globalAlpha = 1; return;
    }
    const tt = Math.min(1, t);
    // iz
    c.strokeStyle = col; c.lineWidth = 1.4;
    const izBas = Math.max(0, tt - 0.35);
    c.globalAlpha = t > 1 ? Math.max(0, 1 - (t - 1) / 0.5) * 0.5 : 0.5;
    c.beginPath();
    for (let s = izBas; s <= tt + 0.001; s += 0.04) { const q = egri(a, b, Math.min(s, tt)); s === izBas ? c.moveTo(q.x, q.y) : c.lineTo(q.x, q.y); }
    c.stroke();
    // baş
    if (t <= 1) {
      const q = egri(a, b, tt);
      const g = c.createRadialGradient(q.x, q.y, 0, q.x, q.y, 9);
      g.addColorStop(0, col); g.addColorStop(1, "transparent");
      c.globalAlpha = 0.9; c.fillStyle = g; c.beginPath(); c.arc(q.x, q.y, 9, 0, Math.PI * 2); c.fill();
      c.globalAlpha = 1; c.fillStyle = col; c.beginPath(); c.arc(q.x, q.y, 2.6, 0, Math.PI * 2); c.fill();
    }
    c.globalAlpha = 1;
  });
  // ajan düğümleri
  let hover = null;
  Object.entries(konum).forEach(([k, p]) => {
    const aj = CANLI.ajanlar[k] || { label: "Ana oturum" };
    const sonAktif = CANLI.aktif.get(k) || 0;
    const yas = (simdi - sonAktif) / 1000;
    const canli = yas < 4;
    const model = aj.model || "";
    const mr = /fable|mythos/.test(model) ? R.mor : /opus/.test(model) ? R.vurgu : /sonnet/.test(model) ? R.amber : /haiku/.test(model) ? R.yesil : R.soluk;
    if (canli) { const nb = (Math.sin(simdi / 220) + 1) / 2; c.fillStyle = mr; c.globalAlpha = 0.12 + nb * 0.12; c.beginPath(); c.arc(p.x, p.y, p.r + 8 + nb * 4, 0, Math.PI * 2); c.fill(); c.globalAlpha = 1; }
    c.fillStyle = R.panel; c.strokeStyle = canli ? mr : R.cizgi; c.lineWidth = k === "main" ? 2 : 1.4;
    c.beginPath(); c.arc(p.x, p.y, p.r, 0, Math.PI * 2); c.fill(); c.stroke();
    c.fillStyle = mr; c.beginPath(); c.arc(p.x, p.y, k === "main" ? 6 : 3.5, 0, Math.PI * 2); c.fill();
    const etiketle = k === "main" || canli || L.sonAltilar.has(k) || (CANLI.fare && Math.hypot(CANLI.fare.x - p.x, CANLI.fare.y - p.y) < p.r + 6);
    if (etiketle) {
      c.fillStyle = canli || k === "main" ? R.metin : R.soluk;
      c.font = (k === "main" ? "600 12px" : "11px") + " 'Segoe UI', sans-serif";
      c.textAlign = "center"; c.textBaseline = "top";
      const ad = k === "main" ? "Ana oturum" : String(aj.label || k);
      c.fillText(ad.length > 22 ? ad.slice(0, 21) + "…" : ad, p.x, p.y + p.r + 5);
    }
    if (CANLI.fare && Math.hypot(CANLI.fare.x - p.x, CANLI.fare.y - p.y) < p.r + 6) hover = { k, aj, p };
  });
  const ip = $("#canliIpucu");
  if (hover) {
    const ev = CANLI.olaylar.filter((o) => o.a === hover.k);
    const say = (k) => ev.filter((o) => o.k === k).length;
    ip.innerHTML = `<b>${esc(hover.k === "main" ? "Ana oturum" : hover.aj.label)}</b><br>${esc(hover.aj.type || "")} · ${esc(modelKisa(hover.aj.model || "?"))}<br>okuma ${say("read")} · yazma ${say("write")} · komut ${say("command")} · hata ${say("err")}<br><span class="cok-soluk">son etkinlik ${gorece(hover.aj.son)}</span>`;
    ip.style.left = Math.min(hover.p.x + 16, w - 260) + "px"; ip.style.top = hover.p.y + 10 + "px"; ip.classList.remove("gizli");
  } else ip.classList.add("gizli");
}

function canliPanel(yeni) {
  const t = CANLI.toplam || {};
  const son60 = CANLI.olaylar.filter((o) => Date.now() / 1000 - (o.t || 0) < 60);
  const aktifAjan = new Set(son60.map((o) => o.a)).size;
  const sayac = $("#canliSayac");
  if (sayac) sayac.innerHTML = `
    ${metrik("API karşılığı", para(t.cost || 0), "bu görünüm açıldığından beri*")}
    ${metrik("Model çağrısı", sayi(t.calls), `${tok(t.tok)} token`)}
    ${metrik("Son 1 dakika", sayi(son60.length) + " olay", `${aktifAjan} ajan etkin`)}
    ${metrik("Ajan", Object.keys(CANLI.ajanlar).length, `${CANLI.dosyalar.size} dosya ekranda`)}`;
  const akis = $("#canliAkis");
  if (akis && yeni.length) {
    const ad = (k) => (k === "main" ? "" : (CANLI.ajanlar[k]?.label || k));
    const html = yeni.filter((o) => o.k !== "model" && o.k !== "hookctx").slice(-60).reverse().map((o) => adimHtml({ ...o, k: o.k === "err" ? "command" : o.k, err: o.k === "err", e: o.k === "err" ? o.h : "", h: o.k === "err" ? "hata döndü" : o.h }, ad(o.a))).join("");
    akis.insertAdjacentHTML("afterbegin", html);
    while (akis.children.length > 220) akis.lastElementChild.remove();
    if (CANLI.otomatik) akis.scrollTop = 0;
  }
  // canlı tasarruf ipuçları: yalnız bu oturumun okunan kısmından
  const ip = $("#canliIpuclari"); if (!ip) return;
  const ev = CANLI.olaylar;
  const hookKar = ev.filter((o) => o.k === "hookctx").reduce((s, o) => s + (parseInt(o.h) || 0), 0);
  const okumalar = {}; let tekrar = 0;
  ev.forEach((o) => { if (o.k === "read") { const k = o.a + "|" + o.h; if (okumalar[k]) tekrar++; okumalar[k] = 1; } if (o.k === "write") Object.keys(okumalar).forEach((k) => { if (k.endsWith("|" + o.h)) delete okumalar[k]; }); });
  const opusKisa = Object.values(CANLI.ajanlar).filter((a) => a.key !== "main" && /opus|fable/.test(a.model || "") && ev.filter((o) => o.a === a.key && o.k === "model").length <= 15 && ev.some((o) => o.a === a.key && o.k === "done"));
  const hatalar = ev.filter((o) => o.k === "err").length;
  const satir = (renkAd, metin) => `<div style="display:flex;gap:8px;margin:4px 0;font-size:12px"><span style="width:6px;height:6px;border-radius:50%;background:var(--${renkAd});margin-top:6px;flex:none"></span><span>${metin}</span></div>`;
  const liste = [];
  if (hookKar > 3000) liste.push(satir("vurgu", `Hook'lar bu oturuma <b>~${tok(Math.round(hookKar / 3.2))} token</b> bağlam ekledi. <a href="#" data-git-sekme="bant">Bant</a>'tan daraltılabilir.`));
  if (tekrar > 3) liste.push(satir("amber", `<b>${tekrar}</b> kez değişmemiş dosya yeniden okundu.`));
  if (opusKisa.length) liste.push(satir("amber", `<b>${opusKisa.length}</b> kısa alt ajan Opus/Fable ile bitti; Sonnet yeterli olabilir. <a href="#" data-git-sekme="ajanlar">Yönlendir</a>`));
  if (hatalar > 5) liste.push(satir("vurgu", `<b>${hatalar}</b> başarısız araç çağrısı; her biri bir model turu harcar.`));
  ip.innerHTML = `<div class="mini-baslik" style="margin:0 0 4px">Bu oturumda tasarruf</div>${liste.join("") || `<div class="cok-soluk" style="font-size:12px">Şimdilik dikkat çeken bir israf yok.</div>`}
    <div class="cok-soluk" style="font-size:10.5px;margin-top:6px">* Açılışta son ~3 MB kayıt okunur; sayaçlar o andan itibaren birikir.</div>`;
  ip.onclick = (e) => { const g = e.target.closest("[data-git-sekme]"); if (g) { e.preventDefault(); sekmeAc(g.dataset.gitSekme); } };
}
