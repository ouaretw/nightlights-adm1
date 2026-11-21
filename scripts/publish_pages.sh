#!/usr/bin/env bash
# Publish build/site to the orphan `gh-pages` branch as a single commit
# (history of generated data is not kept on the branch; versions are kept as
# tags + GitHub releases). Run from the repository root after:
#   python pipeline/build_v2.py && python pipeline/validate.py && python site_src/build_site.py && pytest tests
set -euo pipefail
VERSION=$(python -c "import json;print(json.load(open('build/site/data/v2/manifest.json'))['version'])")
TMP=$(mktemp -d)
git worktree add --detach "$TMP"
pushd "$TMP" >/dev/null
git checkout --orphan gh-pages-new
git rm -rf --quiet . || true
cp -r "$OLDPWD/build/site/." .
git add -A
git commit -q -m "Site and data v$VERSION"
git push -f origin HEAD:gh-pages
popd >/dev/null
git worktree remove --force "$TMP"
git branch -D gh-pages-new >/dev/null 2>&1 || true
echo "Published v$VERSION to gh-pages. Release assets: upload build/release/* to the v$VERSION GitHub release."
