// Sign-in for Night Lights ADM1. The password never leaves the browser: it is turned into an
// AES-256 key with PBKDF2-SHA-256 (salt and iteration count in auth.json), checked by decrypting a
// known test value, and stored in IndexedDB for the decrypting service worker (sw.js).
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
  const check = async (key) => {
    const c = b64(auth.check);
    try { return new TextDecoder().decode(await crypto.subtle.decrypt({ name: "AES-GCM", iv: c.subarray(4, 16) }, key, c.subarray(16))) === auth.check_text; }
    catch { return false; }
  };

  if (q.has("logout")) {
    await idbDel("key");
    await ready();
    history.replaceState(null, "", "index.html");
    msg("You are signed out.", true);
  } else {
    const raw = await idbGet("key");
    if (raw) {
      const k = await crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["decrypt"]);
      if (await check(k)) { msg("Signed in - opening…", true); await ready(); go(); return; }
      await idbDel("key");
      msg("The password has changed. Please sign in again.");
    } else if (q.has("expired")) msg("Your sign-in has expired. Please sign in again.");
  }
  $("pw").focus();

  $("f").addEventListener("submit", async (e) => {
    e.preventDefault();
    btn.disabled = true; msg("Checking…", true);
    try {
      const pw = await crypto.subtle.importKey("raw", new TextEncoder().encode($("pw").value), "PBKDF2", false, ["deriveKey"]);
      const key = await crypto.subtle.deriveKey({ name: "PBKDF2", salt: b64(auth.salt), iterations: auth.iterations, hash: "SHA-256" },
        pw, { name: "AES-GCM", length: 256 }, true, ["decrypt"]);
      if (!(await check(key))) { msg("Incorrect password."); btn.disabled = false; $("pw").select(); return; }
      await idbPut("key", await crypto.subtle.exportKey("raw", key));
      await ready();
      msg("Signed in - opening…", true);
      go();
    } catch (err) {
      console.error(err);
      msg("Sign-in failed in this browser. Please try a normal (non-private) window.");
      btn.disabled = false;
    }
  });
})();
