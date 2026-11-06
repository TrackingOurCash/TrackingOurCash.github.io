"""Estimate how much of each federal budget lands in each riding.

Reads data/budget_measures.json (hand-curated: every measure in each budget's chapter summary
tables, net of the "Less:" lines under it, with one allocation key), data/riding_spending.json
(grants by department and riding), data/contracts_by_riding.json (contracts by department) and
data/ridings.json (population). Writes data/budget_estimate.json:

  {"method": ..., "budgets": [{key, name, date, url, total_placed, excluded, official_net,
     measures: [{measure, net_millions, key, note, ridings_reached}],
     by_riding: {num: {"total": $, "pc": $/person, "by_key": {pop|prov|dept|cdept|places: $},
                       "top": [[measure index, $], ...]}}}]}

This is an estimate, not a record: budgets announce national programs, and where the money
lands is decided later, one award at a time. The keys say what each guess rests on.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from budget import locator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def main():
    src = json.load(open(DATA / "budget_measures.json"))
    ridings = json.load(open(DATA / "ridings.json"))
    sp = json.load(open(DATA / "riding_spending.json"))
    ct = json.load(open(DATA / "contracts_by_riding.json")) if (DATA / "contracts_by_riding.json").exists() else {"dept_by_riding": {}}
    pop = {n: max(1, r.get("population") or 0) for n, r in ridings.items()}
    ridings_for = locator()

    def share(weights):
        tot = sum(weights.values())
        return {n: w / tot for n, w in weights.items() if w > 0} if tot > 0 else None

    def dept_weights(names):
        w = defaultdict(float)
        for d in names:
            for which in ("dept_by_riding", "dept_by_riding_before"):
                for n, v in sp.get(which, {}).get(d, {}).items():
                    if n in pop:
                        w[n] += v
        # Square root of the dollars, so a single very large award does not decide where a whole national program goes.
        return {n: v ** 0.5 for n, v in w.items() if v > 0}

    def key_share(key):
        kind, _, arg = key.partition(":")
        if kind == "pop":
            return share(pop)
        if kind == "prov":
            provs = set(arg.split("|"))
            return share({n: p for n, p in pop.items() if ridings[n]["province"] in provs})
        if kind == "dept":
            names = [d for g in arg.split("|") for d in src["groups"].get(g, [g])]
            return share(dept_weights(names)) or share(pop)
        if kind == "cdept":
            w = defaultdict(float)
            for d in arg.split("|"):
                for n, v in ct["dept_by_riding"].get(d, {}).items():
                    if n in pop:
                        w[n] += v
            return share({n: v ** 0.5 for n, v in w.items() if v > 0}) or share(pop)
        if kind == "places":
            hit = defaultdict(float)
            places = arg.split("|")
            for pl in places:
                nums = ridings_for(pl) or []
                for n in nums:  # each named place gets an equal slice, split over its ridings
                    hit[n] += 1 / len(nums) / len(places)
            return share(hit)
        return None

    out = {"method": src["method"], "as_of": src["as_of"], "budgets": []}
    for b in src["budgets"]:
        by = defaultdict(lambda: {"total": 0.0, "by_key": defaultdict(float), "top": defaultdict(float)})
        excluded, placed, measures = 0.0, 0.0, []
        for i, mz in enumerate(b["measures"]):
            dollars = mz["net_millions"] * 1e6
            sh = None if mz["key"].startswith("excluded") or dollars <= 0 else key_share(mz["key"])
            measures.append({**mz, "ridings_reached": len(sh) if sh else 0})
            if not sh:
                excluded += dollars
                continue
            kind = mz["key"].split(":")[0]
            for n, f in sh.items():
                v = dollars * f
                by[n]["total"] += v
                by[n]["by_key"][kind] += v
                by[n]["top"][i] += v
            placed += dollars
        rows = {}
        for n in ridings:
            r = by.get(n)
            if not r:
                rows[n] = {"total": 0, "pc": 0, "by_key": {}, "top": []}
                continue
            rows[n] = {"total": round(r["total"]), "pc": round(r["total"] / pop[n], 2),
                       "by_key": {k: round(v) for k, v in r["by_key"].items()},
                       "top": [[i, round(v)] for i, v in sorted(r["top"].items(), key=lambda kv: -kv[1])[:12]]}
        official = sum(b.get("official_net_by_chapter", {}).values()) * 1e6 or None
        out["budgets"].append({k: b[k] for k in ("key", "name", "date", "url", "years")} | {
            "official_net": official, "total_placed": round(placed), "excluded": round(excluded),
            "measures": measures, "by_riding": rows})
        print(f"{b['key']}: placed ${placed / 1e9:,.1f}B, excluded ${excluded / 1e9:,.1f}B, official net ${(official or 0) / 1e9:,.1f}B; "
              f"per-person range ${min(x['pc'] for x in rows.values()):,.0f} to ${max(x['pc'] for x in rows.values()):,.0f}")
    json.dump(out, open(DATA / "budget_estimate.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
