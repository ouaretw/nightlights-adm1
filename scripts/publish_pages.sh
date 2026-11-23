#!/usr/bin/env bash
# Publish the password-protected site (build/pages/nightlights-adm1, made by
# scripts/build_secure_site.py) to the orphan `gh-pages` branch as a single commit.
# Only encrypted files (*.enc) and the public sign-in shell are published; the plain
# build in build/site is never pushed. History of generated data is not kept on the
# branch; versions are kept as tags + GitHub releases. Run from the repository root after
# the build sequence in README.md ("Rebuild"), ending with
#   python site_src/build_site.py && pytest tests && python scripts/build_secure_site.py
set -euo pipefail
PY=${PYTHON:-python}
OUT=build/pages/nightlights-adm1
VERSION=$($PY -c "import json;print(json.load(open('build/site/data/v2/manifest.json'))['version'])")
[ -f "$OUT/auth.json" ] && [ -f "$OUT/v3/index.html.enc" ] || { echo "Run scripts/build_secure_site.py first" >&2; exit 1; }
# refuse to publish anything readable except the public shell
PLAIN=$(cd "$OUT" && find . -type f ! -name '*.enc' | sed 's#^\./##' | grep -v -E '^(index\.html|login\.js|login\.css|sw\.js|auth\.json|404\.html|robots\.txt|\.nojekyll|(explore|analysis|about|download|methods|integration|docs)\.html)$' || true)
[ -z "$PLAIN" ] || { echo "Unencrypted files in $OUT: $PLAIN" >&2; exit 1; }
TMP=$(mktemp -d)
git worktree add --detach "$TMP"
pushd "$TMP" >/dev/null
git checkout --orphan gh-pages-new
git rm -rf --quiet . || true
cp -r "$OLDPWD/$OUT/." .
printf '* -text\n' > .gitattributes
git -c core.autocrlf=false add -A
git commit -q -m "Site v$VERSION (password-protected)"
git push -f origin HEAD:gh-pages
popd >/dev/null
git worktree remove --force "$TMP"
git branch -D gh-pages-new >/dev/null 2>&1 || true
REL=$($PY -c "import json;print(json.load(open('build/site/data/v2/manifest.json')).get('release_version',''))")
echo "Published v$VERSION to gh-pages. Large files are expected in the v$REL GitHub release (see manifest.json)."
