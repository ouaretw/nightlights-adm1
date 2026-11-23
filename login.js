// Sign-in for Night Lights ADM1. The password never leaves the browser. auth.json lists one entry
// per password (full access, or v2 only); each holds the site's content keys wrapped with a key
// derived from that password (PBKDF2-SHA-256, own salt). The password is tried against each entry;
// the keys it unwraps are stored in IndexedDB for the decrypting service worker (sw.js).
(async function () {
  const $ = (id) => document.getElementById(id);
  const BASE = new URL("./", location.href).pathname;
  const q = new URLSearchParams(location.search);
  const safe = (n) => (n && /^(v2|v3|data)\/[^\\:]*$/.test(n) && !n.includes("..") ? n : null);
  const next = safe(q.get("next")) || "v3/index.html";
  const msg = (t, ok) => { $("msg").textContent = t; $("msg").className = ok ? "ok" : ""; };
  const btn = $("f").querySelector("button");
  const go = () => location.replace(BASE + next + location.hash);

  if (!("serviceWorker" in navigator) || !window.crypto || !crypto.subtle || !window.indexedDB) {
    msg("This browser blocks the secure viewer (it needs service workers, Web Crypto and IndexedDB). Private or incognito windows in some browsers block them; please use a normal window.");
    btn.disabled = true;
    return;
  }
  const idb = () => new Promise((res, rej) => {
    const r = indexedDB.open("nladm1", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("kv");
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  });
  const tx = async (mode, fn) => { const db = await idb(); return new Promise((res, rej) => { const s = db.transaction("kv", mode).objectStore("kv"); const r = fn(s); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); }); };
  const idbGet = (k) => tx("readonly", (s) => s.get(k));
  const idbPut = (k, v) => tx("readwrite", (s) => s.put(v, k));
  const idbDel = (k) => tx("readwrite", (s) => s.delete(k));
  const b64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));

  const reg = navigator.serviceWorker.register("sw.js", { scope: "./" });
  const ready = async () => { await reg; const r = await navigator.serviceWorker.ready; r.active && r.active.postMessage("reset"); };
  let auth;
  try { auth = await fetch("auth.json", { cache: "no-store" }).then((r) => r.json()); }
  catch { msg("The sign-in configuration could not be loaded. Please reload the page."); btn.disabled = true; return; }
  const imp = (raw) => crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
  // a content key is valid for this build if it decrypts the build's check value for that key id
  const check = async (id, raw) => {
    const c = auth.checks && auth.checks[id] && b64(auth.checks[id]);
    if (!c) return false;
    try { return new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: c.subarray(5, 17), additionalData: c.subarray(0, 5) }, await imp(raw), c.subarray(17))) === auth.check_text; }
    catch { return false; }
  };
  const valid = async (keys) => !!keys && Object.keys(keys).length > 0 && (await Promise.all(Object.entries(keys).map(([id, raw]) => check(id, raw)))).every(Boolean);
  const unwrap = async (pw, entry) => {
    const kek = await crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(entry.salt), iterations: auth.iterations, hash: "SHA-256" },
      pw, { name: "AES-GCM", length: 256 }, false, ["decrypt"]);
    const w = b64(entry.wrapped);
    try {
      const body = JSON.parse(new TextDecoder().decode(await crypto.subtle.decrypt(
        { name: "AES-GCM", iv: w.subarray(0, 12), additionalData: new TextEncoder().encode("nladm1-login") }, kek, w.subarray(12))));
      const keys = {};
      for (const [id, k] of Object.entries(body.keys)) keys[id] = b64(k).buffer;
      return keys;
    } catch { return null; }
  };

  if (q.has("logout")) {
    await idbDel("keys"); await idbDel("key");
    await ready();
    history.replaceState(null, "", "index.html");
    msg("You are signed out.", true);
  } else {
    const keys = await idbGet("keys");
    const old = await idbGet("key");                 // single key of the first v3.0.0 build
    if (keys && (await valid(keys))) { msg("Signed in - opening…", true); await ready(); go(); return; }
    if (keys || old) {
      await idbDel("keys"); await idbDel("key");
      msg("The password has changed. Please sign in again.");
    } else if (q.has("expired")) msg("Your sign-in has expired. Please sign in again.");
  }
  $("pw").focus();

  $("f").addEventListener("submit", async (e) => {
    e.preventDefault();
    btn.disabled = true; msg("Checking…", true);
    try {
      const pw = await crypto.subtle.importKey("raw", new TextEncoder().encode($("pw").value), "PBKDF2", false, ["deriveKey"]);
      const found = (await Promise.all((auth.logins || []).map((e) => unwrap(pw, e)))).find(Boolean);
      if (!found || !(await valid(found))) { msg("Incorrect password."); btn.disabled = false; $("pw").select(); return; }
      await idbDel("key");
      await idbPut("keys", found);
      await ready();
      msg(found["3"] ? "Signed in - opening…" : "Signed in (access to v2) - opening…", true);
      go();
    } catch (err) {
      console.error(err);
      msg("Sign-in failed in this browser. Please try a normal (non-private) window.");
      btn.disabled = false;
    }
  });
})();
