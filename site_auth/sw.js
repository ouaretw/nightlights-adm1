// Night Lights ADM1 - decrypting service worker (build __BUILD__).
// Every page and data file of the site is stored encrypted (AES-256-GCM) as <path>.enc.
// After sign-in, login.js stores the derived key in IndexedDB; this worker reads it,
// fetches <path>.enc, decrypts it and answers the original request, including HEAD and
// byte-range requests (used by the Parquet reader). Without a key nothing is decrypted.
const BASE = new URL("./", self.location).pathname;
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
let keyP = null;

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
async function getKey() {
  if (!keyP) keyP = idbGet("key").then((raw) => (raw ? crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]) : null));
  const k = await keyP;
  if (!k) keyP = null;
  return k;
}
function reset() { keyP = null; mem.clear(); memBytes = 0; }

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("message", (e) => { if (e.data === "reset") reset(); });

// v2/... and v3/... are the two site versions; both read the shared data/ folder.
function encPath(rel) {
  const m = rel.match(/^v[23]\/data\/(.+)$/);
  if (m) return "data/" + m[1] + ".enc";
  if (/^(v[23]|data)\//.test(rel)) return rel + ".enc";
  return null;
}

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(BASE)) return;
  let rel = decodeURIComponent(url.pathname.slice(BASE.length));
  if (rel === "v2" || rel === "v3") rel += "/";
  if (rel.endsWith("/")) rel += "index.html";
  const enc = encPath(rel);
  if (!enc) return;                                   // public file (sign-in page etc.)
  e.respondWith(serve(e.request, rel, url.search, enc));
});

async function plain(enc, key) {
  if (mem.has(enc)) { const v = mem.get(enc); mem.delete(enc); mem.set(enc, v); return v; }
  const r = await fetch(BASE + enc);
  if (!r.ok) return { status: r.status };
  const u8 = new Uint8Array(await r.arrayBuffer());
  if (u8.length < 32 || u8[0] !== 78 || u8[1] !== 76 || u8[2] !== 69 || u8[3] !== 49) return { status: 500 };   // "NLE1"
  let data;
  try { data = await crypto.subtle.decrypt({ name: "AES-GCM", iv: u8.subarray(4, 16) }, key, u8.subarray(16)); }
  catch { return { status: 403 }; }
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

async function serve(req, rel, search, enc) {
  const nav = req.mode === "navigate";
  const key = await getKey();
  if (!key) return nav ? toLogin(rel, search) : new Response("Sign-in required", { status: 401 });
  const p = await plain(enc, key);
  if (p.status === 403) {            // key no longer valid (password changed)
    reset();
    return nav ? toLogin(rel, search, "expired=1&") : new Response("Sign-in expired", { status: 401 });
  }
  if (p.status !== 200) {
    return nav
      ? new Response(`<!doctype html><meta charset="utf-8"><title>Not found</title><p style="font-family:sans-serif;padding:2em">Page not found. <a href="${BASE}v3/index.html">Go to the home page</a>.</p>`, { status: 404, headers: { "Content-Type": TYPES.html } })
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
