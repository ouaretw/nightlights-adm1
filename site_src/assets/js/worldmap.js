// Home-page world map: every World Bank ADM1 unit with a safe outline, coloured by
// its official annual Black Marble value (data/geo/world_adm1_values.json, a display
// copy of adm1_wb_annual_global). Light "scientific cartography" theme.
import { esc, fmt, fmtExact, pct, seqColors, quantileBreaks, classifier, legendHTML, rewind, addPatterns, addZoom, showTip } from "./carto.js";

const $ = (id) => document.getElementById(id);
const IND = {
  mean: { label: "Mean radiance per valid pixel", short: "Mean radiance", unit: "nW·cm⁻²·sr⁻¹", col: "ntl_mean",
    help: "Comparable between large and small provinces." },
  sum: { label: "Sum of radiance over the province", short: "Sum of lights", unit: "nW·cm⁻²·sr⁻¹ × pixels", col: "ntl_sum",
    help: "Grows with both brightness and area." },
};
const K = 7;
const COLORS = seqColors(K);
const st = { ind: "mean", yi: 0, years: [], units: {}, cls: {}, breaks: {} };

function legend() {
  const i = IND[st.ind];
  $("wmLegend").innerHTML = legendHTML({
    title: `${i.label}, ${st.years[st.yi]}`, unitLabel: i.unit, breaks: st.breaks[st.ind], colors: COLORS,
    swatches: [
      { cls: "sw-zero", label: "0 — observed, no detectable light" },
      { cls: "sw-missing", label: "No valid observation in this year" },
      { cls: "sw-unmatched", label: "No province outline (data in downloads)" },
      { cls: "sw-ndlsa", label: "Non-determined legal status" },
    ],
    note: `${K} quantile classes of all province-year values ${st.years[0]}–${st.years.at(-1)} (positive values; no transformation). ` +
      `Class limits are fixed across years, so colour changes reflect changes in the data. ${esc(i.help)}`,
  });
  $("wmTitle").textContent = `${i.short} by province (ADM1), ${st.years[st.yi]}`;
  $("wmYearOut").textContent = st.years[st.yi];
}

async function init() {
  const el = $("worldmap");
  let geo, ctry, ndlsa, vals;
  try {
    [geo, ctry, ndlsa, vals] = await Promise.all(["data/geo/world_adm1.geojson", "data/geo/adm0_world.geojson",
      "data/geo/ndlsa.geojson", "data/geo/world_adm1_values.json"].map((u) => fetch(u).then((r) => (r.ok ? r.json() : null))));
  } catch (e) { console.error(e); }
  if (!geo || !vals || !ctry) { el.innerHTML = '<p class="map-msg">The map could not be loaded. All data remain available from the Explore and Download pages.</p>'; return; }
  st.years = vals.years; st.units = vals.units; st.yi = st.years.length - 1;
  for (const k of Object.keys(IND)) {
    const all = []; for (const u of Object.values(st.units)) for (const v of u[k]) if (v > 0) all.push(v);
    st.breaks[k] = quantileBreaks(all, K);
    st.cls[k] = classifier({ breaks: st.breaks[k], colors: COLORS });
  }
  ctry.features = ctry.features.filter((f) => f.properties.iso !== "ATA");
  [geo, ctry].forEach(rewind); if (ndlsa) rewind(ndlsa);

  const yr = $("wmYear"); yr.min = 0; yr.max = st.years.length - 1; yr.value = st.yi;
  yr.setAttribute("aria-valuetext", st.years[st.yi]);
  $("wmCount").textContent = `${vals.n_units_mapped.toLocaleString()} of ${vals.n_units_total.toLocaleString()}`;

  const W = 1000, H = 480;
  const proj = d3.geoEqualEarth().fitExtent([[6, 6], [W - 6, H - 6]], ctry);
  const path = d3.geoPath(proj);
  el.innerHTML = "";
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
    .attr("aria-label", "World map of nighttime lights by province. Use the country box to zoom to a country.");
  addPatterns(svg);
  const g = svg.append("g");
  g.append("g").selectAll("path").data(ctry.features).join("path").attr("class", "land").attr("d", path);
  const units = g.append("g").selectAll("path").data(geo.features).join("path").attr("class", "u").attr("d", path)
    .on("mousemove", (ev, d) => {
      const u = st.units[d.properties.code]; if (!u) return;
      const v = u[st.ind][st.yi], c = u.cov?.[st.yi];
      const val = v == null ? "No valid observation" : v === 0 ? "0 (observed, no detectable light)" : `${fmtExact(v)} <span class="muted">${IND[st.ind].unit}</span>`;
      showTip($("wmTip"), `<b>${esc(u.name)}</b><span class="muted">${esc(u.country)} · <span class="v">${esc(d.properties.code)}</span></span><br>
        ${esc(IND[st.ind].short)}, ${st.years[st.yi]}: <span class="v">${val}</span><br>
        Valid-pixel coverage: <span class="v">${pct(c)}</span><br><span class="muted">Click to open in the explorer</span>`, ev);
    })
    .on("mouseleave", () => showTip($("wmTip"), null))
    .on("click", (ev, d) => {
      location.href = `explore.html#c=${d.properties.iso}&l=adm1&s=wb&f=annual&v=map&p=${st.years[st.yi]}&r=${encodeURIComponent(d.properties.code)}`;
    });
  g.append("path").datum({ type: "FeatureCollection", features: ctry.features }).attr("class", "borders").attr("d", path);
  if (ndlsa) g.append("g").selectAll("path").data(ndlsa.features).join("path").attr("class", "ndlsa").attr("d", path);
  const z = addZoom({ svg, g, frame: el.parentElement, width: W, height: H, maxScale: 30 });

  const paint = () => {
    const c = st.cls[st.ind];
    units.each(function (d) {
      const u = st.units[d.properties.code];
      const r = c(u ? u[st.ind][st.yi] : null);
      this.setAttribute("fill", r.color);
      this.classList.toggle("zero", r.cls === "zero");
    });
    legend();
  };
  paint();

  document.querySelectorAll("[data-wm]").forEach((b) => b.addEventListener("click", () => {
    st.ind = b.dataset.wm;
    document.querySelectorAll("[data-wm]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    paint();
  }));
  yr.addEventListener("input", (e) => { st.yi = +e.target.value; yr.setAttribute("aria-valuetext", st.years[st.yi]); paint(); });

  // keyboard path: zoom to a country, then open it in the explorer
  const byIso = new Map(ctry.features.map((f) => [f.properties.iso, f]));
  const names = [...new Map(Object.values(st.units).map((u) => [u.iso, u.country])).entries()].sort((a, b) => a[1].localeCompare(b[1]));
  const dl = $("wmCountries");
  for (const [iso, name] of names) dl.appendChild(new Option(`${name} (${iso})`));
  const go = () => {
    const m = $("wmCountry").value.match(/\(([A-Z]{3})\)\s*$/); const iso = m?.[1];
    const f = iso && byIso.get(iso);
    if (!f) { $("wmOpen").hidden = true; return; }
    z.zoomToBounds(path.bounds(f), 0.8);
    $("wmOpen").href = `explore.html#c=${iso}&l=adm1&s=wb&f=annual&v=map&p=${st.years[st.yi]}`;
    $("wmOpen").textContent = `Open ${names.find((n) => n[0] === iso)?.[1] || iso} in the explorer →`;
    $("wmOpen").hidden = false;
  };
  $("wmCountry").addEventListener("change", go);
  $("wmCountry").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); go(); } });
}
init();
