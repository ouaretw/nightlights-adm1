// Home-page world map. Two levels:
//   ADM1 - every World Bank ADM1 unit with a safe outline, coloured by its official annual
//          value (data/geo/world_adm1_values.json, display copy of adm1_wb_annual_global);
//   ADM0 - countries coloured by national values (data/v2/analysis/national.json: exact sums of
//          the ADM1 rows; per-person values use WDI population). Taiwan is shown from the
//          source's China unit "Taiwan Sheng", as in the national panel.
import { esc, fmt, fmtExact, pct, seqColors, quantileBreaks, classifier, legendHTML, rewind, addPatterns, addZoom, showTip } from "./carto.js";

const $ = (id) => document.getElementById(id);
const IND = {
  mean: { label: "Mean radiance per valid pixel", short: "Mean radiance", unit: "nW·cm⁻²·sr⁻¹",
    help: "An intensity measure, comparable between large and small units." },
  sum: { label: "Total radiance", short: "Total radiance", unit: "nW·cm⁻²·sr⁻¹ × px",
    help: "Grows with brightness, population and area." },
  pc: { label: "Total radiance per person", short: "Radiance per person", unit: "nW·cm⁻²·sr⁻¹ × px per person",
    help: "Total radiance ÷ WDI population of the same year. Available for countries only: no global ADM1 population is integrated." },
};
const IMF = { advanced: "IMF advanced economy", emde: "IMF emerging market / developing economy", not_classified: "Not in the IMF classification" };
const K = 7;
const COLORS = seqColors(K);
const st = { lvl: "adm1", ind: "mean", yi: 0, years: [], units: {}, nat: null, cls: {}, breaks: {} };

const natVal = (e, ind, i) => {
  if (!e || i < 0) return null;
  if (ind === "pc") return e.sum[i] != null && e.pop[i] > 0 ? e.sum[i] / e.pop[i] : null;
  return e[ind][i];
};

function legend() {
  const i = IND[st.ind], key = `${st.lvl}:${st.ind}`;
  const sw = [{ cls: "sw-zero", label: "0 — observed, no detectable light" },
    { cls: "sw-missing", label: st.lvl === "adm0" ? "No value (no valid data, or population not reported)" : "No valid observation in this year" }];
  if (st.lvl === "adm1") sw.push({ cls: "sw-unmatched", label: "No province outline (data in downloads)" });
  sw.push({ cls: "sw-ndlsa", label: "Non-determined legal status" });
  $("wmLegend").innerHTML = legendHTML({
    title: `${i.label}, ${st.years[st.yi]}`, unitLabel: i.unit, breaks: st.breaks[key], colors: COLORS, swatches: sw,
    note: `${K} quantile classes of all ${st.lvl === "adm0" ? "country" : "province"}-year values ${st.years[0]}–${st.years.at(-1)} (positive values; no transformation). ` +
      `Class limits are fixed across years, so colour changes reflect changes in the data. ${esc(i.help)}`,
  });
  $("wmTitle").textContent = `${i.short} by ${st.lvl === "adm0" ? "country (ADM0)" : "province (ADM1)"}, ${st.years[st.yi]}`;
  $("wmYearOut").textContent = st.years[st.yi];
}

async function init() {
  const el = $("worldmap");
  let geo, ctry, ndlsa, vals, nat;
  try {
    [geo, ctry, ndlsa, vals, nat] = await Promise.all(["data/geo/world_adm1.geojson", "data/geo/adm0_world.geojson",
      "data/geo/ndlsa.geojson", "data/geo/world_adm1_values.json", "data/v2/analysis/national.json"].map((u) => fetch(u).then((r) => (r.ok ? r.json() : null))));
  } catch (e) { console.error(e); }
  if (!geo || !vals || !ctry) { el.innerHTML = '<p class="map-msg">The map could not be loaded. All data remain available from the Explore and Download pages.</p>'; return; }
  st.years = vals.years; st.units = vals.units; st.yi = st.years.length - 1; st.nat = nat;
  for (const k of ["mean", "sum"]) {
    const all = []; for (const u of Object.values(st.units)) for (const v of u[k]) if (v > 0) all.push(v);
    st.breaks[`adm1:${k}`] = quantileBreaks(all, K);
  }
  if (nat) {
    const ni = st.years.map((y) => nat.years.indexOf(y));
    for (const k of Object.keys(IND)) {
      const all = []; for (const e of Object.values(nat.economies)) ni.forEach((i) => { const v = natVal(e, k, i); if (v > 0) all.push(v); });
      st.breaks[`adm0:${k}`] = quantileBreaks(all, K);
    }
  } else document.querySelector('[data-wl="adm0"]').disabled = true;
  for (const [k, b] of Object.entries(st.breaks)) st.cls[k] = classifier({ breaks: b, colors: COLORS });
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
    .attr("aria-label", "World map of nighttime lights by province or country. Use the country box to zoom to a country.");
  addPatterns(svg);
  const g = svg.append("g");
  g.append("g").selectAll("path").data(ctry.features).join("path").attr("class", "land").attr("d", path);
  const twn = geo.features.filter((f) => st.units[f.properties.code]?.name === "Taiwan Sheng");
  const tipNat = (ev, iso) => {
    const e = nat?.economies[iso]; if (!e) { showTip($("wmTip"), null); return; }
    const i = nat.years.indexOf(st.years[st.yi]); const v = natVal(e, st.ind, i);
    const val = v == null ? (st.ind === "pc" && e.pop[i] == null ? "Population not reported (WDI)" : "No value") : v === 0 ? "0" : `${fmtExact(v)} <span class="muted">${IND[st.ind].unit}</span>`;
    showTip($("wmTip"), `<b>${esc(e.name)}</b><span class="muted">${esc(iso)} · ${esc(IMF[e.imf] ?? "")}</span><br>
      ${esc(IND[st.ind].short)}, ${st.years[st.yi]}: <span class="v">${val}</span><br>
      Valid-pixel coverage: <span class="v">${pct(e.cov[i])}</span><br>
      Population (WDI): <span class="v">${e.pop[i] != null ? fmt(e.pop[i]) : "not reported"}</span> · GDP pc PPP: <span class="v">${e.gdppc[i] != null ? d3.format(",.0f")(e.gdppc[i]) : "not reported"}</span>
      ${e.note ? `<br><span class="muted">${esc(e.note)}</span>` : ""}<br><span class="muted">Click to open in the explorer</span>`, ev);
  };
  const units = g.append("g").attr("class", "lyr-adm1").selectAll("path").data(geo.features).join("path").attr("class", "u").attr("d", path)
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
  const countries = g.append("g").attr("class", "lyr-adm0").attr("display", "none").selectAll("path")
    .data([...ctry.features.map((f) => ({ f, iso: f.properties.iso })), ...twn.map((f) => ({ f, iso: "TWN" }))]).join("path")
    .attr("class", "u").attr("d", (d) => path(d.f))
    .on("mousemove", (ev, d) => tipNat(ev, d.iso)).on("mouseleave", () => showTip($("wmTip"), null))
    .on("click", (ev, d) => { const iso = d.iso === "TWN" ? "CHN" : d.iso; location.href = `explore.html#c=${iso}&l=adm1&s=wb&f=annual&v=map&p=${st.years[st.yi]}`; });
  g.append("path").datum({ type: "FeatureCollection", features: ctry.features }).attr("class", "borders").attr("d", path);
  if (ndlsa) g.append("g").selectAll("path").data(ndlsa.features).join("path").attr("class", "ndlsa").attr("d", path);
  const z = addZoom({ svg, g, frame: el.parentElement, width: W, height: H, maxScale: 30 });

  const paint = () => {
    const c = st.cls[`${st.lvl}:${st.ind}`];
    g.select(".lyr-adm1").attr("display", st.lvl === "adm1" ? null : "none");
    g.select(".lyr-adm0").attr("display", st.lvl === "adm0" ? null : "none");
    if (st.lvl === "adm1") {
      units.each(function (d) {
        const u = st.units[d.properties.code];
        const r = c(u ? u[st.ind][st.yi] : null);
        this.setAttribute("fill", r.color); this.classList.toggle("zero", r.cls === "zero");
      });
    } else {
      const i = nat.years.indexOf(st.years[st.yi]);
      countries.each(function (d) {
        const r = c(natVal(nat.economies[d.iso], st.ind, i));
        this.setAttribute("fill", r.color); this.classList.toggle("zero", r.cls === "zero");
      });
    }
    const pcBtn = document.querySelector('[data-wm="pc"]');
    pcBtn.disabled = st.lvl === "adm1";
    pcBtn.title = st.lvl === "adm1" ? "Countries only (WDI population)" : "";
    legend();
  };
  paint();

  document.querySelectorAll("[data-wm]").forEach((b) => b.addEventListener("click", () => {
    if (b.disabled) return;
    st.ind = b.dataset.wm;
    document.querySelectorAll("[data-wm]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    paint();
  }));
  document.querySelectorAll("[data-wl]").forEach((b) => b.addEventListener("click", () => {
    if (b.disabled) return;
    st.lvl = b.dataset.wl;
    document.querySelectorAll("[data-wl]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    if (st.lvl === "adm1" && st.ind === "pc") { st.ind = "mean"; document.querySelectorAll("[data-wm]").forEach((x) => x.setAttribute("aria-pressed", x.dataset.wm === "mean")); }
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
