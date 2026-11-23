# Access control (since v3.0.0)

The website at https://ouaretw.github.io/nightlights-adm1/ is password-protected. GitHub Pages cannot check passwords on a server, so the protection is done with encryption.

## How it works

- **Public parts:** only a sign-in shell is public: `index.html`, `login.js`, `login.css`, `sw.js`, `auth.json`, `404.html` and redirect pages for the old addresses.
- **Encryption:** every page and data file is stored as `<path>.enc`, encrypted with AES-256-GCM under one of two random content keys. The format is `NLE2 ‖ key id ‖ nonce ‖ ciphertext ‖ tag`, with a random 12-byte nonce per file.
  - **Key 2:** v2 pages, the data files published with v2.0.0 (the build checks they are unchanged, against `archive/site_v2.0.0_data_files.txt`), and v2's own copy of the v2.0.0 `manifest.json`.
  - **Key 3:** v3 pages and the data files that exist only in v3, including the v3 `manifest.json`.
- **Passwords:** there are two.
  - **Full access** (`secrets/site_password.txt`) opens v2 and v3.
  - **v2 only** (`secrets/site_password_v2.txt`) opens v2 and nothing else. It is optional: without the file, only the full-access password exists.
- **Wrapped keys:** for each password, `auth.json` holds the content keys it opens, encrypted with a key derived from that password. The derivation uses PBKDF2-HMAC-SHA-256 with 600,000 iterations and the password's own random 16-byte salt.
- **Sign-in:** the browser tries the password against each entry, unwraps the content keys, and checks them against test values in `auth.json`. It stores them in IndexedDB on that device. The password never leaves the browser.
- **Service worker:** `sw.js` decrypts files on request, including `HEAD` and byte-range requests, so the explorer, maps, charts, CSV exports and downloads work as before.
- **Sign-out:** the "Sign out" link removes the keys from the device.
- **v2-only visitors** never see v3:
  - addresses under `/v3/` (and the old public addresses) open the same page in v2, or the v2 home page if v2 has no such page;
  - the version bar has no "Switch to v3" link;
  - v3 files are refused, because the browser does not hold key 3.

## Versions

| Path | Content |
|---|---|
| `/v3/` | Current site (v3.0.0: content of 2.1.0, with the Economic Analysis page). |
| `/v2/` | Archived site as published on 2026-11-21 (v2.0.0), from `archive/site_v2.0.0/`. |
| `/data/` | Data files shared by both versions. The v2.0.0 data files are unchanged in v3 (same SHA-256). |

## Change or revoke a password

1. Put the new password in the file (git-ignored), or set the environment variable:
   - full access: `secrets/site_password.txt` or `NLADM1_SITE_PASSWORD`;
   - v2 only: `secrets/site_password_v2.txt` or `NLADM1_SITE_PASSWORD_V2`. Delete the file to remove v2-only access.

   Use at least 12 characters, preferably 16 or more. The two passwords must differ.
2. Run `python scripts/build_secure_site.py`, then `bash scripts/publish_pages.sh`.

Every build makes new content keys, salts and nonces, so **everyone** is signed out at their next visit, whichever password was changed. People with an unchanged password simply sign in again with it.

## Limits

These limits are real. Read them before relying on this for sensitive material.

- **Shared passwords.** There are no per-person accounts, so you cannot tell who accessed what or revoke one person. Anyone with a password can pass it on.
- **v2-only access is not a secret boundary for everything v3 adds.** The v3 pages and data are encrypted under a key v2-only visitors do not have, but v3 results are also described in the public repository (below).
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
