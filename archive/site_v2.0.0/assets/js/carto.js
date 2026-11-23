// Shared cartography + formatting helpers (Scientific Cartography system).
// Used by worldmap.js (home page) and explore.js. Requires global d3 v7.

export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// compact display (axes, legends)
export const fmt = (v) => v == null || !isFinite(v) ? "NA" : v === 0 ? "0" : Math.abs(v) >= 1e6 ? d3.format(".3~s")(v).replace("G", "B")
  : Math.abs(v) >= 1000 ? d3.format(",.0f")(v) : Math.abs(v) >= 10 ? d3.format(".1f")(v) : Math.abs(v) >= 0.001 ? d3.format(".2~r")(v) : d3.format(".2~e")(v);
// exact-ish display (tooltips, details): 6 significant digits, grouped
export const fmtExact = (v) => v == null || !isFinite(v) ? "NA" : v === 0 ? "0" : Math.abs(v) >= 1e-3 && Math.abs(v) < 1e15 ? d3.format(",.6~r")(v) : d3.format(".6~e")(v);
export const pct = (v, d = 1) => v == null || !isFinite(v) ? "NA" : d3.format(`.${d}%`)(v);
export const signedPct = (v) => v == null || !isFinite(v) ? "NA" : d3.format("+.1%")(v);

// ---------------------------------------------------------------- palettes
// Sequential: pale sand -> radiance amber -> interactive teal -> ink navy.
// Lightness falls monotonically, so classes read as ordered without colour.
const seqInterp = d3.piecewise(d3.interpolateLab, ["#FAF0D7", "#E5AD4E", "#4E9A8F", "#197D91", "#11263B"]);
export const seqColors = (k) => d3.range(k).map((i) => seqInterp(0.06 + 0.94 * (i / (k - 1))));
// Diverging (changes): decline = burnt amber, no change = light grey, increase = teal.
const divInterp = d3.piecewise(d3.interpolateLab, ["#8A4B12", "#E5AD4E", "#F2F2EE", "#5FA9B5", "#0F5868"]);
export const divColors = (k) => d3.range(k).map((i) => divInterp(i / (k - 1)));

export const MISSING = "#D3DBE1";
export const ZERO = "#FFFFFF";

/** Quantile class breaks of the given values (ascending, deduplicated, 2 significant digits). */
export function quantileBreaks(values, k = 7) {
  const v = values.filter((x) => x != null && isFinite(x)).sort(d3.ascending);
  if (v.length < 2) return [];
  const nice = (x) => +d3.format(".2~r")(x);
  const b = [];
  for (let i = 1; i < k; i++) { const q = nice(d3.quantile(v, i / k)); if (!b.length || q > b.at(-1)) b.push(q); }
  return b.filter((x) => x > v[0] || b.length === 1);
}
/** Symmetric diverging breaks around 0 for change indicators. */
export function divergingBreaks(values, k = 7) {
  const v = values.filter((x) => x != null && isFinite(x)).map(Math.abs).sort(d3.ascending);
  if (!v.length) return [];
  const m = +d3.format(".2~r")(d3.quantile(v, 0.95) || v.at(-1) || 1);
  const half = (k - 1) / 2;  // e.g. 3 on each side
  const pos = d3.range(1, half + 1).map((i) => +d3.format(".2~r")((m * (i - 0.5)) / half));
  return [...pos.slice().reverse().map((x) => -x), ...pos];
}

/** Build a classifier: value -> {color, cls} with explicit treatment of zero and missing. */
export function classifier({ breaks, colors, zeroIsSpecial = true }) {
  const sc = d3.scaleThreshold().domain(breaks).range(colors.slice(0, breaks.length + 1));
  return (v) => {
    if (v == null || !isFinite(v)) return { color: MISSING, cls: "missing" };
    if (zeroIsSpecial && v === 0) return { color: ZERO, cls: "zero" };
    return { color: sc(v), cls: "value" };
  };
}

/** Legend HTML: labelled classes + explicit swatches. */
export function legendHTML({ title, breaks, colors, unitLabel = "", swatches = [], note = "" }) {
  const n = breaks.length + 1;
  const lab = (i) => i === 0 ? `< ${fmt(breaks[0])}` : i === n - 1 ? `≥ ${fmt(breaks.at(-1))}` : `${fmt(breaks[i - 1])} – ${fmt(breaks[i])}`;
  const classes = breaks.length ? `<span class="classes" role="list">${d3.range(n).map((i) =>
    `<span class="cls" role="listitem"><i style="background:${colors[i]}"></i><span>${esc(lab(i))}</span></span>`).join("")}</span>` : "";
  const sw = swatches.map((s) => `<span class="sw"><i class="${s.cls}"></i>${esc(s.label)}</span>`).join("");
  return `<span class="lg-title">${esc(title)}${unitLabel ? ` <span class="muted" style="font-weight:400">(${esc(unitLabel)})</span>` : ""}</span>${classes}${sw}${note ? `<span class="note">${note}</span>` : ""}`;
}

// ---------------------------------------------------------------- geometry
export function rewind(fc) {
  for (const f of fc.features) {
    const g = f.geometry; if (!g) continue;
    const polys = g.type === "Polygon" ? [g.coordinates] : g.type === "MultiPolygon" ? g.coordinates : [];
    for (const p of polys) if (d3.geoArea({ type: "Polygon", coordinates: p }) > 2 * Math.PI) p.forEach((r) => r.reverse());
  }
  return fc;
}

/** SVG hatch patterns used across maps. */
export function addPatterns(svg) {
  const defs = svg.append("defs");
  const hatch = (id, bg, line, w, angle) => {
    const p = defs.append("pattern").attr("id", id).attr("width", w).attr("height", w).attr("patternUnits", "userSpaceOnUse").attr("patternTransform", `rotate(${angle})`);
    p.append("rect").attr("width", w).attr("height", w).attr("fill", bg);
    p.append("rect").attr("width", 1).attr("height", w).attr("fill", line);
  };
  hatch("hatch-unmatched", "#EEF2F5", "#A9B7C3", 4, 45);
  hatch("hatch-ndlsa", "#FFFFFF", "#8C9BA8", 3, 45);
  hatch("hatch-filtered", "#FFFFFF", "#6FA9B5", 4.5, -45);
}

/** Zoom/pan with explicit controls. Plain wheel scrolls the page; Ctrl/⌘+wheel or pinch zooms. */
export function addZoom({ svg, g, frame, width, height, maxScale = 24 }) {
  const zoom = d3.zoom().scaleExtent([1, maxScale]).translateExtent([[-width * 0.1, -height * 0.1], [width * 1.1, height * 1.1]])
    .filter((ev) => (ev.type === "wheel" ? ev.ctrlKey || ev.metaKey : !ev.button))
    .on("zoom", (ev) => g.attr("transform", ev.transform));
  svg.call(zoom).on("dblclick.zoom", null);
  frame.querySelector(".map-tools")?.remove();
  const tools = document.createElement("div");
  tools.className = "map-tools";
  tools.innerHTML = `<button type="button" data-z="in" aria-label="Zoom in" title="Zoom in">+</button>
    <button type="button" data-z="out" aria-label="Zoom out" title="Zoom out">−</button>
    <button type="button" data-z="reset" aria-label="Reset view" title="Reset view">⟲</button>`;
  frame.appendChild(tools);
  tools.addEventListener("click", (e) => {
    const z = e.target.closest("button")?.dataset.z; if (!z) return;
    const t = svg.transition().duration(250);
    if (z === "in") t.call(zoom.scaleBy, 1.7); else if (z === "out") t.call(zoom.scaleBy, 1 / 1.7); else t.call(zoom.transform, d3.zoomIdentity);
  });
  return {
    zoom,
    reset: () => svg.call(zoom.transform, d3.zoomIdentity),
    zoomToBounds: ([[x0, y0], [x1, y1]], pad = 0.9) => {
      const k = Math.min(maxScale, pad / Math.max((x1 - x0) / width, (y1 - y0) / height));
      const tx = width / 2 - k * (x0 + x1) / 2, ty = height / 2 - k * (y0 + y1) / 2;
      svg.transition().duration(450).call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(k));
    },
  };
}

/** Floating tooltip positioned inside the viewport. */
export function showTip(el, html, ev) {
  if (!html) { el.hidden = true; return; }
  el.innerHTML = html; el.hidden = false;
  const r = el.getBoundingClientRect();
  el.style.left = `${Math.max(8, Math.min(ev.clientX + 14, innerWidth - r.width - 8))}px`;
  el.style.top = `${Math.max(8, Math.min(ev.clientY + 14, innerHeight - r.height - 8))}px`;
}

/** CSV download of an array of objects (real file generated in the browser). */
export function downloadCsv(rows, cols, filename) {
  const q = (v) => (v == null || (typeof v === "number" && !isFinite(v)) ? "" : typeof v === "number" ? String(v)
    : /[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v));
  const csv = [cols.join(","), ...rows.map((r) => cols.map((c) => q(r[c])).join(","))].join("\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
