# Riding spending

Federal grants and contributions since the 28 April 2025 election, by riding, set against the 2025 result.

Run `./run.sh` to re-download everything and rebuild. Python 3 standard library only.

| Step | Script | Output |
|---|---|---|
| Ridings, 2025 results, current MPs, 2021 population, boundaries | `scripts/prep_ridings.py` | `data/ridings.json`, `data/ridings_geo.json` |
| Grants → ridings, amendments deduped, flags, before/after, four groups | `scripts/build_spending.py` | `data/riding_spending.json`, `data/summary.json` |
| Map page and spreadsheet | `scripts/build_map.py` | `output/riding_spending_map.html`, `output/riding_spending.csv` |

Method notes are in the docstring at the top of `scripts/build_spending.py`.

## Hosting as a self-updating website

`.github/workflows/update.yml` runs `run.sh` on GitHub Actions every day at 09:17 UTC and publishes
`output/riding_spending_map.html` to GitHub Pages as `index.html`, with the CSV exports beside it.
To turn it on: push this folder to a GitHub repository, then in the repository's
Settings → Pages set Source to "GitHub Actions". The first run can be started by hand from the
Actions tab. The daily run downloads the full grants file (about 2.3 GB) each time; it takes a few minutes.
