/* Miso — cookbook search, cook mode, shopping list, meal plan. Vanilla JS, no build step. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const app = $("#app");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const api = async (path, opts) => (await fetch(path, opts)).json();
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const uid = () => Math.random().toString(36).slice(2, 10);

const ICON = {
  search: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
  star: (on) => `<svg width="16" height="16" viewBox="0 0 24 24" fill="${on ? "currentColor" : "none"}" stroke="currentColor" stroke-width="1.8"><path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/></svg>`,
  cart: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 4h2l2.4 11h11L21 7H6.2"/><circle cx="9" cy="20" r="1.4"/><circle cx="18" cy="20" r="1.4"/></svg>',
  cal: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
  sun: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  x: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  back: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m15 18-6-6 6-6"/></svg>',
};

/* ------------------------------------------------------------------ persisted state */

let S = {
  favorites: [], recent: [], list: [], plan: {}, progress: {}, cooked: {}, notes: {}, tags: {}, ratings: {}, combos: {},
  settings: { theme: "auto", mealTimes: { Breakfast: "08:00", Lunch: "12:30", Dinner: "18:00", Snack: "15:30" }, mealMinutes: 60 },
};
async function loadState() {
  try {
    const d = await api("/api/state");
    S = { ...S, ...d, settings: { ...S.settings, ...(d.settings || {}), mealTimes: { ...S.settings.mealTimes, ...((d.settings || {}).mealTimes || {}) } } };
  } catch (e) { /* first run */ }
  applyTheme();
  updateBadge();
}
const save = debounce(() => post("/api/state", S), 400);
function commit() { save(); updateBadge(); }
function updateBadge() {
  const n = S.list.filter((i) => !i.done).length;
  const b = $("#listCount");
  b.textContent = n;
  b.hidden = !n;
}
function applyTheme() {
  const t = S.settings.theme;
  if (t === "auto") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && !location.hash.startsWith("#/r/")) loadState();
});

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast.t);
  toast.t = setTimeout(() => (t.hidden = true), 2400);
}

/* ------------------------------------------------------------------ modal */

const modal = $("#modal");
function openModal(html, onMount) {
  $("#modalBody").innerHTML = `<div class="m">${html}</div>`;
  modal.showModal();
  onMount && onMount($("#modalBody"));
}
function closeModal() { modal.close(); }
modal.addEventListener("click", (e) => { if (e.target === modal) closeModal(); });

/* ------------------------------------------------------------------ cards */

// live recipe websites Miso can search (keys match web.SITES on the server)
const WEB_SITES = [["nyt", "NYT Cooking"], ["ew", "EatingWell"], ["lal", "Love & Lemons"], ["st", "Skinnytaste"], ["ytf", "Yummy Toddler Food"]];
const WEB_NAME = Object.fromEntries(WEB_SITES);
const SITE_CLASS = { "NYT Cooking": "site-nyt", EatingWell: "site-ew", "Love & Lemons": "site-lal", Skinnytaste: "site-st", "Yummy Toddler Food": "site-ytf" };
function sitePh(site) { return `<div class="site-ph ${SITE_CLASS[site] || "site-nyt"}">${esc(site || "Web")}</div>`; }
function coverImg(c, cls = "cover") {
  return c.cover ? `<img class="${cls}" src="${esc(c.cover)}" alt="" loading="lazy">` : `<div class="cover-ph">${esc(c.bookTitle || "")}</div>`;
}
function cardData(r) {   // compact copy we can store in favourites / plan without a server lookup
  return r.source === "book"
    ? { id: r.id, title: r.title, source: "book", bookTitle: r.bookInfo?.title || r.bookTitle, cover: r.bookInfo?.cover || r.cover, image: r.images?.[0] || r.image || null }
    : { id: r.id, title: r.title, source: "web", site: r.site, image: r.image, author: r.author, rating: r.rating?.value, ratingCount: r.rating?.count };
}
const fmtMin = (m, est) => !m ? "" : (est ? "~" : "") + (m >= 60 ? `${Math.floor(m / 60)} hr${m % 60 ? " " + (m % 60) + " min" : ""}` : `${m} min`);
function card(c, extra = "") {
  const left = c.source === "book"
    ? (c.image ? `<span class="ph"><img class="photo" src="${esc(c.image)}" alt="" loading="lazy">${c.cover ? `<img class="mini" src="${esc(c.cover)}" alt="" title="${esc(c.bookTitle)}" loading="lazy">` : ""}</span>` : coverImg(c))
    : c.image ? `<img class="photo" src="${esc(c.image)}" alt="" loading="lazy">` : sitePh(c.site);
  const src = c.source === "book" ? `${esc(c.bookTitle)}` : `${esc(c.site || "")}${c.author ? ` <em>· ${esc(c.author)}</em>` : ""}${c.byline && !c.author ? ` <em>· ${esc(c.byline)}</em>` : ""}`;
  const match = c.matched ? `<span class="pill ok">uses ${c.matched.length} of ${c.of}</span>` : "";
  const time = c.time ? `<div class="snip">${esc(c.time)}</div>` : "";
  // your own stars win over the site's rating
  const mine = (c.id && S.ratings[c.id]) || c.myRating;
  const stars = mine
    ? `<span class="stars mine" title="Your rating">${"★".repeat(mine)}</span>`
    : c.rating ? `<span class="stars" title="${c.rating} out of 5${c.ratingCount ? ` · ${c.ratingCount.toLocaleString()} ratings` : ""}">★ ${(+c.rating).toFixed(1)}${c.ratingCount ? ` <em>(${c.ratingCount.toLocaleString()})</em>` : ""}</span>` : "";
  const tags = (c.id && S.tags[c.id]) || c.tags || [];
  const foot = (c.minutes || tags.length)
    ? `<div class="foot">${c.minutes ? `<span class="tm" title="${c.est ? "Estimated from the steps" : "From the recipe"}">⏱ ${fmtMin(c.minutes, c.est)}</span>` : ""}${tags.map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>` : "";
  return `<button class="card" data-id="${esc(c.id || "")}" data-url="${esc(c.url || "")}">
      ${left}
      <div class="body"><h3>${esc(c.title)}${match}</h3><div class="src">${src}${stars ? " " + stars : ""}</div>${c.snippet ? `<div class="snip">${esc(c.snippet)}</div>` : time}${foot}</div>
      ${extra}
    </button>`;
}
function bindCards(root, onWeb) {
  $$(".card", root).forEach((el) => el.addEventListener("click", () => {
    if (el.dataset.id) location.hash = "#/r/" + encodeURIComponent(el.dataset.id);
    else if (el.dataset.url && onWeb) onWeb(el.dataset.url, el);
  }));
}

async function importUrl(url, el) {
  if (el) el.querySelector(".body h3").insertAdjacentHTML("beforeend", ' <span class="spin"></span>');
  const r = await post("/api/web/import", { url });
  if (r.id) { location.hash = "#/r/" + encodeURIComponent(r.id); return; }
  el?.querySelector(".spin")?.remove();
  if (r.blocked) {
    openModal(`<h2>${esc(r.site)} needs your browser</h2>
      <p class="sub">That site blocks apps from reading its pages. Open the recipe, then click your <b>Save to Miso</b> bookmark. <button class="link" onclick="bookmarkletModal()">Set up the bookmark</button></p>
      <div class="row"><button class="btn" onclick="closeModal()">Cancel</button><a class="btn primary" href="${esc(url)}" target="_blank" rel="noopener">Open recipe</a></div>`);
  } else toast(r.error || "Couldn't import that page");
}

/* ------------------------------------------------------------------ search view */

const EMPTY_F = () => ({ course: [], protein: [], diet: [], method: [], book: [], tag: [] });
const SEARCH = { q: "", mode: "all", f: EMPTY_F(), maxtime: "", rating: "", with: "", without: "", sort: "relevance", shown: 48 };
const MODES = [
  ["all", "Everything"], ["books", "My cookbooks"], ["web", "Saved from websites"],
  ...WEB_SITES,
];
const GROUP_LABEL = { course: "Course", protein: "Protein", diet: "Diet", method: "Method", book: "Source", tag: "My tags" };
const SORTS = [["relevance", "Best match"], ["rating", "Top rated"], ["time", "Quickest"], ["ingredients", "Fewest ingredients"], ["title", "A–Z"], ["random", "Surprise me"]];
const DEFAULT_TAGS = ["Kid-approved", "Weeknight", "Make again", "Company-worthy", "Freezer-friendly", "Want to try", "Meal prep"];
let LIB = null;
let FACETS = {};
async function getLibrary(force) {
  if (!LIB || force) LIB = await api("/api/library");
  return LIB;
}
const isWebMode = () => SEARCH.mode in WEB_NAME;
const hasFilters = () => Object.values(SEARCH.f).some((v) => v.length) || SEARCH.maxtime || SEARCH.rating || SEARCH.with.trim() || SEARCH.without.trim();
function allTags() { return [...new Set([...Object.values(S.tags).flat(), ...DEFAULT_TAGS])].sort((a, b) => a.localeCompare(b)); }
function usedTags() { const c = {}; Object.values(S.tags).flat().forEach((t) => (c[t] = (c[t] || 0) + 1)); return c; }

function searchQS() {
  // Everything shows a short list of your recipes so the live web results stay in view
  const limit = SEARCH.mode === "all" && SEARCH.q.trim() ? SEARCH.shown - 36 : SEARCH.shown;
  const p = new URLSearchParams({ mode: SEARCH.mode, q: SEARCH.q.trim(), sort: SEARCH.sort, limit });
  Object.entries(SEARCH.f).forEach(([g, v]) => v.length && p.set(g, v.join("|")));
  if (SEARCH.maxtime) p.set("maxtime", SEARCH.maxtime);
  if (SEARCH.rating) p.set("rating", SEARCH.rating);
  if (SEARCH.with.trim()) p.set("with", SEARCH.with);
  if (SEARCH.without.trim()) p.set("without", SEARCH.without);
  return p.toString();
}

function webQS(site, val) {
  const p = new URLSearchParams(searchQS());
  ["mode", "limit"].forEach((k) => p.delete(k));
  p.set("site", site);
  p.set("q", val);
  if (p.get("sort") === "relevance") p.delete("sort");
  return p.toString();
}
const webFiltering = () => hasFilters() || ["rating", "time", "ingredients"].includes(SEARCH.sort);

async function viewSearch() {
  const lib = await getLibrary(true);
  if (!MODES.some(([k]) => k === SEARCH.mode)) SEARCH.mode = "all";
  const placeholder = {
    ...Object.fromEntries(WEB_SITES.map(([k, n]) => [k, `Search ${n}`])),
  }[SEARCH.mode] || "Search recipes, ingredients, tags — or paste a recipe link";
  app.innerHTML = `
    <section class="hero">
      <h1>What are we cooking?</h1>
      <p>${lib.recipes.toLocaleString()} recipes across ${lib.books.length} cookbooks${lib.status.state === "indexing" ? ` <span class="spin"></span> indexing ${lib.status.done}/${lib.status.total}` : ""}</p>
      <div class="searchbox">${ICON.search}<input id="q" type="search" autocomplete="off" placeholder="${esc(placeholder)}" value="${esc(SEARCH.q)}" autofocus></div>
      <div class="chips">${MODES.map(([k, l]) => `<button class="chip ${SEARCH.mode === k ? "on" : ""}" data-mode="${k}">${l}</button>`).join("")}</div>
    </section>
    <div id="fbar"></div>
    <div id="res"></div>`;
  const q = $("#q");
  $$(".chip[data-mode]").forEach((c) => c.addEventListener("click", () => { SEARCH.mode = c.dataset.mode; SEARCH.shown = 48; viewSearch(); }));
  q.addEventListener("input", debounce(() => { SEARCH.q = q.value; SEARCH.shown = 48; !isWebMode() && runSearch(); }, 160));
  q.addEventListener("input", debounce(() => { SEARCH.q = q.value; isWebMode() && runSearch(); }, 700));
  q.addEventListener("keydown", (e) => { if (e.key === "Enter") { SEARCH.q = q.value; runSearch(); } });
  runSearch();
  if (lib.status.state === "indexing") pollIndex(() => location.hash.replace(/^#\/?$/, "") === "" && $("#q") && !$("#q").value && !hasFilters() && viewSearch());
}

let searchSeq = 0;
async function runSearch() {
  const res = $("#res"), fbar = $("#fbar");
  if (!res) return;
  const val = SEARCH.q.trim();
  const seq = ++searchSeq;
  if (/^https?:\/\//i.test(val)) {
    fbar.innerHTML = "";
    res.innerHTML = `<div class="results">${card({ title: "Import this recipe", url: val, source: "web", site: new URL(val).hostname.replace("www.", ""), snippet: val })}</div>`;
    return bindCards(res, importUrl);
  }
  if (isWebMode()) {
    if (!val) { fbar.innerHTML = ""; res.innerHTML = `<p class="empty">Type what you're craving and press Enter.</p>`; return; }
    renderFilterBar();
    res.innerHTML = `<p class="empty"><span class="spin"></span>${webFiltering() ? " Checking each recipe against your filters…" : ""}</p>`;
    const data = await api(`/api/web/search?${webQS(SEARCH.mode, val)}`);
    if (seq !== searchSeq) return;
    noteCombo();
    if (data.error) { res.innerHTML = `<p class="empty">${esc(data.message || `Couldn't reach ${WEB_NAME[SEARCH.mode]} right now. Try again in a few minutes.`)}</p>`; return; }
    const results = data.results || [];
    FACETS = data.facets || {};       // counts only exist when filters ran on this site
    renderFilterBar();
    const head = data.total != null ? `<div class="result-head"><b>${data.total}</b> ${data.total === 1 ? "recipe matches" : "recipes match"} your filters on ${esc(WEB_NAME[SEARCH.mode])}</div>` : "";
    res.innerHTML = head + (results.length
      ? `<p class="hint">${SEARCH.mode === "ytf" ? "Yummy Toddler Food only lets your own browser read its recipes: tap one to open it, then use your <b>Save to Miso</b> bookmark (<button class=\'link\' id=\'bmHint\'>set it up</button>)." : "Tap a recipe to import it into Miso — it'll be searchable (and filterable) offline next time."}</p><div class="results">${results.map((r) => card({ ...r, source: "web", snippet: r.time || "" })).join("")}</div>`
      : `<p class="empty">Nothing ${webFiltering() ? "matching your filters " : ""}found on ${esc(WEB_NAME[SEARCH.mode])}.${hasFilters() ? ` <button class="link" id="clr3">Clear filters</button>` : ""}</p>`);
    $("#clr3")?.addEventListener("click", clearFilters);
    $("#bmHint")?.addEventListener("click", bookmarkletModal);
    return bindCards(res, importUrl);
  }
  if (!val && !hasFilters()) { renderFilterBar(); return renderHome(res); }
  const data = await api("/api/search?" + searchQS());
  if (seq !== searchSeq) return;
  noteCombo();
  FACETS = data.facets || {};
  renderFilterBar();
  const more = data.total > data.results.length;
  res.innerHTML = `<div class="result-head"><b>${data.total.toLocaleString()}</b> ${data.total === 1 ? "recipe" : "recipes"}${SEARCH.mode === "all" && val ? " in your cookbooks & saved recipes · recipe sites below" : ""}</div>` + (data.results.length
    ? `<div class="results">${data.results.map((c) => card(c)).join("")}</div>${more ? `<p style="text-align:center;margin-top:18px"><button class="btn" id="more">Show more from your cookbooks (${(data.total - data.results.length).toLocaleString()})</button></p>` : ""}`
    : `<p class="empty">${SEARCH.mode === "all" && val ? "Nothing in your cookbooks matches." : "Nothing matches."}${hasFilters() ? ` <button class="link" id="clr2">Clear filters</button>` : ""}${val && SEARCH.mode !== "nyt" && SEARCH.mode !== "all" ? ` <button class="link" id="tryNyt">Try NYT Cooking →</button>` : ""}</p>`);
  if (SEARCH.mode === "all" && val) {
    res.insertAdjacentHTML("beforeend", `<div id="webres"></div>`);
    liveWeb(val, seq);
  }
  $("#more")?.addEventListener("click", () => { SEARCH.shown += 48; const y = scrollY; runSearch().then(() => scrollTo(0, y)); });
  $("#tryNyt")?.addEventListener("click", () => { SEARCH.mode = "nyt"; viewSearch(); });
  $("#clr2")?.addEventListener("click", clearFilters);
  bindCards(res);
}
// Everything = your cookbooks + saved recipes + live NYT Cooking & EatingWell results
const WEB_CACHE = {};
let webTimer;
function liveWeb(val, seq) {
  clearTimeout(webTimer);
  const draw = () => {
    const box = $("#webres");
    if (!box || seq !== searchSeq) return;
    const sec = (site, label) => {
      const r = WEB_CACHE[webQS(site, val)];
      if (r === undefined) return `<div class="section-title"><h2>From ${label}</h2><span class="spin"></span></div>`;
      if (r.error) return `<div class="section-title"><h2>From ${label}</h2><span class="status">${esc(r.message || "couldn't be searched right now")}</span></div>`;
      if (!r.length && webFiltering()) return `<div class="section-title"><h2>From ${label}</h2><span class="status">nothing matches your filters</span></div>`;
      if (!r.length) return "";
      return `<div class="section-title"><h2>From ${label}</h2><button data-see="${site}">See all ${r.length} →</button></div>
        <div class="results">${r.slice(0, 6).map((x) => card({ ...x, source: "web", snippet: x.time || "" })).join("")}</div>`;
    };
    box.innerHTML = WEB_SITES.map(([k, n]) => sec(k, n)).join("")
      + (hasFilters() ? `<p class="hint">Filters apply to these sites too. Yummy Toddler Food only shares its own labels (like Breakfast or Dairy-Free), so time, rating and ingredient filters can't check its recipes.</p>` : "");
    bindCards(box, importUrl);
    $$("[data-see]", box).forEach((b) => b.addEventListener("click", () => { SEARCH.mode = b.dataset.see; viewSearch(); }));
  };
  draw();
  webTimer = setTimeout(() => {
    WEB_SITES.forEach(async ([site]) => {
      const key = webQS(site, val);
      if (WEB_CACHE[key] === undefined) {
        let failed = false;
        try {
          const r = await api(`/api/web/search?${key}`);
          WEB_CACHE[key] = r.error ? { error: true, message: r.message } : (r.results || []);
          failed = !!r.error;
        } catch (e) { WEB_CACHE[key] = { error: true }; failed = true; }
        draw();
        if (failed) delete WEB_CACHE[key];   // a site that timed out gets another try next search
        return;
      }
      draw();
    });
  }, 500);
}

// ---- remember filter combinations you settle on, to offer them under Browse
const ratingLabel = (r) => r === "mine" ? "Rated by me" : r === "5" ? "★ 5" : `★ ${r}+`;
function currentCombo() {
  const f = {};
  Object.entries(SEARCH.f).forEach(([g, v]) => v.length && (f[g] = [...v].sort()));
  const c = { f };
  if (SEARCH.maxtime) c.maxtime = SEARCH.maxtime;
  if (SEARCH.rating) c.rating = SEARCH.rating;
  if (SEARCH.with.trim()) c.with = SEARCH.with.trim().toLowerCase();
  if (SEARCH.without.trim()) c.without = SEARCH.without.trim().toLowerCase();
  return c;
}
const comboKey = (c) => JSON.stringify([Object.keys(c.f).sort().map((g) => [g, c.f[g]]), c.maxtime || "", c.rating || "", c.with || "", c.without || ""]);
function comboLabel(c) {
  const parts = [];
  if (c.rating) parts.push(ratingLabel(c.rating));
  if (c.maxtime) parts.push(`≤ ${c.maxtime} min`);
  ["course", "protein", "diet", "method"].forEach((g) => (c.f[g] || []).forEach((v) => parts.push(v)));
  (c.f.tag || []).forEach((t) => parts.push("#" + t));
  (c.f.book || []).forEach((b) => parts.push(facetLabel("book", b)));
  if (c.with) parts.push("with " + c.with);
  if (c.without) parts.push("no " + c.without);
  return parts.join(" · ");
}
let comboTimer;
function noteCombo() {
  clearTimeout(comboTimer);
  if (!hasFilters()) return;
  const c = currentCombo(), key = comboKey(c);
  comboTimer = setTimeout(() => {          // only count combinations you actually stay on
    if (comboKey(currentCombo()) !== key) return;
    const prev = S.combos[key] || { n: 0 };
    S.combos[key] = { ...c, n: prev.n + 1, last: Date.now() };
    const keys = Object.keys(S.combos);
    if (keys.length > 40) {                  // keep the list small: drop the least used
      keys.sort((a, b) => S.combos[a].n - S.combos[b].n || S.combos[a].last - S.combos[b].last).slice(0, keys.length - 40).forEach((k) => delete S.combos[k]);
    }
    commit();
  }, 2500);
}
function applyCombo(c) {
  Object.assign(SEARCH, { f: { ...EMPTY_F(), ...JSON.parse(JSON.stringify(c.f)) }, maxtime: c.maxtime || "", rating: c.rating || "",
    with: c.with || "", without: c.without || "", shown: 48 });
}

function clearFilters() { Object.assign(SEARCH, { f: EMPTY_F(), maxtime: "", rating: "", with: "", without: "", shown: 48 }); runSearch(); }
function setFilter(g, v, on) {
  const arr = SEARCH.f[g];
  const i = arr.indexOf(v);
  if (on && i < 0) arr.push(v);
  if (!on && i >= 0) arr.splice(i, 1);
  SEARCH.shown = 48;
  runSearch();
}

function facetLabel(g, k) {
  if (g === "book") return FACETS.book?.[k]?.title || LIB?.books.find((b) => b.id === k)?.title || k.replace("web:", "");
  return k;
}
function renderFilterBar() {
  const fbar = $("#fbar");
  if (!fbar) return;
  const active = [];
  Object.entries(SEARCH.f).forEach(([g, vs]) => vs.forEach((v) => active.push(`<button class="apill" data-g="${g}" data-v="${esc(v)}">${g === "tag" ? "#" : ""}${esc(facetLabel(g, v))} ${ICON.x}</button>`)));
  if (SEARCH.maxtime) active.push(`<button class="apill" data-g="time">≤ ${SEARCH.maxtime} min ${ICON.x}</button>`);
  if (SEARCH.rating) active.push(`<button class="apill" data-g="rating">${ratingLabel(SEARCH.rating)} ${ICON.x}</button>`);
  if (SEARCH.with.trim()) active.push(`<button class="apill" data-g="with">with ${esc(SEARCH.with)} ${ICON.x}</button>`);
  if (SEARCH.without.trim()) active.push(`<button class="apill" data-g="without">without ${esc(SEARCH.without)} ${ICON.x}</button>`);
  const btn = (g, label, n) => `<button class="fbtn ${n ? "on" : ""}" data-pop="${g}">${label}${n ? ` · ${n}` : ""} <span class="car">▾</span></button>`;
  fbar.innerHTML = `
    <div class="filters">
      ${["course", "protein", "diet", "method"].map((g) => btn(g, GROUP_LABEL[g], SEARCH.f[g].length)).join("")}
      ${btn("time", "Time", SEARCH.maxtime ? 1 : 0)}
      ${btn("rating", "Rating", SEARCH.rating ? 1 : 0)}
      ${btn("book", "Source", SEARCH.f.book.length)}
      ${btn("tag", "My tags", SEARCH.f.tag.length)}
      ${btn("ing", "Ingredients", (SEARCH.with.trim() ? 1 : 0) + (SEARCH.without.trim() ? 1 : 0))}
      <span class="sep"></span>
      <label class="sort">Sort <select id="sortSel">${SORTS.map(([k, l]) => `<option value="${k}" ${SEARCH.sort === k ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>
    ${active.length ? `<div class="active">${active.join("")}<button class="link" id="clrAll">Clear all</button></div>` : ""}`;
  $$(".fbtn", fbar).forEach((b) => b.addEventListener("click", (e) => { e.stopPropagation(); openPop(b.dataset.pop, b); }));
  $$(".apill", fbar).forEach((b) => b.addEventListener("click", () => {
    const g = b.dataset.g;
    if (g === "time") SEARCH.maxtime = "";
    else if (g === "rating") SEARCH.rating = "";
    else if (g === "with") SEARCH.with = "";
    else if (g === "without") SEARCH.without = "";
    else return setFilter(g, b.dataset.v, false);
    runSearch();
  }));
  $("#clrAll")?.addEventListener("click", clearFilters);
  $("#sortSel").addEventListener("change", (e) => { SEARCH.sort = e.target.value; runSearch(); });
}

function closePop() { $(".pop")?.remove(); }
document.addEventListener("click", (e) => { if (!e.target.closest(".pop")) closePop(); });
function openPop(g, anchor) {
  const wasOpen = $(".pop")?.dataset.g === g;
  closePop();
  if (wasOpen) return;
  const pop = document.createElement("div");
  pop.className = "pop";
  pop.dataset.g = g;
  const counts = FACETS[g] || {};
  if (g === "time") {
    const opts = [["", "Any time"], ...[15, 30, 45, 60, 90].map((m) => [String(m), `${m} minutes or less`])];
    pop.innerHTML = opts.map(([v, l]) => `<label class="opt"><input type="radio" name="tm" value="${v}" ${SEARCH.maxtime === v ? "checked" : ""}><span>${l}</span>${v && FACETS.time?.[v] != null ? `<em>${FACETS.time[v]}</em>` : ""}</label>`).join("")
      + `<p class="pnote">Times come from the recipe when it lists them; otherwise they're estimated from the steps (shown with ~).</p>`;
    $$("input", pop).forEach((i) => i.addEventListener("change", () => { SEARCH.maxtime = i.value; SEARCH.shown = 48; closePop(); runSearch(); }));
  } else if (g === "rating") {
    const opts = [["", "Any rating"], ["3", "★ 3 & up"], ["4", "★ 4 & up"], ["4.5", "★ 4.5 & up"], ["5", "★ 5 only"], ["mine", "Only recipes I've rated"]];
    pop.innerHTML = opts.map(([v, l]) => `<label class="opt"><input type="radio" name="rt" value="${v}" ${SEARCH.rating === v ? "checked" : ""}><span>${l}</span>${v && FACETS.rating?.[v] != null ? `<em>${FACETS.rating[v]}</em>` : ""}</label>`).join("")
      + `<p class="pnote">Uses your own stars when you've rated a recipe, otherwise the NYT Cooking / EatingWell rating. Rate any recipe from its page.</p>`;
    $$("input", pop).forEach((i) => i.addEventListener("change", () => { SEARCH.rating = i.value; SEARCH.shown = 48; closePop(); runSearch(); }));
  } else if (g === "ing") {
    pop.innerHTML = `<label class="plab">Must include</label><input type="text" id="pw" placeholder="e.g. chicken, lemon" value="${esc(SEARCH.with)}">
      <label class="plab">Leave out</label><input type="text" id="pwo" placeholder="e.g. mushrooms, cilantro" value="${esc(SEARCH.without)}">
      <p class="pnote">Separate with commas.</p><button class="btn primary sm" id="papply">Apply</button>`;
    const apply = () => { SEARCH.with = $("#pw").value; SEARCH.without = $("#pwo").value; SEARCH.shown = 48; closePop(); runSearch(); };
    setTimeout(() => {
      $("#papply").onclick = apply;
      $$("input", pop).forEach((i) => i.addEventListener("keydown", (e) => e.key === "Enter" && apply()));
      $("#pw").focus();
    });
  } else {
    let keys = Object.keys(counts);
    if (g === "tag") keys = [...new Set([...keys, ...Object.keys(usedTags())])];
    SEARCH.f[g].forEach((v) => !keys.includes(v) && keys.push(v));
    keys.sort((a, b) => (counts[b]?.n ?? counts[b] ?? 0) - (counts[a]?.n ?? counts[a] ?? 0) || facetLabel(g, a).localeCompare(facetLabel(g, b)));
    const cnt = (k) => counts[k]?.n ?? counts[k] ?? 0;
    const note = { diet: `<p class="pnote">Detected from the ingredients. Gluten-free* means no obvious gluten — check labels.</p>`,
      tag: keys.length ? "" : `<p class="pnote">No tags yet. Open a recipe and tap <b>+ Tag</b>.</p>` }[g] || "";
    pop.innerHTML = (keys.length > 10 ? `<input type="text" class="pfind" placeholder="Filter…">` : "")
      + `<div class="opts">${keys.map((k) => `<label class="opt" data-l="${esc(facetLabel(g, k).toLowerCase())}"><input type="checkbox" value="${esc(k)}" ${SEARCH.f[g].includes(k) ? "checked" : ""}><span>${g === "tag" ? "#" : ""}${esc(facetLabel(g, k))}</span><em>${cnt(k)}</em></label>`).join("")}</div>` + note;
    $$("input[type=checkbox]", pop).forEach((i) => i.addEventListener("change", () => setFilter(g, i.value, i.checked)));
    $(".pfind", pop)?.addEventListener("input", (e) => $$(".opt", pop).forEach((o) => (o.hidden = !o.dataset.l.includes(e.target.value.toLowerCase()))));
  }
  document.body.appendChild(pop);
  const r = anchor.getBoundingClientRect();
  pop.style.top = `${r.bottom + scrollY + 6}px`;
  pop.style.left = `${Math.max(12, Math.min(r.left + scrollX, innerWidth - pop.offsetWidth - 12))}px`;
  pop.addEventListener("click", (e) => e.stopPropagation());
}

const QUICK = [
  ["Weeknight · 30 min", () => { SEARCH.maxtime = "30"; SEARCH.f.course = ["Mains"]; }],
  ["Vegetarian mains", () => { SEARCH.f.diet = ["Vegetarian"]; SEARCH.f.course = ["Mains"]; }],
  ["Soups & stews", () => { SEARCH.f.course = ["Soups & stews"]; }],
  ["Air fryer", () => { SEARCH.f.method = ["Air fryer"]; }],
  ["Freezer-friendly", () => { SEARCH.f.method = ["Freezer-friendly"]; }],
  ["Slow cooker", () => { SEARCH.f.method = ["Slow cooker"]; }],
  ["Instant Pot", () => { SEARCH.f.method = ["Instant Pot / pressure"]; }],
  ["Sheet pan", () => { SEARCH.f.method = ["Sheet pan"]; }],
  ["Chicken dinners", () => { SEARCH.f.protein = ["Chicken"]; SEARCH.f.course = ["Mains"]; }],
  ["Desserts", () => { SEARCH.f.course = ["Desserts"]; }],
  ["Breakfast", () => { SEARCH.f.course = ["Breakfast"]; }],
];
async function renderHome(res) {
  const { results } = await api("/api/random?n=6");
  const fav = S.favorites.slice().reverse();
  const recent = S.recent.slice(0, 6);
  const tags = Object.entries(usedTags()).sort((a, b) => b[1] - a[1]);
  const usual = Object.entries(S.combos).sort((a, b) => b[1].n - a[1].n || b[1].last - a[1].last).slice(0, 6);
  res.innerHTML = `
    <div class="section-title"><h2>Browse</h2></div>
    ${usual.length ? `<p class="eyebrow-sm">Your usual filters</p>
    <div class="chips" style="justify-content:flex-start;margin-bottom:10px">${usual.map(([k, c]) => `<span class="chip usual" data-combo="${esc(k)}" role="button" tabindex="0" title="Used ${c.n}×">${esc(comboLabel(c))}<button class="forget" data-forget="${esc(k)}" aria-label="Forget this combination">${ICON.x}</button></span>`).join("")}</div>
    <p class="eyebrow-sm">Ideas</p>` : ""}
    <div class="chips" style="justify-content:flex-start">${QUICK.map(([l], i) => `<button class="chip" data-quick="${i}">${l}</button>`).join("")}
      ${tags.map(([t, n]) => `<button class="chip tagchip" data-tagq="${esc(t)}">#${esc(t)} <em>${n}</em></button>`).join("")}</div>
    ${recent.length ? `<div class="section-title"><h2>Recently opened</h2></div><div class="results">${recent.map((c) => card(c)).join("")}</div>` : ""}
    <div class="section-title"><h2>Tonight, maybe?</h2><button id="shuffle">Shuffle</button></div>
    <div class="results">${results.map((c) => card(c)).join("")}</div>
    ${fav.length ? `<div class="section-title"><h2>Favorites</h2></div><div class="results">${fav.map((c) => card(c)).join("")}</div>` : ""}`;
  $("#shuffle").addEventListener("click", () => renderHome(res));
  $$("[data-quick]", res).forEach((b) => b.addEventListener("click", () => { SEARCH.f = EMPTY_F(); SEARCH.maxtime = ""; QUICK[+b.dataset.quick][1](); runSearch(); }));
  $$("[data-tagq]", res).forEach((b) => b.addEventListener("click", () => { SEARCH.f = EMPTY_F(); SEARCH.f.tag = [b.dataset.tagq]; runSearch(); }));
  $$("[data-combo]", res).forEach((el) => {
    const go = (e) => { if (e.target.closest("[data-forget]")) return; applyCombo(S.combos[el.dataset.combo]); runSearch(); };
    el.addEventListener("click", go);
    el.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(e); } });
  });
  $$("[data-forget]", res).forEach((b) => b.addEventListener("click", (e) => {
    e.stopPropagation(); delete S.combos[b.dataset.forget]; commit(); renderHome(res);
  }));
  bindCards(res);
}

let pollTimer;
function pollIndex(onTick) {
  clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    const lib = await getLibrary(true);
    onTick && onTick(lib);
    if (lib.status.state === "indexing") pollIndex(onTick);
  }, 2000);
}

/* ------------------------------------------------------------------ library */

async function viewLibrary() {
  const lib = await getLibrary(true);
  const st = lib.status;
  app.innerHTML = `
    <div class="section-title" style="margin-top:0"><h2 style="font-size:1.9rem">Your cookbooks</h2>
      <span class="status">${lib.books.length} books · ${lib.recipes.toLocaleString()} recipes</span></div>
    ${st.state === "indexing" ? `<div class="status"><span class="spin"></span> Reading ${esc(st.current)} (${st.done}/${st.total})<div class="progress"><i style="width:${(100 * st.done) / Math.max(1, st.total)}%"></i></div></div>` : ""}
    <div class="shelf">${lib.books.map((b) => `
      <a class="book" href="#/book/${b.id}">
        ${b.cover ? `<img src="${b.cover}" alt="" loading="lazy">` : `<div class="cover-ph">${esc(b.title)}</div>`}
        <b>${esc(b.title)}</b><span>${b.count} recipes${b.author ? " · " + esc(b.author) : ""}</span>
      </a>`).join("")}</div>
    ${lib.problems.length ? `<details class="problems"><summary>${lib.problems.length} files couldn't be used</summary><ul>${lib.problems.map((p) => `<li><b>${esc(p.file)}</b> — ${esc(p.reason)}</li>`).join("")}</ul></details>` : ""}`;
  if (st.state === "indexing") pollIndex(() => location.hash === "#/library" && viewLibrary());
}

async function viewBook(id) {
  const lib = await getLibrary();
  const b = lib.books.find((x) => x.id === id);
  if (!b) { app.innerHTML = `<p class="empty">Book not found.</p>`; return; }
  const { results } = await api(`/api/search?book=${id}&q=`);
  app.innerHTML = `
    <a class="back" href="#/library">${ICON.back} Library</a>
    <div class="book-head">${b.cover ? `<img src="${b.cover}" alt="">` : ""}<div><h1>${esc(b.title)}</h1><p>${esc(b.author || "")} · ${b.count} recipes</p></div></div>
    <input class="filter" id="bf" type="search" placeholder="Filter this book">
    <div class="results" id="br">${results.map((c) => card(c)).join("")}</div>`;
  bindCards($("#br"));
  $("#bf").addEventListener("input", (e) => {
    const v = e.target.value.toLowerCase();
    $$("#br .card").forEach((c) => (c.hidden = v && !c.textContent.toLowerCase().includes(v)));
  });
}

/* ------------------------------------------------------------------ quantities & scaling */

const VULGAR = { "½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 1 / 3, "⅔": 2 / 3, "⅛": 0.125, "⅜": 0.375, "⅝": 0.625, "⅞": 0.875, "⅕": 0.2, "⅖": 0.4, "⅗": 0.6, "⅘": 0.8, "⅙": 1 / 6, "⅚": 5 / 6 };
const VF = Object.keys(VULGAR).join("");
const NUM = `(?:\\d+\\s+\\d+\\/\\d+|\\d+\\/\\d+|\\d+(?:\\.\\d+)?(?:\\s?[${VF}])?|[${VF}])`;
const QTY_RE = new RegExp(`^(\\s*[•●▪✦*-]?\\s*)(${NUM})(\\s*(?:-|–|to)\\s*(${NUM}))?`);

function parseNum(s) {
  s = s.trim();
  let m;
  if ((m = s.match(/^(\d+)\s+(\d+)\/(\d+)$/))) return +m[1] + m[2] / m[3];
  if ((m = s.match(/^(\d+)\/(\d+)$/))) return m[1] / m[2];
  if ((m = s.match(new RegExp(`^(\\d+(?:\\.\\d+)?)?\\s*([${VF}])?$`)))) return (m[1] ? +m[1] : 0) + (m[2] ? VULGAR[m[2]] : 0);
  return NaN;
}
function fmtNum(n) {
  const whole = Math.floor(n + 1e-9);
  const frac = n - whole;
  const opts = [[0, ""], [1 / 8, "⅛"], [1 / 4, "¼"], [1 / 3, "⅓"], [3 / 8, "⅜"], [1 / 2, "½"], [5 / 8, "⅝"], [2 / 3, "⅔"], [3 / 4, "¾"], [7 / 8, "⅞"], [1, ""]];
  let best = opts[0];
  for (const o of opts) if (Math.abs(frac - o[0]) < Math.abs(frac - best[0])) best = o;
  const w = best[0] === 1 ? whole + 1 : whole;
  if (n >= 10 && Math.abs(n - Math.round(n)) > 0.01 && !best[1]) return String(Math.round(n));
  return (w ? String(w) : "") + best[1] || "0";
}
function scaleText(t, f) {
  const m = t.match(QTY_RE);
  if (!m) return esc(t);
  const a = parseNum(m[2]);
  if (isNaN(a)) return esc(t);
  const q = f === 1 ? m[2] + (m[3] || "").replace(/^(\S)/, " $1").replace(/^\s*to\s*/, " to ") : fmtNum(a * f) + (m[4] ? "–" + fmtNum(parseNum(m[4]) * f) : "");
  let rest = t.slice(m[0].length);
  if (/^[A-Za-z(]/.test(rest)) rest = " " + rest;   // some ebooks drop the space after the number ("4leeks")
  return esc(m[1]) + `<span class="q">${esc(q)}</span>` + esc(rest);
}
function scaleTextPlain(t, f) { const d = document.createElement("div"); d.innerHTML = scaleText(t, f); return d.textContent; }

/* ------------------------------------------------------------------ timers */

const TIME_RE = /(\d+(?:\s*(?:to|-|–)\s*\d+)?)\s*(hours?|hrs?|minutes?|mins?|seconds?|secs?)\b/gi;
function linkTimes(html) {
  return html.replace(TIME_RE, (all, n, unit) => {
    const first = parseInt(n, 10);
    const mult = /^h/i.test(unit) ? 3600 : /^s/i.test(unit) ? 1 : 60;
    return `<span class="tmr" data-sec="${first * mult}" title="Start a timer">⏱ ${all}</span>`;
  });
}
const TIMERS = [];
let audioCtx;
function beep() {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    [0, 0.25, 0.5].forEach((d) => {
      const o = audioCtx.createOscillator(), g = audioCtx.createGain();
      o.frequency.value = 880; o.connect(g); g.connect(audioCtx.destination);
      g.gain.setValueAtTime(0.0001, audioCtx.currentTime + d);
      g.gain.exponentialRampToValueAtTime(0.3, audioCtx.currentTime + d + 0.02);
      g.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + d + 0.2);
      o.start(audioCtx.currentTime + d); o.stop(audioCtx.currentTime + d + 0.22);
    });
    navigator.vibrate && navigator.vibrate([200, 100, 200]);
  } catch (e) { /* no audio */ }
}
function startTimer(sec, label) {
  audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();   // unlock audio on tap (iOS)
  TIMERS.push({ id: uid(), end: Date.now() + sec * 1000, label });
  renderTimers();
  toast(`Timer set: ${fmtDur(sec)}`);
}
const fmtDur = (s) => (s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:` : `${Math.floor(s / 60)}:`) + String(Math.floor(s % 60)).padStart(2, "0");
function renderTimers() {
  const now = Date.now();
  $("#timers").innerHTML = TIMERS.map((t) => {
    const left = Math.max(0, Math.round((t.end - now) / 1000));
    return `<div class="timer ${left === 0 ? "ring" : ""}" data-id="${t.id}">
      <small>${esc(t.label)}</small><b>${left === 0 ? "Done!" : fmtDur(left)}</b>
      <button data-a="plus" title="+1 minute">+1</button><button data-a="x" title="Dismiss">${ICON.x}</button></div>`;
  }).join("");
}
$("#timers").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  const id = b.closest(".timer").dataset.id, t = TIMERS.find((x) => x.id === id);
  if (b.dataset.a === "x") TIMERS.splice(TIMERS.indexOf(t), 1);
  else t.end = Math.max(t.end, Date.now()) + 60000, (t.rang = false);
  renderTimers();
});
setInterval(() => {
  if (!TIMERS.length) return;
  const now = Date.now();
  TIMERS.forEach((t) => { if (t.end <= now && (!t.rang || now - t.rang > 4000)) { t.rang = now; beep(); } });
  renderTimers();
}, 500);

/* ------------------------------------------------------------------ keep screen awake */

const Wake = {
  on: false, lock: null, ns: null,
  async enable() {
    this.on = true;
    try {
      if ("wakeLock" in navigator && window.isSecureContext) {
        this.lock = await navigator.wakeLock.request("screen");
        this.lock.addEventListener("release", () => (this.lock = null));
        return true;
      }
    } catch (e) { /* fall through to NoSleep */ }
    try {   // iPad over Wi-Fi isn't a "secure context", so use the silent-video trick
      if (window.NoSleep) { this.ns = this.ns || new NoSleep(); await this.ns.enable(); return true; }
    } catch (e) { /* ignore */ }
    return false;
  },
  disable() { this.on = false; this.lock?.release?.(); this.lock = null; this.ns?.disable(); },
};
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && Wake.on && !Wake.lock && !Wake.ns) Wake.enable(); });

/* ------------------------------------------------------------------ recipe view */

let CUR = null;   // { r, scale, prog }

async function viewRecipe(id) {
  app.innerHTML = `<p class="empty"><span class="spin"></span></p>`;
  const r = await api("/api/recipe/" + encodeURIComponent(id));
  if (r.error) { app.innerHTML = `<p class="empty">Recipe not found. <a class="link" href="#/">Back to search</a></p>`; return; }
  const c = cardData(r);
  S.recent = [c, ...S.recent.filter((x) => x.id !== c.id)].slice(0, 12);
  const prog = S.progress[id] || { ing: [], step: -1 };
  CUR = { r, card: c, scale: 1, prog };
  commit();
  renderRecipe();
}

function renderRecipe() {
  const { r, scale, prog } = CUR;
  const fav = S.favorites.some((f) => f.id === r.id);
  const cooked = S.cooked[r.id] || [];
  const citation = r.source === "book"
    ? `<a class="citation" href="#/book/${r.bookInfo.id}" title="Open this cookbook">
        ${r.bookInfo.cover ? `<img class="cv" src="${r.bookInfo.cover}" alt="Cover of ${esc(r.bookInfo.title)}">` : ""}
        <div><small>From the cookbook</small><b>${esc(r.bookInfo.title)}</b><span>${esc(r.bookInfo.author || "")}</span></div></a>`
    : `<a class="citation" href="${esc(r.url)}" target="_blank" rel="noopener">${sitePh(r.site)}
        <div><small>From ${esc(r.site)}</small><b>${esc(r.author || r.site)}</b><span>${r.rating ? `<span class="stars">★ ${r.rating.value.toFixed(1)}</span>${r.rating.count ? ` · ${r.rating.count.toLocaleString()} ratings` : ""} · ` : ""}View original ↗</span></div></a>`;
  const photo = r.source === "book" ? r.images?.[0] : r.image;
  const steps = r.steps;
  let n = 0;
  const stepIdx = steps.map((s) => (s.h ? -1 : n++));
  const total = n;
  app.innerHTML = `
  <article class="recipe">
    <a class="back" href="javascript:history.back()">${ICON.back} Back</a>
    <div class="r-head">
      <div>
        <h1>${esc(r.title)}</h1>
        ${citation}
        <div class="meta">${(r.meta || []).map((m) => `<span>${esc(m)}</span>`).join("")}${r.facets?.minutes && r.facets.minutesEst ? `<span title="Estimated from the steps">About ${fmtMin(r.facets.minutes)}</span>` : ""}${cooked.length ? `<span>Cooked ${cooked.length}× · last ${new Date(cooked[cooked.length - 1]).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>` : ""}</div>
        <div class="tagrow" id="tagrow">
          ${(S.tags[r.id] || []).map((t) => `<span class="tag big">#${esc(t)}<button data-untag="${esc(t)}" title="Remove tag">${ICON.x}</button></span>`).join("")}
          <span class="myrate" title="Your rating">${[1, 2, 3, 4, 5].map((n) => `<button data-rate="${n}" class="${(S.ratings[r.id] || 0) >= n ? "on" : ""}" aria-label="${n} star${n > 1 ? "s" : ""}">★</button>`).join("")}</span>
          <button class="tag add" id="addTag">+ Tag</button>
          ${["course", "protein", "diet", "method"].flatMap((g) => (r.facets?.[g] || []).map((v) => `<button class="tag auto" data-fg="${g}" data-fv="${esc(v)}" title="Find more like this">${esc(v)}</button>`)).join("")}
        </div>
      </div>
      ${photo ? `<img class="r-photo" src="${esc(photo)}" alt="">` : ""}
    </div>
    ${r.headnote?.length ? `<p class="headnote clamp" id="hn">${esc(r.headnote.join(" "))}</p>` : ""}

    <div class="toolbar">
      <button class="btn ${document.body.classList.contains("cooking") ? "on" : ""}" id="cook">${ICON.sun} Cook mode</button>
      <div class="scale" title="Scale the recipe">${[0.5, 1, 2, 3].map((f) => `<button data-f="${f}" class="${f === scale ? "on" : ""}">${f === 0.5 ? "½" : f}×</button>`).join("")}</div>
      <span class="sep"></span>
      <button class="btn sm ${fav ? "on" : ""}" id="fav">${ICON.star(fav)} ${fav ? "Favorited" : "Favorite"}</button>
      <button class="btn sm" id="toList">${ICON.cart} Shopping list</button>
      <button class="btn sm" id="toPlan">${ICON.cal} Plan</button>
    </div>

    <div class="cols">
      <section>
        <h2>Ingredients <small>tap to check off</small></h2>
        <ul class="ings">${r.ingredients.map((i, k) => i.h
          ? `<li class="sub">${esc(i.t)}</li>`
          : `<li data-k="${k}" class="${prog.ing.includes(k) ? "done" : ""}"><span class="box"></span><span class="t">${scaleText(i.t, scale)}</span></li>`).join("")}</ul>
      </section>
      <section>
        <h2>Method <small>tap the step you're on</small></h2>
        <ol class="steps">${steps.map((s, k) => s.h
          ? `<li class="sub">${esc(s.t)}</li>`
          : `<li data-n="${stepIdx[k]}" class="${stepIdx[k] === prog.step ? "cur" : stepIdx[k] < prog.step ? "past" : ""}">${linkTimes(esc(s.t.replace(/^\d{1,2}[.)]?\s+(?=[A-Z])/, "")))}</li>`).join("")}</ol>
        ${r.notes?.length ? `<div class="notes">${r.notes.map((x) => `<p>${esc(x)}</p>`).join("")}</div>` : ""}
        <div class="notes" style="background:none;border:1px dashed var(--line)">
          <b style="font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--ink-3)">My notes</b>
          <textarea id="mynote" rows="2" placeholder="Kids loved it · less salt next time · double the sauce" style="width:100%;border:0;background:none;resize:vertical;outline:none;margin-top:6px">${esc(S.notes[r.id] || "")}</textarea>
        </div>
        <p style="margin-top:18px"><button class="btn sm" id="reset">Reset checkmarks</button> <button class="btn sm" id="done">Mark as cooked</button></p>
      </section>
    </div>
  </article>
  ${document.body.classList.contains("cooking") ? `<div class="stepper"><button id="prev">←</button><span class="lbl" id="slbl"></span><button id="next">Next →</button></div>` : ""}`;

  const persist = () => { S.progress[r.id] = prog; commit(); };
  $("#hn")?.addEventListener("click", (e) => e.target.classList.toggle("clamp"));
  $$(".ings li[data-k]").forEach((li) => li.addEventListener("click", () => {
    const k = +li.dataset.k;
    prog.ing = prog.ing.includes(k) ? prog.ing.filter((x) => x !== k) : [...prog.ing, k];
    li.classList.toggle("done");
    persist();
  }));
  const setStep = (s) => {
    prog.step = Math.max(-1, Math.min(total - 1, s));
    $$(".steps li[data-n]").forEach((li) => {
      const k = +li.dataset.n;
      li.className = k === prog.step ? "cur" : k < prog.step ? "past" : "";
    });
    const cur = $(".steps li.cur");
    if (cur && document.body.classList.contains("cooking")) cur.scrollIntoView({ behavior: "smooth", block: "center" });
    const l = $("#slbl"); if (l) l.textContent = prog.step < 0 ? `${total} steps` : `Step ${prog.step + 1} of ${total}`;
    persist();
  };
  CUR.setStep = setStep;
  CUR.total = total;
  $$(".steps li[data-n]").forEach((li) => li.addEventListener("click", (e) => {
    if (e.target.closest(".tmr")) return;
    const k = +li.dataset.n;
    setStep(k === prog.step ? k + 1 : k);
  }));
  $$(".tmr").forEach((t) => t.addEventListener("click", () => startTimer(+t.dataset.sec, r.title)));
  $$(".scale button").forEach((b) => b.addEventListener("click", () => { CUR.scale = +b.dataset.f; renderRecipe(); }));
  $("#cook").addEventListener("click", toggleCook);
  $("#fav").addEventListener("click", () => {
    S.favorites = fav ? S.favorites.filter((f) => f.id !== r.id) : [...S.favorites, CUR.card];
    commit(); renderRecipe();
  });
  $("#toList").addEventListener("click", () => addToListModal([{ r, scale: CUR.scale }]));
  $("#toPlan").addEventListener("click", () => planModal(CUR.card, r));
  $("#reset").addEventListener("click", () => { prog.ing = []; prog.step = -1; persist(); renderRecipe(); });
  $("#done").addEventListener("click", () => {
    S.cooked[r.id] = [...(S.cooked[r.id] || []), new Date().toISOString()];
    prog.ing = []; prog.step = -1; persist(); toast("Logged — nice cooking!"); renderRecipe();
  });
  $("#mynote").addEventListener("input", debounce((e) => { S.notes[r.id] = e.target.value; commit(); }, 500));
  $$("[data-rate]").forEach((b) => b.addEventListener("click", () => {
    const n = +b.dataset.rate;
    if (S.ratings[r.id] === n) delete S.ratings[r.id]; else S.ratings[r.id] = n;   // tap the same star again to clear
    commit(); renderRecipe();
  }));
  $$("[data-untag]").forEach((b) => b.addEventListener("click", () => {
    S.tags[r.id] = (S.tags[r.id] || []).filter((t) => t !== b.dataset.untag);
    if (!S.tags[r.id].length) delete S.tags[r.id];
    commit(); renderRecipe();
  }));
  $$("[data-fg]").forEach((b) => b.addEventListener("click", () => {
    Object.assign(SEARCH, { q: "", mode: "all", f: EMPTY_F(), maxtime: "", rating: "", with: "", without: "", shown: 48 });
    SEARCH.f[b.dataset.fg] = [b.dataset.fv];
    location.hash = "#/";
  }));
  $("#addTag").addEventListener("click", () => {
    const mine = S.tags[r.id] || [];
    const sugg = allTags().filter((t) => !mine.includes(t));
    $("#addTag").outerHTML = `<span class="tagadd"><input id="tagIn" list="tagList" placeholder="Tag name" autocomplete="off"><datalist id="tagList">${sugg.map((t) => `<option value="${esc(t)}">`).join("")}</datalist></span>
      ${sugg.slice(0, 8).map((t) => `<button class="tag sugg" data-sugg="${esc(t)}">+ ${esc(t)}</button>`).join("")}`;
    const add = (t) => {
      t = t.trim().replace(/^#/, "");
      if (!t) return renderRecipe();
      const existing = allTags().find((x) => x.toLowerCase() === t.toLowerCase()) || t;
      S.tags[r.id] = [...new Set([...(S.tags[r.id] || []), existing])];
      commit(); renderRecipe();
      toast(`Tagged #${existing}`);
    };
    const inp = $("#tagIn");
    inp.focus();
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") add(inp.value); if (e.key === "Escape") renderRecipe(); });
    inp.addEventListener("change", () => sugg.includes(inp.value) && add(inp.value));
    $$("[data-sugg]").forEach((b) => b.addEventListener("click", () => add(b.dataset.sugg)));
  });
  $("#prev")?.addEventListener("click", () => setStep(prog.step - 1));
  $("#next")?.addEventListener("click", () => {
    if (prog.step >= total - 1) { toast("That's the last step — enjoy!"); return; }
    setStep(prog.step + 1);
  });
  if ($("#slbl")) setStep(prog.step);
}

async function toggleCook() {
  const on = !document.body.classList.contains("cooking");
  document.body.classList.toggle("cooking", on);
  if (on) {
    const ok = await Wake.enable();
    toast(ok ? "Cook mode on — screen will stay awake" : "Cook mode on (this browser can't keep the screen awake)");
  } else Wake.disable();
  renderRecipe();
}
document.addEventListener("keydown", (e) => {
  if (!CUR?.setStep || !location.hash.startsWith("#/r/") || !document.body.classList.contains("cooking")) return;
  if (["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) return;
  if (["ArrowRight", "ArrowDown", " "].includes(e.key)) { e.preventDefault(); CUR.setStep(CUR.prog.step + 1); }
  if (["ArrowLeft", "ArrowUp"].includes(e.key)) { e.preventDefault(); CUR.setStep(CUR.prog.step - 1); }
});

/* ------------------------------------------------------------------ saved: favorites + recipes kept from websites */

let SAVED_SITE = "";
async function viewSaved() {
  app.innerHTML = `<p class="empty"><span class="spin"></span></p>`;
  const { results } = await api("/api/saved");
  const fav = S.favorites.slice().reverse();
  const sites = [...new Set(results.map((r) => r.site).filter(Boolean))].sort();
  if (SAVED_SITE && !sites.includes(SAVED_SITE)) SAVED_SITE = "";
  const shown = SAVED_SITE ? results.filter((r) => r.site === SAVED_SITE) : results;
  app.innerHTML = `
    <div class="section-title" style="margin-top:0"><h2 style="font-size:1.9rem">Saved</h2></div>
    <div class="section-title"><h2>★ Favorites <span class="status">${fav.length}</span></h2></div>
    ${fav.length ? `<div class="results" id="favs">${fav.map((c) => card(c)).join("")}</div>`
      : `<p class="empty" style="text-align:left;padding:8px 0">Nothing yet. Tap <b>☆ Favorite</b> on any recipe to keep it here.</p>`}
    <div class="section-title"><h2>From websites <span class="status">${results.length}</span></h2></div>
    ${sites.length > 1 ? `<div class="chips" style="justify-content:flex-start;margin:0 0 12px">
        <button class="chip ${SAVED_SITE ? "" : "on"}" data-site="">All</button>
        ${sites.map((s) => `<button class="chip ${SAVED_SITE === s ? "on" : ""}" data-site="${esc(s)}">${esc(s)} <em>${results.filter((r) => r.site === s).length}</em></button>`).join("")}
      </div>` : ""}
    ${shown.length ? `<div class="results" id="webs">${shown.map((c) => card(c)).join("")}</div>`
      : `<p class="empty" style="text-align:left;padding:8px 0">Recipes you open from NYT Cooking, EatingWell, Love &amp; Lemons, Skinnytaste, Yummy Toddler Food or a pasted link are kept here.</p>`}`;
  $$("[data-site]").forEach((b) => b.addEventListener("click", () => { SAVED_SITE = b.dataset.site; viewSaved(); }));
  bindCards(app);
}

/* ------------------------------------------------------------------ shopping list */

const AISLES = [
  ["Frozen", /\bfrozen\b|ice cream/],
  ["Spices & seasonings", /\b(salt|black pepper|peppercorns?|ground pepper|pepper to taste|freshly ground|cumin|paprika|cinnamon|nutmeg|turmeric|coriander|cayenne|chili powder|chile powder|red pepper flakes|curry powder|garam masala|bay leaf|bay leaves|dried (oregano|thyme|basil|rosemary|dill|parsley)|oregano|allspice|cloves? \(ground\)|ground (ginger|cloves|cardamom|allspice)|cardamom|five[- ]spice|za.atar|sumac|smoked paprika|garlic powder|onion powder|italian seasoning|seasoning|vanilla)\b/],
  ["Pantry", /\b(broth|stock|bouillon|coconut milk|peanut butter|almond butter|tahini|canned|can |cans|jar|tomato paste|tomato sauce|crushed tomatoes|diced tomatoes|passata|flour|sugar|brown sugar|honey|maple syrup|molasses|syrup|rice|pasta|spaghetti|penne|noodles|macaroni|orzo|couscous|quinoa|farro|barley|oats|oatmeal|lentils|chickpeas|beans|breadcrumbs|panko|cornstarch|cornmeal|polenta|baking powder|baking soda|yeast|cocoa|chocolate|chips|nuts|almonds|walnuts|pecans|cashews|pistachios|pine nuts|peanuts|seeds|raisins|dried|oil|vinegar|soy sauce|tamari|fish sauce|worcestershire|hot sauce|sriracha|mustard|mayonnaise|mayo|ketchup|miso|gochujang|harissa|salsa|olives|capers|pickles|anchovies|tuna|wine|sherry|mirin|sake|beer|extract|gelatin|cereal|crackers)\b/],
  ["Bakery", /\b(bread|baguette|bun|buns|rolls?|tortillas?|pita|naan|brioche|sourdough|croissants?|english muffins?|bagels?)\b/],
  ["Dairy & eggs", /\b(milk|buttermilk|butter|cream|half-and-half|cheese|cheddar|parmesan|parmigiano|pecorino|mozzarella|feta|ricotta|goat cheese|gruyère|gruyere|mascarpone|yogurt|yoghurt|sour cream|crème fraîche|creme fraiche|eggs?|egg yolks?|egg whites?|ghee)\b/],
  ["Meat & seafood", /\b(chicken|beef|pork|lamb|turkey|veal|duck|sausages?|bacon|pancetta|prosciutto|ham|chorizo|salami|steaks?|brisket|ribs|chops?|tenderloin|ground (beef|pork|turkey|chicken|lamb)|shrimp|prawns|salmon|cod|halibut|tilapia|fish|scallops|mussels|clams|crab|lobster|squid|calamari|tofu|tempeh)\b/],
  ["Produce", /\b(apples?|avocados?|bananas?|basil|berries|blueberries|strawberries|raspberries|broccoli|broccolini|brussels|cabbage|carrots?|cauliflower|celery|chard|chiles?|chilies|chives|cilantro|corn|cucumbers?|dill|eggplants?|fennel|garlic|ginger|grapes|greens|herbs|jalapeños?|jalapenos?|kale|leeks?|lemons?|limes?|lettuce|mangoes?|mint|mushrooms?|onions?|oranges?|parsley|peaches?|pears?|peas|bell peppers?|peppers?|potatoes?|radish(es)?|rosemary|sage|scallions?|shallots?|spinach|squash|thyme|tomatoes?|zucchini|arugula|beets?|asparagus|sweet potatoes?|plums?|cherries|pineapple|melon|watermelon|kiwi|sprouts|romaine|bok choy|okra|green beans|snap peas|snow peas|lemongrass|tarragon|oregano leaves)\b/],
];
const STAPLES = /^(?:[\d\s½¼¾⅓⅔⅛\/.-]*(?:pinch|dash|teaspoons?|tsp|tablespoons?|tbsp)?\s*(?:of\s+)?)?(?:kosher |fine |flaky |sea |table )?(salt|salt and (?:freshly ground )?(?:black )?pepper|(?:freshly ground )?black pepper|pepper|water|ice|olive oil|extra[- ]virgin olive oil|vegetable oil|canola oil|neutral oil|cooking spray|nonstick cooking spray|oil)\b(?:,? (?:to taste|for (?:serving|greasing|the pan|frying|drizzling)|as needed|divided|plus more.*))?\.?$/i;

function aisleOf(t) {
  const s = t.toLowerCase();
  for (const [name, re] of AISLES) if (re.test(s)) return name;
  return "Other";
}

function addToListModal(items) {   // items: [{ r, scale }]
  const rows = [];
  items.forEach(({ r, scale }) => r.ingredients.forEach((i) => {
    if (i.h) return;
    rows.push({ t: scaleTextPlain(i.t, scale || 1), from: r.title, rid: r.id, staple: STAPLES.test(i.t.trim()) });
  }));
  openModal(`
    <h2>Add to shopping list</h2>
    <p class="sub">Pantry staples are unchecked. Uncheck anything else you already have.</p>
    <div class="scroll"><ul class="ings">${rows.map((x, k) => `<li data-k="${k}" class="${x.staple ? "" : "done"}"><span class="box"></span><span>${esc(x.t)}${items.length > 1 ? `<span class="from" style="display:block;font-size:.74rem;color:var(--ink-3)">${esc(x.from)}</span>` : ""}</span></li>`).join("")}</ul></div>
    <div class="row"><button class="btn" id="mc">Cancel</button><button class="btn primary" id="ma">Add items</button></div>`, (m) => {
    const sync = () => { $("#ma").textContent = `Add ${$$(".ings li.done", m).length} items`; };
    $$(".ings li", m).forEach((li) => li.addEventListener("click", () => { li.classList.toggle("done"); sync(); }));
    sync();
    $("#mc").onclick = closeModal;
    $("#ma").onclick = () => {
      const picked = $$(".ings li.done", m).map((li) => rows[+li.dataset.k]);
      const have = new Set(S.list.map((i) => i.t.toLowerCase()));
      picked.forEach((x) => { if (!have.has(x.t.toLowerCase())) S.list.push({ id: uid(), t: x.t, aisle: aisleOf(x.t), done: false, from: x.from, rid: x.rid }); });
      commit(); closeModal(); toast(`Added ${picked.length} items to your list`);
    };
  });
}

function viewList() {
  const groups = {};
  S.list.forEach((i) => (groups[i.aisle] = groups[i.aisle] || []).push(i));
  const order = [...AISLES.map((a) => a[0]).reverse(), "Other"];   // walk the store: produce first
  const left = S.list.filter((i) => !i.done).length;
  app.innerHTML = `<div class="wrap-narrow">
    <div class="week-nav"><h1>Shopping list</h1>
      <button class="btn sm" id="copy">Copy</button>${navigator.share ? `<button class="btn sm" id="share">Share</button>` : ""}
      <button class="btn sm" id="clr">Clear checked</button></div>
    <p class="status">${left} to get${S.list.length - left ? ` · ${S.list.length - left} in the cart` : ""}</p>
    <form class="list-add" id="addf"><input id="addi" placeholder="Add an item (e.g. paper towels)" autocomplete="off"><button class="btn primary">Add</button></form>
    ${S.list.length ? order.filter((a) => groups[a]).map((a) => `
      <div class="aisle"><h3>${a}</h3><ul class="ings">${groups[a].sort((x, y) => x.done - y.done).map((i) => `
        <li data-id="${i.id}" class="${i.done ? "done" : ""}"><span class="box"></span><span class="t">${esc(i.t)}${i.from ? `<span class="from">${esc(i.from)}</span>` : ""}</span><button class="x" data-x="${i.id}" title="Remove">${ICON.x}</button></li>`).join("")}</ul></div>`).join("")
      : `<p class="empty">Your list is empty. Open a recipe and tap <b>Shopping list</b>, or build one from your week in <a class="link" href="#/plan">Plan</a>.</p>`}
  </div>`;
  $$(".aisle li").forEach((li) => li.addEventListener("click", (e) => {
    const it = S.list.find((i) => i.id === li.dataset.id);
    if (e.target.closest(".x")) S.list = S.list.filter((i) => i !== it);
    else it.done = !it.done;
    commit(); viewList();
  }));
  $("#addf").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("#addi").value.trim(); if (!t) return;
    S.list.push({ id: uid(), t, aisle: aisleOf(t), done: false });
    commit(); viewList(); $("#addi").focus();
  });
  $("#clr").addEventListener("click", () => { S.list = S.list.filter((i) => !i.done); commit(); viewList(); });
  const text = () => order.filter((a) => groups[a]?.some((i) => !i.done)).map((a) => `${a.toUpperCase()}\n` + groups[a].filter((i) => !i.done).map((i) => `☐ ${i.t}`).join("\n")).join("\n\n");
  $("#copy").addEventListener("click", async () => { await navigator.clipboard.writeText(text()); toast("Copied — paste into Notes or Reminders"); });
  $("#share")?.addEventListener("click", () => navigator.share({ title: "Shopping list", text: text() }));
}

/* ------------------------------------------------------------------ meal plan + calendar */

const MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"];
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parseYmd = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
let weekStart = (() => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d; })();

// Month grid for picking a day; days that already have meals show a dot.
function calendarHTML(selected, month) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1);
  const start = new Date(first); start.setDate(1 - ((first.getDay() + 6) % 7));   // back to Monday
  const today = ymd(new Date());
  const cells = [...Array(42)].map((_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const weeks = cells[35].getMonth() !== month.getMonth() ? cells.slice(0, 35) : cells;   // 5 rows when the month fits
  return `<div class="cal-head">
      <button type="button" class="cal-nav" data-m="-1" aria-label="Previous month">‹</button>
      <b>${month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</b>
      <button type="button" class="cal-nav" data-m="1" aria-label="Next month">›</button>
    </div>
    <div class="cal-grid" role="grid">
      ${["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((w) => `<span class="cal-wd">${w}</span>`).join("")}
      ${weeks.map((d) => {
        const k = ymd(d), n = (S.plan[k] || []).length;
        const cls = [d.getMonth() !== month.getMonth() ? "out" : "", k === today ? "today" : "", k === selected ? "sel" : "", k < today ? "past" : ""].join(" ");
        return `<button type="button" class="cal-day ${cls}" data-d="${k}" aria-pressed="${k === selected}" aria-label="${d.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}${n ? `, ${n} planned` : ""}">${d.getDate()}${n ? `<i>${"•".repeat(Math.min(n, 3))}</i>` : ""}</button>`;
      }).join("")}
    </div>`;
}

function planModal(c, r, presetDate, presetMeal) {
  let day = presetDate || ymd(new Date());
  let month = parseYmd(day); month.setDate(1);
  let meal = presetMeal || "Dinner";
  const dayLabel = () => parseYmd(day).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
  openModal(`
    <h2>Add to meal plan</h2><p class="sub">${esc(c.title)}</p>
    <div class="cal" id="cal"></div>
    <label>Meal</label>
    <div class="seg" id="pm" role="group" aria-label="Meal">${MEALS.map((m) => `<button type="button" data-meal="${m}" aria-pressed="${m === meal}">${m}</button>`).join("")}</div>
    <label style="display:flex;gap:8px;align-items:center;font-weight:500"><input type="checkbox" id="pg" checked style="width:auto;height:auto"> Also add it to Google Calendar</label>
    <div class="row"><button class="btn" id="mc">Cancel</button><button class="btn primary" id="ma"></button></div>`, () => {
    const draw = () => {
      $("#cal").innerHTML = calendarHTML(day, month);
      $("#ma").textContent = `Add to ${dayLabel()}`;
    };
    $("#cal").addEventListener("click", (e) => {
      const nav = e.target.closest(".cal-nav"), cell = e.target.closest(".cal-day");
      if (nav) { month = new Date(month.getFullYear(), month.getMonth() + +nav.dataset.m, 1); draw(); }
      if (cell) {
        day = cell.dataset.d;
        const d = parseYmd(day);
        if (d.getMonth() !== month.getMonth()) month = new Date(d.getFullYear(), d.getMonth(), 1);
        draw();
      }
    });
    $$("#pm button").forEach((b) => b.addEventListener("click", () => {
      meal = b.dataset.meal;
      $$("#pm button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    }));
    draw();
    $("#mc").onclick = closeModal;
    $("#ma").onclick = () => {
      const toGcal = $("#pg").checked;
      const entry = { id: uid(), meal, card: c };
      (S.plan[day] = S.plan[day] || []).push(entry);
      commit(); closeModal();
      if (toGcal) window.open(gcalUrl(day, entry, r), "_blank", "noopener");
      toast(`Planned for ${dayLabel()}`);
      if (location.hash === "#/plan") viewPlan();
    };
  });
}

const pad = (n) => String(n).padStart(2, "0");
function eventTimes(d, meal) {
  const [h, m] = (S.settings.mealTimes[meal] || "18:00").split(":").map(Number);
  const start = parseYmd(d); start.setHours(h, m);
  const end = new Date(start.getTime() + (S.settings.mealMinutes || 60) * 60000);
  const f = (x) => `${x.getFullYear()}${pad(x.getMonth() + 1)}${pad(x.getDate())}T${pad(x.getHours())}${pad(x.getMinutes())}00`;
  return [f(start), f(end)];
}
// A plan entry is either a recipe ({card}) or a free-text meal ({text}, e.g. "Leftovers").
const entryTitle = (e) => e.card ? e.card.title : e.text;
function eventDetails(entry, r) {
  if (!entry.card) return "Planned in Miso";
  const c = entry.card;
  const lines = [c.source === "book" ? `From the cookbook “${c.bookTitle}”` : `From ${c.site}${r?.url ? ": " + r.url : ""}`];
  if (r?.ingredients) lines.push("", "Ingredients:", ...r.ingredients.filter((i) => !i.h).map((i) => "• " + i.t));
  lines.push("", `Open in Miso: ${location.origin}/#/r/${encodeURIComponent(c.id)}`);
  return lines.join("\n").slice(0, 1800);
}
function gcalUrl(d, entry, r) {
  const [s, e] = eventTimes(d, entry.meal);
  const p = new URLSearchParams({ action: "TEMPLATE", text: `${entry.meal}: ${entryTitle(entry)}`, dates: `${s}/${e}`, details: eventDetails(entry, r), ctz: Intl.DateTimeFormat().resolvedOptions().timeZone });
  return "https://calendar.google.com/calendar/render?" + p.toString();
}
async function fetchRecipe(id) { try { return await api("/api/recipe/" + encodeURIComponent(id)); } catch (e) { return null; } }

function weekDays() { return [...Array(7)].map((_, i) => { const d = new Date(weekStart); d.setDate(d.getDate() + i); return d; }); }

function viewPlan() {
  const days = weekDays();
  const today = ymd(new Date());
  const label = `${days[0].toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${days[6].toLocaleDateString(undefined, { month: "short", day: "numeric" })}`;
  const count = days.reduce((n, d) => n + (S.plan[ymd(d)] || []).length, 0);
  app.innerHTML = `
    <div class="week-nav"><h1>Meal plan <span class="status" style="font:400 1rem var(--sans)">${label}</span></h1>
      <button class="btn sm" id="wp">←</button><button class="btn sm" id="wt">This week</button><button class="btn sm" id="wn">→</button></div>
    <div class="week-nav" style="margin-top:14px">
      <button class="btn sm" id="wl" ${count ? "" : "disabled"}>${ICON.cart} Shopping list for this week</button>
      <button class="btn sm" id="wi" ${count ? "" : "disabled"} title="Download an .ics file, then import it in Google Calendar (Settings → Import)">${ICON.cal} Export week to calendar (.ics)</button>
    </div>
    <div class="week">${days.map((d) => {
      const k = ymd(d);
      const meals = (S.plan[k] || []).slice().sort((a, b) => MEALS.indexOf(a.meal) - MEALS.indexOf(b.meal));
      return `<div class="day ${k === today ? "today" : ""}">
        <header><b>${d.toLocaleDateString(undefined, { weekday: "short" })}</b><span>${d.toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span></header>
        ${meals.map((m) => `<div class="meal ${m.card ? "" : "free"}">
          ${!m.card ? `<span class="free-ic" aria-hidden="true">${esc((m.text || "?").trim()[0].toUpperCase())}</span>` : m.card.image ? `<img src="${esc(m.card.image)}" alt="">` : m.card.source === "book" ? coverImg(m.card) : ""}
          <div><small>${m.meal}</small>${m.card ? `<a href="#/r/${encodeURIComponent(m.card.id)}">${esc(m.card.title)}</a>` : `<span class="free-t">${esc(m.text)}</span>`}
          <div class="acts"><button data-g="${k}|${m.id}" title="Add to Google Calendar">${ICON.cal}</button><button data-rm="${k}|${m.id}" title="Remove from plan">${ICON.x}</button></div></div></div>`).join("")}
        <button class="add" data-add="${k}">+ Add a meal</button></div>`;
    }).join("")}</div>`;
  const shift = (n) => { weekStart.setDate(weekStart.getDate() + n); viewPlan(); };
  $("#wp").onclick = () => shift(-7);
  $("#wn").onclick = () => shift(7);
  $("#wt").onclick = () => { weekStart = new Date(); weekStart.setHours(0, 0, 0, 0); weekStart.setDate(weekStart.getDate() - ((weekStart.getDay() + 6) % 7)); viewPlan(); };
  $$("[data-rm]").forEach((b) => b.onclick = () => { const [d, id] = b.dataset.rm.split("|"); S.plan[d] = S.plan[d].filter((m) => m.id !== id); if (!S.plan[d].length) delete S.plan[d]; commit(); viewPlan(); });
  $$("[data-g]").forEach((b) => b.onclick = async () => {
    const [d, id] = b.dataset.g.split("|");
    const entry = S.plan[d].find((m) => m.id === id);
    const w = window.open("about:blank", "_blank");   // open synchronously so popup blockers allow it
    const r = entry.card ? await fetchRecipe(entry.card.id) : null;
    w.location = gcalUrl(d, entry, r);
  });
  $$("[data-add]").forEach((b) => b.onclick = () => pickRecipeModal(b.dataset.add));
  $("#wl").onclick = async () => {
    const entries = days.flatMap((d) => S.plan[ymd(d)] || []).filter((e) => e.card);   // free-text meals have no ingredients
    if (!entries.length) { toast("No recipes planned this week — only free-text meals"); return; }
    const recipes = (await Promise.all(entries.map((e) => fetchRecipe(e.card.id)))).filter((r) => r && !r.error);
    addToListModal(recipes.map((r) => ({ r, scale: 1 })));
  };
  $("#wi").onclick = () => exportIcs(days);
}

const FREE_MEALS = ["Leftovers", "Takeout", "Eat out", "Pizza night", "Breakfast for dinner", "Fend for yourself"];
function pickRecipeModal(date) {
  let meal = "Dinner";
  openModal(`<h2>Add a meal</h2><p class="sub">${parseYmd(date).toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</p>
    <div class="seg" id="fm" role="group" aria-label="Meal">${MEALS.map((m) => `<button type="button" data-meal="${m}" aria-pressed="${m === meal}">${m}</button>`).join("")}</div>
    <label for="pq">Pick a recipe, or write any meal</label>
    <input type="text" id="pq" placeholder="Search recipes, or type e.g. Tacos at Grandma's" autocomplete="off" autofocus>
    <div class="chips" id="fq" style="justify-content:flex-start;margin:8px 0 0">${FREE_MEALS.map((t) => `<button type="button" class="chip" data-free="${esc(t)}">${esc(t)}</button>`).join("")}</div>
    <div class="mini-results" id="pr"></div>`, () => {
    const addFree = (text) => {
      text = text.trim();
      if (!text) return;
      (S.plan[date] = S.plan[date] || []).push({ id: uid(), meal, text });
      commit(); closeModal();
      toast(`${meal}: ${text}`);
      if (location.hash === "#/plan") viewPlan();
    };
    $$("#fm button").forEach((b) => b.addEventListener("click", () => {
      meal = b.dataset.meal;
      $$("#fm button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    }));
    $$("[data-free]").forEach((b) => b.addEventListener("click", () => addFree(b.dataset.free)));
    const show = (list, typed) => {
      const free = typed ? `<button type="button" class="card free-add" id="addTyped">${ICON.cal}<div class="body"><h3>Add “${esc(typed)}”</h3><div class="src">as ${meal.toLowerCase()}, no recipe</div></div></button>` : "";
      $("#pr").innerHTML = free + (list.slice(0, 12).map((c) => card(c)).join("") || (typed ? "" : `<p class="empty">No matches</p>`));
      $("#addTyped")?.addEventListener("click", () => addFree(typed));
      $$("#pr .card:not(.free-add)").forEach((el, i) => el.onclick = () => { closeModal(); planModal(list[i], null, date, meal); });
    };
    show([...S.favorites.slice().reverse(), ...S.recent].filter((c, i, a) => a.findIndex((x) => x.id === c.id) === i), "");
    $("#pq").addEventListener("keydown", (e) => { if (e.key === "Enter") addFree(e.target.value); });
    $("#pq").addEventListener("input", debounce(async (e) => {
      const typed = e.target.value.trim();
      if (!typed) return show([...S.favorites.slice().reverse(), ...S.recent].filter((c, i, a) => a.findIndex((x) => x.id === c.id) === i), "");
      const { results } = await api(`/api/search?q=${encodeURIComponent(typed)}`);
      if ($("#pq")?.value.trim() === typed) show(results, typed);
    }, 180));
  });
}

async function exportIcs(days) {
  const icsEsc = (s) => String(s).replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\n/g, "\\n");
  const fold = (line) => line.match(/.{1,73}/g).join("\r\n ");
  const out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Miso//Meal Plan//EN", "CALSCALE:GREGORIAN"];
  for (const d of days) {
    for (const entry of S.plan[ymd(d)] || []) {
      const r = entry.card ? await fetchRecipe(entry.card.id) : null;
      const [s, e] = eventTimes(ymd(d), entry.meal);
      out.push("BEGIN:VEVENT", `UID:${entry.id}@miso`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, "").split(".")[0]}Z`,
        `DTSTART:${s}`, `DTEND:${e}`, fold(`SUMMARY:${icsEsc(`${entry.meal}: ${entryTitle(entry)}`)}`),
        fold(`DESCRIPTION:${icsEsc(eventDetails(entry, r))}`), "END:VEVENT");
    }
  }
  out.push("END:VCALENDAR");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([out.join("\r\n")], { type: "text/calendar" }));
  a.download = `meal-plan-${ymd(days[0])}.ics`;
  a.click();
  toast("Downloaded — import it in Google Calendar → Settings → Import");
}

/* ------------------------------------------------------------------ settings */

async function settingsModal() {
  const lib = await getLibrary(true);
  const info = await api("/api/info");
  openModal(`
    <h2>Settings</h2>
    <label>Appearance</label>
    <select id="st">${["auto", "light", "dark"].map((t) => `<option value="${t}" ${S.settings.theme === t ? "selected" : ""}>${t === "auto" ? "Match system" : t[0].toUpperCase() + t.slice(1)}</option>`).join("")}</select>
    <label>Meal times (for calendar events)</label>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">${MEALS.map((m) => `<div><span style="font-size:.78rem;color:var(--ink-3)">${m}</span><input type="time" data-meal="${m}" value="${S.settings.mealTimes[m]}"></div>`).join("")}</div>
    <label>Library</label>
    <p class="sub" style="margin:0">${lib.books.length} cookbooks · ${lib.recipes.toLocaleString()} recipes. Folders scanned (edit <code>config.json</code> to change):</p>
    ${lib.folders.map((f) => `<p style="margin:4px 0"><code>${esc(f)}</code></p>`).join("")}
    <p><button class="btn sm" id="ri">Rescan for new books</button> <button class="btn sm" id="rf">Re-read every book</button></p>
    <label>Save recipes from any website</label>
    <p class="sub" style="margin:0">A browser bookmark that saves the recipe you're looking at into Miso. Needed for sites that block apps, like Yummy Toddler Food.</p>
    <p><button class="btn sm" id="bmSetup">Set up the Save to Miso bookmark</button></p>
    ${info.lan?.length ? `<label>Use it on your iPad or phone</label><p class="sub" style="margin:0">Same Wi-Fi, open: ${info.lan.map((u) => `<code>${esc(u)}</code>`).join(" or ")}. Then Share → Add to Home Screen.</p>` : `<label>Use it on your iPad or phone</label><p class="sub" style="margin:0">Start Miso with the <b>Miso.command</b> launcher (it turns on Wi-Fi access).</p>`}
    <div class="row"><button class="btn primary" id="sd">Done</button></div>`, () => {
    $("#st").onchange = (e) => { S.settings.theme = e.target.value; applyTheme(); commit(); };
    $$("[data-meal]").forEach((i) => (i.onchange = () => { S.settings.mealTimes[i.dataset.meal] = i.value; commit(); }));
    $("#ri").onclick = async () => { await post("/api/reindex", {}); closeModal(); location.hash = "#/library"; };
    $("#rf").onclick = async () => { await post("/api/reindex", { full: true }); closeModal(); location.hash = "#/library"; };
    $("#sd").onclick = closeModal;
    $("#bmSetup").onclick = bookmarkletModal;
  });
}
$("#settingsBtn").addEventListener("click", settingsModal);

// The bookmark sends the page's recipe data (schema.org JSON-LD) to Miso. Only recipe blocks are sent,
// to keep the link short; if a pop-up blocker stops the new tab, it opens Miso in the same tab.
function bookmarkletCode() {
  return `javascript:(()=>{const b=[...document.querySelectorAll('script[type="application/ld+json"]')].map(s=>s.textContent).filter(t=>/Recipe/.test(t));`
    + `if(!b.length){alert('Miso could not find a recipe on this page.');return}`
    + `const u='${location.origin}/#import='+encodeURIComponent(JSON.stringify({url:location.href,ld:b}));if(!window.open(u))location.href=u})()`;
}
function bookmarkletModal() {
  const code = bookmarkletCode();
  openModal(`
    <h2>Save to Miso bookmark</h2>
    <p class="sub">Once it's in your bookmarks, open any recipe page and click it to save that recipe into Miso.</p>
    <label>Chrome, Dia, Arc, Edge or Firefox</label>
    <p class="sub" style="margin:0">Show the bookmarks bar (⌘⇧B), then drag this button onto it:</p>
    <a class="bm" href="${esc(code)}" onclick="event.preventDefault();toast('Drag it to the bookmarks bar, or use Copy below')">＋ Save to Miso</a>
    <p class="sub" style="margin:6px 0 0">If the drag doesn't stick (Dia does this):</p>
    <ol class="sub steps-mini">
      <li>Click <b>Copy bookmark code</b> below.</li>
      <li>Bookmark any page (⌘D), naming it <b>Save to Miso</b>.</li>
      <li>Open your bookmarks (try typing <code>chrome://bookmarks</code> in the address bar), find <b>Save to Miso</b>, choose <b>Edit</b>, and paste the code in place of its address (URL).</li>
    </ol>
    <label>Safari on Mac (dragging doesn't work in Safari)</label>
    <ol class="sub steps-mini">
      <li>Click <b>Copy bookmark code</b> below.</li>
      <li>Press <b>⌘D</b> to bookmark this page. Name it <b>Save to Miso</b>, put it in <b>Favorites</b>, click Add.</li>
      <li>Choose <b>Bookmarks ▸ Edit Bookmarks</b>, Control-click <b>Save to Miso</b>, choose <b>Edit Address</b>, paste, and press Return.</li>
    </ol>
    <label>iPad or iPhone (Safari)</label>
    <ol class="sub steps-mini">
      <li>Copy the code below (tap the box, Select All, Copy).</li>
      <li>Tap Share ▸ <b>Add Bookmark</b>, name it <b>Save to Miso</b>, save.</li>
      <li>Open Bookmarks ▸ Edit, tap <b>Save to Miso</b>, replace the address with the code, tap Done.</li>
    </ol>
    <label for="bmCode">Bookmark code</label>
    <textarea id="bmCode" readonly rows="3" style="width:100%;font:12px ui-monospace,Menlo,monospace;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--ink);padding:8px;resize:none">${esc(code)}</textarea>
    <div class="row"><button class="btn" id="bmCopy">Copy bookmark code</button><button class="btn primary" id="bmDone">Done</button></div>`, () => {
    const ta = $("#bmCode");
    ta.addEventListener("focus", () => ta.select());
    $("#bmCopy").onclick = async () => {
      try { await navigator.clipboard.writeText(code); toast("Copied — now paste it as the bookmark's address"); }
      catch (e) { ta.focus(); ta.select(); toast("Selected — press ⌘C (or tap Copy) to copy it"); }
    };
    $("#bmDone").onclick = closeModal;
  });
}

/* ------------------------------------------------------------------ router */

const ROUTES = [
  [/^#\/?$/, viewSearch, "search"],
  [/^#\/library$/, viewLibrary, "library"],
  [/^#\/book\/(.+)$/, viewBook, "library"],
  [/^#\/r\/(.+)$/, (id) => viewRecipe(decodeURIComponent(id)), "search"],
  [/^#\/plan$/, viewPlan, "plan"],
  [/^#\/list$/, viewList, "list"],
  [/^#\/saved$/, viewSaved, "saved"],
];

async function route() {
  const h = location.hash || "#/";
  if (h.startsWith("#import=")) return handleBookmarklet(h.slice(8));
  if (!h.startsWith("#/r/") && document.body.classList.contains("cooking")) { document.body.classList.remove("cooking"); Wake.disable(); }
  if (!h.startsWith("#/r/")) CUR = null;
  for (const [re, fn, tab] of ROUTES) {
    const m = h.match(re);
    if (m) {
      $$("#tabs a").forEach((a) => a.classList.toggle("on", a.dataset.tab === tab));
      await fn(...m.slice(1));
      if (!h.startsWith("#/r/")) window.scrollTo(0, 0);
      return;
    }
  }
  location.hash = "#/";
}

async function handleBookmarklet(payload) {
  app.innerHTML = `<p class="empty"><span class="spin"></span> Saving recipe…</p>`;
  try {
    const { url, ld } = JSON.parse(decodeURIComponent(payload));
    const r = await post("/api/web/import", { url, ld });
    if (r.id) { history.replaceState(null, "", "#/r/" + encodeURIComponent(r.id)); toast("Saved to Miso"); return route(); }
    app.innerHTML = `<p class="empty">${esc(r.error || "Couldn't find a recipe on that page.")}</p>`;
  } catch (e) {
    app.innerHTML = `<p class="empty">Couldn't read that page.</p>`;
  }
}

window.addEventListener("hashchange", route);
loadState().then(route);
