# Archived site versions

`site_v2.0.0/` holds the pages, scripts and styles of the site as published on 2026-11-21 (v2.0.0, gh-pages commit
`34fe229`), extracted byte for byte with `git archive 34fe229 -- '*.html' assets examples`. It has no data files of its own: the v2.0.0
data files are unchanged in later versions (identical SHA-256, see `manifest_v2.0.0.json`), so the archived pages read the
shared `data/` folder of the current site. `scripts/build_secure_site.py` publishes it at `/v2/`.
