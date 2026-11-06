"""Sanity check for the federal layer after a rebuild, before it can replace the last good copy.

run.sh calls this after build_spending.py. Exit 0 = publish the new data; exit 1 = reject it, and
run.sh puts back the last good copy (data/lastgood/, kept between runs) and the committed ledger,
so a truncated download or a bad day at open.canada.ca cannot publish zeros or drop records.

Checks, each against the last good build when there is one:
  - all 343 ridings present, each with a population;
  - money since the election is above zero and has not fallen by more than 10%
    (the window only grows; amendments can trim a little, never a tenth);
  - the grants file still has at least 95% of the rows it had;
  - the ledger has not lost more than 2% of the agreements it held to "no longer in the source".
"""
import csv
import gzip
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GOOD = DATA / "lastgood"


def ledger_counts(path):
    live = gone = 0
    if path.exists():
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                if r["in_source"] == "1":
                    live += 1
                else:
                    gone += 1
    return live, gone


def main():
    problems = []
    try:
        new = json.load(open(DATA / "riding_spending.json"))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"federal: riding_spending.json unreadable ({e}); rejecting")
    rid = new["ridings"]
    if len(rid) != 343:
        problems.append(f"{len(rid)} ridings, expected 343")
    if any(not r.get("population") for r in rid.values()):
        problems.append("a riding has no population")
    after = sum(r["after_total"] for r in rid.values())
    if after <= 0:
        problems.append("no money since the election")
    old = None
    if (GOOD / "riding_spending.json").exists():
        old = json.load(open(GOOD / "riding_spending.json"))
        old_after = sum(r["after_total"] for r in old["ridings"].values())
        if old["meta"]["cutoff"] == new["meta"]["cutoff"] and after < 0.9 * old_after:
            problems.append(f"money since the election fell from ${old_after:,.0f} to ${after:,.0f}")
        old_rows, new_rows = old["meta"]["stats"].get("rows", 0), new["meta"]["stats"].get("rows", 0)
        if new_rows < 0.95 * old_rows:
            problems.append(f"grants file shrank from {old_rows:,} to {new_rows:,} rows")
    live, gone = ledger_counts(DATA / "ledger" / "federal_grants_since_election.csv.gz")
    if (GOOD / "ledger_counts.json").exists():
        prev = json.load(open(GOOD / "ledger_counts.json"))
        newly_gone = gone - prev.get("gone", 0)
        if newly_gone > 0.02 * max(1, prev.get("live", 0)):
            problems.append(f"{newly_gone:,} agreements dropped out of the source since the last good build (more than 2%)")
    if problems:
        print("federal: REJECTED: " + "; ".join(problems))
        sys.exit(1)
    json.dump({"live": live, "gone": gone}, open(DATA / "ledger_counts.json.tmp", "w"))
    print(f"federal: ok, ${after:,.0f} since the election across 343 ridings; ledger {live:,} live, {gone:,} withdrawn and kept"
          + (f"; window to {new['meta']['cutoff']}" if old is None else f"; window {old['meta']['cutoff']} -> {new['meta']['cutoff']}"))


if __name__ == "__main__":
    main()
