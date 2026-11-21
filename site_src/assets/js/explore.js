// Night Lights ADM1 - data explorer. Reads the published per-country Parquet
// files with hyparquet; all views and exports are computed from those rows.
import { asyncBufferFromUrl, parquetReadObjects } from "./../vendor/hyparquet/index.js";

const D = "data/v2/";
const $ = (id) => document.getElementById(id);
const PRODUCTS = {
  "adm1:wb": { dir: "adm1_wb", key: "ADM1CD_c", name: "NAM_1", geo: "data/geo/adm1/", label: "ADM1 · World Bank units" },
  "adm1:gadm": { dir: "adm1_gadm41", key: "GID_1", name: "NAME_1", geo: null, label: "ADM1 · GADM 4.1" },
  "adm2:wb": { dir: "adm2", key: "ADM2CD_c", name: "NAM_2", geo: "data/geo/adm2/", label: "ADM2 · native" },
};
const MAX_SEL = 8;
const st = { iso: null, level: "adm1", sys: "wb", freq: "annual", view: "map", rows: [], cols: [],
  indicator: "ntl_sum", selected: [], period: null, y0: 2012, y1: 2025, dict: {}, index: [], geoCache: new Map() };
const cache = new Map();

// ------------------------------------------------------------------ helpers
const fmt = (v) => v == null || !isFinite(v) ? "–" : Math.abs(v) >= 1e6 ? d3.format(".3~s")(v)
  : Math.abs(v) >= 100 ? d3.format(",.0f")(v) : Math.abs(v) >= 1 ? d3.format(".3~f")(v) : d3.format(".3~g")(v);
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const status = (t, err = false) => { $("status").textContent = t; $("status").classList.toggle("err", err); };
const product = () => PRODUCTS[`${st.level}:${st.level === "adm2" ? "wb" : st.sys}`];
const timeCol = () => (st.freq === "monthly" ? "date" : "year");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const palette = ["#1f6feb", "#d9480f", "#2f9e44", "#ae3ec9", "#f59f00", "#0c8599", "#e64980", "#5c7cfa"];

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
function rewind(fc) {
  for (const f of fc.features) {
    const g = f.geometry; if (!g) continue;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
    for (const p of polys) if (d3.geoArea({ type: "Polygon", coordinates: p }) > 2 * Math.PI) p.forEach((r) => r.reverse());
  }
  return fc;
}
const label = (c) => st.dict[c]?.label || c;
const unit = (c) => st.dict[c]?.unit || "";

// ------------------------------------------------------------------ filtering
function covOf(r) {
  if (r.coverage != null) return r.coverage;
  if (r.coverage_monthly_mean != null) return r.coverage_monthly_mean;
  if (r.ntl_quality_prop_na != null) return 1 - r.ntl_quality_prop_na;
  return null;
}
function passes(r) {
  const y = st.freq === "monthly" ? +String(r.date).slice(0, 4) : r.year;
  if (y < st.y0 || y > st.y1) return false;
  const minCov = +$("minCov").value;
  const c = covOf(r);
  if (minCov > 0 && (c == null || c < minCov)) return false;
  if ($("noEst").checked && (r.w_valid_estimated_share ?? 0) > 0.1) return false;
  if ($("noEst").checked && r.w_valid_estimated === true) return false;
  if ($("hiMatch").checked && st.sys === "gadm" && st.level === "adm1" && r.xw_match_quality !== "high") return false;
  return true;
}
const filtered = () => st.rows.filter(passes);
function periods(rows) { return [...new Set(rows.map((r) => r[timeCol()]))].sort(); }

// ------------------------------------------------------------------ init
async function init() {
  const [index, dict] = await Promise.all([getJSON(D + "index.json"), getJSON(D + "data_dictionary.json")]);
  if (!index) { status("Could not load the country index.", true); return; }
  st.index = index;
  for (const c of dict?.columns || []) st.dict[c.column] = { label: c.description.split(". ")[0].replace(/\.$/, ""), unit: c.unit, desc: c.description };
  const dl = $("countrylist");
  for (const c of index) { const o = document.createElement("option"); o.value = `${c.name} (${c.iso})`; dl.appendChild(o); }
  for (let y = 2012; y <= 2025; y++) { $("y0").add(new Option(y, y)); $("y1").add(new Option(y, y)); }
  $("y0").value = 2012; $("y1").value = 2025;

  $("country").addEventListener("change", onCountry);
  $("country").addEventListener("keydown", (e) => e.key === "Enter" && onCountry());
  document.querySelectorAll("[data-level]").forEach((b) => b.addEventListener("click", () => setSeg("level", b.dataset.level)));
  document.querySelectorAll("[data-sys]").forEach((b) => b.addEventListener("click", () => setSeg("sys", b.dataset.sys)));
  document.querySelectorAll("[data-freq]").forEach((b) => b.addEventListener("click", () => setSeg("freq", b.dataset.freq)));
  document.querySelectorAll("[data-view]").forEach((b) => b.addEventListener("click", () => { st.view = b.dataset.view; syncTabs(); syncHash(); render(); }));
  for (const id of ["y0", "y1"]) $(id).addEventListener("change", () => { st.y0 = +$("y0").value; st.y1 = Math.max(+$("y1").value, st.y0); $("y1").value = st.y1; st.period = null; render(); });
  $("indicator").addEventListener("change", (e) => { st.indicator = e.target.value; render(); });
  for (const id of ["minCov", "noEst", "hiMatch"]) $(id).addEventListener("change", render);
  $("exportCsv").addEventListener("click", exportCsv);
  window.addEventListener("resize", debounce(render, 200));

  const h = new URLSearchParams(location.hash.slice(1));
  if (h.get("c")) { st.level = h.get("l") || st.level; st.sys = h.get("s") || st.sys; st.freq = h.get("f") || st.freq; }
  if (["map", "series", "change", "flares", "quality", "compare", "table"].includes(h.get("v"))) st.view = h.get("v");
  syncSegs(); syncTabs();
  const iso = h.get("c");
  if (iso && index.find((c) => c.iso === iso)) await selectCountry(iso);
  else { showEmpty("Choose a country to begin.", "Type a name in the Country box, e.g. Algeria, India or Kenya."); }
}
function debounce(fn, ms) { let t; return () => { clearTimeout(t); t = setTimeout(fn, ms); }; }

function setSeg(kind, val) {
  st[kind] = val;
  if (st.level === "adm2" && st.freq === "annual_from_monthly") st.freq = "annual";
  syncSegs(); load();
}
function syncSegs() {
  document.querySelectorAll("[data-level]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.level === st.level));
  document.querySelectorAll("[data-sys]").forEach((b) => {
    b.setAttribute("aria-pressed", st.level === "adm2" ? b.dataset.sys === "wb" : b.dataset.sys === st.sys);
    b.disabled = st.level === "adm2" && b.dataset.sys === "gadm";
  });
  document.querySelectorAll("[data-freq]").forEach((b) => {
    b.setAttribute("aria-pressed", b.dataset.freq === st.freq);
    b.disabled = st.level === "adm2" && b.dataset.freq === "annual_from_monthly";
  });
  $("sysNote").textContent = st.level === "adm2" ? "ADM2 is published natively on the World Bank source units only."
    : st.sys === "gadm" ? "Crosswalked: districts assigned whole to the GADM unit they overlap most." : "Exact aggregation of the source districts.";
  $("hiMatch").disabled = !(st.level === "adm1" && st.sys === "gadm");
}
function syncHash() {
  if (st.iso) history.replaceState(null, "", `#c=${st.iso}&l=${st.level}&s=${st.sys}&f=${st.freq}&v=${st.view}`);
}
function syncTabs() { document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-selected", b.dataset.view === st.view)); }

function onCountry() {
  const v = $("country").value.trim();
  const m = v.match(/\(([A-Z]{3})\)$/);
  const hit = m ? st.index.find((c) => c.iso === m[1]) : st.index.find((c) => c.name.toLowerCase() === v.toLowerCase() || c.iso === v.toUpperCase());
  if (hit) selectCountry(hit.iso);
}
async function selectCountry(iso) {
  st.iso = iso; st.selected = []; st.period = null;
  const c = st.index.find((x) => x.iso === iso);
  $("country").value = `${c.name} (${c.iso})`;
  await load();
}

// ------------------------------------------------------------------ load
async function load() {
  if (!st.iso) return;
  const p = product();
  syncHash();
  const url = `${D}${p.dir}/${st.freq}/${st.iso}.parquet`;
  status("Loading…");
  const rows = await getParquet(url);
  if (!rows || !rows.length) {
    st.rows = []; st.cols = [];
    status("");
    showEmpty(`No ${p.label} data for this country.`, st.sys === "gadm"
      ? "None of this country's source districts could be assigned to a GADM 4.1 unit with confidence (see Methods). Use the World Bank units instead."
      : "The source has no observations for this selection.");
    fillFullFiles(null); return;
  }
  st.rows = rows;
  st.cols = Object.keys(rows[0]);
  const num = st.cols.filter((k) => rows.some((r) => typeof r[k] === "number") && !["year", "month"].includes(k));
  const prefer = ["ntl_sum", "ntl_mean", "ntl_nogf_5km_sum", "ntl_sum_monthly_mean", "ntl_mean_from_monthly"];
  if (!num.includes(st.indicator)) st.indicator = prefer.find((k) => num.includes(k)) || num[0];
  const sel = $("indicator"); sel.innerHTML = "";
  for (const k of num) sel.add(new Option(`${k}${unit(k) ? "  [" + unit(k) + "]" : ""}`, k, false, k === st.indicator));
  $("indNote").textContent = st.dict[st.indicator]?.desc || "";
  sel.onchange = (e) => { st.indicator = e.target.value; $("indNote").textContent = st.dict[st.indicator]?.desc || ""; render(); };
  buildColumnChecks();
  fillFullFiles(p);
  // default selection: brightest units in the last period
  const last = periods(rows).at(-1);
  const top = rows.filter((r) => r[timeCol()] === last && r.ntl_sum != null).sort((a, b) => b.ntl_sum - a.ntl_sum).slice(0, 5);
  st.selected = st.selected.filter((k) => rows.some((r) => r[p.key] === k));
  if (!st.selected.length) st.selected = top.map((r) => r[p.key]);
  status(`${rows.length.toLocaleString()} rows loaded`);
  $("exportCsv").disabled = false;
  render();
}

function buildColumnChecks() {
  const box = $("cols"); box.innerHTML = "";
  const p = product();
  const defaults = new Set(["ISO_A3", p.key, p.name, "date", "year", "month", "ntl_sum", "ntl_mean", "ntl_nogf_5km_sum", "coverage",
    "w_valid_estimated_share", "xw_match_quality", "GADM41_GID_1", "has_valid_data", "ntl_sum_monthly_mean", "n_months_with_data"]);
  for (const c of st.cols) {
    const l = document.createElement("label");
    l.innerHTML = `<input type="checkbox" value="${esc(c)}" ${defaults.has(c) ? "checked" : ""}> <span class="mono">${esc(c)}</span>`;
    l.title = st.dict[c]?.desc || "";
    box.appendChild(l);
  }
}
function fillFullFiles(p) {
  const el = $("fullFiles");
  if (!p || !st.iso) { el.innerHTML = ""; return; }
  const base = `${D}${p.dir}/${st.freq}/${st.iso}`;
  el.innerHTML = `<a href="${base}.csv" download>${st.iso} ${st.freq} CSV</a> · <a href="${base}.parquet" download>Parquet</a> · <a href="download.html">all files &amp; Stata</a>`;
}

// ------------------------------------------------------------------ rendering
function showOnly(which) {
  for (const id of ["map", "chart", "tableWrap", "empty"]) $(id).hidden = id !== which;
  if (which !== "map" && which !== "chart") $("legend").innerHTML = "";
}
function showEmpty(title, body) {
  showOnly("empty"); $("empty").innerHTML = `<div><b>${esc(title)}</b>${esc(body)}</div>`;
  $("legend").innerHTML = ""; $("viewControls").innerHTML = "";
}
function render() {
  syncSegs();
  const p = product();
  $("selList").textContent = st.selected.length ? st.selected.map((k) => nameOf(k)).join(", ") : "none";
  if (!st.iso) return;
  if (!st.rows.length) return;
  const c = st.index.find((x) => x.iso === st.iso);
  $("viewTitle").textContent = `${c.name} · ${p.label} · ${st.freq.replaceAll("_", " ")}`;
  ({ map: renderMap, series: renderSeries, change: renderChange, flares: renderFlares, quality: renderQuality,
     compare: renderCompare, table: renderTable })[st.view]();
}
const nameOf = (k) => { const p = product(); const r = st.rows.find((x) => x[p.key] === k); return r ? r[p.name] || k : k; };
function toggleSel(k) {
  const i = st.selected.indexOf(k);
  if (i >= 0) st.selected.splice(i, 1); else { st.selected.push(k); if (st.selected.length > MAX_SEL) st.selected.shift(); }
  render();
}
function tooltip(html, ev) {
  const t = $("tooltip"); if (!html) { t.hidden = true; return; }
  t.innerHTML = html; t.hidden = false;
  t.style.left = `${Math.min(ev.clientX + 14, innerWidth - 290)}px`; t.style.top = `${ev.clientY + 14}px`;
}

// ---- map
async function renderMap() {
  const p = product();
  const rows = filtered();
  const ps = periods(rows);
  if (!ps.length) return showEmpty("No rows pass the current filters.", "Widen the year range or relax the quality criteria.");
  if (!st.period || !ps.includes(st.period)) st.period = ps.at(-1);
  $("viewControls").innerHTML = `Period <select id="periodSel" style="width:auto;display:inline-block">${ps.map((x) => `<option ${x === st.period ? "selected" : ""}>${x}</option>`).join("")}</select>`;
  $("periodSel").onchange = (e) => { st.period = isNaN(+e.target.value) ? e.target.value : +e.target.value; renderMap(); };
  if (!p.geo) {
    return showEmpty("No map for GADM units.",
      "GADM's licence does not allow redistributing its boundaries, so GADM 4.1 results are shown as tables and charts only. Switch to World Bank units for a map.");
  }
  const url = `${p.geo}${st.iso}.geojson`;
  if (!st.geoCache.has(url)) st.geoCache.set(url, getJSON(url).then((g) => (g ? rewind(g) : null)));
  const geo = await st.geoCache.get(url);
  if (!geo || !geo.features.length) {
    return showEmpty("No map outline for this country at this level.",
      "Its source units could not be matched safely to today's World Bank outlines (codes were reused or units reorganised). All data remain available in the other views and downloads.");
  }
  showOnly("map");
  const el = $("map"); el.innerHTML = "";
  const { width, height } = el.getBoundingClientRect();
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const vals = new Map(rows.filter((r) => r[timeCol()] === st.period).map((r) => [r[p.key], r[st.indicator]]));
  const pos = [...vals.values()].filter((v) => v > 0).sort(d3.ascending);
  const lo = d3.quantile(pos, 0.02) ?? 0.001, hi = d3.max(pos) ?? 1;
  const useLog = pos.length && hi / Math.max(lo, 1e-9) > 50;
  const ramp = (t) => d3.interpolateBlues(0.15 + 0.85 * t);       // keep the lightest class visible on a light page
  const sc = (useLog ? d3.scaleSequentialLog() : d3.scaleSequential()).domain(useLog ? [Math.max(lo, 1e-6), hi] : [d3.min(pos) ?? 0, hi]).interpolator(ramp).clamp(true);
  const color = (v) => (v == null ? css("--nodata") : v <= 0 ? ramp(0) : sc(v));
  const cen = d3.geoCentroid(geo);
  const proj = d3.geoMercator().rotate([-cen[0], 0]).fitExtent([[6, 6], [width - 6, height - 6]], geo);
  const path = d3.geoPath(proj);
  svg.append("g").selectAll("path").data(geo.features).join("path")
    .attr("class", (d) => "unit" + (st.selected.includes(d.properties.code) ? " sel" : ""))
    .attr("d", path).attr("fill", (d) => color(vals.get(d.properties.code)))
    .on("mousemove", (ev, d) => tooltip(`<b>${esc(d.properties.name)}</b>${esc(st.indicator)}: ${fmt(vals.get(d.properties.code))}<br><span class="muted">${esc(d.properties.code)} · ${st.period}</span>`, ev))
    .on("mouseleave", () => tooltip(null))
    .on("click", (ev, d) => toggleSel(d.properties.code));
  svg.selectAll(".unit.sel").raise();
  const nAll = new Set(st.rows.map((r) => r[p.key])).size;
  const stops = d3.range(0, 1.01, 0.1).map((t) => `${ramp(t)} ${t * 100}%`).join(",");
  $("legend").innerHTML = `<span>${fmt(sc.domain()[0])}</span><span class="ramp" style="background:linear-gradient(90deg,${stops})"></span><span>${fmt(hi)}</span>
    <span>${esc(unit(st.indicator))}${useLog ? " · log scale" : ""}</span><span class="tag">${geo.features.length} of ${nAll} units have an outline</span><span class="tag">grey = filtered out / no data</span>`;
}

// ---- generic line chart
function lineChart(series, { yLabel = "", zeroBase = true } = {}) {
  showOnly("chart");
  const el = $("chart"); el.innerHTML = "";
  const { width, height } = el.getBoundingClientRect();
  const mg = { t: 10, r: 14, b: 28, l: 62 };
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const parse = (t) => (typeof t === "number" ? new Date(Date.UTC(t, 6, 1)) : new Date(t + "-01T00:00:00Z"));
  const all = series.flatMap((s) => s.points.filter((d) => d.v != null));
  if (!all.length) return showEmpty("No values to plot.", "All values are missing or filtered out for this selection.");
  const x = d3.scaleUtc().domain(d3.extent(all, (d) => parse(d.t))).range([mg.l, width - mg.r]);
  const ext = d3.extent(all, (d) => d.v);
  const y = d3.scaleLinear().domain(zeroBase ? [Math.min(0, ext[0]), ext[1] * 1.05] : [ext[0], ext[1]]).nice().range([height - mg.b, mg.t]);
  svg.append("g").attr("class", "grid-line").attr("transform", `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickSize(-(width - mg.l - mg.r)).tickFormat(""));
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - mg.b})`).call(d3.axisBottom(x).ticks(width < 560 ? 5 : 10).tickSizeOuter(0));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(fmt).tickSizeOuter(0));
  series.forEach((s, i) => {
    const col = s.color || palette[i % palette.length];
    svg.append("path").datum(s.points).attr("fill", "none").attr("stroke", col).attr("stroke-width", s.width || 1.8)
      .attr("stroke-dasharray", s.dash || null)
      .attr("d", d3.line().defined((d) => d.v != null).x((d) => x(parse(d.t))).y((d) => y(d.v)));
    if (s.points.length < 30) svg.append("g").selectAll("circle").data(s.points.filter((d) => d.v != null)).join("circle")
      .attr("r", 3).attr("fill", col).attr("cx", (d) => x(parse(d.t))).attr("cy", (d) => y(d.v));
  });
  // hover
  const ts = [...new Set(all.map((d) => d.t))].sort();
  const fx = svg.append("line").attr("y1", mg.t).attr("y2", height - mg.b).attr("stroke", css("--muted")).attr("stroke-dasharray", "3 3").style("display", "none");
  svg.append("rect").attr("x", mg.l).attr("y", mg.t).attr("width", width - mg.l - mg.r).attr("height", height - mg.t - mg.b).attr("fill", "transparent")
    .on("mousemove", (ev) => {
      const [px] = d3.pointer(ev); const tx = x.invert(px);
      const t = ts.reduce((a, b) => (Math.abs(parse(b) - tx) < Math.abs(parse(a) - tx) ? b : a));
      fx.style("display", null).attr("x1", x(parse(t))).attr("x2", x(parse(t)));
      tooltip(`<b>${t}</b>` + series.map((s, i) => { const d = s.points.find((q) => q.t === t); return `<span style="color:${s.color || palette[i % palette.length]}">■</span> ${esc(s.name)}: ${fmt(d?.v)}`; }).join("<br>"), ev);
    })
    .on("mouseleave", () => { fx.style("display", "none"); tooltip(null); });
  $("legend").innerHTML = `<div class="series-legend">${series.map((s, i) => `<span><i style="background:${s.color || palette[i % palette.length]}"></i>${esc(s.name)}</span>`).join("")}</div>
    <span class="muted">${esc(yLabel)}</span>`;
}
function seriesFor(key, col, rows) {
  const p = product();
  const ps = periods(st.rows.filter((r) => { const y = st.freq === "monthly" ? +String(r.date).slice(0, 4) : r.year; return y >= st.y0 && y <= st.y1; }));
  const ok = new Map(rows.filter((r) => r[p.key] === key).map((r) => [r[timeCol()], r[col]]));
  return ps.map((t) => ({ t, v: ok.has(t) ? ok.get(t) : null }));
}

function renderSeries() {
  $("viewControls").innerHTML = "Lines break where a period is missing or fails the quality criteria.";
  if (!st.selected.length) return showEmpty("No regions selected.", "Click regions on the map or in the table.");
  const rows = filtered();
  lineChart(st.selected.map((k) => ({ name: nameOf(k), points: seriesFor(k, st.indicator, rows) })),
    { yLabel: `${st.indicator} ${unit(st.indicator) ? "[" + unit(st.indicator) + "]" : ""}` });
}

function renderChange() {
  if (st.freq !== "annual" || !st.cols.includes("dln_ntl_sum")) {
    return showEmpty("Annual change needs the official annual series.", "Switch Frequency to Annual. Changes are year-on-year differences in log(ntl_sum) between consecutive years.");
  }
  const p = product();
  const rows = filtered().filter((r) => r.dln_ntl_sum != null);
  const years = [...new Set(rows.map((r) => r.year))].sort();
  if (!years.length) return showEmpty("No annual changes pass the filters.", "Relax the quality criteria or the year range.");
  if (!years.includes(st.changeYear)) st.changeYear = years.at(-1);
  $("viewControls").innerHTML = `Year <select id="cy" style="width:auto;display:inline-block">${years.map((y) => `<option ${y === st.changeYear ? "selected" : ""}>${y}</option>`).join("")}</select> · Δ log(ntl_sum) vs previous year`;
  $("cy").onchange = (e) => { st.changeYear = +e.target.value; renderChange(); };
  const data = rows.filter((r) => r.year === st.changeYear).map((r) => ({ k: r[p.key], n: r[p.name], v: r.dln_ntl_sum })).sort((a, b) => b.v - a.v);
  showOnly("chart");
  const el = $("chart"); el.innerHTML = "";
  const n = data.length; const rowH = 16;
  el.style.height = `${Math.max(340, n * rowH + 40)}px`;
  const { width } = el.getBoundingClientRect(); const height = Math.max(340, n * rowH + 40);
  const mg = { t: 10, r: 60, b: 24, l: Math.min(220, width * 0.35) };
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
  const x = d3.scaleLinear().domain(d3.extent([0, ...data.map((d) => d.v)])).nice().range([mg.l, width - mg.r]);
  const y = d3.scaleBand().domain(data.map((d) => d.k)).range([mg.t, height - mg.b]).padding(0.15);
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - mg.b})`).call(d3.axisBottom(x).ticks(6).tickFormat(d3.format("+.2f")));
  svg.append("g").selectAll("rect").data(data).join("rect").attr("x", (d) => x(Math.min(0, d.v))).attr("width", (d) => Math.abs(x(d.v) - x(0)))
    .attr("y", (d) => y(d.k)).attr("height", y.bandwidth()).attr("fill", (d) => (d.v >= 0 ? css("--blue") : "#d9480f"))
    .style("cursor", "pointer").on("click", (ev, d) => toggleSel(d.k))
    .on("mousemove", (ev, d) => tooltip(`<b>${esc(d.n)}</b>Δ log = ${d3.format("+.3f")(d.v)} (${d3.format("+.1%")(Math.exp(d.v) - 1)})`, ev)).on("mouseleave", () => tooltip(null));
  svg.append("g").selectAll("text").data(data).join("text").attr("x", mg.l - 6).attr("y", (d) => y(d.k) + y.bandwidth() / 2).attr("dy", "0.32em")
    .attr("text-anchor", "end").attr("font-size", 11).attr("fill", css("--muted")).text((d) => (d.n.length > 30 ? d.n.slice(0, 29) + "…" : d.n));
  svg.append("line").attr("x1", x(0)).attr("x2", x(0)).attr("y1", mg.t).attr("y2", height - mg.b).attr("stroke", css("--text"));
  $("legend").innerHTML = `<span class="muted">${n} units with a valid change in ${st.changeYear}. Click a bar to select the region.</span>`;
}

function renderFlares() {
  if (!st.selected.length) return showEmpty("No region selected.", "Select a region to compare total and flare-excluded light.");
  const k = st.selected[0];
  const rows = filtered();
  const tot = st.freq === "annual_from_monthly" ? "ntl_sum_monthly_mean" : "ntl_sum";
  const ex = st.freq === "annual_from_monthly" ? "ntl_nogf_5km_sum_monthly_mean" : "ntl_nogf_5km_sum";
  $("viewControls").innerHTML = `First selected region: <b>${esc(nameOf(k))}</b>. Gas-flare light = total − light more than 5 km from any flaring site.`;
  lineChart([{ name: "All light", points: seriesFor(k, tot, rows), color: palette[0] },
    { name: "Excluding ≤5 km of gas flares", points: seriesFor(k, ex, rows), color: palette[1], dash: "5 3" }], { yLabel: unit("ntl_sum") });
}

function renderQuality() {
  if (!st.selected.length) return showEmpty("No region selected.", "Select a region to inspect observation quality.");
  const k = st.selected[0];
  const rows = st.rows.filter((r) => { const y = st.freq === "monthly" ? +String(r.date).slice(0, 4) : r.year; return y >= st.y0 && y <= st.y1; });
  $("viewControls").innerHTML = `First selected region: <b>${esc(nameOf(k))}</b>. Unfiltered, so you can see what the quality criteria remove.`;
  if (st.freq === "annual_from_monthly") {
    return lineChart([{ name: "Average monthly coverage", points: seriesFor(k, "coverage_monthly_mean", rows) },
      { name: "Months with data / 12", points: seriesFor(k, "n_months_with_data", rows).map((d) => ({ t: d.t, v: d.v == null ? null : d.v / 12 })) }], { yLabel: "share" });
  }
  const cov = st.level === "adm2" ? seriesFor(k, "ntl_quality_prop_na", rows).map((d) => ({ t: d.t, v: d.v == null ? null : 1 - d.v })) : seriesFor(k, "coverage", rows);
  lineChart([
    { name: "Coverage (valid pixels)", points: cov, color: "#0d1b33", width: 2.4 },
    { name: "Good (>3 clear nights)", points: seriesFor(k, "ntl_quality_prop_0_good", rows), color: palette[2] },
    { name: "Poor (≤3 clear nights)", points: seriesFor(k, "ntl_quality_prop_1_poor", rows), color: palette[4] },
    { name: "Gap-filled", points: seriesFor(k, "ntl_quality_prop_2_gapfilled", rows), color: palette[1] },
    { name: "Missing", points: seriesFor(k, "ntl_quality_prop_na", rows), color: "#868e96", dash: "4 3" },
  ], { yLabel: "share of pixels" });
}

async function renderCompare() {
  const f = st.freq === "annual_from_monthly" ? "annual" : st.freq;
  $("viewControls").innerHTML = `Country total of <b>ntl_sum</b> (${f}) from the three products. ADM2 and World Bank ADM1 must coincide; the GADM line falls below them by the light of unassigned districts.`;
  status("Loading comparison…");
  const [a2, wb, gd] = await Promise.all(["adm2", "adm1_wb", "adm1_gadm41"].map((d) => getParquet(`${D}${d}/${f}/${st.iso}.parquet`)));
  status("");
  const t = f === "monthly" ? "date" : "year";
  const tot = (rows) => {
    const m = d3.rollup((rows || []).filter((r) => { const y = f === "monthly" ? +String(r.date).slice(0, 4) : r.year; return y >= st.y0 && y <= st.y1; }),
      (v) => (v.every((r) => r.ntl_sum == null) ? null : d3.sum(v, (r) => r.ntl_sum)), (r) => r[t]);
    return [...m].sort((a, b) => (a[0] > b[0] ? 1 : -1)).map(([k, v]) => ({ t: k, v }));
  };
  lineChart([
    { name: "ADM2 native (sum of districts)", points: tot(a2), color: "#868e96", width: 5 },
    { name: "ADM1 · World Bank units", points: tot(wb), color: palette[0] },
    { name: "ADM1 · GADM 4.1", points: tot(gd), color: palette[1], dash: "5 3" },
  ], { yLabel: unit("ntl_sum") });
}

function renderTable() {
  const p = product();
  const rows = filtered();
  $("viewControls").innerHTML = `${rows.length.toLocaleString()} rows pass the filters${rows.length > 1000 ? " (first 1,000 shown; the export contains all)" : ""}. Click a row to select its region.`;
  if (!rows.length) return showEmpty("No rows pass the current filters.", "Widen the year range or relax the quality criteria.");
  showOnly("tableWrap");
  const cols = exportCols();
  $("table").querySelector("thead").innerHTML = `<tr>${cols.map((c) => `<th class="${typeof rows[0][c] === "number" ? "num" : ""}" title="${esc(st.dict[c]?.desc || "")}">${esc(c)}</th>`).join("")}</tr>`;
  $("table").querySelector("tbody").innerHTML = rows.slice(0, 1000).map((r) =>
    `<tr data-k="${esc(r[p.key])}">${cols.map((c) => `<td class="${typeof r[c] === "number" ? "num" : ""}">${typeof r[c] === "number" ? fmt(r[c]) : esc(r[c])}</td>`).join("")}</tr>`).join("");
  $("table").querySelectorAll("tbody tr").forEach((tr) => tr.addEventListener("click", () => toggleSel(tr.dataset.k)));
}

// ------------------------------------------------------------------ export
function exportCols() { return [...$("cols").querySelectorAll("input:checked")].map((i) => i.value); }
function exportCsv() {
  const rows = filtered(); const cols = exportCols();
  if (!rows.length || !cols.length) { status("Nothing to export with the current filters.", true); return; }
  const q = (v) => (v == null ? "" : typeof v === "number" ? String(v) : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => q(r[c])).join(","))].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `ntl_${product().dir}_${st.freq}_${st.iso}_${st.y0}-${st.y1}.csv`;
  a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  status(`Exported ${rows.length.toLocaleString()} rows × ${cols.length} columns.`);
}

init();
