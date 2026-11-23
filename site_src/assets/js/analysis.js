// Economic Analysis page. Every value is read from files written by
// pipeline/build_analysis.py (data/v2/analysis/*.json); every model estimate
// comes from models.json (statsmodels), nothing is re-estimated here except the
// descriptive least-squares lines drawn on the scatterplots, which are labelled as such.
import { esc, fmt, fmtExact, pct, showTip, downloadCsv } from "./carto.js";

const $ = (id) => document.getElementById(id);
const tip = $("anTip");
// categorical slots (validated: lightness, chroma, CVD separation, contrast)
const C1 = "#0F86A0", C2 = "#B87A12", C3 = "#6E5BB8", GREY = "#8D9BA8", INK = "#11263B", LIGHT = "#C3D0DA";
const GROUP = {
  advanced: { label: "Advanced economies", short: "Advanced", color: C1 },
  emde: { label: "Emerging market and developing economies", short: "EMDE", color: C2 },
  not_classified: { label: "Not in the IMF classification", short: "Not classified", color: GREY, hollow: true },
};
const UNIT = { mean: "nW·cm⁻²·sr⁻¹", sum: "nW·cm⁻²·sr⁻¹ × px", pc: "nW·cm⁻²·sr⁻¹ × px per person" };
const MEASURES = {
  mean: { label: "Mean radiance", key: "ntl_mean", unit: UNIT.mean,
    note: "Mean radiance over all valid land pixels (sum ÷ valid-pixel weight): an intensity measure, low for large sparsely settled countries." },
  sum: { label: "Total radiance", key: "ntl_sum", unit: UNIT.sum,
    note: "Sum of radiance over the whole country: grows with population, area and brightness." },
  pc: { label: "Total radiance per person", key: "ntl_sum_per_capita", unit: UNIT.pc,
    note: "Total radiance divided by WDI population (SP.POP.TOTL) of the same year." },
  pcnogf: { label: "Radiance per person, gas flares excluded", key: "ntl_nogf_5km_sum_per_capita", unit: UNIT.pc,
    note: "Total radiance outside 5 km buffers around gas-flaring sites, divided by WDI population. Removes light from oil and gas flaring." },
};
const S = { nat: null, A: null, M: null, adm1: null, dose: null, exp: {} };
const st = { aYear: 2022, aM: "mean", aFind: null, bIso: "CHN", bYear: null, bM: "mean", bSel: null, cL: "nat", cYear: 2022, cIso: "", c5: "IND" };

// ---------------------------------------------------------------- helpers
const yi = (y) => S.nat.years.indexOf(y);
const isPos = (v) => v != null && isFinite(v) && v > 0;
const f3 = d3.format(".3~r");
const fN = (v) => (v == null ? "NA" : d3.format(",")(v));
const fP = (p) => (p == null ? "NA" : p < 0.001 ? "< 0.001" : d3.format(".3f")(p));
const fB = (c) => (c ? `${d3.format(".2f")(c.b)} <span class="muted">[${d3.format(".2f")(c.ci95[0])}, ${d3.format(".2f")(c.ci95[1])}]</span>` : "—");
const econValue = (e, m, i) => {
  if (!e) return null;
  if (m === "mean") return e.mean[i];
  if (m === "sum") return e.sum[i];
  if (m === "pc") return e.sum[i] != null && isPos(e.pop[i]) ? e.sum[i] / e.pop[i] : null;
  if (m === "pcnogf") return e.nogf[i] != null && isPos(e.pop[i]) ? e.nogf[i] / e.pop[i] : null;
};
const economyOf = (u) => (u.iso === "CHN" && u.name === "Taiwan Sheng" ? "TWN" : u.iso);
function hash(s) { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return ((h >>> 0) % 1000) / 1000; }
function setExport(key, rows, cols, name) { S.exp[key] = { rows, cols, name }; }
function empty(el, msg) { el.innerHTML = `<p class="map-msg">${esc(msg)}</p>`; }
function size(el, h) { return [Math.max(280, el.clientWidth || 600), h || el.clientHeight || 320]; }
function logDomain(vals) {
  let [a, b] = d3.extent(vals); if (a === b) { a /= 2; b *= 2; }
  return [a / 1.15, b * 1.15];
}
// log-axis labels as plain numbers (0.01, 100, 20k, 3M, 4B) — SI "m"/"µ" would read like units
const logLab = (v) => (v >= 1e9 ? d3.format("~s")(v).replace("G", "B") : v >= 1e3 ? d3.format("~s")(v) : d3.format("~g")(+v.toPrecision(2)));
function axisLog(g, scale, orient, n) {
  const [a, b] = scale.domain();
  const decades = Math.log10(b / a);
  const ax = orient === "x" ? d3.axisBottom(scale) : d3.axisLeft(scale);
  if (decades > 2.2) {
    const vals = d3.range(Math.ceil(Math.log10(a)), Math.floor(Math.log10(b)) + 1).map((e) => 10 ** e);
    const step = Math.max(1, Math.ceil(vals.length / Math.max(3, n)));
    ax.tickValues(vals.filter((_, i) => i % step === 0)).tickFormat(logLab);
  } else {
    const ticks = scale.ticks(n);
    const keep = ticks.length > n * 2 ? ticks.filter((t) => /^[125]/.test(t.toExponential())) : ticks;
    ax.tickValues(keep.length > n * 2 ? keep.filter((t) => /^[1]/.test(t.toExponential())) : keep).tickFormat(logLab);
  }
  g.call(ax).attr("class", "axis");
}
function ols(pts) {
  const n = pts.length; if (n < 3) return null;
  const X = pts.map((p) => Math.log(p.x)), Y = pts.map((p) => Math.log(p.y));
  const mx = d3.mean(X), my = d3.mean(Y);
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { sxy += (X[i] - mx) * (Y[i] - my); sxx += (X[i] - mx) ** 2; syy += (Y[i] - my) ** 2; }
  if (!sxx) return null;
  const b = sxy / sxx;
  return { b, a: my - b * mx, r2: (sxy * sxy) / (sxx * syy), n };
}

// ---------------------------------------------------------------- chart: scatter (log-log)
function scatter(el, { pts, xLabel, yLabel, fit = true, height = 0, highlight = null, labelIds = [], onClick = null, tipHtml }) {
  el.innerHTML = "";
  if (pts.length < 2) { empty(el, "Not enough observations with positive values for this selection."); return null; }
  const [W, H] = size(el, height);
  const m = { t: 10, r: 16, b: 42, l: 58 };
  const x = d3.scaleLog().domain(logDomain(pts.map((d) => d.x))).range([m.l, W - m.r]);
  const y = d3.scaleLog().domain(logDomain(pts.map((d) => d.y))).range([H - m.b, m.t]);
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
    .attr("aria-label", `${yLabel} against ${xLabel}, ${pts.length} observations, logarithmic scales`);
  svg.append("g").attr("transform", `translate(0,${H - m.b})`).call((g) => axisLog(g, x, "x", Math.max(3, Math.floor(W / 110))));
  svg.append("g").attr("transform", `translate(${m.l},0)`).call((g) => axisLog(g, y, "y", 5));
  svg.append("text").attr("class", "axis-title").attr("x", (m.l + W - m.r) / 2).attr("y", H - 6).attr("text-anchor", "middle").text(`${xLabel} (log scale)`);
  svg.append("text").attr("class", "axis-title").attr("transform", `translate(12,${(m.t + H - m.b) / 2}) rotate(-90)`).attr("text-anchor", "middle").text(`${yLabel} (log)`);
  const fitR = fit ? ols(pts) : null;
  if (fitR) {
    const [x0, x1] = x.domain();
    svg.append("line").attr("x1", x(x0)).attr("x2", x(x1)).attr("y1", y(Math.exp(fitR.a + fitR.b * Math.log(x0))))
      .attr("y2", y(Math.exp(fitR.a + fitR.b * Math.log(x1)))).attr("stroke", INK).attr("stroke-width", 1.2).attr("stroke-dasharray", "4 4")
      .attr("opacity", 0.55).attr("clip-path", null);
  }
  const ordered = [...pts].sort((a, b) => (a.id === highlight) - (b.id === highlight));
  svg.append("g").selectAll("circle").data(ordered).join("circle")
    .attr("cx", (d) => x(d.x)).attr("cy", (d) => y(d.y)).attr("r", (d) => (d.id === highlight ? 6.5 : d.r || 4))
    .attr("fill", (d) => (d.hollow ? "#fff" : d.color)).attr("stroke", (d) => (d.id === highlight ? INK : d.hollow ? d.color : "#fff"))
    .attr("stroke-width", (d) => (d.id === highlight ? 2.2 : d.hollow ? 1.5 : 1)).attr("opacity", (d) => (highlight && d.id !== highlight ? 0.85 : 0.95));
  const lab = new Set([...labelIds, highlight].filter(Boolean));
  svg.append("g").selectAll("text").data(pts.filter((d) => lab.has(d.id))).join("text")
    .attr("x", (d) => (x(d.x) > W * 0.7 ? x(d.x) - 8 : x(d.x) + 8)).attr("text-anchor", (d) => (x(d.x) > W * 0.7 ? "end" : "start"))
    .attr("y", (d) => y(d.y) - 7).attr("class", "pt-label").text((d) => d.label);
  // hover / click: nearest point within 24 px (hit target larger than the mark)
  const del = d3.Delaunay.from(pts, (d) => x(d.x), (d) => y(d.y));
  const ring = svg.append("circle").attr("r", 8).attr("fill", "none").attr("stroke", INK).attr("stroke-width", 1.5).attr("visibility", "hidden");
  const near = (ev) => { const [px, py] = d3.pointer(ev); const i = del.find(px, py); const d = pts[i]; return Math.hypot(x(d.x) - px, y(d.y) - py) < 24 ? d : null; };
  svg.on("mousemove", (ev) => {
    const d = near(ev);
    if (!d) { ring.attr("visibility", "hidden"); showTip(tip, null); return; }
    ring.attr("cx", x(d.x)).attr("cy", y(d.y)).attr("visibility", "visible");
    showTip(tip, tipHtml(d), ev);
  }).on("mouseleave", () => { ring.attr("visibility", "hidden"); showTip(tip, null); });
  if (onClick) svg.style("cursor", "pointer").on("click", (ev) => { const d = near(ev); if (d) onClick(d); });
  return fitR;
}

// ---------------------------------------------------------------- chart: group strip (log)
function strip(el, { groups, yLabel, highlight }) {
  el.innerHTML = "";
  const all = groups.flatMap((g) => g.pts);
  if (all.length < 2) { empty(el, "No observations."); return; }
  const [W, H] = size(el);
  const m = { t: 10, r: 16, b: 38, l: 58 };
  const x = d3.scaleBand().domain(groups.map((g) => g.key)).range([m.l, W - m.r]).padding(0.25);
  const y = d3.scaleLog().domain(logDomain(all.map((d) => d.y))).range([H - m.b, m.t]);
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", `${yLabel} by IMF group`);
  svg.append("g").attr("transform", `translate(0,${H - m.b})`).attr("class", "axis")
    .call(d3.axisBottom(x).tickFormat((k) => `${GROUP[k].short} (n = ${groups.find((g) => g.key === k).pts.length})`));
  svg.append("g").attr("transform", `translate(${m.l},0)`).call((g) => axisLog(g, y, "y", 5));
  svg.append("text").attr("class", "axis-title").attr("transform", `translate(12,${(m.t + H - m.b) / 2}) rotate(-90)`).attr("text-anchor", "middle").text(`${yLabel} (log)`);
  for (const g of groups) {
    const v = g.pts.map((d) => d.y).sort(d3.ascending);
    if (!v.length) continue;
    const q1 = d3.quantile(v, 0.25), q2 = d3.quantile(v, 0.5), q3 = d3.quantile(v, 0.75);
    const x0 = x(g.key), bw = x.bandwidth();
    svg.append("rect").attr("x", x0 + bw * 0.12).attr("width", bw * 0.76).attr("y", y(q3)).attr("height", Math.max(1, y(q1) - y(q3)))
      .attr("fill", "none").attr("stroke", LIGHT).attr("stroke-width", 1.5).attr("rx", 4);
    svg.append("line").attr("x1", x0 + bw * 0.12).attr("x2", x0 + bw * 0.88).attr("y1", y(q2)).attr("y2", y(q2)).attr("stroke", INK).attr("stroke-width", 2);
    g.pts.forEach((d) => { d._x = x0 + bw * (0.2 + 0.6 * hash(d.id)); });
  }
  const pts = all;
  svg.append("g").selectAll("circle").data(pts).join("circle").attr("cx", (d) => d._x).attr("cy", (d) => y(d.y))
    .attr("r", (d) => (d.id === highlight ? 6.5 : 3.6)).attr("fill", (d) => d.color).attr("stroke", (d) => (d.id === highlight ? INK : "#fff"))
    .attr("stroke-width", (d) => (d.id === highlight ? 2.2 : 0.8)).attr("opacity", 0.9);
  const del = d3.Delaunay.from(pts, (d) => d._x, (d) => y(d.y));
  svg.on("mousemove", (ev) => {
    const [px, py] = d3.pointer(ev); const d = pts[del.find(px, py)];
    if (!d || Math.hypot(d._x - px, y(d.y) - py) > 20) { showTip(tip, null); return; }
    showTip(tip, `<b>${esc(d.label)}</b>${esc(GROUP[d.group].label)}<br><span class="v">${fmtExact(d.y)}</span> <span class="muted">${esc(d.unit)}</span>`, ev);
  }).on("mouseleave", () => showTip(tip, null));
}

// ---------------------------------------------------------------- chart: horizontal bars from zero
function bars(el, { rows, xLabel, ref = null, refLabel = "", selected = null, onClick, fmtV = fmt }) {
  el.innerHTML = "";
  if (!rows.length) { empty(el, "No observations for this selection."); return; }
  const W = Math.max(300, el.clientWidth || 600), rh = 18;
  const m = { t: 8, r: 64, b: 38, l: Math.min(190, Math.max(90, d3.max(rows, (r) => r.label.length) * 6.2)) };
  const H = m.t + m.b + rows.length * rh;
  const x = d3.scaleLinear().domain([0, d3.max([...rows.map((r) => r.v), ref ?? 0])]).nice().range([m.l, W - m.r]);
  const y = d3.scaleBand().domain(rows.map((r) => r.id)).range([m.t, H - m.b]).padding(0.18);
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).style("height", `${H}px`).attr("role", "img").attr("aria-label", `${xLabel}, ${rows.length} units ranked`);
  svg.append("g").attr("transform", `translate(0,${H - m.b})`).attr("class", "axis").call(d3.axisBottom(x).ticks(Math.max(3, Math.floor(W / 120)), "~s"));
  svg.append("text").attr("class", "axis-title").attr("x", (m.l + W - m.r) / 2).attr("y", H - 6).attr("text-anchor", "middle").text(xLabel);
  const gy = svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).tickSize(0).tickFormat((id) => rows.find((r) => r.id === id).label));
  gy.select(".domain").remove();
  const sel = svg.append("g").selectAll("g").data(rows).join("g").attr("transform", (r) => `translate(0,${y(r.id)})`).style("cursor", onClick ? "pointer" : null);
  // bars: rounded data end, square at the zero baseline
  sel.append("path").attr("d", (r) => {
    const w = Math.max(0, x(r.v) - m.l), h = y.bandwidth(), rr = Math.min(4, w / 2, h / 2);
    return `M${m.l},0h${w - rr}a${rr},${rr} 0 0 1 ${rr},${rr}v${h - 2 * rr}a${rr},${rr} 0 0 1 -${rr},${rr}h-${w - rr}z`;
  }).attr("fill", (r) => (r.id === selected ? INK : C1));
  sel.append("text").attr("x", (r) => x(r.v) + 4).attr("y", y.bandwidth() / 2).attr("dy", "0.35em").attr("class", "bar-label").text((r) => fmtV(r.v));
  sel.append("rect").attr("x", 0).attr("width", W).attr("height", y.step()).attr("y", -y.step() * 0.09).attr("fill", "transparent")
    .on("mousemove", (ev, r) => showTip(tip, r.tip, ev)).on("mouseleave", () => showTip(tip, null))
    .on("click", (ev, r) => onClick && onClick(r));
  if (ref != null && isFinite(ref)) {
    svg.append("line").attr("x1", x(ref)).attr("x2", x(ref)).attr("y1", m.t - 4).attr("y2", H - m.b).attr("stroke", C2).attr("stroke-width", 2).attr("stroke-dasharray", "5 3");
    svg.append("text").attr("x", Math.min(x(ref) + 4, W - m.r)).attr("y", H - m.b - 4).attr("class", "ref-label").text(refLabel);
  }
}

// ---------------------------------------------------------------- chart: lines on one axis
function lines(el, { series, years, yLabel, base = null, legend = [] }) {
  el.innerHTML = "";
  const pts = series.flatMap((s) => s.values.filter((v) => v.v != null));
  if (!pts.length) { empty(el, "No observations for this selection."); return; }
  const [W, H] = size(el);
  const m = { t: 14, r: 92, b: 38, l: 56 };
  const x = d3.scaleLinear().domain(d3.extent(years)).range([m.l, W - m.r]);
  const y = d3.scaleLinear().domain(d3.extent([...pts.map((p) => p.v), ...(base != null ? [base] : [])])).nice().range([H - m.b, m.t]);
  const svg = d3.select(el).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img").attr("aria-label", yLabel);
  svg.append("g").attr("transform", `translate(0,${H - m.b})`).attr("class", "axis").call(d3.axisBottom(x).ticks(Math.min(years.length, Math.floor(W / 70))).tickFormat(d3.format("d")));
  svg.append("g").attr("transform", `translate(${m.l},0)`).attr("class", "axis").call(d3.axisLeft(y).ticks(5));
  svg.append("text").attr("class", "axis-title").attr("transform", `translate(12,${(m.t + H - m.b) / 2}) rotate(-90)`).attr("text-anchor", "middle").text(yLabel);
  svg.append("text").attr("class", "axis-title").attr("x", (m.l + W - m.r) / 2).attr("y", H - 6).attr("text-anchor", "middle").text("Year");
  if (base != null) svg.append("line").attr("x1", m.l).attr("x2", W - m.r).attr("y1", y(base)).attr("y2", y(base)).attr("stroke", LIGHT).attr("stroke-dasharray", "3 3");
  const line = d3.line().defined((d) => d.v != null).x((d) => x(d.t)).y((d) => y(d.v));
  const ord = [...series].sort((a, b) => (a.w || 1) - (b.w || 1));
  svg.append("g").selectAll("path").data(ord).join("path").attr("d", (s) => line(s.values)).attr("fill", "none")
    .attr("stroke", (s) => s.color).attr("stroke-width", (s) => s.w || 2).attr("opacity", (s) => s.opacity ?? 1).attr("stroke-linejoin", "round");
  // isolated points (a value with missing neighbours would otherwise be invisible)
  for (const s of series) s.values.forEach((d, i) => {
    if (d.v != null && (s.values[i - 1]?.v == null) && (s.values[i + 1]?.v == null))
      svg.append("circle").attr("cx", x(d.t)).attr("cy", y(d.v)).attr("r", 3).attr("fill", s.color);
  });
  // direct labels for labelled series
  for (const s of series.filter((s) => s.label && s.direct)) {
    const last = [...s.values].reverse().find((d) => d.v != null);
    if (last) svg.append("text").attr("x", x(last.t) + 6).attr("y", y(last.v)).attr("dy", "0.35em").attr("class", "pt-label").text(s.label);
  }
  // crosshair
  const cross = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).attr("stroke", LIGHT).attr("visibility", "hidden");
  svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", W - m.l - m.r).attr("height", H - m.t - m.b).attr("fill", "transparent")
    .on("mousemove", (ev) => {
      const [px] = d3.pointer(ev); const t = Math.round(x.invert(px));
      cross.attr("x1", x(t)).attr("x2", x(t)).attr("visibility", "visible");
      const rowsT = series.filter((s) => s.label).map((s) => [s, s.values.find((d) => d.t === t)]).filter(([, d]) => d && d.v != null)
        .sort((a, b) => b[1].v - a[1].v).slice(0, 8);
      showTip(tip, `<b>${t}</b>` + rowsT.map(([s, d]) => `<span style="color:${s.color}">●</span> ${esc(s.label)}: <span class="v">${f3(d.v)}</span>`).join("<br>"), ev);
    })
    .on("mouseleave", () => { cross.attr("visibility", "hidden"); showTip(tip, null); });
  if (legend.length) {
    const lg = d3.select(el).append("div").attr("class", "an-legend");
    for (const l of legend) lg.append("span").html(`<i style="background:${l.color};height:${l.w || 3}px"></i>${esc(l.label)}`);
  }
}

// ================================================================ MODULE A
function renderA() {
  const i = yi(st.aYear), meas = MEASURES[st.aM];
  $("aMeasureNote").textContent = meas.note;
  const pts = [], rank = [];
  let nNoGdp = 0;
  for (const [iso, e] of Object.entries(S.nat.economies)) {
    const v = econValue(e, st.aM, i);
    const g = GROUP[e.imf] || GROUP.not_classified;
    if (!isPos(v)) continue;
    rank.push({ iso, name: e.name, group: e.imf, v, gdppc: e.gdppc[i], cov: e.cov[i] });
    if (!isPos(e.gdppc[i])) { nNoGdp++; continue; }
    pts.push({ id: iso, x: e.gdppc[i], y: v, label: e.name, color: g.color, hollow: g.hollow, group: e.imf });
  }
  // A1 scatter
  const fitR = scatter($("a1"), {
    pts, xLabel: "GDP per capita, PPP (constant 2021 int. $)", yLabel: meas.label, highlight: st.aFind, labelIds: ["AUS", "IND", "CHN", "USA"],
    tipHtml: (d) => `<b>${esc(d.label)}</b>${esc(GROUP[d.group].label)}<br>${esc(meas.label)}: <span class="v">${fmtExact(d.y)}</span> <span class="muted">${esc(meas.unit)}</span><br>GDP per capita: <span class="v">${d3.format(",.0f")(d.x)}</span> <span class="muted">int. $</span>`,
    onClick: (d) => { st.aFind = d.id; $("aFind").value = `${d.label} (${d.id})`; renderA(); },
  });
  $("a1Title").textContent = `${meas.label} and GDP per capita, ${st.aYear}`;
  $("a1Cap").innerHTML = `${legendDots()} · n = ${pts.length} economies with positive radiance and WDI GDP per capita${nNoGdp ? `; ${nNoGdp} without WDI GDP per capita left out` : ""}.
    Dashed line: least-squares fit on logs (descriptive${fitR ? `, slope ${d3.format(".2f")(fitR.b)}, R² ${d3.format(".2f")(fitR.r2)}` : ""}). Sources: lights v2; WDI NY.GDP.PCAP.PP.KD; IMF WEO April 2023.`;
  setExport("a1", pts.map((p) => ({ iso3: p.id, economy: p.label, imf_group: p.group, year: st.aYear, [meas.key]: p.y, gdp_pc_ppp: p.x })),
    ["iso3", "economy", "imf_group", "year", meas.key, "gdp_pc_ppp"], `ntl_${meas.key}_vs_gdppc_${st.aYear}.csv`);

  // A2 strip + statistics from module_a.json
  const groups = ["advanced", "emde"].map((k) => ({ key: k, pts: rank.filter((r) => r.group === k).map((r) => ({ id: r.iso, y: r.v, label: r.name, group: k, color: GROUP[k].color, unit: meas.unit })) }));
  strip($("a2"), { groups, yLabel: meas.label, highlight: st.aFind });
  const s = S.A.by_year[st.aYear]?.[meas.key];
  if (s && s.separation) {
    const sep = s.separation;
    $("a2Stats").innerHTML = `<dl class="kv">
      <dt>Median, advanced</dt><dd>${fmtExact(s.advanced.median)} <span class="muted">(IQR ${fmt(s.advanced.q25)}–${fmt(s.advanced.q75)}, n = ${s.advanced.n})</span></dd>
      <dt>Median, EMDE</dt><dd>${fmtExact(s.emde.median)} <span class="muted">(IQR ${fmt(s.emde.q25)}–${fmt(s.emde.q75)}, n = ${s.emde.n})</span></dd>
      <dt>Separation (AUC)</dt><dd>${d3.format(".2f")(sep.auc)} <span class="muted">[95% bootstrap ${d3.format(".2f")(sep.ci95[0])}–${d3.format(".2f")(sep.ci95[1])}]; Mann–Whitney p ${fP(sep.p_mannwhitney)}</span></dd>
      <dt>Overlap</dt><dd class="text">${pct(s.share_emde_above_advanced_median, 0)} of EMDE are above the advanced median; ${pct(s.share_advanced_below_emde_median, 0)} of advanced economies are below the EMDE median</dd></dl>`;
  } else $("a2Stats").innerHTML = `<p class="hint">Group statistics are not available for this year and measure.</p>`;
  $("a2Cap").innerHTML = `Each dot is an economy; box = interquartile range, bar = median. AUC is the probability that a randomly drawn advanced economy has a higher value than a randomly drawn EMDE (0.5 = no separation, 1 = complete). ${st.aYear}; positive values only.`;
  setExport("a2", rank.filter((r) => r.group !== "not_classified").map((r) => ({ iso3: r.iso, economy: r.name, imf_group: r.group, year: st.aYear, [meas.key]: r.v })),
    ["iso3", "economy", "imf_group", "year", meas.key], `ntl_${meas.key}_by_imf_group_${st.aYear}.csv`);

  // A3 ranking table
  rank.sort((a, b) => b.v - a.v);
  $("a3Title").textContent = `Ranking by ${meas.label.toLowerCase()}, ${st.aYear}`;
  $("a3").innerHTML = `<table><thead><tr><th class="num">Rank</th><th>Economy</th><th>IMF group</th><th class="num">${esc(meas.label)}</th><th class="num">GDP pc (PPP)</th><th class="num">Coverage</th></tr></thead><tbody>${
    rank.map((r, k) => `<tr data-iso="${r.iso}" tabindex="0" class="${r.iso === st.aFind ? "sel" : ""}"><td class="num">${k + 1}</td><td>${esc(r.name)}</td>
      <td><span class="tag ${r.group === "advanced" ? "exact" : r.group === "emde" ? "approx" : "planned"}">${esc(GROUP[r.group].short)}</span></td>
      <td class="num">${fmtExact(r.v)}</td><td class="num">${r.gdppc ? d3.format(",.0f")(r.gdppc) : "NA"}</td><td class="num">${pct(r.cov, 0)}</td></tr>`).join("")}</tbody></table>`;
  $("a3Cap").innerHTML = `${rank.length} economies with a positive value in ${st.aYear}. ${esc(meas.unit)}. “NA” = not reported by WDI (left missing, not estimated).
    Taiwan is built from the source's China unit “Taiwan Sheng” and has no WDI series.`;
  const selRow = $("a3").querySelector("tr.sel"); if (selRow) selRow.scrollIntoView({ block: "nearest" });
  $("a3").querySelectorAll("tbody tr").forEach((tr) => {
    const go = () => { st.aFind = tr.dataset.iso; $("aFind").value = `${S.nat.economies[st.aFind].name} (${st.aFind})`; renderA(); };
    tr.addEventListener("click", go); tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
  });
  setExport("a3", rank.map((r, k) => ({ rank: k + 1, iso3: r.iso, economy: r.name, imf_group: r.group, year: st.aYear, [meas.key]: r.v, gdp_pc_ppp: r.gdppc, coverage: r.cov })),
    ["rank", "iso3", "economy", "imf_group", "year", meas.key, "gdp_pc_ppp", "coverage"], `ranking_${meas.key}_${st.aYear}.csv`);

  // A4 correlations (all measures, chosen year)
  const rowsC = Object.entries(MEASURES).map(([k, mm]) => {
    const c = S.A.by_year[st.aYear]?.[mm.key]?.corr_with_ln_gdp_pc_ppp;
    const cell = (g) => (c?.[g] ? `${d3.format(".2f")(c[g].spearman)} <span class="muted">(n ${c[g].n})</span>` : "—");
    return `<tr class="${k === st.aM ? "sel" : ""}"><td>${esc(mm.label)}</td><td class="num">${cell("all")}</td><td class="num">${cell("advanced")}</td><td class="num">${cell("emde")}</td><td class="num">${c?.all ? d3.format(".2f")(c.all.pearson_logs) : "—"}</td></tr>`;
  }).join("");
  $("a4").innerHTML = `<div class="table-scroll"><table><thead><tr><th>Measure, ${st.aYear}</th><th class="num">Spearman, all</th><th class="num">Advanced</th><th class="num">EMDE</th><th class="num">Pearson (logs), all</th></tr></thead><tbody>${rowsC}</tbody></table></div>`;
}
function legendDots() {
  return Object.values(GROUP).map((g) => `<span class="an-key"><i style="${g.hollow ? `border:1.5px solid ${g.color};background:#fff` : `background:${g.color}`}"></i>${esc(g.label)}</span>`).join(" ");
}

// ================================================================ MODULE B
function bUnits() {
  const ys = S.adm1.years, i = ys.indexOf(st.bYear);
  return Object.entries(S.adm1.units).filter(([, u]) => economyOf(u) === st.bIso).map(([code, u]) => ({ code, ...u, i }));
}
function renderB() {
  const units = bUnits(), ys = S.adm1.years, i = ys.indexOf(st.bYear);
  const e = S.nat.economies[st.bIso], ni = yi(st.bYear);
  const natSum = e?.sum[ni], natMean = e?.mean[ni];
  const val = (u) => (st.bM === "mean" ? u.mean[i] : st.bM === "sum" ? u.sum[i] : u.sum[i] != null && isPos(natSum) ? u.sum[i] / natSum : null);
  const rows = units.map((u) => ({ id: u.code, label: u.name, v: val(u), u })).filter((r) => r.v != null);
  const missing = units.length - rows.length;
  rows.sort((a, b) => b.v - a.v);
  const mLabel = st.bM === "mean" ? "Mean radiance (nW·cm⁻²·sr⁻¹)" : st.bM === "sum" ? "Total radiance (nW·cm⁻²·sr⁻¹ × px)" : "Share of national total radiance";
  const fmtV = st.bM === "share" ? (v) => pct(v, 1) : fmt;
  for (const r of rows) r.tip = `<b>${esc(r.label)}</b><span class="muted">${esc(r.id)}</span><br>${esc(mLabel)}: <span class="v">${st.bM === "share" ? pct(r.v, 2) : fmtExact(r.v)}</span><br>Coverage: <span class="v">${pct(r.u.cov[i], 0)}</span><br><span class="muted">Click to follow it over time</span>`;
  bars($("b1"), { rows, xLabel: mLabel, ref: st.bM === "mean" ? natMean : null, refLabel: `National mean ${fmt(natMean)}`, selected: st.bSel, fmtV,
    onClick: (r) => { st.bSel = r.id === st.bSel ? null : r.id; renderB(); } });
  $("b1Title").textContent = `${e?.name ?? st.bIso}: ADM1 units ranked, ${st.bYear}`;
  $("b1Cap").innerHTML = `World Bank ADM1 units, official annual composite ${st.bYear}; exact aggregates of the source districts.${missing ? ` ${missing} unit(s) without a valid observation in this year are not drawn.` : ""}
    ${st.bM === "mean" ? "Dashed line: national mean radiance (all valid pixels of the country)." : ""} Bars start at zero.`;
  setExport("b1", rows.map((r, k) => ({ rank: k + 1, ADM1CD_c: r.id, name: r.label, year: st.bYear, value: r.v, measure: st.bM, coverage: r.u.cov[i] })),
    ["rank", "ADM1CD_c", "name", "year", "measure", "value", "coverage"], `${st.bIso}_adm1_${st.bM}_${st.bYear}.csv`);

  // disparity statistics (descriptive)
  const pos = rows.filter((r) => isPos(r.u.sum[i]));
  const means = pos.map((r) => r.u.mean[i]).filter(isPos).sort(d3.ascending);
  const sums = pos.map((r) => r.u.sum[i]).sort(d3.descending);
  const top = sums.length >= 5 ? d3.sum(sums.slice(0, Math.ceil(sums.length * 0.2))) / d3.sum(sums) : null;
  const hi = rows.length && st.bM !== "share" ? rows[0] : null;
  const loMean = means.length ? pos.find((r) => r.u.mean[i] === means[0]) : null, hiMean = means.length ? pos.find((r) => r.u.mean[i] === means.at(-1)) : null;
  $("bStats").innerHTML = `<dl class="kv an-kv">
    <dt>ADM1 units</dt><dd>${units.length}${missing ? ` (${missing} without data)` : ""}</dd>
    <dt>National mean · total</dt><dd>${fmtExact(natMean)} · ${fmt(natSum)}</dd>
    <dt>Brightest ÷ dimmest (mean)</dt><dd>${means.length > 1 ? `${d3.format(",.1f")(means.at(-1) / means[0])}× <span class="muted">(${esc(hiMean.label)} vs ${esc(loMean.label)})</span>` : "—"}</dd>
    <dt>P90 ÷ P10 (mean)</dt><dd>${means.length >= 10 ? `${d3.format(",.1f")(d3.quantile(means, 0.9) / d3.quantile(means, 0.1))}×` : "— (fewer than 10 units)"}</dd>
    <dt>Coefficient of variation (mean)</dt><dd>${means.length > 2 ? d3.format(".2f")(d3.deviation(means) / d3.mean(means)) : "—"} <span class="muted">unweighted across units</span></dd>
    <dt>Share of light in brightest 20% of units</dt><dd>${top != null ? pct(top, 0) : "—"}</dd></dl>`;

  // B2 over time
  const idx = st.bM !== "share";
  const key = st.bM === "mean" ? "mean" : "sum";
  const series = units.map((u) => {
    const v0 = u[key].find(isPos);
    const values = ys.map((t, k) => ({ t, v: idx ? (isPos(v0) && u[key][k] != null ? (100 * u[key][k]) / v0 : null) : (u.sum[k] != null && isPos(e?.sum[yi(t)]) ? (100 * u.sum[k]) / e.sum[yi(t)] : null) }));
    const sel = u.code === st.bSel;
    return { id: u.code, label: u.name, values, color: sel ? C1 : LIGHT, w: sel ? 3 : 1.1, direct: sel };
  });
  const natSeries = e ? { id: "nat", label: `${e.name} (national)`, color: INK, w: 2.6, direct: true,
    values: ys.map((t) => { const v0 = e[key].find(isPos); const v = e[key][yi(t)]; return { t, v: idx ? (isPos(v0) && v != null ? (100 * v) / v0 : null) : 100 / Math.max(1, units.length) }; }) } : null;
  if (natSeries && idx) series.push(natSeries);
  lines($("b2"), { series, years: ys, yLabel: idx ? `${st.bM === "mean" ? "Mean" : "Total"} radiance, first year = 100` : "Share of national total (%)",
    base: idx ? 100 : null,
    legend: [{ label: idx ? "National" : "", color: INK, w: 3 }, { label: st.bSel ? "Selected unit" : "Select a bar to highlight a unit", color: C1, w: 3 }, { label: "Other ADM1 units", color: LIGHT, w: 2 }].filter((l) => l.label) });
  $("b2Title").textContent = idx ? `${st.bM === "mean" ? "Mean" : "Total"} radiance over time, indexed` : "Share of national light over time";
  $("b2Cap").innerHTML = `Official annual composites ${ys[0]}–${ys.at(-1)}. ${idx ? "Each line is divided by its first positive value (×100), so lines show relative change, not level." : "Unit total ÷ national total of the same year."} Gaps are years without a valid observation.`;
  setExport("b2", units.flatMap((u) => ys.map((t, k) => ({ ADM1CD_c: u.code, name: u.name, year: t, ntl_sum: u.sum[k], ntl_mean: u.mean[k], coverage: u.cov[k] }))),
    ["ADM1CD_c", "name", "year", "ntl_sum", "ntl_mean", "coverage"], `${st.bIso}_adm1_annual_series.csv`);
  renderB3();
}
function renderB3() {
  const D = S.dose, body = $("b3Body");
  const regs = Object.entries(D.regions).filter(([, r]) => r.iso === st.bIso);
  const e = S.nat.economies[st.bIso];
  if (!regs.length) {
    body.innerHTML = `<p class="panel-pad muted" style="margin:0">No documented subnational GDP and population source is integrated for ${esc(e?.name ?? st.bIso)}.
      DOSE V2.14 covers ${new Set(Object.values(D.regions).map((r) => r.iso)).size} countries; values are never estimated for others.</p>`;
    $("b3Title").textContent = "Regional GDP, population and radiance"; $("b3Cap").textContent = ""; setExport("b3", [], [], "none.csv"); return;
  }
  const year = Math.min(Math.max(st.bYear, D.years[0]), D.years.at(-1)), k = D.years.indexOf(year);
  const rows = regs.map(([gid, r]) => ({ gid, name: r.name, link: r.link, pop: r.pop[k], grppc: r.grppc[k], sum: r.sum[k], mean: r.mean[k] }))
    .map((r) => ({ ...r, pc: r.sum != null && isPos(r.pop) ? r.sum / r.pop : null }));
  const pts = rows.filter((r) => isPos(r.pc) && isPos(r.grppc)).map((r) => ({ id: r.gid, x: r.grppc, y: r.pc, label: r.name, color: C1 }));
  body.innerHTML = `<div class="an-b3-grid"><div class="chart" id="b3c" style="height:340px"></div><div class="table-scroll datatable" id="b3t" style="max-height:340px"></div></div>`;
  const fitR = scatter($("b3c"), { pts, xLabel: "GRP per capita (constant 2015 US$)", yLabel: "Radiance per person", labelIds: pts.length <= 40 ? [] : [],
    tipHtml: (d) => { const r = rows.find((x) => x.gid === d.id); return `<b>${esc(r.name)}</b><span class="muted">${esc(r.gid)} · DOSE link: ${esc(r.link)}</span><br>GRP per capita: <span class="v">${d3.format(",.0f")(r.grppc)}</span> US$<br>Population: <span class="v">${d3.format(",.0f")(r.pop)}</span><br>Radiance per person: <span class="v">${fmtExact(r.pc)}</span>`; } });
  const byG = [...rows].sort((a, b) => (b.grppc ?? -1) - (a.grppc ?? -1));
  const rankPc = new Map([...rows].filter((r) => r.pc != null).sort((a, b) => b.pc - a.pc).map((r, j) => [r.gid, j + 1]));
  $("b3t").innerHTML = `<table><thead><tr><th>Region</th><th class="num">GRP pc rank</th><th class="num">Light pc rank</th><th class="num">GRP pc</th><th class="num">Population</th><th class="num">Radiance / person</th></tr></thead><tbody>${
    byG.map((r, j) => `<tr><td>${esc(r.name)}</td><td class="num">${r.grppc != null ? j + 1 : "NA"}</td><td class="num">${rankPc.get(r.gid) ?? "NA"}</td><td class="num">${r.grppc != null ? d3.format(",.0f")(r.grppc) : "NA"}</td><td class="num">${r.pop != null ? fmt(r.pop) : "NA"}</td><td class="num">${r.pc != null ? fmt(r.pc) : "NA"}</td></tr>`).join("")}</tbody></table>`;
  const sp = pts.length > 4 ? spearman(pts.map((p) => p.x), pts.map((p) => p.y)) : null;
  $("b3Title").textContent = `${e?.name ?? st.bIso}: regional GDP per capita and radiance per person, ${year}`;
  $("b3Cap").innerHTML = `DOSE V2.14 regions (GADM-based <code>GID_1</code>; for ${esc(e?.name ?? "")} these may differ from the World Bank ADM1 units above), ${year}${year !== st.bYear ? ` (closest DOSE year to ${st.bYear})` : ""}.
    Lights aggregated to each DOSE region from its own districts (exact rules). n = ${pts.length} of ${rows.length} regions with positive radiance, population and GRP;
    ${sp != null ? `Spearman ρ = ${d3.format(".2f")(sp)}; ` : ""}dashed line: descriptive least-squares fit on logs${fitR ? ` (slope ${d3.format(".2f")(fitR.b)})` : ""}.
    Radiance per person depends on how lighting, settlement and industry differ across regions; it is not a GDP estimate.`;
  setExport("b3", rows.map((r) => ({ GID_1: r.gid, region: r.name, year, pop: r.pop, grp_pc_usd_2015: r.grppc, ntl_sum: r.sum, ntl_mean: r.mean, ntl_sum_per_person: r.pc, link_method: r.link })),
    ["GID_1", "region", "year", "pop", "grp_pc_usd_2015", "ntl_sum", "ntl_mean", "ntl_sum_per_person", "link_method"], `${st.bIso}_dose_${year}.csv`);
}
function spearman(a, b) {
  const rk = (v) => { const o = v.map((x, i) => [x, i]).sort((p, q) => p[0] - q[0]); const r = Array(v.length); o.forEach(([, i], j) => (r[i] = j + 1)); return r; };
  const ra = rk(a), rb = rk(b), ma = d3.mean(ra), mb = d3.mean(rb);
  let s = 0, sa = 0, sb = 0; for (let i = 0; i < ra.length; i++) { s += (ra[i] - ma) * (rb[i] - mb); sa += (ra[i] - ma) ** 2; sb += (rb[i] - mb) ** 2; }
  return s / Math.sqrt(sa * sb);
}

// ================================================================ MODULE C
function cData() {
  const out = [];
  if (st.cL === "nat") {
    const i = yi(st.cYear);
    for (const [iso, e] of Object.entries(S.nat.economies)) {
      if (iso === "TWN") continue;
      out.push({ id: iso, label: e.name, group: e.imf, pop: e.pop[i], gdppc: e.gdppc[i], gdp: e.gdp[i], sum: e.sum[i], mean: e.mean[i] });
    }
  } else {
    const k = S.dose.years.indexOf(st.cYear);
    for (const [gid, r] of Object.entries(S.dose.regions)) {
      if (st.cIso && r.iso !== st.cIso) continue;
      const pop = r.pop[k], g = r.grppc[k];
      out.push({ id: gid, label: `${r.name} (${r.iso})`, iso: r.iso, pop, gdppc: g, gdp: isPos(pop) && isPos(g) ? pop * g : null, sum: r.sum[k], mean: r.mean[k] });
    }
  }
  return out;
}
function renderC() {
  const rows = cData(), nat = st.cL === "nat";
  const gdpLab = nat ? "GDP, PPP (constant 2021 int. $)" : "GRP (constant 2015 US$)";
  const gdppcLab = nat ? "GDP per capita, PPP (2021 int. $)" : "GRP per capita (2015 US$)";
  const color = (r) => (nat ? (GROUP[r.group] || GROUP.not_classified).color : st.cIso ? C1 : r.iso === "AUS" ? C3 : r.iso === "IND" ? C2 : C1);
  const hollow = (r) => nat && (GROUP[r.group] || GROUP.not_classified).hollow;
  const lab = nat ? ["AUS", "IND"] : [];
  const panels = [
    ["c1", "pop", "sum", nat ? "Population (WDI)" : "Population (DOSE)", "Total radiance"],
    ["c2", "gdp", "sum", gdpLab, "Total radiance"],
    ["c3", "gdppc", "mean", gdppcLab, "Mean radiance"],
    ["c4", "gdppc", "pc", gdppcLab, "Radiance per person"],
  ];
  $("c2Title").textContent = nat ? "Total radiance vs GDP" : "Total radiance vs gross regional product";
  $("c3Title").textContent = nat ? "Mean radiance vs GDP per capita" : "Mean radiance vs GRP per capita";
  $("c4Title").textContent = nat ? "Radiance per person vs GDP per capita" : "Radiance per person vs GRP per capita";
  const exportRows = rows.map((r) => ({ id: r.id, name: r.label, year: st.cYear, pop: r.pop, gdp_pc: r.gdppc, gdp: r.gdp, ntl_sum: r.sum, ntl_mean: r.mean }));
  for (const [id, xk, yk, xl, yl] of panels) {
    const pts = [];
    let excl = 0;
    for (const r of rows) {
      const yv = yk === "pc" ? (r.sum != null && isPos(r.pop) ? r.sum / r.pop : null) : r[yk];
      const xv = r[xk];
      if (!isPos(xv) || !isPos(yv)) { excl++; continue; }
      pts.push({ id: r.id, x: xv, y: yv, label: r.label, color: color(r), hollow: hollow(r), group: r.group, r: nat ? 4 : 3 });
    }
    const fitR = scatter($(id), { pts, xLabel: xl, yLabel: yl, labelIds: lab,
      tipHtml: (d) => `<b>${esc(d.label)}</b>${nat ? esc((GROUP[d.group] || GROUP.not_classified).label) + "<br>" : ""}${esc(yl)}: <span class="v">${fmtExact(d.y)}</span><br>${esc(xl)}: <span class="v">${fmt(d.x)}</span>` });
    $(id + "Cap").innerHTML = `n = ${pts.length}${excl ? ` · ${excl} without positive values for both variables (not drawn; no constant added)` : ""}${fitR ? ` · descriptive slope on logs ${d3.format(".2f")(fitR.b)}, R² ${d3.format(".2f")(fitR.r2)}` : ""}`;
  }
  setExport("c", exportRows, ["id", "name", "year", "pop", "gdp_pc", "gdp", "ntl_sum", "ntl_mean"], `population_development_${st.cL}_${st.cYear}.csv`);
  $("cNote").innerHTML = nat
    ? `Countries, ${st.cYear}: lights (official annual composite) and WDI population, GDP and GDP per capita (PPP, constant 2021 international $). ${legendDots()}. Labelled: Australia, India.`
    : `DOSE regions, ${st.cYear}${st.cIso ? `, ${esc(S.nat.economies[st.cIso]?.name ?? st.cIso)}` : ` · <span class="an-key"><i style="background:${C3}"></i>Australia</span> <span class="an-key"><i style="background:${C2}"></i>India</span> <span class="an-key"><i style="background:${C1}"></i>other countries</span>`}: DOSE population and gross regional product per capita (constant 2015 US$); lights aggregated to each region. Regions of different countries share the axes but not price levels; the models below compare regions within the same country.`;
  renderModels();
}
function modelRow(label, m, extra = "") {
  if (!m) return "";
  return `<tr><td>${label}${m.warning ? ` <span class="tag warn" title="${esc(m.warning)}">few clusters</span>` : ""}</td><td class="num">${fN(m.n)}</td>
    <td class="num">${fB(m.coef.ln_pop)}</td><td class="num">${fB(m.coef.ln_gdppc)}</td><td class="num">${d3.format(".2f")(m.r2)}</td>
    <td class="num">${m.test_equal_elasticities ? fP(m.test_equal_elasticities.p) : "—"}</td><td class="small">${esc(m.se)}${extra}</td></tr>`;
}
function renderModels() {
  const M = S.M, nat = st.cL === "nat";
  const head = `<thead><tr><th>Specification</th><th class="num">n</th><th class="num">log population</th><th class="num">log GDP pc</th><th class="num">R²</th><th class="num">p (equal)</th><th>Standard errors</th></tr></thead>`;
  let body = "", notes = "";
  if (nat) {
    const xs = M.national.cross_sections.ntl_sum[st.cYear], xg = M.national.cross_sections.ntl_nogf_5km_sum[st.cYear];
    const mor = (m) => (m?.morans_i_residuals ? `; Moran's I ${d3.format(".2f")(m.morans_i_residuals.I)} (p ${fP(m.morans_i_residuals.p_perm)})` : "");
    body += modelRow(`Countries, ${st.cYear}`, xs, mor(xs)) + modelRow(`Countries, ${st.cYear}, gas flares excluded`, xg, mor(xg));
    const P = M.national.pooled;
    body += modelRow(`Pooled ${M.national.sample.years.join("–")}, year effects`, P.both) + modelRow("Within-country (country + year effects)", P.both_country_fe);
    body += modelRow("Population only, year effects", P.pop_only) + modelRow("GDP per capita only, year effects", P.gdppc_only);
    const ex = xs?.excluded;
    notes = `<p class="hint">${ex ? `${st.cYear}: excluded ${ex.nonpositive_or_missing_radiance} without positive radiance, ${ex.missing_population} without WDI population, ${ex.missing_gdp_pc} without WDI GDP per capita (some overlap). ` : ""}
      Brackets: 95% confidence intervals. “p (equal)” tests whether the two elasticities are equal, i.e. whether total radiance scales with GDP alone.
      ${P.both_country_fe?.note ? esc(P.both_country_fe.note) : ""} Moran's I &gt; 0 with small p means residuals of neighbouring countries are similar, so the cross-section standard errors are too small.</p>`;
  } else {
    const D = M.subnational_dose, P = D.pooled;
    body += modelRow(`All DOSE regions ${D.sample.years.join("–")}, year effects`, P.both_pooled) + modelRow("Within-country (country + year effects)", P.both_country_fe);
    body += modelRow("Population only, within-country", P.pop_only_country_fe) + modelRow("GRP per capita only, within-country", P.gdppc_only_country_fe);
    for (const [iso, m] of Object.entries(D.by_country)) {
      const mor = m.morans_i_residuals_last_year ? `; Moran's I ${d3.format(".2f")(m.morans_i_residuals_last_year.I)} (p ${fP(m.morans_i_residuals_last_year.p_perm)})` : "";
      body += modelRow(`${esc(S.nat.economies[iso]?.name ?? iso)} (${m.n_regions} regions, ${m.years.join("–")})`, m, mor);
    }
    notes = `<p class="hint">GDP per capita here is DOSE gross regional product per capita (constant 2015 US$). Sample: ${fN(D.sample.n_obs)} region-years, ${D.sample.n_regions} regions,
      ${D.sample.n_countries} countries; excluded ${D.sample.excluded.nonpositive_or_missing_radiance} without positive radiance, ${D.sample.excluded.missing_population} without population, ${D.sample.excluded.missing_gdp_pc} without GRP.
      Country rows use year effects and standard errors clustered by region; with fewer than about 20 regions (Australia has 8) they are unreliable and the row is descriptive.</p>`;
  }
  $("cModels").innerHTML = `<div class="table-scroll"><table class="an-models">${head}<tbody>${body}</tbody></table></div>${notes}
    <p class="hint">${M.notes.map(esc).join(" ")}</p>`;
  const cvs = nat ? [M.national.cv_leave_one_region_out, M.national.cv_temporal] : [M.subnational_dose.cv_leave_one_country_out, M.subnational_dose.cv_temporal];
  const nm = { pop_only: "Population only", gdppc_only: "GDP per capita only", both: "Both", both_country_fe: "Both + country effects" };
  $("cCv").innerHTML = cvs.map((c) => `<div><h4 class="an-h4">${esc(c.design)}</h4><div class="table-scroll"><table><thead><tr><th>Predictors</th><th class="num">RMSE (log points)</th><th class="num">R² out of sample</th><th class="num">n test</th></tr></thead><tbody>${
    Object.entries(c.models).map(([k, v]) => `<tr><td>${nm[k] ?? k}</td><td class="num">${d3.format(".2f")(v.rmse)}</td><td class="num">${d3.format(".2f")(v.r2_oos_vs_training_mean)}</td><td class="num">${fN(v.n_test)}</td></tr>`).join("")}
    <tr><td class="muted">Null: training mean</td><td class="num muted">${d3.format(".2f")(Object.values(c.models)[0].rmse_null_training_mean)}</td><td class="num muted">0</td><td></td></tr></tbody></table></div></div>`).join("") +
    `<p class="hint">Error of predicting log total radiance for held-out ${nat ? "regions of the world or later years" : "countries or later years"}. Lower RMSE is better; R² is relative to predicting the training mean. One log point ≈ a factor of 2.7.</p>`;
  renderC5();
}
function renderC5() {
  const e = S.nat.economies[st.c5]; const ys = S.nat.years;
  const idx = (arr) => { const v0 = arr.find(isPos); return ys.map((t, k) => ({ t, v: isPos(v0) && arr[k] != null ? (100 * arr[k]) / v0 : null })); };
  const series = [
    { id: "sum", label: "Total radiance", values: idx(e.sum), color: C1, w: 2.4, direct: true },
    { id: "pop", label: "Population", values: idx(e.pop), color: C3, w: 2.4, direct: true },
    { id: "gdp", label: "GDP (PPP)", values: idx(e.gdp), color: C2, w: 2.4, direct: true },
  ];
  lines($("c5"), { series, years: ys, yLabel: "Index, first available year = 100", base: 100 });
  $("c5Title").textContent = `${e.name}: radiance, population and GDP over time`;
  const miss = ["pop", "gdp"].filter((k) => e[k].every((v) => v == null));
  $("c5Cap").innerHTML = `Each series divided by its first available value (×100), so all three share one axis. Lights: official annual composites ${ys[0]}–${ys.at(-1)};
    population and GDP: WDI${miss.length ? ` (${miss.join(", ")} not reported for this economy)` : ""}. Co-movement over a short period is not evidence of a causal link.`;
  setExport("c5", ys.map((t, k) => ({ iso3: st.c5, year: t, ntl_sum: e.sum[k], pop: e.pop[k], gdp_ppp: e.gdp[k] })), ["iso3", "year", "ntl_sum", "pop", "gdp_ppp"], `${st.c5}_lights_pop_gdp.csv`);
}

// ================================================================ wiring
function seg(id, attr, key, fn) {
  document.querySelectorAll(`#${id} [data-${attr}]`).forEach((b) => b.addEventListener("click", () => {
    if (b.disabled) return;
    st[key] = b.dataset[attr];
    document.querySelectorAll(`#${id} [data-${attr}]`).forEach((x) => x.setAttribute("aria-pressed", x === b));
    fn();
  }));
}
function fillSelect(sel, items, value) {
  sel.innerHTML = items.map(([v, l]) => `<option value="${esc(v)}"${String(v) === String(value) ? " selected" : ""}>${esc(l)}</option>`).join("");
}
function cYears() {
  return st.cL === "nat" ? Object.keys(S.M.national.cross_sections.ntl_sum).map(Number) : S.dose.years;
}
async function init() {
  try {
    const get = (u) => fetch(u).then((r) => { if (!r.ok) throw new Error(u); return r.json(); });
    [S.nat, S.A, S.M, S.adm1, S.dose] = await Promise.all(["national", "module_a", "models", "adm1_annual", "dose_regions"].map((n) => get(`data/v2/analysis/${n}.json`)));
  } catch (err) {
    console.error(err);
    document.querySelectorAll(".an-fig .chart, #cModels, #cCv").forEach((el) => empty(el, "The analysis data could not be loaded."));
    return;
  }
  $("wdiDate").textContent = S.nat.sources.wdi.retrieved_utc.slice(0, 10);
  const names = Object.entries(S.nat.economies).map(([iso, e]) => [iso, e.name]).sort((a, b) => a[1].localeCompare(b[1]));
  // A
  const aYears = Object.keys(S.A.by_year).map(Number);
  fillSelect($("aYear"), aYears.map((y) => [y, y]), st.aYear);
  $("aYear").addEventListener("change", (e) => { st.aYear = +e.target.value; renderA(); });
  seg("aMeasure", "m", "aM", renderA);
  for (const [iso, n] of names) $("aCountries").appendChild(new Option(`${n} (${iso})`));
  const find = () => { const m = $("aFind").value.match(/\(([A-Z]{3})\)\s*$/); st.aFind = m && S.nat.economies[m[1]] ? m[1] : null; renderA(); };
  $("aFind").addEventListener("change", find); $("aFind").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); find(); } });
  // B
  const counts = {};
  for (const u of Object.values(S.adm1.units)) if (!String(u.tier).startsWith("none")) counts[economyOf(u)] = (counts[economyOf(u)] || 0) + 1;
  const bList = names.filter(([iso]) => (counts[iso] || 0) >= 2);
  const hash0 = new URLSearchParams(location.hash.slice(1));
  if (hash0.get("b") && counts[hash0.get("b")] >= 2) st.bIso = hash0.get("b");
  fillSelect($("bCountry"), bList.map(([iso, n]) => [iso, `${n} (${counts[iso]})`]), st.bIso);
  st.bYear = S.adm1.years.at(-1);
  fillSelect($("bYear"), S.adm1.years.map((y) => [y, y]), st.bYear);
  $("bCountry").addEventListener("change", (e) => { st.bIso = e.target.value; st.bSel = null; history.replaceState(null, "", `#b=${st.bIso}`); renderB(); });
  $("bYear").addEventListener("change", (e) => { st.bYear = +e.target.value; renderB(); });
  seg("bMeasure", "m", "bM", renderB);
  // C
  const doseIso = [...new Set(Object.values(S.dose.regions).map((r) => r.iso))].sort();
  fillSelect($("cCountry"), [["", "All countries"], ...doseIso.map((iso) => [iso, S.nat.economies[iso]?.name ?? iso])], "");
  const refreshCYear = () => { const ys = cYears(); if (!ys.includes(st.cYear)) st.cYear = st.cL === "nat" ? 2022 : ys.at(-1); fillSelect($("cYear"), ys.map((y) => [y, y]), st.cYear); };
  refreshCYear();
  $("cYear").addEventListener("change", (e) => { st.cYear = +e.target.value; renderC(); });
  $("cCountry").addEventListener("change", (e) => { st.cIso = e.target.value; renderC(); });
  seg("cLevel", "l", "cL", () => { $("cCountryWrap").hidden = st.cL === "nat"; refreshCYear(); renderC(); });
  fillSelect($("c5Country"), names.filter(([iso]) => S.nat.economies[iso].pop.some((v) => v != null)), st.c5);
  $("c5Country").addEventListener("change", (e) => { st.c5 = e.target.value; renderC5(); });
  // exports
  document.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", () => {
    const x = S.exp[b.dataset.export]; if (x && x.rows.length) downloadCsv(x.rows, x.cols, x.name);
  }));
  renderA(); renderB(); renderC();
  let t; addEventListener("resize", () => { clearTimeout(t); t = setTimeout(() => { renderA(); renderB(); renderC(); }, 200); });
  if (location.hash.startsWith("#b=")) $("subnational").scrollIntoView();
}
init();
