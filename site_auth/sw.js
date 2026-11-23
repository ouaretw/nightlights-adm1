// Night Lights ADM1 - decrypting service worker (build __BUILD__).
// Every page and data file of the site is stored encrypted (AES-256-GCM) as <path>.enc, under
// one of two content keys named in the file header: "2" (v2 pages and the data v2 uses) or
// "3" (v3 pages and v3-only data). After sign-in, login.js stores the keys the password
// unlocked in IndexedDB; this worker reads them, fetches <path>.enc, decrypts it and answers
// the original request, including HEAD and byte-range requests (used by the Parquet reader).
// Without a key nothing is decrypted; a v2-only sign-in is sent from v3 addresses to v2.
const BASE = new URL("./", self.location).pathname;
const V2_OWN = new Set(["__V2_OWN__"]);   // data files for which v2 has its own (v2.0.0) copy
const TYPES = {
  html: "text/html; charset=utf-8", js: "text/javascript; charset=utf-8", css: "text/css; charset=utf-8",
  json: "application/json; charset=utf-8", geojson: "application/geo+json", csv: "text/csv; charset=utf-8",
  parquet: "application/vnd.apache.parquet", dta: "application/x-stata-dta", zip: "application/zip", gz: "application/gzip",
  svg: "image/svg+xml", png: "image/png", txt: "text/plain; charset=utf-8", md: "text/markdown; charset=utf-8",
  r: "text/plain; charset=utf-8", do: "text/plain; charset=utf-8", py: "text/plain; charset=utf-8", ts: "text/plain; charset=utf-8",
};
const MEM_MAX = 200e6;            // decrypted-file cache (bytes)
const mem = new Map();
let memBytes = 0;
let keysP = null;

function idb() {
  return new Promise((res, rej) => {
    const r = indexedDB.open("nladm1", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("kv");
    r.onsuccess = () => res(r.result);
    r.onerror = () => rej(r.error);
  });
}
async function idbGet(k) {
  const db = await idb();
  return new Promise((res, rej) => { const q = db.transaction("kv").objectStore("kv").get(k); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error); });
}
// {"2": CryptoKey, "3": CryptoKey} - only the keys this sign-in unlocked; null when signed out
async function getKeys() {
  if (!keysP) keysP = idbGet("keys").then(async (raw) => {
    if (!raw || !Object.keys(raw).length) return null;
    const out = {};
    for (const [id, k] of Object.entries(raw)) out[id] = await crypto.subtle.importKey("raw", k, "AES-GCM", false, ["decrypt"]);
    return out;
  });
  const k = await keysP;
  if (!k) keysP = null;
  return k;
}
function reset() { keysP = null; mem.clear(); memBytes = 0; }

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("message", (e) => { if (e.data === "reset") reset(); });

// v2/... and v3/... are the two site versions; both read the shared data/ folder, except
// for the few files v2 keeps its own copy of (V2_OWN).
function encPath(rel) {
  const m = rel.match(/^(v[23])\/data\/(.+)$/);
  if (m) return m[1] === "v2" && V2_OWN.has("data/" + m[2]) ? rel + ".enc" : "data/" + m[2] + ".enc";
  if (/^(v[23]|data)\//.test(rel)) return rel + ".enc";
  return null;
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(BASE)) return;
  let rel = decodeURIComponent(url.pathname.slice(BASE.length));
  if (rel === "__access.json") { e.respondWith(access()); return; }
  if (rel === "v2" || rel === "v3") rel += "/";
  if (rel.endsWith("/")) rel += "index.html";
  const enc = encPath(rel);
  if (!enc) return;                                   // public file (sign-in page etc.)
  e.respondWith(serve(e.request, rel, url.search, enc));
});

async function access() {
  const k = (await getKeys()) || {};
  return new Response(JSON.stringify({ signed_in: !!Object.keys(k).length, v2: !!k["2"], v3: !!k["3"] }),
    { headers: { "Content-Type": TYPES.json, "Cache-Control": "no-store" } });
}

async function plain(enc, keys) {
  if (mem.has(enc)) { const v = mem.get(enc); mem.delete(enc); mem.set(enc, v); return v; }
  const r = await fetch(BASE + enc);
  if (!r.ok) return { status: r.status };
  const u8 = new Uint8Array(await r.arrayBuffer());
  if (u8.length < 33 || u8[0] !== 78 || u8[1] !== 76 || u8[2] !== 69 || u8[3] !== 50) return { status: 500 };   // "NLE2"
  const key = keys[String.fromCharCode(u8[4])];
  if (!key) return { status: 403 };                  // not included in this sign-in
  let data;
  try { data = await crypto.subtle.decrypt({ name: "AES-GCM", iv: u8.subarray(5, 17), additionalData: u8.subarray(0, 5) }, key, u8.subarray(17)); }
  catch { return { status: 401 }; }                  // key no longer valid (password changed)
  const v = { status: 200, data };
  if (data.byteLength < 60e6) {
    mem.set(enc, v); memBytes += data.byteLength;
    while (memBytes > MEM_MAX && mem.size > 1) { const [k0, v0] = mem.entries().next().value; mem.delete(k0); memBytes -= v0.data.byteLength; }
  }
  return v;
}

function toLogin(rel, search, extra = "") {
  return Response.redirect(`${BASE}index.html?${extra}next=${encodeURIComponent(rel + search)}`, 302);
}
const page = (title, body, status) => new Response(
  `<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title>` +
  `<p style="font-family:system-ui,sans-serif;padding:2em;max-width:40em">${body}</p>`, { status, headers: { "Content-Type": TYPES.html } });

async function serve(req, rel, search, enc) {
  const nav = req.mode === "navigate";
  const keys = await getKeys();
  if (!keys) return nav ? toLogin(rel, search) : new Response("Sign-in required", { status: 401 });
  const home = keys["3"] ? "v3/index.html" : "v2/index.html";
  // v2-only sign-in: v3 addresses open the same page in v2 (or the v2 home page)
  if (nav && rel.startsWith("v3/") && !keys["3"]) {
    const v2 = "v2/" + rel.slice(3);
    const ok = (await fetch(BASE + v2 + ".enc", { method: "HEAD" }).catch(() => ({ ok: false }))).ok;
    return Response.redirect(BASE + (ok ? v2 + search : "v2/index.html"), 302);
  }
  const p = await plain(enc, keys);
  if (p.status === 401) {
    reset();
    return nav ? toLogin(rel, search, "expired=1&") : new Response("Sign-in expired", { status: 401 });
  }
  if (p.status === 403) {
    return nav
      ? page("Not available", `This page is not included in your access. <a href="${BASE}${home}">Go to the home page</a>.`, 403)
      : new Response("Not included in your access", { status: 403 });
  }
  if (p.status !== 200) {
    return nav ? page("Not found", `Page not found. <a href="${BASE}${home}">Go to the home page</a>.`, 404)
               : new Response("Not found", { status: 404 });
  }
  const ext = (rel.split("/").pop().split(".").pop() || "").toLowerCase();
  const size = p.data.byteLength;
  const h = { "Content-Type": TYPES[ext] || "application/octet-stream", "Accept-Ranges": "bytes", "Cache-Control": "no-store" };
  if (req.method === "HEAD") return new Response(null, { status: 200, headers: { ...h, "Content-Length": String(size) } });
  const range = req.headers.get("Range");
  const m = range && range.match(/^bytes=(\d*)-(\d*)$/);
  if (m && (m[1] !== "" || m[2] !== "")) {
    const a = m[1] === "" ? Math.max(0, size - Number(m[2])) : Number(m[1]);
    const b = m[1] === "" || m[2] === "" ? size - 1 : Math.min(Number(m[2]), size - 1);
    if (a >= size || a > b) return new Response(null, { status: 416, headers: { "Content-Range": `bytes */${size}` } });
    return new Response(p.data.slice(a, b + 1), { status: 206, headers: { ...h, "Content-Range": `bytes ${a}-${b}/${size}`, "Content-Length": String(b - a + 1) } });
  }
  return new Response(p.data.slice(0), { status: 200, headers: { ...h, "Content-Length": String(size) } });
}
