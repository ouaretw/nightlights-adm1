#!/usr/bin/env bash
# Publish build/site to the orphan `gh-pages` branch as a single commit
# (history of generated data is not kept on the branch; versions are kept as
# tags + GitHub releases). Run from the repository root after:
#   the build sequence in README.md ("Rebuild"), ending with
#   python site_src/build_site.py && pytest tests
set -euo pipefail
PY=${PYTHON:-python}
VERSION=$($PY -c "import json;print(json.load(open('build/site/data/v2/manifest.json'))['version'])")
TMP=$(mktemp -d)
git worktree add --detach "$TMP"
pushd "$TMP" >/dev/null
git checkout --orphan gh-pages-new
git rm -rf --quiet . || true
cp -r "$OLDPWD/build/site/." .
# store files byte-for-byte so sizes/SHA-256 match manifest.json (no CRLF/LF conversion)
printf '* -text\n' > .gitattributes
git -c core.autocrlf=false add -A
git commit -q -m "Site and data v$VERSION"
git push -f origin HEAD:gh-pages
popd >/dev/null
git worktree remove --force "$TMP"
git branch -D gh-pages-new >/dev/null 2>&1 || true
REL=$($PY -c "import json;print(json.load(open('build/site/data/v2/manifest.json')).get('release_version',''))")
echo "Published v$VERSION to gh-pages. Large files are expected in the v$REL GitHub release (see manifest.json)."
