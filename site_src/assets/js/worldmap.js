// Landing-page world map: every World Bank ADM1 unit that has a safe outline,
// coloured by its official annual Black Marble value. Values come from
// data/geo/world_adm1_values.json (a display copy of adm1_wb_annual_global).
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (v) => v == null || !isFinite(v) ? "no data" : Math.abs(v) >= 1e6 ? d3.format(".3~s")(v)
  : Math.abs(v) >= 100 ? d3.format(",.0f")(v) : Math.abs(v) >= 1 ? d3.format(".3~f")(v) : d3.format(".2~g")(v);

const IND = {
  mean: { label: "Average brightness", unit: "nW/cm²/sr per pixel", note: "comparable between large and small provinces" },
  sum: { label: "Total light", unit: "nW/cm²/sr, summed over the province", note: "grows with both brightness and area" },
};
// 7 classes, each holding ~1/7 of all province-years (fixed across years so the
// slider shows real change): deep blue -> signal blue -> warm white
const CLASSES = ["#13306e", "#1b4cb0", "#2a6ee8", "#4f95fb", "#8cbcff", "#cde2ff", "#fff0b3"];
const NODATA = "#3b3f48";

const st = { ind: "mean", yi: 0, years: [], units: {}, scales: {}, playing: null };

function rewind(fc) {
  for (const f of fc.features) {
    const g = f.geometry; if (!g) continue;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
    for (const p of polys) if (d3.geoArea({ type: "Polygon", coordinates: p }) > 2 * Math.PI) p.forEach((r) => r.reverse());
  }
  return fc;
}

function buildScales() {
  for (const k of Object.keys(IND)) {
    const all = [];
    for (const u of Object.values(st.units)) for (const v of u[k]) if (v > 0) all.push(v);
    all.sort(d3.ascending);
    const nice = (v) => +d3.format(".2~g")(v);
    const breaks = d3.range(1, CLASSES.length).map((i) => nice(d3.quantile(all, i / CLASSES.length)));
    st.scales[k] = d3.scaleThreshold().domain(breaks).range(CLASSES);
  }
}
const colorOf = (code) => {
  const u = st.units[code]; if (!u) return NODATA;
  const v = u[st.ind][st.yi];
  return v == null ? NODATA : v <= 0 ? CLASSES[0] : st.scales[st.ind](v);
};

function legend() {
  const b = st.scales[st.ind].domain();
  const lab = (i) => i === 0 ? `< ${fmt(b[0])}` : i === CLASSES.length - 1 ? `≥ ${fmt(b.at(-1))}` : `${fmt(b[i - 1])}–${fmt(b[i])}`;
  $("wmLegend").innerHTML = `<span class="wm-classes">${CLASSES.map((c, i) => `<span class="key"><i style="background:${c}"></i>${lab(i)}</span>`).join("")}</span>
    <span>${esc(IND[st.ind].unit)} · each colour ≈ one seventh of provinces</span>
    <span class="key"><i style="background:${NODATA}"></i>no outline / no data</span>`;
  $("wmTitle").textContent = `${IND[st.ind].label} by province (ADM1), ${st.years[st.yi]}`;
  $("wmYearOut").textContent = st.years[st.yi];
}

function tip(html, ev) {
  const t = $("wmTip");
  if (!html) { t.hidden = true; return; }
  t.innerHTML = html; t.hidden = false;
  const r = t.getBoundingClientRect();
  t.style.left = Math.min(ev.clientX + 14, innerWidth - r.width - 8) + "px";
  t.style.top = Math.min(ev.clientY + 14, innerHeight - r.height - 8) + "px";
}

async function init() {
  const el = $("worldmap");
  let geo, ctry, ndlsa, vals;
  try {
    [geo, ctry, ndlsa, vals] = await Promise.all(["data/geo/world_adm1.geojson", "data/geo/adm0_world.geojson",
      "data/geo/ndlsa.geojson", "data/geo/world_adm1_values.json"].map((u) => fetch(u).then((r) => r.ok ? r.json() : null)));
  } catch (e) { console.error(e); }
  if (!geo || !vals || !ctry) { el.innerHTML = '<p class="wm-msg">The map could not be loaded. All data remain available from the Explore and Download pages.</p>'; return; }
  st.years = vals.years; st.units = vals.units; st.yi = st.years.length - 1;
  buildScales();
  ctry.features = ctry.features.filter((f) => f.properties.iso !== "ATA");
  [geo, ctry].forEach(rewind); if (ndlsa) rewind(ndlsa);

  $("wmYear").min = 0; $("wmYear").max = st.years.length - 1; $("wmYear").value = st.yi;
  $("wmCount").textContent = `${vals.n_units_mapped.toLocaleString()} of ${vals.n_units_total.toLocaleString()}`;

  const W = 1000, H = 470;
  const proj = d3.geoEqualEarth().fitExtent([[4, 4], [W - 4, H - 4]], ctry);
  const path = d3.geoPath(proj);
  el.innerHTML = "";
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
    .attr("aria-label", "World map of nighttime lights by province");
  const defs = svg.append("defs");
  defs.append("pattern").attr("id", "hatch").attr("width", 4).attr("height", 4).attr("patternUnits", "userSpaceOnUse")
    .attr("patternTransform", "rotate(45)").append("rect").attr("width", 1.2).attr("height", 4).attr("fill", "#7d8bab");
  const g = svg.append("g");
  g.append("g").selectAll("path").data(ctry.features).join("path").attr("class", "wm-land").attr("d", path);
  const units = g.append("g").selectAll("path").data(geo.features).join("path")
    .attr("class", "wm-unit").attr("d", path)
    .on("mousemove", (ev, d) => {
      const u = st.units[d.properties.code];
      const v = u ? u[st.ind][st.yi] : null;
      tip(u ? `<b>${esc(u.name)}</b>${esc(u.country)}<br>${esc(IND[st.ind].label)} ${st.years[st.yi]}: <b>${fmt(v)}</b>
        <br><span class="muted">${esc(d.properties.code)} · click to explore ${esc(u.country)}</span>` : esc(d.properties.code), ev);
    })
    .on("mouseleave", () => tip(null))
    .on("click", (ev, d) => { location.href = `explore.html#c=${d.properties.iso}&l=adm1&s=wb&f=annual&v=map`; });
  g.append("path").datum({ type: "FeatureCollection", features: ctry.features }).attr("class", "wm-borders").attr("d", path);
  if (ndlsa) g.append("g").selectAll("path").data(ndlsa.features).join("path").attr("class", "wm-ndlsa").attr("d", path);

  const paint = () => { units.attr("fill", (d) => colorOf(d.properties.code)); legend(); };
  paint();

  // zoom: buttons, drag, double-click, ctrl/pinch wheel (plain wheel keeps scrolling the page)
  const zoom = d3.zoom().scaleExtent([1, 12]).translateExtent([[0, 0], [W, H]])
    .filter((ev) => ev.type === "wheel" ? ev.ctrlKey : !ev.button)
    .on("zoom", (ev) => { g.attr("transform", ev.transform); });
  svg.call(zoom);
  $("wmIn").onclick = () => svg.transition().duration(300).call(zoom.scaleBy, 1.8);
  $("wmOut").onclick = () => svg.transition().duration(300).call(zoom.scaleBy, 1 / 1.8);
  $("wmReset").onclick = () => svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);

  document.querySelectorAll("[data-wm]").forEach((b) => b.addEventListener("click", () => {
    st.ind = b.dataset.wm;
    document.querySelectorAll("[data-wm]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    paint();
  }));
  $("wmYear").addEventListener("input", (e) => { st.yi = +e.target.value; paint(); });
  $("wmPlay").addEventListener("click", () => {
    if (st.playing) { clearInterval(st.playing); st.playing = null; $("wmPlay").textContent = "▶ Play"; return; }
    if (st.yi === st.years.length - 1) st.yi = -1;
    $("wmPlay").textContent = "❚❚ Pause";
    st.playing = setInterval(() => {
      st.yi += 1; $("wmYear").value = st.yi; paint();
      if (st.yi >= st.years.length - 1) { clearInterval(st.playing); st.playing = null; $("wmPlay").textContent = "▶ Play"; }
    }, 700);
  });
}
init();
