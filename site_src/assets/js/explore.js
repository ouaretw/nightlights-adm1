// Night Lights ADM1 - data explorer. Reads the published per-country Parquet files
// with hyparquet; every map, chart, table and export is computed from those rows.
import { asyncBufferFromUrl, parquetReadObjects } from "./../vendor/hyparquet/index.js";
import { esc, fmt, fmtExact, pct, seqColors, divColors, quantileBreaks, divergingBreaks, classifier, legendHTML,
  rewind, addPatterns, addZoom, showTip, downloadCsv } from "./carto.js";

const D = "data/v2/";
const $ = (id) => document.getElementById(id);
const PRODUCTS = {
  "adm1:wb": { dir: "adm1_wb", key: "ADM1CD_c", name: "NAM_1", geo: "data/geo/adm1/", label: "ADM1 · World Bank units",
    tag: ["exact", "exact aggregate"], note: "Exact aggregation of the source districts (sums exact; means coverage-weighted)." },
  "adm1:gadm": { dir: "adm1_gadm41", key: "GID_1", name: "NAME_1", geo: null, label: "ADM1 · GADM 4.1",
    tag: ["approx", "crosswalk"], note: "Approximate: whole districts assigned to the GADM 4.1 unit they overlap most; graded per unit." },
  "adm2:wb": { dir: "adm2", key: "ADM2CD_c", name: "NAM_2", geo: "data/geo/adm2/", label: "ADM2 · native districts",
    tag: ["native", "source"], note: "Source district observations, published natively on World Bank units only." },
};
const FREQ = {
  monthly: { label: "monthly", note: "Monthly composites (NASA VNP46A3)." },
  annual: { label: "official annual", note: "NASA's official annual composite (VNP46A4)." },
  annual_from_monthly: { label: "annual from monthly", note: "Annual values computed here from the monthly data; not the official composite and kept separate from it." },
};
const MAX_SEL = 8, K = 7;
const SERIES = ["#197D91", "#C47F17", "#11263B", "#B42318", "#6B4FA0", "#2E7D4F", "#8C564B", "#5B6B7A"];
const st = { iso: null, level: "adm1", sys: "wb", freq: "annual", view: "map", rows: [], cols: [], indicator: "ntl_sum",
  selected: [], focus: null, period: null, y0: 2012, y1: 2025, dict: {}, index: [], manifest: new Map(),
  geoCache: new Map(), viewData: null, changeYear: null, changeMetric: "dlog", changeBase: "ntl_sum", mapState: null, pending: {} };
const cache = new Map();

// ------------------------------------------------------------------ helpers
const status = (t, err = false) => { $("status").textContent = t; $("status").classList.toggle("err", err); };
const product = () => PRODUCTS[`${st.level}:${st.level === "adm2" ? "wb" : st.sys}`];
const timeCol = () => (st.freq === "monthly" ? "date" : "year");
const yearOf = (r) => (st.freq === "monthly" ? +String(r.date).slice(0, 4) : r.year);
const inWindow = (r) => { const y = yearOf(r); return y >= st.y0 && y <= st.y1; };
const unit = (c) => st.dict[c]?.unit || "";
const colLabel = (c) => st.dict[c]?.label || c;
const isChange = (c) => /^(dln_|pct_change_)/.test(c);
const parsePeriod = (v) => (st.freq === "monthly" ? String(v) : +v);
const colorOfSel = (k) => SERIES[Math.max(0, st.selected.indexOf(k)) % SERIES.length];

async function getJSON(url) {
  if (!cache.has(url)) cache.set(url, fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null));
  return cache.get(url);
}
async function getParquet(url) {
  if (!cache.has(url)) {
    cache.set(url, (async () => {
      const head = await fetch(url, { method: "HEAD" });
      if (!head.ok) return null;
      const file = await asyncBufferFromUrl({ url });
      const rows = await parquetReadObjects({ file });
      for (const r of rows) for (const k in r) if (typeof r[k] === "bigint") r[k] = Number(r[k]);
      return rows;
    })().catch((e) => { console.error(e); return null; }));
  }
  return cache.get(url);
}

// ------------------------------------------------------------------ filtering
function covOf(r) {
  if (r.coverage != null) return r.coverage;
  if (r.coverage_monthly_mean != null) return r.coverage_monthly_mean;
  if (r.ntl_quality_prop_na != null) return 1 - r.ntl_quality_prop_na;
  return null;
}
/** Reasons a row is excluded by the current quality criteria (empty = passes). */
function excludedBy(r) {
  const why = [];
  const minCov = +$("minCov").value;
  const c = covOf(r);
  if (minCov > 0 && (c == null || c < minCov)) why.push(`coverage < ${pct(minCov, 0)}`);
  if ($("noEst").checked && ((r.w_valid_estimated_share ?? 0) > 0.1 || r.w_valid_estimated === true)) why.push("estimated weight > 10%");
  if ($("allObs").checked && st.level === "adm1" && (r.n_adm2_no_valid_data ?? 0) > 0) why.push("district(s) without valid data");
  if ($("hiMatch").checked && st.level === "adm1" && st.sys === "gadm" && r.xw_match_quality !== "high") why.push(`crosswalk grade ${r.xw_match_quality ?? "NA"}`);
  return why;
}
const passes = (r) => excludedBy(r).length === 0;
const filtered = () => st.rows.filter((r) => inWindow(r) && passes(r));
const periodsOf = (rows) => [...new Set(rows.map((r) => r[timeCol()]))].sort();

// ------------------------------------------------------------------ init
async function init() {
  const [index, dict, man] = await Promise.all([getJSON(D + "index.json"), getJSON(D + "data_dictionary.json"), getJSON(D + "manifest.json")]);
  if (!index) { status("Could not load the country index.", true); return; }
  st.index = index;
  for (const c of dict?.columns || []) st.dict[c.column] = { label: c.description.split(/\. |\(/)[0].replace(/\.$/, "").trim(), unit: c.unit, desc: c.description, group: c.group, status: c.status };
  for (const f of man?.files || []) st.manifest.set(f.path, f);
  const dl = $("countrylist");
  for (const c of index) dl.appendChild(new Option(`${c.name} (${c.iso})`));
  for (let y = 2012; y <= 2025; y++) { $("y0").add(new Option(y, y)); $("y1").add(new Option(y, y)); }
  $("y0").value = 2012; $("y1").value = 2025;
  const picks = ["BRA", "IND", "NGA", "DEU", "IDN"].map((i) => index.find((c) => c.iso === i)).filter(Boolean);
  $("quickPicks").innerHTML = picks.map((c, i) => `${i ? (i === picks.length - 1 ? " or " : ", ") : ""}<a href="#c=${c.iso}" data-pick="${c.iso}">${esc(c.name)}</a>`).join("");
  $("quickPicks").addEventListener("click", (e) => { const a = e.target.closest("[data-pick]"); if (a) { e.preventDefault(); selectCountry(a.dataset.pick); } });

  $("country").addEventListener("change", onCountry);
  $("country").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); onCountry(); } });
  document.querySelectorAll("[data-level]").forEach((b) => b.addEventListener("click", () => setSeg("level", b.dataset.level)));
  document.querySelectorAll("[data-sys]").forEach((b) => b.addEventListener("click", () => setSeg("sys", b.dataset.sys)));
  document.querySelectorAll("[data-freq]").forEach((b) => b.addEventListener("click", () => setSeg("freq", b.dataset.freq)));
  document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
  $("period").addEventListener("change", (e) => { st.period = parsePeriod(e.target.value); syncHash(); render(); });
  $("indicator").addEventListener("change", (e) => { st.indicator = e.target.value; describeIndicator(); render(); });
  for (const id of ["y0", "y1"]) $(id).addEventListener("change", () => {
    st.y0 = +$("y0").value; st.y1 = Math.max(+$("y1").value, st.y0); $("y1").value = st.y1; render();
  });
  for (const id of ["minCov", "noEst", "allObs", "hiMatch"]) $(id).addEventListener("change", () => render());
  $("exportCsv").addEventListener("click", exportFiltered);
  $("exportView").addEventListener("click", exportView);
  window.addEventListener("resize", debounce(() => { st.mapState = null; render(); }, 200));

  // mobile: collapsible filters
  const mq = matchMedia("(max-width: 980px)");
  const setCollapsed = (c) => { $("controls").classList.toggle("collapsed", c); $("filtersToggle").setAttribute("aria-expanded", String(!c)); $("filtersToggle").textContent = c ? "Show filters" : "Hide filters"; };
  setCollapsed(mq.matches);
  $("filtersToggle").addEventListener("click", () => setCollapsed(!$("controls").classList.contains("collapsed")));

  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("c")) {
    if (["adm1", "adm2"].includes(h.get("l"))) st.level = h.get("l");
    if (["wb", "gadm"].includes(h.get("s"))) st.sys = h.get("s");
    if (FREQ[h.get("f")]) st.freq = h.get("f");
    st.pending = { period: h.get("p"), region: h.get("r") };
  }
  if (["map", "series", "change", "flares", "quality", "compare", "table"].includes(h.get("v"))) st.view = h.get("v");
  syncSegs(); syncTabs(); advSummary();
  const iso = h.get("c");
  if (iso && index.find((c) => c.iso === iso)) {
    if (mq.matches) setCollapsed(true);
    await selectCountry(iso);
  }
}
function debounce(fn, ms) { let t; return () => { clearTimeout(t); t = setTimeout(fn, ms); }; }

function setSeg(kind, val) {
  if (st[kind] === val) return;
  st[kind] = val;
  if (st.level === "adm2" && st.freq === "annual_from_monthly") st.freq = "annual";
  if (kind !== "freq") { st.selected = []; st.focus = null; }
  st.period = null; st.mapState = null;
  syncSegs(); load();
}
function setView(v) { st.view = v; syncTabs(); syncHash(); render(); }
function syncSegs() {
  document.querySelectorAll("[data-level]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.level === st.level)));
  document.querySelectorAll("[data-sys]").forEach((b) => {
    b.setAttribute("aria-pressed", String(st.level === "adm2" ? b.dataset.sys === "wb" : b.dataset.sys === st.sys));
    b.disabled = st.level === "adm2" && b.dataset.sys === "gadm";
  });
  document.querySelectorAll("[data-freq]").forEach((b) => {
    b.setAttribute("aria-pressed", String(b.dataset.freq === st.freq));
    b.disabled = st.level === "adm2" && b.dataset.freq === "annual_from_monthly";
  });
  $("sysNote").textContent = product().note;
  $("freqNote").textContent = FREQ[st.freq].note + (st.level === "adm2" ? " ADM2 has monthly and official annual data only." : "");
  $("hiMatch").disabled = !(st.level === "adm1" && st.sys === "gadm");
  $("allObs").disabled = st.level !== "adm1";
}
function syncHash() {
  if (!st.iso) return;
  const p = new URLSearchParams({ c: st.iso, l: st.level, s: st.sys, f: st.freq, v: st.view });
  if (st.period != null) p.set("p", st.period);
  if (st.focus) p.set("r", st.focus);
  history.replaceState(null, "", "#" + p.toString());
}
function syncTabs() {
  document.querySelectorAll("[data-view]").forEach((b) => { const on = b.dataset.view === st.view; b.setAttribute("aria-selected", String(on)); b.tabIndex = on ? 0 : -1; });
}
document.querySelector(".view-tabs")?.addEventListener("keydown", (e) => {
  if (!["ArrowLeft", "ArrowRight"].includes(e.key)) return;
  const tabs = [...document.querySelectorAll("[data-view]")]; const i = tabs.findIndex((t) => t.dataset.view === st.view);
  const n = tabs[(i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length]; setView(n.dataset.view); n.focus();
});
function advSummary() {
  const bits = [FREQ[st.freq].label, `${st.y0}–${st.y1}`];
  const mc = +$("minCov").value; bits.push(mc ? `coverage ≥ ${pct(mc, 0)}` : "no coverage threshold");
  if ($("noEst").checked) bits.push("no estimated weights");
  if ($("allObs").checked && st.level === "adm1") bits.push("all districts observed");
  if ($("hiMatch").checked && st.level === "adm1" && st.sys === "gadm") bits.push("high-grade GADM only");
  $("advSummary").textContent = bits.join(" · ");
}

function onCountry() {
  const v = $("country").value.trim();
  const m = v.match(/\(([A-Z]{3})\)$/);
  const hit = m ? st.index.find((c) => c.iso === m[1]) : st.index.find((c) => c.name.toLowerCase() === v.toLowerCase() || c.iso === v.toUpperCase());
  if (hit) selectCountry(hit.iso); else if (v) status("No country matches that name. Pick one from the list.", true);
}
async function selectCountry(iso) {
  if (st.iso !== iso) { st.selected = []; st.focus = null; st.period = null; }
  st.iso = iso; st.mapState = null;
  const c = st.index.find((x) => x.iso === iso);
  $("country").value = `${c.name} (${c.iso})`;
  await load();
}

// ------------------------------------------------------------------ load
async function load() {
  if (!st.iso) return;
  const p = product();
  const url = `${D}${p.dir}/${st.freq}/${st.iso}.parquet`;
  status("Loading…");
  const rows = await getParquet(url);
  if (!rows || !rows.length) {
    st.rows = []; st.cols = [];
    status("");
    $("period").innerHTML = "<option>—</option>"; $("period").disabled = true; $("indicator").disabled = true;
    $("exportCsv").disabled = true; fillFullFiles();
    syncHash();
    showEmpty(`No ${p.label} data for this country.`, st.sys === "gadm" && st.level === "adm1"
      ? "None of this country's source districts could be assigned to a GADM 4.1 unit with confidence (see Methods). Use World Bank units instead."
      : "The source has no observations for this selection.");
    renderRegion(); renderSelbar(); return;
  }
  st.rows = rows;
  st.cols = Object.keys(rows[0]);
  // indicator options grouped by the data dictionary
  const num = st.cols.filter((k) => rows.some((r) => typeof r[k] === "number") && !["year", "month"].includes(k));
  const prefer = ["ntl_sum", "ntl_sum_monthly_mean", "ntl_mean", "ntl_nogf_5km_sum"];
  if (!num.includes(st.indicator)) st.indicator = prefer.find((k) => num.includes(k)) || num[0];
  const groups = [["ntl", "Radiance"], ["afm", "Derived from monthly data"], ["transform", "Transformations"], ["qa", "Quality and weights"], [undefined, "Other"]];
  const sel = $("indicator"); sel.innerHTML = ""; sel.disabled = false;
  for (const [g, lab] of groups) {
    const cols = num.filter((k) => (st.dict[k]?.group ?? undefined) === g || (g === undefined && !["ntl", "afm", "transform", "qa"].includes(st.dict[k]?.group)));
    if (!cols.length) continue;
    const og = document.createElement("optgroup"); og.label = lab;
    for (const k of cols) og.appendChild(new Option(k, k, false, k === st.indicator));
    sel.appendChild(og);
  }
  describeIndicator();
  // periods
  const ps = periodsOf(rows);
  const want = st.pending.period != null ? parsePeriod(st.pending.period) : st.period;
  st.period = ps.includes(want) ? want : ps.at(-1);
  $("period").innerHTML = ps.slice().reverse().map((x) => `<option value="${x}" ${x === st.period ? "selected" : ""}>${x}</option>`).join("");
  $("period").disabled = false;
  buildColumnChecks(); fillFullFiles();
  // selection: keep what still exists, else the URL's region, else the five brightest units
  const keys = new Set(rows.map((r) => r[p.key]));
  st.selected = st.selected.filter((k) => keys.has(k));
  if (st.pending.region && keys.has(st.pending.region)) { st.selected = [st.pending.region]; st.focus = st.pending.region; }
  if (!st.selected.length) {
    const lit = rows.filter((r) => r.ntl_sum != null);
    const ref = lit.some((r) => r[timeCol()] === st.period) ? st.period : periodsOf(lit).at(-1);
    const top = lit.filter((r) => r[timeCol()] === ref).sort((a, b) => b.ntl_sum - a.ntl_sum).slice(0, 5);
    st.selected = top.map((r) => r[p.key]);
  }
  if (!st.focus || !keys.has(st.focus)) st.focus = st.selected[0] ?? null;
  st.pending = {};
  status(`${rows.length.toLocaleString()} rows loaded`);
  $("exportCsv").disabled = false;
  render();
}
function describeIndicator() {
  const d = st.dict[st.indicator];
  $("indNote").innerHTML = d ? `${esc(d.desc)}${d.unit ? ` <span class="mono">[${esc(d.unit)}]</span>` : ""}` : "";
}
function buildColumnChecks() {
  const box = $("cols"); box.innerHTML = "";
  const p = product();
  const defaults = new Set(["ISO_A3", p.key, p.name, "date", "year", "month", "ntl_sum", "ntl_mean", "ntl_nogf_5km_sum", "coverage",
    "w_valid_estimated_share", "xw_match_quality", "GADM41_GID_1", "has_valid_data", "ntl_sum_monthly_mean", "n_months_with_data"]);
  for (const c of st.cols) {
    const l = document.createElement("label"); l.className = "check";
    l.innerHTML = `<input type="checkbox" value="${esc(c)}" ${defaults.has(c) ? "checked" : ""}><span class="mono">${esc(c)}</span>`;
    l.title = st.dict[c]?.desc || "";
    box.appendChild(l);
  }
}
const human = (n) => n >= 1e6 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`;
function fillFullFiles() {
  const el = $("fullFiles");
  if (!st.iso || !st.rows.length) { el.innerHTML = ""; return; }
  const p = product();
  const links = [];
  for (const ext of ["csv", "parquet"]) {
    const path = `${D}${p.dir}/${st.freq}/${st.iso}.${ext}`;
    const f = st.manifest.get(path);
    if (f) links.push(`<a href="${path}" download>${st.iso} ${ext.toUpperCase()}</a> <span class="mono">${human(f.bytes)}</span>`);
  }
  if (st.freq === "monthly" && st.level === "adm1") {
    const f = st.manifest.get(`${p.dir}_monthly_by_country_csv.zip`);
    if (f) links.push(`<a href="${f.url}">all countries, monthly CSV (zip)</a> <span class="mono">${human(f.bytes)}</span>`);
  }
  el.innerHTML = `Published files for ${st.iso} (${esc(FREQ[st.freq].label)}): ${links.join(" · ") || "none"} · <a href="download.html">all files</a>`;
}

// ------------------------------------------------------------------ rendering
function showOnly(which) {
  for (const id of ["mapframe", "chart", "tableWrap", "empty"]) $(id).hidden = id !== which;
  if (which !== "mapframe") $("notDrawn").innerHTML = "";
}
function showEmpty(title, body) {
  showOnly("empty"); $("empty").innerHTML = `<div><b>${esc(title)}</b>${esc(body)}</div>`;
  $("legend").innerHTML = ""; $("viewControls").innerHTML = ""; $("viewNote").textContent = "";
  st.viewData = null; $("exportView").disabled = true; st.mapState = null;
}
function render() {
  syncSegs(); advSummary(); syncHash();
  renderSelbar();
  if (!st.iso || !st.rows.length) { renderRegion(); return; }
  const c = st.index.find((x) => x.iso === st.iso);
  $("viewTitle").innerHTML = `${esc(c.name)} <span class="muted" style="font-weight:400">· ${esc(product().label)} · ${esc(FREQ[st.freq].label)}</span>`;
  $("viewNote").textContent = "";
  ({ map: renderMap, series: renderSeries, change: renderChange, flares: renderFlares, quality: renderQuality,
    compare: renderCompare, table: renderTable })[st.view]();
  renderRegion();
}
const rowsOf = (k) => st.rows.filter((r) => r[product().key] === k);
const nameOf = (k) => { const r = st.rows.find((x) => x[product().key] === k); return r ? r[product().name] || k : k; };
function clickRegion(k) {
  const i = st.selected.indexOf(k);
  if (i < 0) { st.selected.push(k); if (st.selected.length > MAX_SEL) st.selected.shift(); st.focus = k; }
  else if (st.focus !== k) st.focus = k;
  else { st.selected.splice(i, 1); st.focus = st.selected.at(-1) ?? null; }
  render();
}
function renderSelbar() {
  const el = $("selbar");
  if (!st.rows.length) { el.innerHTML = ""; return; }
  el.innerHTML = `<span>Selected for comparison (${st.selected.length}/${MAX_SEL}):</span>` + (st.selected.length
    ? st.selected.map((k, i) => `<span class="chip${k === st.focus ? " focus" : ""}"><button type="button" class="name" data-focus="${esc(k)}" title="Show details"><i style="background:${SERIES[i % SERIES.length]}"></i>${esc(nameOf(k))}</button><button type="button" class="x" data-remove="${esc(k)}" aria-label="Remove ${esc(nameOf(k))}">×</button></span>`).join("")
    : `<span class="muted">none — click regions on the map, bars or table rows.</span>`);
  el.querySelectorAll("[data-focus]").forEach((b) => b.addEventListener("click", () => { st.focus = b.dataset.focus; render(); }));
  el.querySelectorAll("[data-remove]").forEach((b) => b.addEventListener("click", () => {
    st.selected = st.selected.filter((k) => k !== b.dataset.remove);
    if (st.focus === b.dataset.remove) st.focus = st.selected.at(-1) ?? null;
    render();
  }));
}
function setViewData(name, rows, cols) { st.viewData = { name, rows, cols }; $("exportView").disabled = !rows.length; }
function exportView() {
  if (!st.viewData) return;
  downloadCsv(st.viewData.rows, st.viewData.cols, `ntl_${product().dir}_${st.freq}_${st.iso}_${st.viewData.name}.csv`);
  status(`Exported ${st.viewData.rows.length.toLocaleString()} rows of the ${st.viewData.name} view.`);
}

// ---- value classification shared by map and region panel
function stateOf(row) {
  if (!row) return { s: "norow", label: "No row for this period" };
  const v = row[st.indicator];
  if (v == null || !isFinite(v)) return { s: "missing", label: covOf(row) === 0 || row.has_valid_data === false ? "Missing — no valid pixel in this period" : "Missing — no value for this indicator" };
  const why = excludedBy(row);
  if (why.length) return { s: "filtered", label: `Excluded by quality filter (${why.join("; ")})`, v };
  if (v === 0 && !isChange(st.indicator)) return { s: "zero", label: "0 — observed, no detectable light", v };
  return { s: "value", v };
}
function mapScale() {
  const vals = st.rows.filter(inWindow).map((r) => r[st.indicator]).filter((v) => v != null && isFinite(v));
  const ind = st.indicator;
  if (isChange(ind)) {
    const breaks = divergingBreaks(vals, K);
    return { breaks, colors: divColors(breaks.length + 1), zeroSpecial: false, kind: "diverging" };
  }
  const nonneg = vals.every((v) => v >= 0);
  const breaks = quantileBreaks(nonneg ? vals.filter((v) => v > 0) : vals, K);
  return { breaks, colors: seqColors(breaks.length + 1), zeroSpecial: nonneg, kind: nonneg ? "quantile-positive" : "quantile" };
}
function transformNote(ind) {
  if (ind.startsWith("ln_")) return "Values are natural logarithms as stored in the column (undefined, hence missing, where the level is 0).";
  if (ind.startsWith("asinh_")) return "Values are inverse hyperbolic sines as stored in the column (defined at 0).";
  if (ind.startsWith("dln_")) return "Values are year-on-year differences of logs between consecutive official annual composites.";
  if (ind.startsWith("pct_change_")) return "Values are year-on-year proportional changes; undefined where the previous year is 0.";
  return "No transformation applied.";
}

// ---- map
async function renderMap() {
  const p = product();
  $("viewControls").innerHTML = "";
  if (!p.geo) {
    return showEmpty("No map for GADM 4.1 units.",
      "GADM's licence does not allow redistributing its boundaries, so GADM 4.1 results are shown in the charts, table and region details only. Switch the boundary system to World Bank for a map.");
  }
  const url = `${p.geo}${st.iso}.geojson`;
  if (!st.geoCache.has(url)) st.geoCache.set(url, getJSON(url).then((g) => (g ? rewind(g) : null)));
  const [geo, world] = await Promise.all([st.geoCache.get(url), getJSON("data/geo/adm0_world.geojson")]);
  if (!geo || !geo.features.length) {
    $("notDrawn").innerHTML = "";
    return showEmpty("No map outline for this country at this level.",
      "Its source units could not be matched safely to a boundary (codes reused or units reorganised between boundary versions). All data remain available in the other views, the region details and the downloads.");
  }
  const sc = mapScale();
  const cls = classifier({ breaks: sc.breaks, colors: sc.colors, zeroIsSpecial: sc.zeroSpecial });
  const atP = new Map(st.rows.filter((r) => r[timeCol()] === st.period).map((r) => [r[p.key], r]));
  const fill = (code) => {
    const s = stateOf(atP.get(code));
    if (s.s === "filtered") return "url(#hatch-filtered)";
    if (s.s === "norow" || s.s === "missing") return "#D3DBE1";
    return cls(s.v).color;
  };
  const key = [st.iso, st.level, st.sys, st.freq, st.period, st.indicator, $("minCov").value, $("noEst").checked, $("allObs").checked, $("hiMatch").checked, st.y0, st.y1].join("|");
  showOnly("mapframe");
  const el = $("map");
  if (st.mapState?.key === key) { restyleMap(); return; }
  el.innerHTML = "";
  const { width, height } = el.getBoundingClientRect();
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${height}`).attr("role", "img")
    .attr("aria-label", `Map of ${st.indicator} for ${st.period}. Regions can also be selected from the table view.`);
  addPatterns(svg);
  const drawn = new Set(geo.features.map((f) => f.properties.code));
  const allUnits = [...new Set(st.rows.map((r) => r[p.key]))];
  const missingOutline = allUnits.filter((k) => !drawn.has(k));
  const ctry = world?.features.find((f) => f.properties.iso === st.iso);
  const fitTo = missingOutline.length && ctry ? { type: "FeatureCollection", features: [rewind({ features: [ctry] }).features[0], ...geo.features] } : geo;
  const cen = d3.geoCentroid(fitTo);
  const proj = d3.geoMercator().rotate([-cen[0], 0]).fitExtent([[10, 10], [width - 10, height - 10]], fitTo);
  const path = d3.geoPath(proj);
  const g = svg.append("g");
  if (missingOutline.length && ctry) g.append("path").datum(ctry).attr("class", "land").attr("d", path);
  g.append("g").selectAll("path").data(geo.features).join("path")
    .attr("class", "u").attr("d", path).attr("data-k", (d) => d.properties.code)
    .attr("tabindex", -1)
    .on("mousemove", (ev, d) => {
      const r = atP.get(d.properties.code); const s = stateOf(r);
      const val = s.s === "value" || (s.s === "filtered" && s.v != null) ? `${fmtExact(s.v)} <span class="muted">${esc(unit(st.indicator))}</span>` : esc(s.label);
      showTip($("tooltip"), `<b>${esc(d.properties.name)}</b><span class="muted v">${esc(d.properties.code)}${d.properties.approx ? " · approximate outline" : ""}</span><br>
        ${esc(st.indicator)}, ${st.period}: <span class="v">${val}</span>${s.s === "filtered" ? `<br><span class="muted">${esc(s.label)}</span>` : ""}<br>
        Valid-pixel coverage: <span class="v">${pct(r ? covOf(r) : null)}</span>`, ev);
    })
    .on("mouseleave", () => showTip($("tooltip"), null))
    .on("click", (ev, d) => clickRegion(d.properties.code));
  const z = addZoom({ svg, g, frame: $("mapframe"), width, height });
  st.mapState = { key, svg, fill, z, atP };
  restyleMap();
  const sw = [];
  if (sc.zeroSpecial) sw.push({ cls: "sw-zero", label: "0 — observed, no detectable light" });
  sw.push({ cls: "sw-missing", label: "No valid observation" }, { cls: "sw-filtered", label: "Excluded by quality filter" });
  if (missingOutline.length && ctry) sw.push({ cls: "sw-unmatched", label: "Area without a unit outline" });
  const how = sc.kind === "diverging" ? `${sc.breaks.length + 1} symmetric classes around 0 (limits from the 95th percentile of |values|)`
    : `${sc.breaks.length + 1} quantile classes of all ${sc.kind === "quantile-positive" ? "positive " : ""}values in ${st.y0}–${st.y1}`;
  $("legend").innerHTML = legendHTML({ title: `${st.indicator}, ${st.period}`, unitLabel: unit(st.indicator), breaks: sc.breaks, colors: sc.colors, swatches: sw,
    note: `${esc(how)}; limits fixed across periods. ${esc(transformNote(st.indicator))} Thick outline = selected; amber = region shown in details.` });
  $("notDrawn").innerHTML = missingOutline.length ? `<details class="notdrawn"><summary>${missingOutline.length} of ${allUnits.length} units have no outline and are not drawn</summary>
    ${missingOutline.map((k) => `<button type="button" class="btn ghost sm" data-k="${esc(k)}">${esc(nameOf(k))} <span class="mono">${esc(k)}</span></button>`).join(" ")}
    <p class="hint" style="margin:4px 0 0">Their data are complete in the other views and downloads; see <a href="methods.html#outlines">map outlines</a>.</p></details>` : "";
  $("notDrawn").querySelectorAll("[data-k]").forEach((b) => b.addEventListener("click", () => clickRegion(b.dataset.k)));
  setViewData(`map_${st.period}`, allUnits.map((k) => { const r = atP.get(k); const s = stateOf(r);
    return { code: k, name: nameOf(k), period: st.period, indicator: st.indicator, value: r ? r[st.indicator] : null, coverage: r ? covOf(r) : null, state: s.s, has_outline: drawn.has(k) }; }),
    ["code", "name", "period", "indicator", "value", "coverage", "state", "has_outline"]);
  $("viewNote").textContent = "Click a region to select it (again to show its details, a third time to remove it).";
}
function restyleMap() {
  const m = st.mapState; if (!m) return;
  m.svg.selectAll(".u").each(function (d) {
    const k = d.properties.code;
    this.setAttribute("fill", m.fill(k));
    this.classList.toggle("zero", stateOf(m.atP.get(k)).s === "zero");
    this.classList.toggle("sel", st.selected.includes(k));
    this.classList.toggle("focus", k === st.focus);
  });
  m.svg.selectAll(".u.sel").raise(); m.svg.selectAll(".u.focus").raise();
}

// ---- line chart (gaps for missing/excluded values; hollow markers for excluded values)
function lineChart(el, series, { yLabel = "", zeroBase = true, height = null, tipEl = $("tooltip") } = {}) {
  el.innerHTML = "";
  const width = el.getBoundingClientRect().width || 600;
  const H = height || el.getBoundingClientRect().height || 340;
  const mg = { t: 26, r: 16, b: 40, l: 68 };
  const parse = (t) => (typeof t === "number" ? new Date(Date.UTC(t, 6, 1)) : new Date(t + "-15T00:00:00Z"));
  const ok = (d) => d.v != null && isFinite(d.v) && !d.excluded;
  const all = series.flatMap((s) => s.points.filter((d) => d.v != null && isFinite(d.v)));
  if (!all.length) { el.innerHTML = `<div class="unavailable"><div><b>No values to plot.</b>All values are missing for this selection.</div></div>`; return false; }
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${H}`).attr("role", "img").attr("aria-label", `Line chart: ${yLabel}`);
  const x = d3.scaleUtc().domain(d3.extent(all, (d) => parse(d.t))).range([mg.l, width - mg.r]);
  const ext = d3.extent(all, (d) => d.v);
  const y = d3.scaleLinear().domain(zeroBase ? [Math.min(0, ext[0]), ext[1] === 0 ? 1 : ext[1] * 1.05] : ext[0] === ext[1] ? [ext[0] - 1, ext[1] + 1] : ext).nice().range([H - mg.b, mg.t]);
  svg.append("g").attr("class", "grid-line").attr("transform", `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(width - mg.l - mg.r)).tickFormat(""));
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - mg.b})`).call(d3.axisBottom(x).ticks(width < 560 ? 5 : 10).tickSizeOuter(0));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(fmt).tickSizeOuter(0));
  svg.append("text").attr("class", "axis-title").attr("x", width - mg.r).attr("y", H - 6).attr("text-anchor", "end").text(st.freq === "monthly" ? "Month" : "Year");
  svg.append("text").attr("class", "axis-title").attr("x", 4).attr("y", 12).text(yLabel.length > 70 ? yLabel.slice(0, 69) + "…" : yLabel);
  series.forEach((s, i) => {
    const col = s.color || SERIES[i % SERIES.length];
    svg.append("path").datum(s.points).attr("fill", "none").attr("stroke", col).attr("stroke-width", s.width || 2)
      .attr("stroke-dasharray", s.dash || null)
      .attr("d", d3.line().defined(ok).x((d) => x(parse(d.t))).y((d) => y(d.v)));
    const pts = s.points;
    const dots = pts.filter((d, j) => ok(d) && (pts.length <= 40 || !ok(pts[j - 1] || {}) && !ok(pts[j + 1] || {})));
    svg.append("g").selectAll("circle").data(dots).join("circle").attr("r", 2.8).attr("fill", col).attr("cx", (d) => x(parse(d.t))).attr("cy", (d) => y(d.v));
    svg.append("g").selectAll("circle").data(pts.filter((d) => d.excluded && d.v != null && isFinite(d.v))).join("circle")
      .attr("r", 3).attr("fill", "#fff").attr("stroke", col).attr("stroke-width", 1.4).attr("cx", (d) => x(parse(d.t))).attr("cy", (d) => y(d.v));
  });
  const ts = [...new Set(series.flatMap((s) => s.points.map((d) => d.t)))].sort();
  const fx = svg.append("line").attr("y1", mg.t).attr("y2", H - mg.b).attr("stroke", "#8C9BA8").attr("stroke-dasharray", "3 3").style("display", "none");
  svg.append("rect").attr("x", mg.l).attr("y", mg.t).attr("width", Math.max(0, width - mg.l - mg.r)).attr("height", Math.max(0, H - mg.t - mg.b)).attr("fill", "transparent")
    .on("mousemove", (ev) => {
      const [px] = d3.pointer(ev); const tx = x.invert(px);
      const t = ts.reduce((a, b) => (Math.abs(parse(b) - tx) < Math.abs(parse(a) - tx) ? b : a));
      fx.style("display", null).attr("x1", x(parse(t))).attr("x2", x(parse(t)));
      showTip(tipEl, `<b>${t}</b>` + series.map((s, i) => {
        const d = s.points.find((q) => q.t === t);
        const v = !d || d.v == null || !isFinite(d.v) ? `<span class="muted">${d?.missingLabel || "missing"}</span>` : `<span class="v">${fmtExact(d.v)}</span>${d.excluded ? ' <span class="muted">(excluded by filter)</span>' : ""}`;
        return `<span style="color:${s.color || SERIES[i % SERIES.length]}">■</span> ${esc(s.name)}: ${v}`;
      }).join("<br>"), ev);
    })
    .on("mouseleave", () => { fx.style("display", "none"); showTip(tipEl, null); });
  return true;
}
function seriesLegend(series, extra = "") {
  return `<div class="series-legend">${series.map((s, i) => `<span><i class="${s.dash ? "dash" : ""}" style="border-color:${s.color || SERIES[i % SERIES.length]}"></i>${esc(s.name)}</span>`).join("")}</div>${extra}`;
}
/** Points over all periods in the window; excluded rows keep their value but are flagged. */
function pointsFor(key, col, { transform = (v) => v, applyFilter = true } = {}) {
  const p = product();
  const ps = periodsOf(st.rows.filter(inWindow));
  const m = new Map(st.rows.filter((r) => r[p.key] === key && inWindow(r)).map((r) => [r[timeCol()], r]));
  return ps.map((t) => {
    const r = m.get(t);
    if (!r) return { t, v: null, missingLabel: "no row" };
    const v = r[col] == null ? null : transform(r[col]);
    return { t, v, excluded: applyFilter && !passes(r), missingLabel: "missing (no valid observation)" };
  });
}
function chartToViewData(name, series) {
  const rows = [];
  for (const s of series) for (const d of s.points) rows.push({ series: s.name, period: d.t, value: d.v, excluded_by_filter: !!d.excluded });
  setViewData(name, rows, ["series", "period", "value", "excluded_by_filter"]);
}

function renderSeries() {
  $("viewControls").innerHTML = `<span>${esc(FREQ[st.freq].label)} · ${st.y0}–${st.y1}</span>`;
  if (!st.selected.length) return showEmpty("No regions selected.", "Select regions on the map, in the Annual change bars or in the table.");
  showOnly("chart"); $("chart").style.height = "";
  const series = st.selected.map((k) => ({ name: nameOf(k), points: pointsFor(k, st.indicator) }));
  lineChart($("chart"), series, { yLabel: `${st.indicator}${unit(st.indicator) ? " [" + unit(st.indicator) + "]" : ""}`, zeroBase: !st.indicator.match(/^(ln_|dln_|pct_change_)/) });
  $("legend").innerHTML = seriesLegend(series, `<span class="note">Lines break where a period is missing; hollow markers are values excluded by the quality filters. ${esc(transformNote(st.indicator))}</span>`);
  chartToViewData("timeseries", series);
}

function renderChange() {
  const p = product();
  if (st.freq !== "annual") {
    return showEmpty("Annual change uses the official annual composites.",
      "Switch Frequency (Advanced) to Annual. Changes are computed between consecutive official composites only; month-to-month changes mix seasonal effects and are not shown.");
  }
  const rows = filtered();
  const years = [...new Set(rows.map((r) => r.year))].sort().filter((y) => rows.some((r) => r.year === y - 1));
  if (!years.length) return showEmpty("No pair of consecutive years passes the filters.", "Widen the time window or relax the quality criteria.");
  if (!years.includes(st.changeYear)) st.changeYear = years.includes(st.period) ? st.period : years.at(-1);
  const base = st.cols.includes(st.changeBase) ? st.changeBase : "ntl_sum";
  $("viewControls").innerHTML = `<label>Interval <select id="cy">${years.slice().reverse().map((y) => `<option value="${y}" ${y === st.changeYear ? "selected" : ""}>${y - 1} → ${y}</option>`).join("")}</select></label>
    <label>Variable <select id="cb">${["ntl_sum", "ntl_nogf_5km_sum"].filter((c) => st.cols.includes(c)).map((c) => `<option ${c === base ? "selected" : ""}>${c}</option>`).join("")}</select></label>
    <span class="seg" role="group" aria-label="Change metric" style="min-width:300px">${[["dlog", "Δ log"], ["abs", "Absolute"], ["pct", "Percent"]].map(([k, l]) => `<button type="button" data-cm="${k}" aria-pressed="${k === st.changeMetric}">${l}</button>`).join("")}</span>`;
  $("cy").onchange = (e) => { st.changeYear = +e.target.value; renderChange(); renderRegion(); };
  $("cb").onchange = (e) => { st.changeBase = e.target.value; renderChange(); };
  document.querySelectorAll("[data-cm]").forEach((b) => b.addEventListener("click", () => { st.changeMetric = b.dataset.cm; renderChange(); }));
  const y1 = st.changeYear, y0 = y1 - 1;
  const at = (y) => new Map(rows.filter((r) => r.year === y).map((r) => [r[p.key], r]));
  const A = at(y0), B = at(y1);
  const keys = [...new Set(st.rows.map((r) => r[p.key]))];
  const skip = { notBoth: 0, missing: 0, zeroBase: 0, zeroLog: 0 };
  const data = [];
  for (const k of keys) {
    const a = A.get(k), b = B.get(k);
    if (!a || !b) { skip.notBoth++; continue; }
    const va = a[base], vb = b[base];
    if (va == null || vb == null) { skip.missing++; continue; }
    let v;
    if (st.changeMetric === "abs") v = vb - va;
    else if (st.changeMetric === "pct") { if (va === 0) { skip.zeroBase++; continue; } v = vb / va - 1; }
    else { if (va <= 0 || vb <= 0) { skip.zeroLog++; continue; } v = Math.log(vb) - Math.log(va); }
    data.push({ k, n: b[p.name] || k, v, va, vb });
  }
  data.sort((a, b) => b.v - a.v);
  if (!data.length) return showEmpty("No valid change for this interval.", "Every unit is missing, excluded, or has a zero base for this metric.");
  showOnly("chart");
  const el = $("chart"); el.innerHTML = "";
  const rowH = 18, H = Math.max(300, data.length * rowH + 50);
  el.style.height = `${H}px`;
  const width = el.getBoundingClientRect().width;
  const mg = { t: 10, r: 70, b: 34, l: Math.min(220, width * 0.36) };
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${H}`).attr("role", "img").attr("aria-label", `Bar chart of change ${y0} to ${y1}`);
  const x = d3.scaleLinear().domain(d3.extent([0, ...data.map((d) => d.v)])).nice().range([mg.l, width - mg.r]);
  const y = d3.scaleBand().domain(data.map((d) => d.k)).range([mg.t, H - mg.b]).padding(0.18);
  const tf = st.changeMetric === "pct" ? d3.format("+.0%") : st.changeMetric === "dlog" ? d3.format("+.2f") : fmt;
  svg.append("g").attr("class", "grid-line").attr("transform", `translate(0,${mg.t})`).call(d3.axisTop(x).ticks(6).tickSize(-(H - mg.t - mg.b)).tickFormat(""));
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - mg.b})`).call(d3.axisBottom(x).ticks(6).tickFormat(tf));
  const metricLabel = { dlog: `Δ ln(${base})`, abs: `Δ ${base} [${unit(base)}]`, pct: `% change in ${base}` }[st.changeMetric];
  svg.append("text").attr("class", "axis-title").attr("x", width - mg.r).attr("y", H - 4).attr("text-anchor", "end").text(`${metricLabel}, ${y0} → ${y1}`);
  svg.append("g").selectAll("rect").data(data).join("rect").attr("x", (d) => x(Math.min(0, d.v))).attr("width", (d) => Math.max(1, Math.abs(x(d.v) - x(0))))
    .attr("y", (d) => y(d.k)).attr("height", y.bandwidth()).attr("fill", (d) => (d.v >= 0 ? "#197D91" : "#C47F17"))
    .attr("stroke", (d) => (d.k === st.focus ? "#E5AD4E" : st.selected.includes(d.k) ? "#11263B" : null)).attr("stroke-width", 2)
    .style("cursor", "pointer").on("click", (ev, d) => clickRegion(d.k))
    .on("mousemove", (ev, d) => showTip($("tooltip"), `<b>${esc(d.n)}</b>${y0}: <span class="v">${fmtExact(d.va)}</span><br>${y1}: <span class="v">${fmtExact(d.vb)}</span><br>
      Absolute: <span class="v">${fmtExact(d.vb - d.va)}</span><br>Percent: <span class="v">${d.va === 0 ? "undefined (zero base)" : d3.format("+.2%")(d.vb / d.va - 1)}</span><br>
      Δ log: <span class="v">${d.va > 0 && d.vb > 0 ? d3.format("+.4f")(Math.log(d.vb) - Math.log(d.va)) : "undefined (zero)"}</span>`, ev))
    .on("mouseleave", () => showTip($("tooltip"), null));
  svg.append("g").selectAll("text").data(data).join("text").attr("x", mg.l - 6).attr("y", (d) => y(d.k) + y.bandwidth() / 2).attr("dy", "0.32em")
    .attr("text-anchor", "end").attr("font-size", 11).attr("fill", "#33475B").text((d) => (d.n.length > 30 ? d.n.slice(0, 29) + "…" : d.n));
  svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", mg.t).attr("y2", H - mg.b).attr("stroke", "#11263B");
  const sk = [skip.notBoth && `${skip.notBoth} missing or excluded in ${y0} or ${y1}`, skip.missing && `${skip.missing} with no valid observation`,
    skip.zeroBase && `${skip.zeroBase} with a zero base in ${y0} (percent undefined)`, skip.zeroLog && `${skip.zeroLog} with zero light in either year (log undefined)`].filter(Boolean);
  $("legend").innerHTML = `<span class="note">${data.length} units with a valid change from ${y0} to ${y1} (official annual composites, both years passing the filters).
    ${sk.length ? "Not shown: " + esc(sk.join("; ")) + "." : "No unit omitted."} Teal = increase, amber = decrease. Descriptive change only; no significance is implied.</span>`;
  setViewData(`change_${y0}_${y1}`, data.map((d) => ({ code: d.k, name: d.n, variable: base, [`value_${y0}`]: d.va, [`value_${y1}`]: d.vb, change_abs: d.vb - d.va,
    change_pct: d.va === 0 ? null : d.vb / d.va - 1, change_dlog: d.va > 0 && d.vb > 0 ? Math.log(d.vb) - Math.log(d.va) : null })),
    ["code", "name", "variable", `value_${y0}`, `value_${y1}`, "change_abs", "change_pct", "change_dlog"]);
  $("viewNote").textContent = "Click a bar to select the region.";
}

function focusOrEmpty(what) {
  if (!st.focus) { showEmpty("No region selected.", `Select a region to ${what}.`); return null; }
  return st.focus;
}
function renderFlares() {
  const k = focusOrEmpty("compare total and flare-excluded light"); if (!k) return;
  const afm = st.freq === "annual_from_monthly";
  const cols = afm ? [["ntl_sum_monthly_mean", "All light"], ["ntl_nogf_5km_sum_monthly_mean", "Excluding ≤5 km of gas flares"]]
    : [["ntl_sum", "All light"], ["ntl_nogf_5km_sum", "Excluding ≤5 km of gas flares"], ["ntl_nogf_10km_sum", "Excluding ≤10 km of gas flares"]];
  const avail = cols.filter(([c]) => st.cols.includes(c));
  $("viewControls").innerHTML = `<span>Region: <b>${esc(nameOf(k))}</b> <span class="mono">${esc(k)}</span>. Flare light = total − light more than 5 km (10 km) from any flaring site. Country has <b>${esc(rowsOf(k)[0]?.n_gasflaring_locs_country ?? "NA")}</b> flaring sites.</span>`;
  showOnly("chart"); $("chart").style.height = "";
  const series = avail.map(([c, n], i) => ({ name: n, points: pointsFor(k, c), color: [SERIES[0], SERIES[1], SERIES[2]][i], dash: i ? (i === 1 ? "6 3" : "2 3") : null }));
  lineChart($("chart"), series, { yLabel: `${avail[0][0]} [${unit(avail[0][0])}]` });
  $("legend").innerHTML = seriesLegend(series, `<span class="note">Where the lines coincide, no flare light was detected. Hollow markers are excluded by the quality filters.</span>`);
  chartToViewData(`gasflares_${k}`, series);
}

function renderQuality() {
  const k = focusOrEmpty("inspect observation quality"); if (!k) return;
  const r0 = rowsOf(k)[0] || {};
  const xw = st.level === "adm1" && st.sys === "gadm"
    ? ` Crosswalk: grade <b>${esc(r0.xw_match_quality ?? "NA")}</b>, smallest district overlap ${pct(r0.xw_min_overlap)}, located directly ${pct(r0.xw_share_adm2_located_directly)}${r0.xw_absorbs_units ? `, absorbs <span class="mono">${esc(r0.xw_absorbs_units)}</span>` : ""}.` : "";
  $("viewControls").innerHTML = `<span>Region: <b>${esc(nameOf(k))}</b> <span class="mono">${esc(k)}</span>. Unfiltered, so you can see what the quality criteria remove.${xw}</span>`;
  showOnly("chart"); $("chart").style.height = "";
  let series;
  if (st.freq === "annual_from_monthly") {
    series = [{ name: "Average monthly coverage", points: pointsFor(k, "coverage_monthly_mean", { applyFilter: false }), color: SERIES[2], width: 2.4 },
      { name: "Months with data / 12", points: pointsFor(k, "n_months_with_data", { applyFilter: false, transform: (v) => v / 12 }), color: SERIES[0] }];
  } else {
    const cov = st.level === "adm2" ? pointsFor(k, "ntl_quality_prop_na", { applyFilter: false, transform: (v) => 1 - v }) : pointsFor(k, "coverage", { applyFilter: false });
    series = [
      { name: "Valid-pixel coverage", points: cov, color: SERIES[2], width: 2.4 },
      { name: "Good (>3 clear nights)", points: pointsFor(k, "ntl_quality_prop_0_good", { applyFilter: false }), color: SERIES[5] },
      { name: "Poor (≤3 clear nights)", points: pointsFor(k, "ntl_quality_prop_1_poor", { applyFilter: false }), color: SERIES[1] },
      { name: "Gap-filled", points: pointsFor(k, "ntl_quality_prop_2_gapfilled", { applyFilter: false }), color: SERIES[4] },
      { name: "Missing", points: pointsFor(k, "ntl_quality_prop_na", { applyFilter: false }), color: "#8C9BA8", dash: "4 3" },
    ];
    if (st.cols.includes("w_valid_estimated_share")) series.push({ name: "Estimated share of pixel weight", points: pointsFor(k, "w_valid_estimated_share", { applyFilter: false }), color: SERIES[3], dash: "2 3" });
  }
  lineChart($("chart"), series, { yLabel: "share (0–1)" });
  const mc = +$("minCov").value;
  $("legend").innerHTML = seriesLegend(series, `<span class="note">Shares of pixels (quality) or of the province's pixel weight (estimated weight).${mc ? ` Current coverage threshold: ${pct(mc, 0)}.` : ""} Estimated weights affect means only, never sums.</span>`);
  chartToViewData(`quality_${k}`, series);
}

async function renderCompare() {
  const f = st.freq === "annual_from_monthly" ? "annual" : st.freq;
  $("viewControls").innerHTML = `<span>Country total of <b>ntl_sum</b> (${esc(FREQ[f].label)}) from the three products. ADM2 and World Bank ADM1 must coincide; GADM falls below them by the light of districts that could not be assigned.</span>`;
  status("Loading comparison…");
  const [a2, wb, gd] = await Promise.all(["adm2", "adm1_wb", "adm1_gadm41"].map((d) => getParquet(`${D}${d}/${f}/${st.iso}.parquet`)));
  status(`${st.rows.length.toLocaleString()} rows loaded`);
  if (st.view !== "compare") return;
  const t = f === "monthly" ? "date" : "year";
  const tot = (rows) => {
    const m = d3.rollup((rows || []).filter((r) => { const y = f === "monthly" ? +String(r.date).slice(0, 4) : r.year; return y >= st.y0 && y <= st.y1; }),
      (v) => (v.every((r) => r.ntl_sum == null) ? null : d3.sum(v, (r) => r.ntl_sum)), (r) => r[t]);
    return [...m].sort((a, b) => (a[0] > b[0] ? 1 : -1)).map(([k, v]) => ({ t: k, v }));
  };
  showOnly("chart"); $("chart").style.height = "";
  const series = [
    { name: "ADM2 native (sum of districts)", points: tot(a2), color: "#A9B7C3", width: 6 },
    { name: "ADM1 · World Bank units", points: tot(wb), color: SERIES[0] },
    { name: "ADM1 · GADM 4.1", points: tot(gd), color: SERIES[1], dash: "6 3" },
  ];
  lineChart($("chart"), series, { yLabel: `country total ntl_sum [${unit("ntl_sum")}]` });
  $("legend").innerHTML = seriesLegend(series, `<span class="note">Unfiltered totals. A missing GADM line means no district of this country could be assigned to GADM 4.1.</span>`);
  chartToViewData("compare_boundaries", series);
}

function renderTable() {
  const p = product();
  const rows = filtered();
  const excluded = st.rows.filter((r) => inWindow(r) && !passes(r)).length;
  $("viewControls").innerHTML = `<span>${rows.length.toLocaleString()} rows pass the filters${excluded ? `, ${excluded.toLocaleString()} excluded by the quality criteria` : ""}${rows.length > 1000 ? " (first 1,000 shown; the export contains all)" : ""}. <span class="muted">NA</span> = missing; 0 = observed darkness.</span>`;
  if (!rows.length) return showEmpty("No rows pass the current filters.", "Widen the time window or relax the quality criteria.");
  showOnly("tableWrap");
  const cols = exportCols();
  const isNum = (c) => rows.some((r) => typeof r[c] === "number");
  $("table").querySelector("thead").innerHTML = `<tr>${cols.map((c) => `<th scope="col" class="${isNum(c) ? "num" : ""}" title="${esc(st.dict[c]?.desc || "")}">${esc(c)}</th>`).join("")}</tr>`;
  $("table").querySelector("tbody").innerHTML = rows.slice(0, 1000).map((r) =>
    `<tr tabindex="0" data-k="${esc(r[p.key])}" class="${st.selected.includes(r[p.key]) ? "sel" : ""}">${cols.map((c) => {
      const v = r[c];
      return isNum(c) ? `<td class="num">${v == null ? '<span class="muted">NA</span>' : esc(c === "year" || c === "month" ? String(v) : fmtExact(v))}</td>` : `<td>${v == null ? '<span class="muted">NA</span>' : esc(v)}</td>`;
    }).join("")}</tr>`).join("");
  $("table").querySelectorAll("tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => clickRegion(tr.dataset.k));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); clickRegion(tr.dataset.k); } });
  });
  setViewData("table", rows, cols);
  $("legend").innerHTML = "";
  $("viewNote").textContent = "Click a row or press Enter to select its region.";
}

// ---- region details
function renderRegion() {
  const box = $("region");
  const k = st.focus;
  if (!st.rows.length || !k) { box.innerHTML = `<div><p class="muted small" style="margin:0">No region selected. Click a region on the map, a bar in Annual change, or a table row.</p></div>`; $("regionTitle").textContent = "Region details"; return; }
  const p = product();
  const rs = rowsOf(k);
  const r = rs.find((x) => x[timeCol()] === st.period);
  const s = stateOf(r);
  const ind = st.indicator;
  const c = st.index.find((x) => x.iso === st.iso);
  $("regionTitle").textContent = "Region details";
  const big = s.s === "value" ? `${esc(fmtExact(s.v))}` : s.s === "zero" ? "0" : s.s === "filtered" && s.v != null ? `${esc(fmtExact(s.v))}` : "—";
  const bigNote = s.s === "value" ? esc(unit(ind)) : s.s === "zero" ? "observed, no detectable light" : esc(s.label);
  const kv = [];
  const add = (dt, dd, text = false) => kv.push(`<dt>${dt}</dt><dd class="${text ? "text" : ""}">${dd}</dd>`);
  add("Period", esc(st.period ?? "—"));
  if (r) {
    add("Valid-pixel coverage", pct(covOf(r)));
    if (r.ntl_quality_prop_0_good != null) add("Good · poor · gap-filled", `${pct(r.ntl_quality_prop_0_good)} · ${pct(r.ntl_quality_prop_1_poor)} · ${pct(r.ntl_quality_prop_2_gapfilled)}`);
    if (r.w_valid_estimated_share != null) add("Estimated pixel weight", pct(r.w_valid_estimated_share));
    if (r.n_adm2 != null) add("Districts (no valid data)", `${r.n_adm2} (${r.n_adm2_no_valid_data ?? 0})`);
    if (r.n_months_with_data != null) add("Months with data", `${r.n_months_with_data} of ${r.n_months ?? 12}`);
    if (r.GADM41_GID_1) add("GADM 4.1 parent", `${esc(r.GADM41_GID_1)} ${esc(r.GADM41_NAME_1 ?? "")}`);
  }
  const flags = [];
  if (r) {
    const cv = covOf(r);
    if (cv != null && cv < 0.5) flags.push(`<span class="tag warn">Low coverage (${pct(cv, 0)})</span>`);
    if ((r.w_valid_estimated_share ?? 0) > 0.1) flags.push(`<span class="tag warn">Estimated weight ${pct(r.w_valid_estimated_share, 0)}</span>`);
    if ((r.n_adm2_no_valid_data ?? 0) > 0) flags.push(`<span class="tag warn">${r.n_adm2_no_valid_data} district(s) without valid data</span>`);
    if (s.s === "filtered") flags.push(`<span class="tag bad">Excluded by your filters</span>`);
  }
  if (st.level === "adm1" && st.sys === "gadm" && rs[0]) {
    const q = rs[0].xw_match_quality;
    add("Crosswalk grade", `<span class="tag ${q === "high" ? "exact" : q === "low" ? "bad" : "warn"}">${esc(q ?? "NA")}</span>`, true);
    add("Smallest district overlap", pct(rs[0].xw_min_overlap));
    add("Districts located directly", pct(rs[0].xw_share_adm2_located_directly));
    if (rs[0].xw_absorbs_units) flags.push(`<span class="tag warn">Absorbs ${esc(rs[0].xw_absorbs_units)}</span>`);
  }
  // change vs previous official composite
  let change = "";
  if (st.freq === "annual" && r && typeof st.period === "number") {
    const prev = rs.find((x) => x.year === st.period - 1);
    const base = "ntl_sum";
    if (!prev || prev[base] == null || r[base] == null) change = `<p class="hint" style="margin:10px 0 0">Change ${st.period - 1} → ${st.period}: not available (missing year).</p>`;
    else {
      const a = prev[base], b = r[base];
      change = `<dl class="kv"><dt>Δ ntl_sum ${st.period - 1}→${st.period}</dt><dd>${fmtExact(b - a)}</dd>
        <dt>Percent</dt><dd>${a === 0 ? "undefined (zero base)" : d3.format("+.2%")(b / a - 1)}</dd>
        <dt>Δ log</dt><dd>${a > 0 && b > 0 ? d3.format("+.4f")(Math.log(b) - Math.log(a)) : "undefined (zero)"}</dd></dl>
        ${!passes(prev) || !passes(r) ? '<p class="hint" style="margin:4px 0 0">At least one of the two years is excluded by your quality filters.</p>' : ""}`;
    }
  } else if (st.freq !== "annual") change = `<p class="hint" style="margin:10px 0 0">Year-on-year change is reported for the official annual composites only.</p>`;
  box.innerHTML = `<div>
      <h3>${esc(nameOf(k))}</h3>
      <div class="region-id">${esc(k)} · ${esc(c?.name ?? st.iso)} · <span class="tag ${p.tag[0]}">${esc(p.label)} — ${esc(p.tag[1])}</span></div>
      <div class="bigval">${big}<small>${esc(ind)} · ${bigNote}</small></div>
      <div class="flags">${flags.join("") || '<span class="tag native">No quality flags</span>'}</div>
      <dl class="kv">${kv.join("")}</dl>
      ${change}
      <div class="btn-row" style="margin-top:14px">
        <button class="btn sm" type="button" id="dlRegion">Download region CSV</button>
        <button class="btn sm secondary" type="button" id="tblRegion">Show in table</button>
      </div>
      <p class="hint" style="margin-top:6px">All columns, ${st.y0}–${st.y1}, quality filters not applied (the quality columns are included).</p>
    </div>
    <div><h4>${esc(ind)} over time <span class="muted" style="font-weight:400">· ${esc(FREQ[st.freq].label)}</span></h4><div id="regionChart" class="chart spark"></div>
      <p class="hint" style="margin:6px 0 0">Gaps = missing periods; hollow markers = excluded by your quality filters.</p></div>`;
  lineChart($("regionChart"), [{ name: nameOf(k), points: pointsFor(k, ind), color: SERIES[0] }],
    { yLabel: unit(ind) ? `[${unit(ind)}]` : ind, height: 190, zeroBase: !ind.match(/^(ln_|dln_|pct_change_)/) });
  $("dlRegion").onclick = () => downloadCsv(rs.filter(inWindow), st.cols, `ntl_${p.dir}_${st.freq}_${k}_${st.y0}-${st.y1}.csv`);
  $("tblRegion").onclick = () => setView("table");
}

// ------------------------------------------------------------------ export
function exportCols() { return [...$("cols").querySelectorAll("input:checked")].map((i) => i.value); }
function exportFiltered() {
  const rows = filtered(); const cols = exportCols();
  if (!rows.length || !cols.length) { status("Nothing to export with the current filters.", true); return; }
  downloadCsv(rows, cols, `ntl_${product().dir}_${st.freq}_${st.iso}_${st.y0}-${st.y1}.csv`);
  status(`Exported ${rows.length.toLocaleString()} rows × ${cols.length} columns.`);
}

init();
