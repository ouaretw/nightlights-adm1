/* Night Lights ADM1 - explorer. Static: reads JSON/GeoJSON from ./data */
(() => {
  "use strict";
  const DATA = "data/";
  const VARS = {
    mean: { label: "Mean radiance", unit: "nW·cm⁻²·sr⁻¹", m: "m_mean", a: "a_mean", log: true },
    sum:  { label: "Sum of lights", unit: "radiance × pixels", m: "m_sum", a: "a_sum", log: true },
    nogf: { label: "Sum of lights, excl. gas flares (5 km)", unit: "radiance × pixels", m: "m_nogf", a: "a_nogf", log: true },
  };
  const state = { iso: null, var: "mean", year: 2024, region: null, series: null, geo: null, sortK: "v", sortDir: -1 };
  const $ = (id) => document.getElementById(id);
  const fmt = (v) => v == null || !isFinite(v) ? "–" :
    Math.abs(v) >= 1e6 ? d3.format(".3~s")(v) : Math.abs(v) >= 100 ? d3.format(",.0f")(v) :
    Math.abs(v) >= 1 ? d3.format(".2f")(v) : d3.format(".3f")(v);
  const pct = (v) => v == null || !isFinite(v) ? "–" : (v > 0 ? "+" : "") + d3.format(".0%")(v);
  const cache = new Map();
  const getJSON = (url) => {
    if (!cache.has(url)) cache.set(url, fetch(url).then((r) => (r.ok ? r.json() : null)).catch(() => null));
    return cache.get(url);
  };
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  // d3 wants clockwise exterior rings; RFC 7946 GeoJSON is counter-clockwise.
  function rewind(fc) {
    for (const f of fc.features) {
      const g = f.geometry; if (!g) continue;
      const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
      for (const p of polys) {
        if (d3.geoArea({ type: "Polygon", coordinates: p }) > 2 * Math.PI) p.forEach((ring) => ring.reverse());
      }
    }
    return fc;
  }

  let index = [], byIso = new Map(), world = null, ndlsa = null;

  async function init() {
    [index, world, ndlsa] = await Promise.all([
      getJSON(DATA + "adm1_index.json"), getJSON(DATA + "geo/adm0_world.geojson"), getJSON(DATA + "geo/ndlsa.geojson"),
    ]);
    if (world) rewind(world);
    if (ndlsa) rewind(ndlsa);
    byIso = new Map(index.map((c) => [c.iso, c]));
    const dl = $("countries");
    index.forEach((c) => { const o = document.createElement("option"); o.value = `${c.name} (${c.iso})`; dl.appendChild(o); });
    const meta = await getJSON(DATA + "build_meta.json");
    if (meta) $("built").textContent = `Source data ${meta.months[0]} to ${meta.months[1]}.`;

    $("country").addEventListener("change", onCountryInput);
    $("country").addEventListener("keydown", (e) => { if (e.key === "Enter") onCountryInput(); });
    $("var").addEventListener("change", (e) => { state.var = e.target.value; renderAll(); });
    $("year").addEventListener("input", (e) => { state.year = +e.target.value; $("yearOut").textContent = state.year; renderMap(); renderTable(); });
    $("hideLow").addEventListener("change", renderChart);
    document.querySelectorAll("#regions th").forEach((th) => th.addEventListener("click", () => {
      const k = th.dataset.k; state.sortDir = state.sortK === k ? -state.sortDir : (k === "name" ? 1 : -1); state.sortK = k; renderTable();
    }));
    $("copyCite").addEventListener("click", () => {
      const t = [...document.querySelectorAll("#cite blockquote")].map((b) => b.textContent.trim()).join("\n\n");
      navigator.clipboard?.writeText(t).then(() => { $("copyCite").textContent = "Copied"; setTimeout(() => ($("copyCite").textContent = "Copy citation"), 1500); });
    });
    window.addEventListener("resize", debounce(renderAll, 150));
    window.matchMedia("(prefers-color-scheme: light)").addEventListener?.("change", renderAll);

    const hash = (location.hash.match(/^#c=([A-Z]{3})/) || [])[1];
    if (hash && byIso.has(hash)) selectCountry(hash); else renderWorld();
  }

  function debounce(fn, ms) { let t; return () => { clearTimeout(t); t = setTimeout(fn, ms); }; }

  function onCountryInput() {
    const v = $("country").value.trim();
    const m = v.match(/\(([A-Z]{3})\)$/);
    let iso = m ? m[1] : null;
    if (!iso) { const hit = index.find((c) => c.name.toLowerCase() === v.toLowerCase() || c.iso === v.toUpperCase()); iso = hit?.iso; }
    if (iso && byIso.has(iso)) selectCountry(iso);
  }

  async function selectCountry(iso) {
    state.iso = iso; state.region = null;
    const c = byIso.get(iso);
    $("country").value = `${c.name} (${c.iso})`;
    history.replaceState(null, "", `#c=${iso}`);
    $("mapTitle").textContent = c.name; $("mapNote").textContent = "Loading…";
    const [series, geo] = await Promise.all([getJSON(`${DATA}series/${iso}.json`), getJSON(`${DATA}geo/adm1/${iso}.geojson`)]);
    if (state.iso !== iso) return;
    state.series = series; state.geo = geo ? rewind(geo) : null;
    // default region: brightest by annual sum in the latest year
    const yi = series.years.length - 1;
    state.region = [...series.regions].sort((a, b) => (b.a_sum[yi] ?? -1) - (a.a_sum[yi] ?? -1))[0]?.code ?? null;
    $("dlMonthly").href = `${DATA}monthly/${iso}.csv`; $("dlMonthly").setAttribute("download", `ntl_adm1_monthly_${iso}.csv`);
    $("dlAnnual").href = `${DATA}annual/${iso}.csv`; $("dlAnnual").setAttribute("download", `ntl_adm1_annual_${iso}.csv`);
    $("dlGMonthly").href = `${DATA}gadm/monthly/${iso}.csv`; $("dlGMonthly").setAttribute("download", `ntl_gadm41_adm1_monthly_${iso}.csv`);
    $("dlGAnnual").href = `${DATA}gadm/annual/${iso}.csv`; $("dlGAnnual").setAttribute("download", `ntl_gadm41_adm1_annual_${iso}.csv`);
    $("countryDl").hidden = false;
    renderAll();
  }

  function renderAll() { if (!state.iso) { renderWorld(); return; } renderMap(); renderTable(); renderChart(); }

  // --------------------------------------------------------------- map
  function svgFor(el) {
    el.innerHTML = "";
    const { width, height } = el.getBoundingClientRect();
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
    const defs = svg.append("defs");
    defs.append("pattern").attr("id", "hatch").attr("patternUnits", "userSpaceOnUse").attr("width", 5).attr("height", 5)
      .attr("patternTransform", "rotate(45)").append("line").attr("x1", 0).attr("y1", 0).attr("x2", 0).attr("y2", 5)
      .attr("stroke", css("--hatch")).attr("stroke-width", 1.2);
    return { svg, width, height };
  }

  function tooltip(html, ev) {
    const tt = $("tooltip");
    if (!html) { tt.hidden = true; return; }
    tt.innerHTML = html; tt.hidden = false;
    const box = $("map").parentElement.getBoundingClientRect();
    let x = ev.clientX - box.left + 14, y = ev.clientY - box.top + 14;
    if (x + 260 > box.width) x = ev.clientX - box.left - 270;
    tt.style.left = `${Math.max(4, x)}px`; tt.style.top = `${y}px`;
  }

  function renderWorld() {
    const el = $("map");
    const { svg, width, height } = svgFor(el);
    $("legend").innerHTML = ""; $("listNote").textContent = "";
    if (!world) { el.innerHTML = '<div class="nomap">World outline failed to load.</div>'; return; }
    const proj = d3.geoEqualEarth().fitExtent([[4, 4], [width - 4, height - 4]], { type: "Sphere" });
    const path = d3.geoPath(proj);
    svg.append("path").attr("d", path({ type: "Sphere" })).attr("fill", "none").attr("stroke", css("--line"));
    svg.append("g").selectAll("path").data(world.features).join("path")
      .attr("class", (d) => "land" + (byIso.has(d.properties.iso) ? " has-data" : ""))
      .attr("d", path)
      .on("mousemove", (ev, d) => tooltip(`<b>${d.properties.name}</b>${byIso.has(d.properties.iso) ? byIso.get(d.properties.iso).n_adm1 + " ADM1 units" : "no data"}`, ev))
      .on("mouseleave", () => tooltip(null))
      .on("click", (ev, d) => { tooltip(null); if (byIso.has(d.properties.iso)) selectCountry(d.properties.iso); });
    if (ndlsa) svg.append("g").selectAll("path").data(ndlsa.features).join("path").attr("class", "ndlsa").attr("d", path);
    $("chart").innerHTML = "";
  }

  function regionValue(r, key, yi) { const v = r[VARS[state.var][key]][yi]; return v == null ? null : v; }

  function colorScale(values) {
    const pos = values.filter((v) => v != null && v > 0);
    if (!pos.length) return { scale: () => css("--nodata"), domain: [0, 1] };
    let lo = d3.quantile(pos.sort(d3.ascending), 0.02), hi = d3.max(pos);
    if (!(hi > lo)) { lo = hi / 10; }
    const s = d3.scaleSequentialLog(d3.interpolateInferno).domain([lo, hi]).clamp(true);
    const scale = (v) => (v == null ? css("--nodata") : v <= 0 ? d3.interpolateInferno(0.02) : s(v));
    return { scale, domain: [lo, hi], interp: (t) => d3.interpolateInferno(t) };
  }

  function renderMap() {
    const el = $("map");
    const S = state.series; if (!S) return;
    const yi = S.years.indexOf(state.year);
    const vals = new Map(S.regions.map((r) => [r.code, regionValue(r, "a", yi)]));
    const cs = colorScale([...vals.values()]);
    const nMapped = state.geo ? state.geo.features.length : 0;
    $("mapNote").textContent = nMapped === 0 ? "" :
      `${VARS[state.var].label}, ${state.year} · ${nMapped} of ${S.regions.length} units drawn`;

    if (!state.geo || !nMapped) {
      el.innerHTML = `<div class="nomap"><div><b>No map outline for ${S.name}.</b><br>The ADM1 units in the source data come from an older boundary vintage that cannot be matched safely to today's outlines (see Method). The data and downloads are complete.</div></div>`;
      $("legend").innerHTML = "";
      return;
    }
    const { svg, width, height } = svgFor(el);
    const centroid = d3.geoCentroid(state.geo);
    const proj = d3.geoMercator().rotate([-centroid[0], 0]).fitExtent([[8, 8], [width - 8, height - 8]], state.geo);
    const path = d3.geoPath(proj);
    if (world) svg.append("g").selectAll("path").data(world.features.filter((f) => f.properties.iso !== state.iso))
      .join("path").attr("class", "ctx").attr("d", path);
    const regionsByCode = new Map(S.regions.map((r) => [r.code, r]));
    svg.append("g").selectAll("path").data(state.geo.features).join("path")
      .attr("class", (d) => "adm1" + (d.properties.approx ? " approx" : "") + (d.properties.code === state.region ? " sel" : ""))
      .attr("d", path)
      .attr("fill", (d) => cs.scale(vals.get(d.properties.code)))
      .on("mousemove", (ev, d) => tooltip(`<b>${d.properties.name}</b>${VARS[state.var].label} ${state.year}: ${fmt(vals.get(d.properties.code))}${d.properties.approx ? "<br><span class='muted'>Approximate outline</span>" : ""}`, ev))
      .on("mouseleave", () => tooltip(null))
      .on("click", (ev, d) => { if (regionsByCode.has(d.properties.code)) { state.region = d.properties.code; renderMap(); renderTable(); renderChart(); } });
    if (ndlsa) svg.append("g").selectAll("path").data(ndlsa.features).join("path").attr("class", "ndlsa").attr("d", path);
    // raise selected outline
    svg.selectAll(".adm1.sel").raise();
    // legend
    const stops = d3.range(0, 1.01, 0.1).map((t) => `${d3.interpolateInferno(t)} ${t * 100}%`).join(",");
    const approx = state.geo.features.some((f) => f.properties.approx);
    $("legend").innerHTML = `<span>${fmt(cs.domain[0])}</span><span class="bar" style="background:linear-gradient(90deg,${stops})"></span><span>${fmt(cs.domain[1])}</span><span>${VARS[state.var].unit} · log scale</span>` +
      (approx ? `<span class="tag">dashed = approximate outline</span>` : "");
  }

  // --------------------------------------------------------------- table
  function renderTable() {
    const S = state.series; if (!S) return;
    const yi = S.years.indexOf(state.year), y0 = S.years.indexOf(2013);
    const mapped = new Set(state.geo ? state.geo.features.map((f) => f.properties.code) : []);
    const rows = S.regions.map((r) => {
      const v = regionValue(r, "a", yi), b = regionValue(r, "a", y0);
      const s = r.a_sum[yi], ng = r.a_nogf[yi];
      const flare = s > 0 && ng != null ? 1 - ng / s : 0;
      return { code: r.code, name: r.name, v, chg: b > 0 && v != null ? v / b - 1 : null, mapped: mapped.has(r.code), flare };
    });
    const k = state.sortK, dir = state.sortDir;
    rows.sort((a, b) => k === "name" ? dir * a.name.localeCompare(b.name) : dir * ((a[k] ?? -Infinity) - (b[k] ?? -Infinity)));
    const tb = d3.select("#regions tbody");
    tb.selectAll("tr").data(rows, (d) => d.code).join("tr")
      .attr("class", (d) => (d.code === state.region ? "sel" : ""))
      .html((d) => `<td>${escapeHtml(d.name)}${d.mapped || mapped.size === 0 ? "" : '<span class="tag" title="No safe outline match">no outline</span>'}${d.flare >= 0.05 ? `<span class="tag" title="Share of ${state.year} light within 5 km of a gas-flaring site">${d3.format(".0%")(d.flare)} flare light</span>` : ""}</td>` +
        `<td class="num">${fmt(d.v)}</td><td class="num ${d.chg > 0 ? "up" : d.chg < 0 ? "down" : ""}">${pct(d.chg)}</td>`)
      .on("click", (ev, d) => { state.region = d.code; renderMap(); renderTable(); renderChart(); });
    $("listNote").textContent = `${S.regions.length} units · ${state.year}`;
    const sel = document.querySelector("#regions tbody tr.sel");
    if (sel && !isInView(sel)) sel.scrollIntoView({ block: "nearest" });
  }
  const isInView = (el) => { const p = el.closest(".table-scroll").getBoundingClientRect(), r = el.getBoundingClientRect(); return r.top >= p.top && r.bottom <= p.bottom; };
  const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // --------------------------------------------------------------- chart
  function renderChart() {
    const el = $("chart"); el.innerHTML = "";
    const S = state.series; if (!S || !state.region) return;
    const r = S.regions.find((x) => x.code === state.region); if (!r) return;
    const V = VARS[state.var];
    $("chartTitle").textContent = `${r.name}, ${S.name}: ${V.label}`;
    const hide = $("hideLow").checked;
    const parse = d3.utcParse("%Y-%m");
    const m = S.months.map((d, i) => ({ t: parse(d), v: r[V.m][i], cov: r.m_cov[i] }))
      .map((d) => ({ ...d, show: d.v != null && (!hide || (d.cov ?? 0) >= 0.5) }));
    const a = S.years.map((y, i) => ({ t: new Date(Date.UTC(y, 6, 1)), v: r[V.a][i] })).filter((d) => d.v != null);
    const nHidden = m.filter((d) => d.v != null && !d.show).length;
    $("chartNote").textContent = `Monthly values (line) and NASA annual composite (dots). ${V.unit}.` +
      (nHidden ? ` ${nHidden} low-coverage month${nHidden > 1 ? "s" : ""} hidden.` : "") + ` Code ${r.code}.`;

    const { width, height } = el.getBoundingClientRect();
    const mg = { t: 12, r: 12, b: 26, l: 56 };
    const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${width} ${height}`);
    const x = d3.scaleUtc().domain(d3.extent(m, (d) => d.t)).range([mg.l, width - mg.r]);
    const all = m.filter((d) => d.show).map((d) => d.v).concat(a.map((d) => d.v));
    const y = d3.scaleLinear().domain([0, (d3.max(all) || 1) * 1.05]).nice().range([height - mg.b, mg.t]);
    svg.append("g").attr("class", "grid-line").attr("transform", `translate(${mg.l},0)`)
      .call(d3.axisLeft(y).ticks(5).tickSize(-(width - mg.l - mg.r)).tickFormat(""));
    svg.append("g").attr("class", "axis").attr("transform", `translate(0,${height - mg.b})`).call(d3.axisBottom(x).ticks(width < 560 ? 5 : 10).tickSizeOuter(0));
    svg.append("g").attr("class", "axis").attr("transform", `translate(${mg.l},0)`).call(d3.axisLeft(y).ticks(5).tickFormat(fmt).tickSizeOuter(0));
    svg.append("path").datum(m).attr("class", "m-line")
      .attr("d", d3.line().defined((d) => d.show).x((d) => x(d.t)).y((d) => y(d.v)));
    svg.append("path").datum(a).attr("class", "a-line").attr("opacity", 0.35).attr("d", d3.line().x((d) => x(d.t)).y((d) => y(d.v)));
    svg.append("g").selectAll("circle").data(a).join("circle").attr("class", "a-dot").attr("r", 4).attr("cx", (d) => x(d.t)).attr("cy", (d) => y(d.v));

    // hover readout
    const focus = svg.append("g").style("display", "none");
    focus.append("line").attr("y1", mg.t).attr("y2", height - mg.b).attr("stroke", css("--muted")).attr("stroke-dasharray", "3 3");
    const label = focus.append("text").attr("class", "chart-legend").attr("y", mg.t + 10);
    const bis = d3.bisector((d) => d.t).center;
    svg.append("rect").attr("x", mg.l).attr("y", mg.t).attr("width", width - mg.l - mg.r).attr("height", height - mg.t - mg.b)
      .attr("fill", "transparent")
      .on("mousemove", (ev) => {
        const [px] = d3.pointer(ev); const d = m[bis(m, x.invert(px))];
        focus.style("display", null).attr("transform", `translate(${x(d.t)},0)`);
        const txt = `${d3.utcFormat("%b %Y")(d.t)}: ${d.v == null ? "no data" : fmt(d.v)}${d.cov != null ? ` · ${d3.format(".0%")(d.cov)} valid` : ""}`;
        label.text(txt).attr("text-anchor", x(d.t) > width * 0.7 ? "end" : "start").attr("x", x(d.t) > width * 0.7 ? -6 : 6);
      })
      .on("mouseleave", () => focus.style("display", "none"));
  }

  init();
})();
