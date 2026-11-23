# Release workflow

Releases are immutable. A source revision or a method change produces a **new version**. Earlier versions stay
available through their git tag and GitHub release.

1. **Detect.** The `Watch upstream sources` workflow runs weekly and opens an issue when the World Bank files or the
   latest DOSE record change (`pipeline/check_sources.py` compares HTTP metadata with `pipeline/source_lock.json`).
2. **Rebuild** locally, following the steps in the README. Economic sources go in `raw/econ/`:
   - DOSE V2.14: `https://zenodo.org/api/records/20035157/files/DOSE_V2.14.csv/content` and `DOSE_additional_regions_V2_14.gpkg`
   - US BEA: `https://apps.bea.gov/regional/zip/SAGDP.zip`
   - IBGE states: `https://servicodados.ibge.gov.br/api/v1/localidades/estados` → `raw/econ/ibge/estados.json`
3. **Verify:** `pytest tests` must pass, including source-assumption and output tests. Then read `validation.json`.
4. **Version.** Bump `VERSION` in `pipeline/build_v2.py`. Bump `RELEASE_VERSION` only when the files in `build/release/` change; it names the release that holds them. Then add a changelog entry in `site_src/build_site.py` and
   `CITATION.cff`, and commit. Then tag: `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`.
5. **Publish the site and data:** `bash scripts/publish_pages.sh`. This force-pushes `build/site` to the orphan `gh-pages` branch.
   GitHub Pages must be set to *Deploy from a branch → gh-pages / (root)*.
6. **Release assets.** Create the GitHub release for the tag and upload every file in `build/release/`, either in the
   web UI or with `gh release create vX.Y.Z build/release/*`. The download page links to
   `releases/download/vX.Y.Z/<file>`, so the file names must not change.
7. **Archive.** With the Zenodo–GitHub integration enabled, each release receives a DOI. Add the DOI to `CITATION.cff`.
8. **Update the lock:** `python pipeline/check_sources.py --update`, then commit.
