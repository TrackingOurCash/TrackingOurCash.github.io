# Riding spending

Federal grants and contributions since the 28 April 2025 election, by riding, set against the 2025 result.

Run `./run.sh` to re-download everything and rebuild. Python 3 standard library only.

| Step | Script | Output |
|---|---|---|
| Ridings, 2025 results, current MPs, 2021 population, boundaries | `scripts/prep_ridings.py` | `data/ridings.json`, `data/ridings_geo.json` |
| Grants → ridings, amendments deduped, flags, before/after, four groups | `scripts/build_spending.py` | `data/riding_spending.json`, `data/summary.json` |
| Map page and spreadsheet | `scripts/build_map.py` | `output/riding_spending_map.html`, `output/riding_spending.csv` |
| Every grant since the election, kept even when withdrawn from the source | `scripts/build_spending.py` | `data/ledger/federal_grants_since_election.csv.gz` (committed) |
| Budget measures that name a place, located in ridings | `scripts/budget.py` | `data/budget_by_riding.json` (from the hand-kept `data/budget_items.json`) |
| Each budget's estimated dollars per riding | `scripts/budget_estimate.py` | `data/budget_estimate.json` (from the hand-kept `data/budget_measures.json`), `output/budget.html`, `output/budget_by_riding.csv` |
| By-election ridings: all funding since the election | `scripts/byelections.py` | `data/byelection_detail.json` (from the hand-kept `data/byelections.json`), `output/byelections.html` |

## After a new budget

Add its place-named items to `data/budget_items.json` (plus the document in `documents`), add every row of each
chapter's summary table to `data/budget_measures.json` with an allocation key, and check that the totals match the
budget's own "net fiscal impact" lines (`official_net_by_chapter`). `budget_estimate.py` prints both.

## After by-elections

Move the ridings in `data/byelections.json` from `upcoming` to `held` with the winner, and add any newly called ones.

Method notes are in the docstring at the top of `scripts/build_spending.py`.

## Hosting as a self-updating website

`.github/workflows/update.yml` runs `run.sh` on GitHub Actions every day at 09:17 UTC and publishes
`output/riding_spending_map.html` to GitHub Pages as `index.html`, with the CSV exports beside it.
To turn it on: push this folder to a GitHub repository, then in the repository's
Settings → Pages set Source to "GitHub Actions". The first run can be started by hand from the
Actions tab. The daily run downloads the full grants file (about 2.3 GB) each time; it takes a few minutes.

### Safeguards in the daily run

- **Downloads** go through `fetch` in `run.sh`: a failed request or a file under its minimum size never replaces the
  previous copy.
- **Federal layer**: after the rebuild, `scripts/check_federal.py` rejects the result if ridings are missing, money since
  the election falls by more than 10%, the grants file loses more than 5% of its rows, or more than 2% of agreements drop
  out of the source. A rejected or failed rebuild puts back the last good copy (`data/lastgood/`, kept between runs in the
  Actions cache) and the rest of the site still builds. Provincial layers keep their existing snapshot-and-restore.
- **Ledger**: `data/ledger/federal_grants_since_election.csv.gz` keeps every agreement since election day. Records the
  government later withdraws stay, marked `in_source=0` with the date they dropped out; `value_first_seen` keeps the
  original amount. The workflow commits it when it changes.
- **Before publishing**, `scripts/check_site.py` checks every page was built, carries data, and has not shrunk below 60% of
  the live page. If not, nothing is deployed and the live site stays as it was. It writes `status.json` (published with
  the site) listing the data dates and any fallbacks.
- **Alerts**: a failed run, or one that fell back to old data, opens (or comments on) a GitHub issue labelled
  `refresh-alert`, which emails the repository owner.
