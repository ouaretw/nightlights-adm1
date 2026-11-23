# Access control (since v3.0.0)

The website at https://ouaretw.github.io/nightlights-adm1/ is password-protected. GitHub Pages cannot check passwords on a server, so the protection is done with encryption.

## How it works

- **Public parts:** only a sign-in shell is public: `index.html`, `login.js`, `login.css`, `sw.js`, `auth.json`, `404.html` and redirect pages for the old addresses.
- **Encryption:** every page and data file is stored as `<path>.enc`, encrypted with AES-256-GCM. A random 12-byte nonce is used per file, in the format `NLE1 ‖ nonce ‖ ciphertext ‖ tag`.
- **Key:** derived from the shared password with PBKDF2-HMAC-SHA-256, using 600,000 iterations and a random 16-byte salt stored in `auth.json`.
- **Sign-in:** the browser derives the key and checks it by decrypting a test value in `auth.json`. It then stores the key in IndexedDB on that device. The password never leaves the browser.
- **Service worker:** `sw.js` decrypts files on request, including `HEAD` and byte-range requests, so the explorer, maps, charts, CSV exports and downloads work as before.
- **Sign-out:** the "Sign out" link removes the key from the device.

## Versions

| Path | Content |
|---|---|
| `/v3/` | Current site (v3.0.0: content of 2.1.0, with the Economic Analysis page). |
| `/v2/` | Archived site as published on 2026-11-21 (v2.0.0), from `archive/site_v2.0.0/`. |
| `/data/` | Data files shared by both versions. The v2.0.0 data files are unchanged in v3 (same SHA-256). |

## Change or revoke the password

1. Put the new password in `secrets/site_password.txt` (git-ignored), or set `NLADM1_SITE_PASSWORD`. Use at least 12 characters, preferably 16 or more.
2. Run `python scripts/build_secure_site.py`, then `bash scripts/publish_pages.sh`.

Everyone is signed out at their next visit. A new salt and new nonces are used, so files encrypted under the old password are no longer published.

## Limits

These limits are real. Read them before relying on this for sensitive material.

- **One shared password.** There are no per-person accounts, so you cannot tell who accessed what or revoke one person. Anyone with the password can pass it on.
- **Offline guessing.** The encrypted files and salt are public, so an attacker can try passwords offline. A long random password, like the generated one, makes this impractical; a short or common one does not.
- **File names and sizes are visible** (for example `data/v2/adm1_wb/annual/DZA.parquet.enc`). Contents are not.
- **Not covered by the password:**
  - **The public GitHub repository**: code, documentation (including `docs/VALIDATION_REPORT.md` and `docs/PUBLICATION_PLAN.md`) and its git history.
  - **The GitHub release `v2.0.0`**: about 1 GB of global CSV, Stata and Parquet files. The download page links to these assets, and they remain publicly downloadable.
  - **Copies made before v3.0.0**: the site was public until 2026-11-23, so copies may exist in caches, web archives or earlier downloads.
- **Downloads are plain files.** Once someone signed in downloads a file, it is ordinary unencrypted data.
- **Programmatic URLs** such as `…/data/v2/…csv` no longer work from scripts: files must be downloaded after signing in. The merge examples in `examples/` have been changed accordingly.
- **Browser requirements:** a browser with service workers, Web Crypto and IndexedDB. Some private or incognito windows block service workers.

For per-person accounts and server-side access control, the site would have to move to a host that offers it, such as Cloudflare Pages with Cloudflare Access.
