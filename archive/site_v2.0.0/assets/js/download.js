// Download picker: resolves a (level, frequency, scope, format) choice to files that
// exist in data/v2/manifest.json. Nothing is offered that the manifest does not list.
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const META = JSON.parse($("pickerMeta").textContent);
const BASE = "https://ouaretw.github.io/nightlights-adm1/";
const st = { level: "adm1_wb", freq: "annual", scope: "global", fmt: "csv", iso: null, man: new Map(), dict: [], index: [] };

const LEVEL = {
  adm1_wb: { title: "ADM1 · World Bank units", key: "ADM1CD_c", units: "n_adm1_wb", code: "adm1_wb", status: ["exact", "Derived — exact aggregate"],
    desc: "States and provinces as in the source's World Bank boundary vintage. Source districts nest exactly, so sums and maxima are exact and means are exact coverage-weighted means.",
    caveats: ["The source uses an older World Bank boundary vintage; some ADM1 codes were later reused for different units. Join on ADM1CD_c, not on names."] },
  adm1_gadm41: { title: "ADM1 · GADM 4.1", key: "GID_1", units: "n_adm1_gadm", code: "adm1_gadm41", status: ["approx", "Derived — crosswalk (approximate)"],
    desc: "States and provinces keyed on GADM 4.1 GID_1, the identifier used by DOSE and many subnational economic datasets. Whole districts are assigned to the GADM unit they overlap most.",
    caveats: ["Values are approximate where GADM borders cut through source districts. Use xw_match_quality (high/medium/low) and xw_min_overlap to filter.",
      "Some GADM units are absorbed by a neighbour (xw_absorbs_units); merge those regions on the economic side too.",
      "Districts that could not be located are left out, so GADM country totals can fall below the World Bank totals."] },
  adm2: { title: "ADM2 · native districts", key: "ADM2CD_c", units: "n_adm2", code: "adm2", status: ["native", "Source — native districts"],
    desc: "The World Bank Space2Stats district observations, unchanged except that 'no valid pixel' sums are set to missing instead of the source's 0. Includes medians and percentiles, and each district's GADM 4.1 parent.",
    caveats: ["Medians and percentiles exist only at this level; they cannot be aggregated.", "Stored as float32, as in the source."] },
};
const FREQ = {
  annual: { title: "official annual composite", code: "a", periods: () => `${META.years_official_annual[0]}–${META.years_official_annual[1]}`,
    caveats: ["The official composite is NASA's annual product (VNP46A4). It is not the mean of the monthly values (median ratio 0.86, see Methods)."] },
  monthly: { title: "monthly composites", code: "m", periods: () => `${META.months[0]} – ${META.months[1]}`,
    caveats: ["Monthly sums are biased downward when valid-pixel coverage is low (clouds, high-latitude summers). Filter on coverage."] },
  annual_from_monthly: { title: "annual, derived from monthly data", code: "afm", periods: () => `${META.years_afm[0]}–${META.years_afm[1]}`,
    caveats: ["Computed here from months with valid data; kept separate from the official composite. Check n_months_with_data."] },
};
const FMT = { csv: "CSV", parquet: "Parquet", stata: "Stata" };
const human = (n) => n >= 1073741824 ? `${(n / 1073741824).toFixed(2)} GB` : n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : n >= 1024 ? `${(n / 1024).toFixed(0)} KB` : `${n} B`;

/** Candidate manifest entries for the current choice, best first. */
function resolve() {
  const { level: L, freq: F, scope, fmt, iso } = st;
  const get = (p) => st.man.get(p);
  const out = [];
  if (scope === "global") {
    const stem = `${L}_${F}_global`;
    if (fmt === "parquet") out.push(get(`data/v2/${L}/${stem}.parquet`) || get(`${stem}.parquet`));
    if (fmt === "csv") out.push(get(`${stem}.csv.gz`));
    if (fmt === "stata") out.push(get(`${stem}.dta.zip`));
  } else if (iso) {
    if (fmt === "parquet") out.push(get(`data/v2/${L}/${F}/${iso}.parquet`));
    if (fmt === "csv") {
      out.push(get(`data/v2/${L}/${F}/${iso}.csv`));
      if (!out[0] && F === "monthly") out.push(Object.assign({ bundle: true }, get(`${L}_monthly_by_country_csv.zip`) || {}));
    }
  }
  return out.filter((f) => f && f.path);
}
/** Real alternatives in other formats for the same level/frequency/scope. */
function alternatives() {
  const keep = st.fmt; const alts = [];
  for (const f of Object.keys(FMT)) if (f !== keep) { st.fmt = f; const r = resolve(); if (r.length) alts.push([f, r[0], ""]); }
  st.fmt = keep;
  if (st.scope === "country") {  // the same format exists for all countries together
    st.scope = "global"; const g = resolve(); st.scope = "country";
    if (g.length) alts.push([keep, g[0], "all countries"]);
  }
  return alts;
}
const href = (f) => f.url || f.path;
const absUrl = (f) => f.url || BASE + f.path;

function render() {
  for (const [attr, key] of [["pl", "level"], ["pf", "freq"], ["ps", "scope"], ["pk", "fmt"]])
    document.querySelectorAll(`[data-${attr}]`).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset[attr] === st[key])));
  document.querySelectorAll("[data-pf]").forEach((b) => { b.disabled = st.level === "adm2" && b.dataset.pf === "annual_from_monthly"; });
  $("pCountry").hidden = st.scope !== "country";
  const Lv = LEVEL[st.level], Fq = FREQ[st.freq];
  const c = st.index.find((x) => x.iso === st.iso);
  const units = st.scope === "global" ? st.index.reduce((a, x) => a + (x[Lv.units] || 0), 0) : c?.[Lv.units] ?? 0;
  const countries = st.scope === "global" ? st.index.filter((x) => (x[Lv.units] || 0) > 0).length : 1;
  const files = resolve();
  const f = files[0];
  const scopeLabel = st.scope === "global" ? "all countries" : (c ? `${c.name} (${c.iso})` : "choose a country");
  let fileHtml;
  if (st.scope === "country" && units === 0) {
    fileHtml = `<div class="filebox"><div><div class="fname">No ${esc(Lv.title)} data for ${esc(c?.name ?? "this country")}</div>
      <div class="fmeta">None of its source districts could be assigned to a GADM 4.1 unit with confidence. Use World Bank units instead.</div></div></div>`;
  } else if (f) {
    fileHtml = `<div class="filebox"><div>
        <div class="fname">${esc(f.path.split("/").pop())}</div>
        <div class="fmeta">${esc(human(f.bytes))} · <span class="mono">${f.bytes.toLocaleString()} bytes</span> · hosted on ${f.host === "release" ? "the GitHub release" : "this site"}${f.bundle ? " · <b>bundle of per-country CSV files for all countries</b>" : ""}</div>
        <div class="sha" id="shaText">SHA-256 ${esc(f.sha256)}</div>
        <div class="fmeta" style="margin-top:4px">URL: <span class="mono" style="overflow-wrap:anywhere">${esc(absUrl(f))}</span></div>
      </div>
      <div class="btn-row"><a class="btn" href="${esc(href(f))}" download>Download ${esc(FMT[st.fmt])}</a>
        <button class="copy light" type="button" id="copyUrl">Copy URL</button></div></div>`;
  } else {
    const alts = alternatives();
    const explorer = st.scope === "country" && st.fmt === "csv" && st.iso
      ? `<li>Generate a CSV in the browser from the published Parquet: <a href="explore.html#c=${st.iso}&l=${st.level === "adm2" ? "adm2" : "adm1"}&s=${st.level === "adm1_gadm41" ? "gadm" : "wb"}&f=${st.freq}&v=table">open the explorer</a> → Export.</li>` : "";
    fileHtml = `<div class="filebox"><div><div class="fname">Not published as ${esc(FMT[st.fmt])} for this selection</div>
      <div class="fmeta">Available instead:</div><ul class="small" style="margin:6px 0 0;padding-left:18px">
      ${alts.map(([k, a, note]) => `<li><a href="${esc(href(a))}" download>${esc(a.path.split("/").pop())}</a> (${FMT[k]}${note ? ", " + note : ""}, ${human(a.bytes)})</li>`).join("")}${explorer}
      ${!alts.length && !explorer ? "<li>Choose a different format or scope.</li>" : ""}</ul></div></div>`;
  }
  const vars = st.dict.filter((d) => d.products.split(",").includes(Lv.code) && d.frequencies.split(",").includes(Fq.code));
  const caveats = [...Lv.caveats, ...Fq.caveats];
  $("result").innerHTML = `<div class="result-head">
      <h2>${esc(Lv.title)} · ${esc(Fq.title)} · ${esc(scopeLabel)}</h2>
      <p>${esc(Lv.desc)}</p>
      <div class="flags"><span class="tag ${Lv.status[0]}">${esc(Lv.status[1])}</span>${st.freq === "annual_from_monthly" ? '<span class="tag warn">Derived from monthly data</span>' : ""}</div>
    </div>
    ${fileHtml}
    <div class="result-body">
      <dl class="kv" style="margin:0">
        <dt>Coverage</dt><dd class="text">${units.toLocaleString()} units in ${countries.toLocaleString()} ${countries === 1 ? "country" : "countries/territories"} · ${esc(Fq.periods())}</dd>
        <dt>Key</dt><dd><code>${esc(Lv.key)}</code> + <code>${st.freq === "monthly" ? "date" : "year"}</code></dd>
        <dt>Missing values</dt><dd class="text">empty cells (CSV) or nulls (Parquet/Stata); a zero always means observed darkness</dd>
        <dt>Source</dt><dd class="text">World Bank Space2Stats Black Marble (dataset 0066940, CC BY 4.0), from NASA Black Marble</dd>
      </dl>
      <div><h3>Caveats</h3><ul class="small" style="margin:0;padding-left:18px">${caveats.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
      <details><summary style="cursor:pointer"><h3 style="display:inline">Variables (${vars.length})</h3> <span class="hint">show definitions</span></summary>
        <ul class="varlist" style="margin-top:8px">${vars.map((d) => `<li><code>${esc(d.column)}</code> <span class="tag">${esc(d.status)}</span>${d.unit ? ` <span class="mono xs muted">[${esc(d.unit)}]</span>` : ""}<br><span class="muted xs">${esc(d.description)}</span></li>`).join("")}</ul>
        <p class="xs muted" style="margin-top:6px">Full definitions: <a href="docs.html#dictionary">data dictionary</a>. Status: source = copied from the source; exact = exact aggregation; derived = computed here; crosswalk = depends on the GADM crosswalk.</p></details>
    </div>`;
  $("copyUrl")?.addEventListener("click", (e) => {
    navigator.clipboard.writeText(absUrl(f)).then(() => { e.target.textContent = "Copied"; setTimeout(() => (e.target.textContent = "Copy URL"), 1400); });
  });
  const p = new URLSearchParams({ l: st.level, f: st.freq, s: st.scope, k: st.fmt }); if (st.iso && st.scope === "country") p.set("c", st.iso);
  history.replaceState(null, "", "#" + p);
}

async function init() {
  const [man, dict, index] = await Promise.all(["data/v2/manifest.json", "data/v2/data_dictionary.json", "data/v2/index.json"]
    .map((u) => fetch(u).then((r) => (r.ok ? r.json() : null)).catch(() => null)));
  if (!man) { $("result").innerHTML = `<div class="result-head"><p>The manifest could not be loaded. Use the <a href="#all-files">full file list</a>.</p></div>`; return; }
  for (const f of man.files) st.man.set(f.path, f);
  st.dict = dict?.columns || []; st.index = index || [];
  const sel = $("pCountry");
  for (const c of st.index) sel.add(new Option(`${c.name} (${c.iso})`, c.iso));
  const h = new URLSearchParams(location.hash.slice(1));
  if (LEVEL[h.get("l")]) st.level = h.get("l");
  if (FREQ[h.get("f")]) st.freq = h.get("f");
  if (["global", "country"].includes(h.get("s"))) st.scope = h.get("s");
  if (FMT[h.get("k")]) st.fmt = h.get("k");
  st.iso = st.index.find((c) => c.iso === h.get("c"))?.iso || st.index[0]?.iso;
  sel.value = st.iso;
  const bind = (attr, key) => document.querySelectorAll(`[data-${attr}]`).forEach((b) => b.addEventListener("click", () => {
    st[key] = b.dataset[attr];
    if (st.level === "adm2" && st.freq === "annual_from_monthly") st.freq = "annual";
    render();
  }));
  bind("pl", "level"); bind("pf", "freq"); bind("ps", "scope"); bind("pk", "fmt");
  sel.addEventListener("change", () => { st.iso = sel.value; render(); });
  render();
}
init();
