"use strict";
// Claude Base — tamamen yerel. Tek veri kaynağı 127.0.0.1 üzerindeki /api uçları.

const D = {
  gun: 30, sekme: "genel", oturum: null, ajan: "main", zoom: 0.85, tumAjanlar: false,
  projeFiltre: null, katFiltre: null, arama: "", gecmisSaat: 48, emir: null, adimFiltre: "hepsi",
  skillFiltre: "hepsi", sonTarama: null, veri: {},
};
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

// ------------------------------------------------------------------ biçimlendirme
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ond = (x, d) => x.toFixed(d).replace(".", ",");
const para = (x) => (x == null ? "—" : "$" + (x >= 100 ? Math.round(x).toLocaleString("tr-TR") : ond(x, x >= 10 ? 1 : 2)));
const tok = (n) => { n = n || 0; if (n >= 1e9) return ond(n / 1e9, 1) + " mlr"; if (n >= 1e6) return ond(n / 1e6, 1) + " mn"; if (n >= 1e3) return ond(n / 1e3, n >= 1e4 ? 0 : 1) + " bin"; return String(n); };
const sayi = (n) => (n || 0).toLocaleString("tr-TR");
const sure = (sn) => { sn = Math.round(sn || 0); if (sn < 60) return sn + " sn"; if (sn < 3600) return Math.floor(sn / 60) + " dk " + (sn % 60) + " sn"; if (sn < 86400) return Math.floor(sn / 3600) + " sa " + Math.floor((sn % 3600) / 60) + " dk"; return Math.floor(sn / 86400) + " gün " + Math.floor((sn % 86400) / 3600) + " sa"; };
const AYLAR = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
const tarih = (ts) => { if (!ts) return "—"; const d = new Date(ts * 1000); return `${d.getDate()} ${AYLAR[d.getMonth()]} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
const saat = (ts) => { if (!ts) return ""; const d = new Date(ts * 1000); return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`; };
const gorece = (ts) => { if (!ts) return "—"; const f = Date.now() / 1000 - ts; if (f < 90) return "az önce"; if (f < 3600) return Math.floor(f / 60) + " dk önce"; if (f < 86400) return Math.floor(f / 3600) + " sa önce"; return Math.floor(f / 86400) + " gün önce"; };
const dosyaAdi = (p) => String(p || "").split(/[\\/]/).filter(Boolean).pop() || p;
const modelKisa = (m) => String(m || "?").replace("claude-", "").replace(/-(\d)-(\d)/, " $1.$2").replace(/-(\d)$/, " $1");
const MODEL_RENK = (m) => /fable|mythos/.test(m) ? "var(--mor)" : /opus/.test(m) ? "var(--vurgu)" : /sonnet/.test(m) ? "var(--amber)" : /haiku/.test(m) ? "var(--yesil)" : "var(--mavi)";
const KAT_RENK = { "Projelerim": "var(--mavi)", "Oyunlar": "var(--vurgu)", "Uygulamalar": "var(--amber)", "Side-projects": "var(--yesil)", "Sınıflanmadı": "var(--cok-soluk)" };
const TUR_AD = { read: "okuma", write: "yazma", command: "komut", search: "arama", skill: "skill", agent: "ajan", mcp: "mcp", web: "web", tool: "araç", prompt: "EMİR", done: "bitti", hook: "hook" };

// ------------------------------------------------------------------ ağ
async function api(yol) {
  const r = await fetch("/api/" + yol, { cache: "no-store" });
  const j = await r.json();
  if (!r.ok) throw new Error(j.hata || r.statusText);
  return j;
}
async function post(yol, govde) {
  const r = await fetch("/api/" + yol, { method: "POST", headers: { "Content-Type": "application/json", "X-Bant": "1" }, body: JSON.stringify(govde || {}) });
  let j = {};
  try { j = await r.json(); } catch { }
  if (!r.ok) throw new Error(j.hata || r.statusText);
  return j;
}
function bildir(m, hata) {
  const el = document.createElement("div");
  el.className = "bildirim" + (hata ? " hata" : "");
  el.textContent = m;
  document.body.appendChild(el);
  setTimeout(() => el.remove(), hata ? 7000 : 4200);
}
function onayla(baslik, metin) {
  return new Promise((res) => {
    const o = document.createElement("div");
    o.className = "ortu";
    o.innerHTML = `<div class="modal"><h3>${esc(baslik)}</h3><div class="soluk">${metin}</div><div class="dugmeler"><button class="kucuk-dugme" data-x="0">Vazgeç</button><button class="ana-dugme" data-x="1">Onayla</button></div></div>`;
    o.addEventListener("click", (e) => { const x = e.target.dataset.x; if (x != null || e.target === o) { o.remove(); res(x === "1"); } });
    document.body.appendChild(o);
  });
}
const gunQ = () => "gun=" + (D.gun || 0);

// ------------------------------------------------------------------ ipucu
const ip = $("#ipucu");
document.addEventListener("mousemove", (e) => {
  const t = e.target.closest("[data-ip]");
  if (!t) { ip.classList.add("gizli"); return; }
  ip.innerHTML = t.dataset.ip;
  ip.classList.remove("gizli");
  ip.style.left = Math.min(e.clientX + 14, innerWidth - ip.offsetWidth - 10) + "px";
  ip.style.top = e.clientY + 16 + "px";
});

// ------------------------------------------------------------------ gezinme
function sekmeAc(s) {
  if (s !== "canli" && typeof canliDurdur === "function") canliDurdur();
  D.sekme = s;
  $$(".sekme").forEach((b) => b.classList.toggle("aktif", b.dataset.sekme === s));
  $$(".sayfa").forEach((x) => x.classList.toggle("gizli", x.id !== "s-" + s));
  try { localStorage.setItem("bant.sekme", s); } catch { }
  ciz();
}
$("#sekmeler").addEventListener("click", (e) => { const b = e.target.closest(".sekme"); if (b) sekmeAc(b.dataset.sekme); });
$("#donem").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  D.gun = +b.dataset.gun;
  $$("#donem button").forEach((x) => x.classList.toggle("aktif", x === b));
  ciz();
});
$("#tema").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  document.documentElement.dataset.tema = b.dataset.tema;
  $$("#tema button").forEach((x) => x.classList.toggle("aktif", x === b));
  try { localStorage.setItem("bant.tema", b.dataset.tema); } catch { }
});
$("#yenileDugme").addEventListener("click", async () => { await post("tara", { zorla: false }); bildir("Tarama başladı; değişen oturumlar yeniden okunuyor"); durumYokla(); });
$("#obsidianDugme").addEventListener("click", async () => {
  if (!(await onayla("Obsidian'a yaz", "Son 7 günün özeti ayarlardaki Obsidian kasasının <code>notes/bant/</code> klasörüne günlük notlar olarak yazılır. Emir metinleri yazılmaz; yalnız başlık, proje, süre, token, maliyet ve yazılan dosya adları."))) return;
  try { const r = await post("obsidian", { gunler: 7 }); bildir(r.mesaj.split("\n").filter((x) => x.includes("yazıldı")).length + " gün yazıldı"); } catch (e) { bildir(e.message, true); }
});

$("#kapatDugme").addEventListener("click", async () => {
  if (!(await onayla("Claude Base'i kapat", "Yerel sunucu durur. Yeniden açmak için <b>Claude Base.exe</b>'ye çift tıkla."))) return;
  try { await post("kapat"); } catch { }
  if (typeof canliDurdur === "function") canliDurdur();
  document.body.innerHTML = `<div class="bos" style="padding:80px">Claude Base kapandı. Bu pencereyi kapatabilirsin.</div>`;
  setTimeout(() => window.close(), 600);
});

function ciz() {
  const f = { genel: cizGenel, canli: cizCanli, projeler: cizProjeler, oturumlar: cizOturumlar, gecmis: cizGecmis, bant: cizBant, ajanlar: cizAjanlar, oneriler: cizOneriler }[D.sekme];
  const kap = $("#s-" + D.sekme);
  if (!kap.innerHTML) kap.innerHTML = `<div class="yukleniyor">Yükleniyor…</div>`;
  f(kap).catch((e) => { kap.innerHTML = `<div class="bos">Hata: ${esc(e.message)}</div>`; console.error(e); });
}

// ------------------------------------------------------------------ durum yoklama
async function durumYokla() {
  try {
    const d = await api("durum");
    const n = $("#taramaNokta"), m = $("#taramaMetin");
    n.classList.toggle("calisiyor", d.calisiyor);
    m.textContent = d.calisiyor ? `taranıyor ${d.biten}/${d.toplam}` : d.son ? `son tarama ${gorece(d.son)}` : "ilk tarama bekleniyor";
    if (!d.calisiyor && d.son && D.sonTarama && d.son !== D.sonTarama && !["bant", "ajanlar"].includes(D.sekme)) ciz();
    D.sonTarama = d.son;
    const a = await api("acik");
    const busy = a.acik.filter((x) => x.durum === "busy").length;
    $("#acikSayac").innerHTML = `<b>${a.acik.length}</b> açık oturum · <span style="color:var(--amber2)">${busy} çalışıyor</span>`;
  } catch { $("#taramaMetin").textContent = "sunucuya ulaşılamıyor"; }
}
setInterval(durumYokla, 6000);

// ================================================================== GENEL
async function cizGenel(kap) {
  const [g, o] = await Promise.all([api("genel?" + gunQ()), api("oneriler?" + gunQ())]);
  D.veri.oneriler = o;
  rozetGuncelle(o);
  const maxG = Math.max(...g.gunluk.map((x) => x.cost), 0.01);
  const katToplam = Object.values(g.kategoriler).reduce((a, b) => a + b.cost, 0) || 1;
  const modeller = Object.entries(g.modeller).sort((a, b) => b[1].cost - a[1].cost);
  const maxM = Math.max(...modeller.map((x) => x[1].cost), 0.01);
  const maxP = Math.max(...g.projeler.map((x) => x.cost), 0.01);
  kap.innerHTML = `
  <div class="bolum-baslik"><h2>Şu an açık</h2><span class="aciklama">çalışan Claude Code süreçleri · tıkla, canlı izle</span></div>
  <div class="canli-serit">${g.acik.length ? g.acik.map((a) => `
    <div class="canli-kart ${esc(a.durum)}" data-oturum="${esc(a.id)}">
      <div class="ust"><span>${esc(a.proje || "?")}</span><span class="durum-rozet ${esc(a.durum)}">${a.durum === "busy" ? "çalışıyor" : "boşta"}</span></div>
      <div class="b">${esc(a.baslik || a.ad || a.id)}</div>
      <div class="alt">${esc(a.kategori || "")} · ${a.ajan ? a.ajan + " ajan · " : ""}${para(a.cost)} · ${gorece(a.baslangic)} açıldı</div>
    </div>`).join("") : `<div class="bos">Şu an açık oturum yok.</div>`}</div>

  <div class="bolum-baslik"><h2>${D.gun ? "Son " + D.gun + " gün" : "Tüm zamanlar"}</h2><span class="aciklama">${g.oturum} oturum · API karşılığı abonelikte faturalanmaz, yapılan işin ölçüsüdür</span></div>
  <div class="kart-izgara">
    ${metrik("API karşılığı / USD", para(g.cost), "liste fiyatıyla hesaplanan değer", "vurgulu")}
    ${metrik("Toplam token", tok(g.tok), `girdi ${tok(g.inp)} · çıktı ${tok(g.out)}`)}
    ${metrik("Önbellekten okunan", tok(g.cr), `önbelleğe yazılan ${tok(g.cw)}`)}
    ${metrik("Model çağrısı", sayi(g.calls), "ana + alt ajanlar")}
    ${metrik("Alt ajan", sayi(g.ajan), "başlatılan alt ajan sayısı")}
    ${metrik("Hata", sayi(g.hata), "başarısız araç çağrısı", g.hata ? "kirmizi" : "")}
  </div>

  <div class="iki-kolon" style="margin-top:16px">
    <div class="panel panel-ic">
      <div class="mini-baslik" style="margin-top:0">Günlük API karşılığı</div>
      ${alanGrafik(g.gunluk.map((x) => ({ y: x.cost, ip: `<b>${esc(x.gun)}</b><br>${para(x.cost)} · ${tok(x.tok)} token · ${x.oturum} oturum` })), 150)}
      <div class="eksen"><span>${esc(g.gunluk[0]?.gun || "")}</span><span>${esc(g.gunluk.at(-1)?.gun || "")}</span></div>
      <div class="mini-baslik">Kategoriler</div>
      <div class="oran-bar" style="height:12px">${Object.entries(g.kategoriler).map(([k, v]) => `<span style="width:${(v.cost / katToplam) * 100}%;background:${KAT_RENK[k] || "var(--soluk)"}" data-ip="<b>${esc(k)}</b><br>${para(v.cost)} · ${tok(v.tok)} token"></span>`).join("")}</div>
      <div class="kat-izgara">${Object.entries(g.kategoriler).sort((a, b) => b[1].cost - a[1].cost).map(([k, v]) => `
          <div class="kat-kutu" style="--k:${KAT_RENK[k]}"><div class="a">${esc(k)}</div><div class="d">${para(v.cost)}</div><div class="s">${tok(v.tok)} token · ${v.oturum} oturum</div></div>`).join("")}</div>
    </div>
    <div class="panel panel-ic">
      <div class="mini-baslik" style="margin-top:0">Modeller</div>
      ${modeller.map(([m, v]) => `<div class="yatay-bar"><span class="tek-satir"><i style="display:inline-block;width:8px;height:8px;border-radius:2px;background:${MODEL_RENK(m)};margin-right:7px"></i>${esc(modelKisa(m))}</span><div class="iz"><span style="width:${(v.cost / maxM) * 100}%"></span></div><span class="s" data-ip="${sayi(v.calls)} çağrı · ${tok(v.tok)} token">${para(v.cost)}</span></div>`).join("")}
      <div class="mini-baslik">En çok token yakan projeler</div>
      ${g.projeler.map((p) => `<div class="yatay-bar tikla" data-proje="${esc(p.ad)}" style="cursor:pointer"><span class="tek-satir" style="border-left:3px solid ${KAT_RENK[p.kategori]};padding-left:7px">${esc(p.ad)}</span><div class="iz"><span style="width:${(p.cost / maxP) * 100}%"></span></div><span class="s" data-ip="${tok(p.tok)} token">${para(p.cost)}</span></div>`).join("")}
    </div>
  </div>

  <div class="bolum-baslik"><h2>Öne çıkan öneriler</h2><span class="aciklama">token azaltmak için, senin verinden</span><div class="sag"><button class="kucuk-dugme" data-git="oneriler">Tümü →</button></div></div>
  ${o.oneriler.slice(0, 3).map(oneriHtml).join("") || `<div class="bos">Şimdilik öneri yok.</div>`}`;
  kap.onclick = (e) => {
    const c = e.target.closest("[data-oturum]"); if (c) { canliSifirla(c.dataset.oturum); return sekmeAc("canli"); }
    const p = e.target.closest("[data-proje]"); if (p) { D.projeFiltre = p.dataset.proje; D.oturum = null; return sekmeAc("oturumlar"); }
    const gt = e.target.closest("[data-git]"); if (gt) return oneriGit(gt.dataset.git);
  };
}
const metrik = (ad, deger, alt, sinif = "") => `<div class="metrik ${sinif}"><div class="ad">${esc(ad)}</div><div class="deger">${deger}</div><div class="alt">${alt}</div></div>`;
function rozetGuncelle(o) {
  const n = o.oneriler.filter((x) => x.oncelik <= 2).length;
  const r = $("#oneriRozet"); r.textContent = n; r.classList.toggle("gizli", !n);
}
function oturumAc(id) { D.oturum = id; D.ajan = "main"; D.projeFiltre = null; sekmeAc("oturumlar"); }

// ================================================================== PROJELER
async function cizProjeler(kap) {
  const v = await api("projeler?" + gunQ());
  const katlar = v.kategoriler;
  kap.innerHTML = `
  <div class="bolum-baslik"><h2>Projeler</h2><span class="aciklama">kartı sürükleyip başka kategoriye bırak · tıkla, oturumlarını gör · yeşil nokta: şu an açık</span></div>
  <div class="kanban">${katlar.map((k) => {
    const ps = v.projeler.filter((p) => p.kategori === k);
    const top = ps.reduce((a, b) => a + b.cost, 0);
    return `<div class="kolon" data-kat="${esc(k)}"><div class="kolon-baslik" style="--k:${KAT_RENK[k]}"><b>${esc(k)}</b><span>${ps.length} · ${para(top)}</span></div>
      ${ps.map((p) => projeKart(p, katlar)).join("") || `<div class="bos">Boş</div>`}</div>`;
  }).join("")}</div>`;
  kap.onclick = (e) => {
    if (e.target.closest("select")) return;
    const c = e.target.closest(".proje-kart"); if (c) { D.projeFiltre = c.dataset.proje; D.oturum = null; sekmeAc("oturumlar"); }
  };
  kap.onchange = async (e) => {
    const s = e.target.closest("select[data-proje]"); if (!s) return;
    await kategoriKaydet(s.dataset.proje, s.value);
  };
  $$(".proje-kart", kap).forEach((c) => c.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/plain", c.dataset.proje)));
  $$(".kolon", kap).forEach((k) => {
    k.addEventListener("dragover", (e) => { e.preventDefault(); k.classList.add("uzerinde"); });
    k.addEventListener("dragleave", () => k.classList.remove("uzerinde"));
    k.addEventListener("drop", async (e) => { e.preventDefault(); k.classList.remove("uzerinde"); const p = e.dataTransfer.getData("text/plain"); if (p) await kategoriKaydet(p, k.dataset.kat); });
  });
}
function projeKart(p, katlar) {
  const toplamM = Object.values(p.modeller).reduce((a, b) => a + b, 0) || 1;
  return `<div class="proje-kart" draggable="true" data-proje="${esc(p.ad)}">
    <div class="ad">${p.acik ? `<span class="canli" data-ip="Şu an açık oturumu var"></span>` : ""}<span class="tek-satir" style="max-width:150px">${esc(p.ad)}</span></div>
    <div class="soluk yol tek-satir" style="font-size:10.5px;margin-top:2px" data-ip="${esc(p.kok)}">${esc(p.kok || "")}</div>
    <div class="s">
      <span>API karşılığı</span><b>${para(p.cost)}</b>
      <span>Token</span><b>${tok(p.tok)}</b>
      <span>Oturum</span><b>${p.oturum}</b>
      <span>Alt ajan</span><b>${p.ajan}</b>
      <span>Aktif süre</span><b>${sure(p.aktif)}</b>
      <span>Son</span><b>${gorece(p.son)}</b>
    </div>
    <div class="oran-bar model-bar">${Object.entries(p.modeller).map(([m, c]) => `<span style="width:${(c / toplamM) * 100}%;background:${MODEL_RENK(m)}" data-ip="${esc(modelKisa(m))}: ${para(c)}"></span>`).join("")}</div>
    <span class="kat-ac">⋯</span><select data-proje="${esc(p.ad)}" title="Kategoriyi değiştir">${katlar.map((k) => `<option ${k === p.kategori ? "selected" : ""}>${esc(k)}</option>`).join("")}</select>
  </div>`;
}
async function kategoriKaydet(proje, kat, oturum) {
  try { await post("kategori", oturum ? { oturum, kategori: kat } : { proje, kategori: kat }); bildir(`${oturum ? "Oturum" : proje} → ${kat}`); ciz(); }
  catch (e) { bildir(e.message, true); }
}

// ================================================================== OTURUMLAR
async function cizOturumlar(kap) {
  const v = await api("oturumlar?" + gunQ());
  let liste = v.oturumlar;
  if (D.projeFiltre) liste = liste.filter((o) => o.project === D.projeFiltre);
  if (D.katFiltre) liste = liste.filter((o) => o.category === D.katFiltre);
  if (D.arama) { const q = D.arama.toLocaleLowerCase("tr"); liste = liste.filter((o) => (o.title + " " + o.project).toLocaleLowerCase("tr").includes(q)); }
  liste.sort((a, b) => (b.acik - a.acik) || (b.end - a.end));
  if (!D.oturum || !liste.find((o) => o.id === D.oturum)) D.oturum = liste[0]?.id || null;
  kap.innerHTML = `
  <div class="bolum-baslik" style="margin-top:6px"><h2>Oturum</h2>
    <input class="arama" id="aramaKutu" placeholder="Başlık ya da proje ara…" value="${esc(D.arama)}">
    ${D.projeFiltre ? `<span class="cip">proje: <b>${esc(D.projeFiltre)}</b> <a href="#" id="projeTemizle">×</a></span>` : ""}
    <div class="filtreler">${["Hepsi", ...v.kategoriler].map((k) => `<button class="filtre ${(k === "Hepsi" && !D.katFiltre) || k === D.katFiltre ? "aktif" : ""}" data-kat="${esc(k)}">${esc(k)}</button>`).join("")}</div>
    <span class="aciklama" style="margin-left:auto">${liste.length} oturum</span>
  </div>
  <div class="oturum-secici">${liste.slice(0, 60).map((o) => `
    <button class="oturum-hap ${o.id === D.oturum ? "aktif" : ""}" data-oturum="${esc(o.id)}">
      <div class="b">${o.acik ? `<span class="durum-rozet ${esc(o.durum)}" style="margin-right:6px">${o.durum === "busy" ? "çalışıyor" : "açık"}</span>` : ""}${esc(o.title)}</div>
      <div class="m">${tarih(o.end)} · ${esc(o.project)} · ${para(o.cost)} · ${o.agents - 1} alt ajan</div>
    </button>`).join("") || `<div class="bos">Bu filtreyle oturum yok.</div>`}</div>
  <div id="oturumDetay"></div>`;
  const ak = $("#aramaKutu");
  ak.oninput = () => { clearTimeout(ak._t); ak._t = setTimeout(() => { D.arama = ak.value; D.oturum = null; cizOturumlar(kap).then(() => { const x = $("#aramaKutu"); x.focus(); x.setSelectionRange(x.value.length, x.value.length); }); }, 250); };
  kap.onclick = (e) => {
    const h = e.target.closest(".oturum-hap"); if (h) { D.oturum = h.dataset.oturum; D.ajan = "main"; $$(".oturum-hap", kap).forEach((x) => x.classList.toggle("aktif", x === h)); return detayCiz(); }
    const f = e.target.closest(".filtre[data-kat]"); if (f) { D.katFiltre = f.dataset.kat === "Hepsi" ? null : f.dataset.kat; D.oturum = null; return cizOturumlar(kap); }
    if (e.target.id === "projeTemizle") { e.preventDefault(); D.projeFiltre = null; return cizOturumlar(kap); }
  };
  if (D.oturum) await detayCiz();
}

async function detayCiz() {
  const kap = $("#oturumDetay");
  kap.innerHTML = `<div class="yukleniyor">Yükleniyor…</div>`;
  const d = await api("oturum/" + encodeURIComponent(D.oturum));
  D.veri.detay = d;
  const o = d.ozet;
  kap.innerHTML = `
  <div class="bolum-baslik"><h2>${esc(o.title)}</h2>
    <span class="aciklama">${esc(o.project)} · ${esc(o.cwd || "")}</span>
    <div class="sag"><select id="oturumKat" title="Bu oturumun kategorisi">${["Projelerim", "Oyunlar", "Uygulamalar", "Side-projects", "Sınıflanmadı"].map((k) => `<option ${k === o.category ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></div>
  </div>
  <div class="kart-izgara">
    ${metrik("API karşılığı / USD", para(o.cost), "abonelikte faturalanmaz", "vurgulu")}
    ${metrik("Ajan", o.agents, "ana oturum dahil")}
    ${metrik("Aktif süre", sure(o.active), `ilk–son kayıt: ${sure(o.duration)}`)}
    ${metrik("Model çağrısı", sayi(o.calls), `${o.prompts} emir`)}
    ${metrik("Çıktı token", tok(o.out), `girdi ${tok(o.in)}`)}
    ${metrik("Önbellekten okunan", tok(o.cr), `yazılan ${tok(o.cw)}`)}
    ${metrik("Gereksiz okuma", o.redundant, "değişmemiş dosyayı yeniden okuma", o.redundant > 20 ? "kirmizi" : "")}
    ${metrik("Hata", o.errors, "başarısız araç çağrısı", o.errors ? "kirmizi" : "")}
    ${metrik("Tekrar", o.retries, "hatadan sonra aynı çağrı")}
    ${metrik("Dosya", `${o.files_read} / ${o.files_written}`, "okunan / yazılan")}
    ${metrik("Devir", o.handoffs, "bir ajan yazdı, başkası okudu")}
    ${metrik("Sıkıştırma", o.compacts || 0, "bağlam özetlenip kısaltıldı")}
  </div>
  <div class="bolum-baslik"><div class="lejant"><span><i style="background:var(--amber)"></i>yazılan dosya</span><span><i style="background:var(--mavi)"></i>okunan dosya</span><span><i style="background:var(--cizgi2);height:2px"></i>ajan başlattı</span></div>
    <div class="sag">
      ${d.agents.length > 17 ? `<button class="kucuk-dugme" id="tumAjan">${D.tumAjanlar ? "En pahalı 16 ajan" : "Tüm " + (d.agents.length - 1) + " ajanı göster"}</button>` : ""}
      <div class="anahtar-grup" id="zoom">${[0.6, 0.85, 1].map((z) => `<button data-z="${z}" class="${z === D.zoom ? "aktif" : ""}">${Math.round(z * 100)}%</button>`).join("")}</div>
    </div>
  </div>
  <div class="iki-kolon">
    <div class="graf-kap" id="grafKap"><div class="graf-ic" id="grafIc"></div></div>
    <div class="panel panel-ic detay-panel" id="ajanPanel"></div>
  </div>`;
  $("#oturumKat").onchange = (e) => kategoriKaydet(null, e.target.value, D.oturum);
  $("#zoom").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; D.zoom = +b.dataset.z; grafCiz(d); $$("#zoom button").forEach((x) => x.classList.toggle("aktif", x === b)); };
  const ta = $("#tumAjan"); if (ta) ta.onclick = () => { D.tumAjanlar = !D.tumAjanlar; detayCiz(); };
  grafCiz(d);
  ajanPanelCiz(d);
}

function grafCiz(d) {
  const ic = $("#grafIc");
  const ana = d.agents.find((a) => a.key === "main");
  let altlar = d.agents.filter((a) => a.key !== "main").sort((a, b) => (a.first || 0) - (b.first || 0));
  if (!D.tumAjanlar && altlar.length > 16) altlar = [...altlar].sort((a, b) => b.cost - a.cost).slice(0, 16).sort((a, b) => (a.first || 0) - (b.first || 0));
  const GEN = 280, CIP = 30, MAXCIP = 5;
  const KOL = Math.max(2, Math.min(5, Math.floor((($("#grafKap").clientWidth || 1000) / D.zoom - 30) / GEN)));
  const genislik = Math.max(KOL * GEN + 40, 700);
  const parcalar = [], cizgiler = [];
  const dugum = (a, x, y, anaMi) => {
    const hataR = a.errors ? `<span class="etiket hata">${a.errors} hata</span>` : "";
    const durum = a.key === "main" ? "" : a.finished === false ? `<span class="etiket amber">sürüyor</span>` : `<span class="etiket">bitti</span>`;
    const model = Object.keys(a.models || {}).map(modelKisa).join(", ") || modelKisa(a.model_req);
    parcalar.push(`<div class="dugum ${anaMi ? "ana" : ""} ${D.ajan === a.key ? "secili" : ""}" data-ajan="${esc(a.key)}" style="left:${x}px;top:${y}px">
      <div class="b"><span class="nokta" style="background:${MODEL_RENK(model)}"></span><span class="ad" title="${esc(a.label)}">${esc(a.label)}</span>${hataR}</div>
      <div class="acik">${esc(anaMi ? "Seninle konuşan ana oturum" : a.type + (a.background ? " · arka planda" : ""))} ${durum}</div>
      <div class="m">${esc(model)}${a.effort ? " · " + esc(a.effort) : ""}<br>okuma ${a.reads} · yazma ${a.writes} · komut ${a.cmds}<br>çıktı ${tok(a.out)} · <span class="para">${para(a.cost)}</span></div>
    </div>`);
    const dosyalar = a.files || [];
    const cy0 = y + 128;
    dosyalar.slice(0, MAXCIP).forEach((f, i) => {
      const cy = cy0 + i * CIP;
      const rw = f.r && f.w ? "R+W" : f.w ? "W" : "R";
      parcalar.push(`<div class="dosya-cip" style="left:${x + 30}px;top:${cy}px;border-left-color:${f.w ? "var(--amber)" : "var(--mavi)"}" data-ip="${esc(f.path)}<br>okuma ${f.r} · yazma ${f.w}"><span class="tek-satir">${esc(dosyaAdi(f.path))}</span><span class="rw">${rw}</span></div>`);
      cizgiler.push(`<path d="M${x + 14} ${cy + 12} H${x + 30}" stroke="var(--cizgi)" stroke-width="1.2" fill="none"/>`);
    });
    const n = Math.min(dosyalar.length, MAXCIP);
    if (dosyalar.length > MAXCIP) parcalar.push(`<div class="dosya-cip daha" style="left:${x + 30}px;top:${cy0 + n * CIP}px">+${dosyalar.length - MAXCIP} dosya daha</div>`);
    const son = cy0 + (n + (dosyalar.length > MAXCIP ? 1 : 0)) * CIP;
    if (n) cizgiler.push(`<path d="M${x + 14} ${y + 120} V${cy0 + (n - 1) * CIP + 12}" stroke="var(--cizgi)" stroke-width="1.2" fill="none"/>`);
    return son;
  };
  const ax = genislik / 2 - 135, ay = 24;
  const anaSon = dugum(ana, ax, ay, true);
  const baslaY = Math.max(anaSon, ay + 150) + 70;
  let satirYuks = 0, y = baslaY, enAlt = baslaY;
  altlar.forEach((a, i) => {
    const kol = i % KOL;
    if (kol === 0 && i) { y += satirYuks + 40; satirYuks = 0; }
    const x = 20 + kol * GEN;
    const son = dugum(a, x, y, false);
    satirYuks = Math.max(satirYuks, son - y);
    enAlt = Math.max(enAlt, son);
    cizgiler.push(`<path d="M${ax + 135} ${ay + 118} C ${ax + 135} ${baslaY - 30}, ${x + 118} ${y - 50}, ${x + 118} ${y}" stroke="var(--cizgi2)" stroke-width="1.3" fill="none"/>`);
  });
  const yuk = Math.max(enAlt, anaSon) + 40;
  ic.style.width = genislik + "px";
  ic.style.height = yuk + "px";
  ic.style.transform = `scale(${D.zoom})`;
  ic.innerHTML = `<svg width="${genislik}" height="${yuk}">${cizgiler.join("")}</svg>${parcalar.join("")}`;
  ic.onclick = (e) => { const n = e.target.closest(".dugum"); if (!n) return; D.ajan = n.dataset.ajan; $$(".dugum", ic).forEach((x) => x.classList.toggle("secili", x === n)); ajanPanelCiz(d); };
}

function ajanPanelCiz(d) {
  const a = d.agents.find((x) => x.key === D.ajan) || d.agents[0];
  const p = $("#ajanPanel");
  const turler = {};
  d.timeline.filter((e) => e.a === a.key && e.k !== "prompt").forEach((e) => (turler[e.k] = (turler[e.k] || 0) + 1));
  const adimlar = d.timeline.filter((e) => e.a === a.key).slice(-160).reverse();
  p.innerHTML = `
    <div class="mini-baslik" style="margin-top:0">${a.key === "main" ? "Ana oturum" : "Alt ajan · " + esc(a.type)}</div>
    <h3>${esc(a.label)}</h3>
    ${a.desc && a.key !== "main" ? `<div class="soluk" style="font-size:13px">${esc(a.desc)}</div>` : ""}
    <div style="margin:10px 0">
      ${a.model_req ? `<span class="cip">istenen model: <b>${esc(a.model_req)}</b></span>` : ""}
      ${a.effort ? `<span class="cip">efor: <b>${esc(a.effort)}</b></span>` : ""}
      <span class="cip">API karşılığı: <b>${para(a.cost)}</b></span>
      <span class="cip">${tarih(a.first)} – ${saat(a.last)}</span>
      ${a.errors ? `<span class="cip kirmizi">${a.errors} hata</span>` : ""}
    </div>
    <div class="mini-baslik">Model ve token</div>
    <table class="tablo"><tr><th>Model</th><th class="sayi">Çağrı</th><th class="sayi">Girdi</th><th class="sayi">Çıktı</th><th class="sayi">Önbellek</th><th class="sayi">$</th></tr>
      ${Object.entries(a.models || {}).map(([m, v]) => `<tr><td>${esc(modelKisa(m))}</td><td class="sayi">${sayi(v.calls)}</td><td class="sayi">${tok(v.in)}</td><td class="sayi">${tok(v.out)}</td><td class="sayi">${tok(v.cr)}</td><td class="sayi">${para(v.cost)}</td></tr>`).join("") || `<tr><td colspan="6" class="soluk">model çağrısı yok</td></tr>`}
    </table>
    <div class="mini-baslik">Araç kullanımı</div>
    <div>${Object.entries(turler).sort((x, y) => y[1] - x[1]).map(([k, v]) => `<span class="cip">${esc(TUR_AD[k] || k)} <b>${v}</b></span>`).join("") || `<span class="soluk">—</span>`}</div>
    <div class="mini-baslik">Dosyalar (${(a.files || []).length})</div>
    <table class="tablo"><tr><th>Yol</th><th class="sayi">Okuma</th><th class="sayi">Yazma</th></tr>
      ${(a.files || []).slice(0, 40).map((f) => `<tr><td class="yol" title="${esc(f.path)}">${esc(dosyaAdi(f.path))}<div class="cok-soluk" style="font-size:10.5px">${esc(f.path)}</div></td><td class="sayi">${f.r}</td><td class="sayi">${f.w}</td></tr>`).join("") || `<tr><td colspan="3" class="soluk">dosya yok</td></tr>`}
    </table>
    <div class="mini-baslik">Zaman çizelgesi (en yeni üstte)</div>
    <div class="zaman">${adimlar.map(adimHtml).join("") || `<div class="bos">adım yok</div>`}</div>`;
}

function adimHtml(e, ajanAdi) {
  const cls = [e.k, e.err ? "err" : ""].join(" ");
  const hedef = e.k === "read" || e.k === "write" ? `<span class="yol" title="${esc(e.h)}">${esc(dosyaAdi(e.h))}</span> <span class="cok-soluk" style="font-size:11px">${esc(e.h)}</span>` : esc(e.h);
  return `<div class="adim ${cls}">
    <span class="zm">${saat(e.t)}</span>
    <span class="tur ${e.err ? "err" : e.k}">${esc(TUR_AD[e.k] || e.k)}${e.redundant ? " ↺" : ""}${e.retry ? " ⟳" : ""}</span>
    <div class="ic">${ajanAdi ? `<span class="ajan-adi">${esc(ajanAdi)}</span>` : ""}${e.k === "prompt" ? `<b>${hedef}</b>` : hedef}
      ${e.k !== "read" && e.k !== "write" && e.k !== "prompt" && e.n && !["Bash", "PowerShell"].includes(e.n) ? `<span class="cok-soluk" style="font-size:11px"> · ${esc(e.n)}</span>` : ""}
      ${e.err && e.e ? `<div class="hata-m">${esc(e.e)}</div>` : ""}</div>
  </div>`;
}

// ================================================================== GEÇMİŞ
async function cizGecmis(kap) {
  const v = await api("gecmis?saat=" + D.gecmisSaat);
  if (!D.emir || !v.akis.find((x) => x.oturum + "@" + x.t === D.emir)) D.emir = v.akis[0] ? v.akis[0].oturum + "@" + v.akis[0].t : null;
  kap.innerHTML = `
  <div class="bolum-baslik" style="margin-top:6px"><h2>Emir verip gittiğinde</h2><span class="aciklama">her emir ve ardından ajanların adım adım yaptıkları</span>
    <div class="sag"><div class="anahtar-grup" id="gecmisSaat">${[[24, "24 saat"], [48, "48 saat"], [168, "7 gün"], [720, "30 gün"]].map(([s, l]) => `<button data-s="${s}" class="${s === D.gecmisSaat ? "aktif" : ""}">${l}</button>`).join("")}</div></div></div>
  <div class="iki-kolon" style="grid-template-columns:minmax(300px,0.8fr) minmax(0,1.6fr)">
    <div class="panel" style="max-height:calc(100vh - 220px);overflow:auto">${v.akis.map((x) => `
      <div class="emir-kart ${x.oturum + "@" + x.t === D.emir ? "secili" : ""}" data-emir="${esc(x.oturum + "@" + x.t)}">
        <div class="e">${esc(x.emir)}</div>
        <div class="m">${tarih(x.t)} · ${esc(x.proje)} · ${x.adim} adım · ${sure((x.bitis || x.t) - x.t)}${x.ajan ? " · " + x.ajan + " ajan" : ""}${x.yazilan ? " · " + x.yazilan + " dosya yazıldı" : ""}${x.hata ? ` · <span style="color:var(--vurgu2)">${x.hata} hata</span>` : ""}</div>
        <div class="m cok-soluk tek-satir">${esc(x.baslik)}</div>
      </div>`).join("") || `<div class="bos">Bu aralıkta emir yok.</div>`}</div>
    <div class="panel panel-ic" id="emirDetay"></div>
  </div>`;
  $("#gecmisSaat").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; D.gecmisSaat = +b.dataset.s; D.emir = null; cizGecmis(kap); };
  kap.querySelector(".panel").onclick = (e) => { const c = e.target.closest(".emir-kart"); if (!c) return; D.emir = c.dataset.emir; $$(".emir-kart", kap).forEach((x) => x.classList.toggle("secili", x === c)); emirDetayCiz(); };
  if (D.emir) await emirDetayCiz();
}

async function emirDetayCiz() {
  const kap = $("#emirDetay");
  const [sid, ts] = D.emir.split("@");
  kap.innerHTML = `<div class="yukleniyor">Yükleniyor…</div>`;
  const d = await api("oturum/" + encodeURIComponent(sid));
  const tl = d.timeline;
  const i = tl.findIndex((e) => e.k === "prompt" && Math.abs(e.t - +ts) < 0.002);
  if (i < 0) { kap.innerHTML = `<div class="bos">Emir zaman çizelgesinde bulunamadı (çok eski olabilir).</div>`; return; }
  let j = tl.findIndex((e, k) => k > i && e.k === "prompt");
  if (j < 0) j = tl.length;
  const emir = tl[i];
  let adimlar = tl.slice(i + 1, j);
  const ajanAd = Object.fromEntries(d.agents.map((a) => [a.key, a.key === "main" ? "ana" : a.label]));
  const yazilan = [...new Set(adimlar.filter((e) => e.k === "write").map((e) => e.h))];
  const ajanlar = [...new Set(adimlar.map((e) => e.a))].filter((a) => a !== "main");
  const hatalar = adimlar.filter((e) => e.err).length;
  const fl = { hepsi: () => true, yazma: (e) => e.k === "write", komut: (e) => e.k === "command", hata: (e) => e.err, ajan: (e) => e.k === "agent" || e.k === "done", okuma: (e) => e.k === "read" };
  const goster = adimlar.filter(fl[D.adimFiltre] || fl.hepsi);
  let onceki = emir.t;
  const satirlar = [];
  goster.forEach((e) => {
    const bos = (e.t || onceki) - onceki;
    if (bos > 120) satirlar.push(`<div class="bosluk">— ${sure(bos)} sessizlik —</div>`);
    satirlar.push(adimHtml(e, e.a !== "main" ? ajanAd[e.a] : ""));
    onceki = e.t || onceki;
  });
  const son = adimlar.at(-1)?.t || emir.t;
  kap.innerHTML = `
    <div class="mini-baslik" style="margin-top:0">${tarih(emir.t)} · ${esc(d.ozet.title)}</div>
    <h3 style="font-family:inherit;font-size:16px;font-weight:600;margin:4px 0 12px;white-space:pre-wrap">${esc((d.prompts.find((p) => Math.abs(p.t - emir.t) < 0.002) || {}).x || emir.h)}</h3>
    <div class="kart-izgara" style="grid-template-columns:repeat(auto-fill,minmax(140px,1fr))">
      ${metrik("Süre", sure(son - emir.t), `${saat(emir.t)} → ${saat(son)}`)}
      ${metrik("Adım", adimlar.length, "araç çağrısı ve olay")}
      ${metrik("Alt ajan", ajanlar.length, ajanlar.slice(0, 2).map((a) => esc(ajanAd[a])).join(", "))}
      ${metrik("Yazılan dosya", yazilan.length, "")}
      ${metrik("Hata", hatalar, "", hatalar ? "kirmizi" : "")}
    </div>
    ${yazilan.length ? `<div class="mini-baslik">Yazılan dosyalar</div><div>${yazilan.slice(0, 30).map((f) => `<span class="cip" data-ip="${esc(f)}">${esc(dosyaAdi(f))}</span>`).join("")}${yazilan.length > 30 ? `<span class="cip">+${yazilan.length - 30}</span>` : ""}</div>` : ""}
    <div class="mini-baslik" style="display:flex;align-items:center;gap:10px">Adım adım
      <div class="filtreler" id="adimFiltre">${["hepsi", "yazma", "okuma", "komut", "ajan", "hata"].map((f) => `<button class="filtre ${f === D.adimFiltre ? "aktif" : ""}" data-f="${f}">${f}</button>`).join("")}</div></div>
    <div class="zaman">${satirlar.join("") || `<div class="bos">Bu filtreyle adım yok.</div>`}</div>`;
  $("#adimFiltre").onclick = (e) => { const b = e.target.closest("button"); if (!b) return; D.adimFiltre = b.dataset.f; emirDetayCiz(); };
}

// ================================================================== BANT
async function cizBant(kap) {
  const b = await api("bant?" + gunQ());
  D.veri.bant = b;
  const maxCtx = Math.max(...b.hook_ctx.map((h) => h.token), 1);
  const skillFiltre = { hepsi: () => true, kullanilmayan: (s) => s.acik && !s.kullanim && !s.kilitli, kapali: (s) => !s.acik, eklenti: (s) => s.eklenti };
  const skills = b.skills.filter(skillFiltre[D.skillFiltre]).sort((x, y) => (y.acik - x.acik) || (y.kullanim - x.kullanim) || x.ad.localeCompare(y.ad, "tr"));
  const listeTok = b.skills.filter((s) => s.acik).reduce((a, s) => a + s.liste_token, 0);
  kap.innerHTML = `
  <div class="bolum-baslik" style="margin-top:6px"><h2>Bant</h2><span class="aciklama">her oturumda kendiliğinden çalışan ya da yüklenen her şey · kapatılan silinmez, kenara alınır, tek tıkla geri gelir · değişiklik yeni oturumlarda geçerli</span></div>
  <div class="uc-kolon">
    <div class="panel panel-ic"><div class="mini-baslik" style="margin-top:0">Hook'ların eklediği bağlam (son ${b.gun || "∞"} gün)</div>
      ${b.hook_ctx.map((h) => `<div class="yatay-bar"><span>${esc(h.olay)}</span><div class="iz"><span style="width:${(h.token / maxCtx) * 100}%"></span></div><span class="s" data-ip="${h.kez} kez · ortalama ${sayi(h.ortalama)} karakter">${tok(h.token)} tk</span></div>`).join("") || `<div class="bos">—</div>`}
    </div>
    ${ozetKart("Skill", b.skills.filter((s) => s.acik).length + " açık", `${b.skills.filter((s) => !s.acik).length} kapalı · açık olanların listesi oturum başına ~${tok(listeTok)} token`)}
    ${ozetKart("Hook · MCP · Eklenti", `${b.hooks.filter((h) => h.acik).length} · ${b.mcp.filter((m) => m.acik && !m.kilitli).length} · ${b.eklentiler.filter((e) => e.acik).length}`, `${b.oturum} oturum incelendi · hafıza dosyası ${b.hafiza.length}`)}
  </div>

  <div class="bolum-baslik"><h2>Hook'lar</h2><span class="aciklama">çalışma ve hata sayısı seçili dönemin kayıtlarından</span></div>
  <div class="panel">${b.hooks.map((h) => bantSatir("hook", h.id, h.acik, h.kilitli,
    `${esc(h.ad)} <span class="etiket mor">${esc(h.olay)}</span>${h.matcher ? ` <span class="etiket">${esc(h.matcher)}</span>` : ""} <span class="etiket">${esc(h.kapsam)}</span>`,
    `<span class="yol" data-ip="${esc(h.komut)}">${esc(kisaKomut(h.komut))}</span>`,
    `<span class="cip">çalışma <b>${sayi(h.calisma)}</b></span>${h.hata ? `<span class="cip kirmizi">hata ${h.hata}</span>` : ""}${h.timeout ? `<span class="cip">${h.timeout} sn</span>` : ""}`)).join("")}</div>

  <div class="bolum-baslik"><h2>Skill'ler</h2><span class="aciklama">açık skill'lerin açıklaması her oturumun başında listelenir</span>
    <div class="sag filtreler" id="skillFiltre">${[["hepsi", "Hepsi"], ["kullanilmayan", "Kullanılmayan"], ["kapali", "Kapalı"], ["eklenti", "Eklentiden"]].map(([k, l]) => `<button class="filtre ${k === D.skillFiltre ? "aktif" : ""}" data-f="${k}">${l}</button>`).join("")}</div></div>
  <div class="panel">${skills.map((s) => bantSatir("skill", s.id, s.acik, s.kilitli,
    `${esc(s.ad)}${s.eklenti ? ` <span class="etiket mavi">eklenti</span>` : ""}${s.id.startsWith("synced:") ? ` <span class="etiket mavi">claude.ai</span>` : ""}${s.acik && !s.kullanim && !s.kilitli ? ` <span class="etiket amber">kullanılmadı</span>` : ""}`,
    esc(s.aciklama),
    `<span class="cip">kullanım <b>${s.kullanim}</b></span><span class="cip" data-ip="Her oturumun başında listelenen kısım">liste ~${s.liste_token} tk</span><span class="cip" data-ip="Skill çağrıldığında yüklenen gövde">gövde ~${tok(s.govde_token)} tk</span>${s.son ? `<span class="cip">${gorece(s.son)}</span>` : ""}`)).join("") || `<div class="bos">Bu filtreyle skill yok.</div>`}</div>

  <div class="bolum-baslik"><h2>MCP sunucuları</h2><span class="aciklama">kapatma resmi <code>claude mcp</code> komutuyla yapılır; ayar panoda saklanır</span></div>
  <div class="panel">${b.mcp.map((m) => bantSatir("mcp", m.id, m.acik, m.kilitli,
    `${esc(m.ad)} <span class="etiket">${esc(m.tur)}</span>${m.acik && !m.kullanim && !m.kilitli ? ` <span class="etiket amber">kullanılmadı</span>` : ""}`,
    `<span class="yol" style="font-size:11px">${esc(m.komut)}</span>`,
    `<span class="cip">çağrı <b>${sayi(m.kullanim)}</b></span>`)).join("")}</div>

  <div class="bolum-baslik"><h2>Eklentiler</h2></div>
  <div class="panel">${b.eklentiler.map((e) => bantSatir("eklenti", e.id, e.acik, null,
    `${esc(e.ad)} <span class="etiket">${esc(e.kaynak)}</span>${e.surum ? ` <span class="etiket">v${esc(e.surum)}</span>` : ""}`, "",
    `<span class="cip">kullanım <b>${e.kullanim}</b></span>`)).join("")}</div>

  <div class="bolum-baslik"><h2>Hafıza dosyaları</h2><span class="aciklama">ilgili klasörde açılan her oturuma otomatik yüklenir · MEMORY.md satırlarını tek tek banttan çıkarabilirsin</span></div>
  <div class="panel">${b.hafiza.map((h) => `
    ${bantSatir("hafiza", h.id, h.acik, h.kilitli,
      `<span class="yol">${esc(h.yol.replace(/^.*?\\(\.claude|Desktop|Documents)\\/, "$1\\"))}</span>${h.proje ? ` <span class="etiket">${esc(h.proje)}</span>` : ""}${h.importlar.length ? ` <span class="etiket mor">${h.importlar.map(esc).join(", ")}</span>` : ""}`,
      h.satirlar.length ? `<a href="#" data-ac-satir="${esc(h.id)}">${h.satirlar.length} hafıza satırı ▾</a>` : "",
      `<span class="cip">~<b>${sayi(h.token)}</b> tk / oturum</span>`)}
    <div class="alt-satirlar gizli" data-satirlar="${esc(h.id)}">${h.satirlar.map((s) => bantSatir("hafiza", h.id, s.acik, h.kilitli, `${esc(s.baslik)} <span class="cok-soluk yol" style="font-size:11px">${esc(s.dosya)}</span>`, esc(s.aciklama), `<span class="cip">satır ~${s.token} tk</span>${s.dosya_token ? `<span class="cip" data-ip="Not dosyası; satır kapanınca yüklenmez">not ~${tok(s.dosya_token)} tk</span>` : ""}`, s.id)).join("")}</div>`).join("")}</div>`;
  $("#skillFiltre").onclick = (e) => { const x = e.target.closest("button"); if (!x) return; D.skillFiltre = x.dataset.f; cizBant(kap); };
  kap.onclick = async (e) => {
    const ac = e.target.closest("[data-ac-satir]");
    if (ac) { e.preventDefault(); $(`[data-satirlar="${CSS.escape(ac.dataset.acSatir)}"]`, kap).classList.toggle("gizli"); return; }
    const d = e.target.closest(".dugme"); if (!d || d.disabled) return;
    const acilacak = !d.classList.contains("acik");
    const satirAd = d.closest(".bant-satir").querySelector(".b").innerText.trim().split("\n")[0];
    const ne = { hook: "hook", skill: "skill", mcp: "MCP sunucusu", eklenti: "eklenti", hafiza: d.dataset.satir ? "hafıza satırı" : "hafıza dosyası" }[d.dataset.tur];
    const aciklama = acilacak ? `Bu ${ne} yeniden açılacak; yeni oturumlarda etkin olur.` :
      `Bu ${ne} banttan çıkarılacak. Silinmez: ${d.dataset.tur === "skill" ? "klasörü <code>~/.claude/bant-kapali/</code> altına taşınır" : d.dataset.tur === "hafiza" ? "satır panoda saklanır / dosya .kapali olarak kalır" : "ayarı panoda saklanır"}. Ayar dosyasının yedeği alınır. Açık oturumlar etkilenmez; yeni oturumlarda geçerli.`;
    if (!(await onayla(`${acilacak ? "Aç" : "Kapat"}: ${satirAd}`, aciklama))) return;
    try { const r = await post("bant", { tur: d.dataset.tur, id: d.dataset.id, ac: acilacak, satir: d.dataset.satir || null }); bildir(r.mesaj); cizBant(kap); }
    catch (err) { bildir(err.message, true); }
  };
}
function kisaKomut(k) {
  const m = String(k || "").match(/[^'"\s]+\.(py|js|mjs|ps1|sh|cmd)\b/g);
  if (m) { const p = m.find((x) => !/python\.exe|node\.exe/i.test(x)) || m[0]; return p.replace(/^.*?[\\/](\.claude|Desktop|Documents)[\\/]/, "$1/").replace(/\\/g, "/"); }
  return String(k || "").slice(0, 90);
}
const ozetKart = (ad, deger, alt) => `<div class="metrik"><div class="ad">${esc(ad)}</div><div class="deger" style="font-size:26px">${deger}</div><div class="alt">${alt}</div></div>`;
function bantSatir(tur, id, acik, kilit, baslik, aciklama, olcum, satir) {
  return `<div class="bant-satir ${acik ? "" : "kapali"}">
    <button class="dugme ${acik ? "acik" : ""}" data-tur="${tur}" data-id="${esc(id)}" ${satir ? `data-satir="${esc(satir)}"` : ""} ${kilit ? `disabled data-ip="${esc(kilit)}"` : ""} aria-label="aç/kapat"></button>
    <div style="min-width:0"><div class="b">${baslik}</div>${aciklama ? `<div class="a">${aciklama}</div>` : ""}</div>
    <div class="olcum">${olcum}</div>
  </div>`;
}

// ================================================================== AJANLAR
async function cizAjanlar(kap) {
  const v = await api("ajanlar?" + gunQ());
  D.veri.ajanlar = v;
  const g = v.gozlenen, y = v.yonlendirme;
  const ajanSecenek = ["", "general-purpose", "Explore", ...v.tanimlar.filter((t) => t.acik).map((t) => t.ad)];
  const sec = (liste, deger, ad) => `<select data-alan="${ad}">${liste.map((x) => `<option value="${esc(x)}" ${x === deger ? "selected" : ""}>${esc(x || "—")}</option>`).join("")}</select>`;
  kap.innerHTML = `
  <div class="bolum-baslik" style="margin-top:6px"><h2>Alt ajanlar nasıl çalışıyor</h2></div>
  <div class="akis-semasi">
    <div class="akis-kutu"><b>1 · Ana oturum</b>Seninle konuşan oturum işi böler ve Agent aracıyla alt ajan başlatır.</div>
    <div class="akis-ok">→</div>
    <div class="akis-kutu"><b>2 · Yönlendirme tablosu</b>Ana oturum iş türüne bakar; tablodaki ajanı ya da modeli seçer. ${y.bagli ? `<span class="etiket yesil">bağlı</span>` : `<span class="etiket amber">henüz bağlı değil</span>`}</div>
    <div class="akis-ok">→</div>
    <div class="akis-kutu"><b>3 · Ajan tanımı</b><code>~/.claude/agents/ad.md</code>: model ve efor burada sabitlenir. Efor yalnız buradan kontrol edilebilir.</div>
    <div class="akis-ok">→</div>
    <div class="akis-kutu"><b>4 · Çalışma ve rapor</b>Alt ajan kendi bağlamında çalışır, dosya okur/yazar, sonunda ana oturuma rapor verir. Her adımı Oturumlar ve Geçmiş'te.</div>
  </div>

  <div class="bolum-baslik"><h2>Gözlenen kullanım</h2><span class="aciklama">${g.toplam.ajan} alt ajan · ${para(g.toplam.cost)} API karşılığı · tür, model ve efor kırılımı</span></div>
  <div class="panel"><table class="tablo"><tr><th>Tür</th><th>Model</th><th>Efor</th><th class="sayi">Adet</th><th class="sayi">Ort. süre</th><th class="sayi">Çıktı</th><th class="sayi">Hata</th><th class="sayi">Ort. $</th><th class="sayi">Toplam $</th><th>Örnek işler</th></tr>
    ${g.satirlar.map((r) => `<tr><td>${esc(r.tur)}</td><td><span style="color:${MODEL_RENK(r.model)}">${esc(modelKisa(r.model))}</span></td><td>${esc(r.effort)}</td><td class="sayi">${r.adet}</td><td class="sayi">${sure(r.ort_sure)}</td><td class="sayi">${tok(r.out)}</td><td class="sayi">${r.hata}</td><td class="sayi">${para(r.ort_cost)}</td><td class="sayi"><b>${para(r.cost)}</b></td><td class="soluk" style="font-size:12px">${r.ornek.map(esc).join(" · ")}</td></tr>`).join("") || `<tr><td colspan="10" class="bos">Bu dönemde alt ajan yok.</td></tr>`}
  </table></div>

  <div class="bolum-baslik"><h2>Yönlendirme tablosu</h2><span class="aciklama">ana oturum alt ajan başlatırken buna uyar · <code>${esc(y.md_yolu)}</code></span></div>
  <div class="panel panel-ic">
    <table class="tablo yon-tablo" id="yonTablo"><tr><th style="width:40%">İş türü</th><th>Alt ajan</th><th>Model (ajan yoksa)</th><th>Efor (bilgi)</th><th></th></tr>
      ${(y.satirlar || []).map((r) => `<tr><td><input type="text" data-alan="is" value="${esc(r.is)}"></td><td>${sec(ajanSecenek, r.ajan, "ajan")}</td><td>${sec(["", ...v.modeller], r.model, "model")}</td><td>${sec(["", ...v.eforlar], r.effort, "effort")}</td><td><button class="kucuk-dugme" data-sil>Sil</button></td></tr>`).join("")}
    </table>
    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap">
      <button class="kucuk-dugme" id="yonEkle">+ Satır</button>
      ${!(y.satirlar || []).length ? `<button class="kucuk-dugme" id="yonOneri" data-ip="Ekrana ekler; Kaydet'e basana kadar hiçbir dosyaya yazılmaz">Önerilen satırları ekle</button><span class="cok-soluk" style="font-size:12px">Tablo henüz boş; ana oturum modeli kendisi seçiyor.</span>` : ""}
      <span class="soluk" style="margin-left:12px">Varsayılan alt ajan modeli</span>
      <select id="varsayilanModel">${["", "haiku", "sonnet", "opus", "fable"].map((m) => `<option value="${m}" ${m === (y.varsayilan_model || "") ? "selected" : ""}>${m || "ana ajan seçsin"}</option>`).join("")}</select>
      <span style="margin-left:auto"></span>
      ${y.bagli ? `<button class="kucuk-dugme" id="yonKopar">CLAUDE.md'den çıkar</button>` : ""}
      <button class="ana-dugme" id="yonKaydet">Kaydet ${y.bagli ? "" : "ve bağla"}</button>
    </div>
    <div class="cok-soluk" style="font-size:12px;margin-top:8px">Efor sütunu ajan tanımındaki eforu hatırlatır; eforu değiştirmek için aşağıdaki ajan kartını düzenle. "Ana ajan seçsin" iken model, ana oturumun Agent çağrısındaki seçimdir.</div>
  </div>

  <div class="bolum-baslik"><h2>Özel ajanlar</h2><span class="aciklama"><code>~/.claude/agents/</code> · model ve efor burada sabitlenir</span>
    <div class="sag">${v.onerilen.some((o) => !v.tanimlar.find((t) => t.ad === o.ad)) ? `<button class="kucuk-dugme" id="onerilenKur">Önerilen 3 ajanı kur</button>` : ""}<button class="kucuk-dugme" id="yeniAjan">+ Yeni ajan</button></div></div>
  <div class="uc-kolon" id="tanimlar">${v.tanimlar.map((t) => tanimKart(t, v)).join("") || `<div class="bos">Henüz özel ajan yok. "Önerilen 3 ajanı kur" ile hızlı (Sonnet), derin (Opus) ve toplu veri (Haiku) ajanlarını ekleyebilirsin.</div>`}</div>`;

  const yt = $("#yonTablo");
  $("#yonEkle").onclick = () => {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><input type="text" data-alan="is" placeholder="ör. Godot test ve derleme"></td><td>${sec(ajanSecenek, "", "ajan")}</td><td>${sec(["", ...v.modeller], "", "model")}</td><td>${sec(["", ...v.eforlar], "", "effort")}</td><td><button class="kucuk-dugme" data-sil>Sil</button></td>`;
    yt.appendChild(tr);
  };
  yt.onclick = (e) => { if (e.target.dataset.sil != null) e.target.closest("tr").remove(); };
  const yo = $("#yonOneri");
  if (yo) yo.onclick = () => {
    (y.oneri_satirlar || []).forEach((r) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><input type="text" data-alan="is" value="${esc(r.is)}"></td><td>${sec([...new Set([...ajanSecenek, r.ajan])], r.ajan, "ajan")}</td><td>${sec(["", ...v.modeller], r.model, "model")}</td><td>${sec(["", ...v.eforlar], r.effort, "effort")}</td><td><button class="kucuk-dugme" data-sil>Sil</button></td>`;
      yt.appendChild(tr);
    });
    yo.remove();
    bildir("Önerilen satırlar eklendi; kaydedene kadar hiçbir yere yazılmadı");
  };
  $("#yonKaydet").onclick = async () => {
    const satirlar = $$("tr", yt).slice(1).map((tr) => Object.fromEntries($$("[data-alan]", tr).map((el) => [el.dataset.alan, el.value.trim()])));
    const varsayilan = $("#varsayilanModel").value;
    if (!(await onayla("Yönlendirmeyi kaydet", `Tablo <code>~/.claude/bant-yonlendirme.md</code> dosyasına yazılır${y.bagli ? "" : " ve <code>~/.claude/CLAUDE.md</code> sonuna <code>@bant-yonlendirme.md</code> satırı eklenir (yedek alınır)"}. ${varsayilan !== (y.varsayilan_model || "") ? `Varsayılan alt ajan modeli <b>${esc(varsayilan || "kaldırılacak")}</b> olarak settings.json'a yazılır.` : ""} Yeni oturumlarda geçerli.`))) return;
    try { const r = await post("yonlendirme", { satirlar, varsayilan_model: varsayilan, bagla: true }); bildir(r.mesaj); cizAjanlar(kap); } catch (err) { bildir(err.message, true); }
  };
  const kop = $("#yonKopar");
  if (kop) kop.onclick = async () => { if (!(await onayla("Bağlantıyı kopar", "CLAUDE.md'deki <code>@bant-yonlendirme.md</code> satırı kaldırılır; tablo dosyası durur."))) return; try { bildir((await post("yonlendirme/kopar")).mesaj); cizAjanlar(kap); } catch (err) { bildir(err.message, true); } };
  const ok = $("#onerilenKur");
  if (ok) ok.onclick = async () => { if (!(await onayla("Önerilen ajanları kur", v.onerilen.map((o) => `<b>${o.ad}</b> · ${o.model} / ${o.effort}<br><span class="cok-soluk">${esc(o.aciklama)}</span>`).join("<br><br>")))) return; try { bildir((await post("ajan/onerilenler")).mesaj); cizAjanlar(kap); } catch (err) { bildir(err.message, true); } };
  $("#yeniAjan").onclick = () => { const k = $("#tanimlar"); if (k.querySelector(".bos")) k.innerHTML = ""; k.insertAdjacentHTML("afterbegin", tanimKart({ ad: "", aciklama: "", model: "sonnet", effort: "medium", govde: "", acik: true, yeni: true }, v)); };
  $("#tanimlar").onclick = async (e) => {
    const kart = e.target.closest(".tanim-kart"); if (!kart) return;
    const al = (n) => kart.querySelector(`[data-t="${n}"]`).value.trim();
    if (e.target.dataset.kaydet != null) {
      try { const r = await post("ajan/kaydet", { ad: al("ad"), aciklama: al("aciklama"), model: al("model"), effort: al("effort"), govde: al("govde") }); bildir(r.mesaj); cizAjanlar(kap); } catch (err) { bildir(err.message, true); }
    }
    if (e.target.dataset.durum != null) {
      const ac = e.target.dataset.durum === "ac";
      if (!(await onayla(`${ac ? "Aç" : "Kapat"}: ${kart.dataset.ad}`, ac ? "Ajan tanımı geri yüklenir." : "Tanım dosyası <code>~/.claude/bant-kapali/agents/</code> altına taşınır; ana oturum bu ajanı artık seçemez."))) return;
      try { bildir((await post("ajan/degistir", { ad: kart.dataset.ad, ac })).mesaj); cizAjanlar(kap); } catch (err) { bildir(err.message, true); }
    }
  };
}
function tanimKart(t, v) {
  const sec = (liste, deger, ad) => `<select data-t="${ad}">${liste.map((x) => `<option value="${esc(x)}" ${x === deger ? "selected" : ""}>${esc(x || "—")}</option>`).join("")}</select>`;
  return `<div class="tanim-kart" data-ad="${esc(t.ad)}" style="${t.acik ? "" : "opacity:.6"}">
    <div class="ust"><b>${t.yeni ? "Yeni ajan" : esc(t.ad)}</b>${t.yeni ? "" : t.acik ? `<button class="kucuk-dugme" data-durum="kapat">Kapat</button>` : `<button class="kucuk-dugme" data-durum="ac">Aç</button>`}</div>
    <div class="form-satir"><label>Ad</label><input type="text" data-t="ad" value="${esc(t.ad)}" ${t.yeni ? "" : "readonly"} placeholder="kucuk-harf-tire"></div>
    <div class="form-satir"><label>Model</label>${sec(v.modeller, t.model || "inherit", "model")}</div>
    <div class="form-satir"><label>Efor</label>${sec(["", ...v.eforlar], t.effort || "", "effort")}</div>
    <div class="form-satir" style="align-items:start"><label>Ne zaman</label><textarea data-t="aciklama" style="min-height:60px" placeholder="Ana oturum bu ajanı ne zaman seçmeli?">${esc(t.aciklama)}</textarea></div>
    <details style="margin-top:8px"><summary class="soluk" style="cursor:pointer;font-size:12.5px">Sistem talimatı</summary><textarea data-t="govde" style="margin-top:6px">${esc(t.govde)}</textarea></details>
    <div style="display:flex;justify-content:flex-end;margin-top:10px"><button class="ana-dugme" data-kaydet>Kaydet</button></div>
  </div>`;
}

// ================================================================== ÖNERİLER
async function cizOneriler(kap) {
  const o = await api("oneriler?" + gunQ());
  rozetGuncelle(o);
  kap.innerHTML = `
  <div class="bolum-baslik" style="margin-top:6px"><h2>Token azaltma önerileri</h2><span class="aciklama">${o.oturum} oturum · ${sayi(o.toplam_cagri)} model çağrısı · ${para(o.toplam_cost)} API karşılığı · kural tabanlı, model çağırmaz, veri göndermez</span></div>
  ${o.oneriler.map(oneriHtml).join("") || `<div class="bos">Şimdilik öneri yok; her şey yerli yerinde.</div>`}`;
  kap.onclick = (e) => { const g = e.target.closest("[data-git]"); if (g) oneriGit(g.dataset.git); };
}
function oneriHtml(x) {
  const hedef = x.hedef?.sekme;
  return `<div class="oneri o${x.oncelik}"><div class="serit-dik"></div>
    <div class="ic"><h4>${esc(x.baslik)}</h4><div class="n">${esc(x.neden)}</div><div class="eylem"><b>Ne yapılır:</b> ${esc(x.eylem)}</div>
      ${x.kanit?.length ? `<details><summary>Ayrıntı (${x.kanit.length})</summary>${x.kanit.map((k) => `<div>· ${esc(k)}</div>`).join("")}</details>` : ""}</div>
    <div class="tasarruf"><div class="mini-baslik">Kazanç</div><div class="d">${esc(x.tasarruf)}</div>
      ${hedef ? `<button class="kucuk-dugme" style="margin-top:10px" data-git="${esc(hedef)}${x.hedef.filtre ? ":" + esc(x.hedef.filtre) : ""}">${{ bant: "Bant'a git", ajanlar: "Ajanlar'a git", oturumlar: "Oturumlara git", gecmis: "Geçmiş'e git" }[hedef] || "Git"} →</button>` : ""}</div>
  </div>`;
}
function oneriGit(h) {
  const [s, f] = h.split(":");
  if (s === "bant" && f) D.skillFiltre = f;
  if (s === "gecmis" && f === "hata") D.adimFiltre = "hata";
  sekmeAc(s);
}

// ------------------------------------------------------------------ başlat
(function baslat() {
  try {
    const t = localStorage.getItem("bant.tema"); if (t === "acik" || t === "koyu") { document.documentElement.dataset.tema = t; $$("#tema button").forEach((x) => x.classList.toggle("aktif", x.dataset.tema === t)); }
    const s = localStorage.getItem("bant.sekme"); if (s && $("#s-" + s)) D.sekme = s;
  } catch { }
  // Adres çubuğundan doğrudan sekme ve tema: ?sekme=oturumlar&tema=acik
  const q = new URLSearchParams(location.search);
  if (q.get("sekme") && $("#s-" + q.get("sekme"))) D.sekme = q.get("sekme");
  const qt = q.get("tema");
  if (qt === "acik" || qt === "koyu") { document.documentElement.dataset.tema = qt; $$("#tema button").forEach((x) => x.classList.toggle("aktif", x.dataset.tema === qt)); }
  durumYokla();
  sekmeAc(D.sekme);
})();


// ------------------------------------------------------------------ yumuşak alan grafiği (monoton kübik eğri)
function alanGrafik(nok, yuk = 140) {
  if (!nok.length) return `<div class="bos">Veri yok</div>`;
  const W = 1000, H = yuk, P = 6;
  const max = Math.max(...nok.map((n) => n.y), 1e-9);
  const xs = nok.map((_, i) => (nok.length === 1 ? W / 2 : P + (i / (nok.length - 1)) * (W - 2 * P)));
  const ys = nok.map((n) => H - 4 - (n.y / max) * (H - 18));
  // Fritsch–Carlson monoton eğim
  const n = xs.length, d = [], m = [];
  for (let i = 0; i < n - 1; i++) d.push((ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i] || 1));
  for (let i = 0; i < n; i++) m.push(i === 0 ? d[0] || 0 : i === n - 1 ? d[n - 2] || 0 : d[i - 1] * d[i] <= 0 ? 0 : (d[i - 1] + d[i]) / 2);
  let yol = `M${xs[0]},${ys[0]}`;
  for (let i = 0; i < n - 1; i++) {
    const h = (xs[i + 1] - xs[i]) / 3;
    yol += ` C${xs[i] + h},${ys[i] + m[i] * h} ${xs[i + 1] - h},${ys[i + 1] - m[i + 1] * h} ${xs[i + 1]},${ys[i + 1]}`;
  }
  const alan = `${yol} L${xs[n - 1]},${H} L${xs[0]},${H} Z`;
  const id = "g" + Math.random().toString(36).slice(2, 8);
  const genis = W / Math.max(1, n);
  return `<svg class="alan-grafik" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:${H}px;display:block">
    <defs><linearGradient id="${id}" x1="0" x2="0" y1="0" y2="1"><stop offset="0" style="stop-color:var(--vurgu);stop-opacity:.34"/><stop offset="1" style="stop-color:var(--vurgu);stop-opacity:0"/></linearGradient></defs>
    ${[0.25, 0.5, 0.75].map((f) => `<line x1="0" x2="${W}" y1="${H * f}" y2="${H * f}" style="stroke:var(--cizgi)" stroke-width="1" vector-effect="non-scaling-stroke"/>`).join("")}
    <path d="${alan}" fill="url(#${id})"/>
    <path d="${yol}" fill="none" style="stroke:var(--vurgu)" stroke-width="2" vector-effect="non-scaling-stroke" class="alan-cizgi"/>
    ${xs.map((x, i) => `<rect x="${x - genis / 2}" y="0" width="${genis}" height="${H}" fill="transparent" data-ip="${nok[i].ip}" class="alan-hedef"/><circle cx="${x}" cy="${ys[i]}" r="3" class="alan-nokta" vector-effect="non-scaling-stroke"/>`).join("")}
  </svg>`;
}
