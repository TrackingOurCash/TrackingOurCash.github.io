"""Everything the federal government has put into the ridings with a by-election coming up.

Reads data/byelections.json (hand-kept list of the vacant seats), the grants ledger
(data/ledger/federal_grants_since_election.csv.gz, every agreement since election day, including
quarters still being reported and any record the source has since dropped), the contracts layer,
the budget lists and the budget estimate. Writes data/byelection_detail.json.
"""
import csv
import gzip
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def load(name, default=None):
    p = DATA / name
    return json.load(open(p)) if p.exists() else default


def main():
    be = load("byelections.json")
    sp = load("riding_spending.json")
    ct = load("contracts_by_riding.json", {"ridings": {}, "meta": {}})
    bud = load("budget_by_riding.json", {"by_riding": {}})
    est = load("budget_estimate.json", {"budgets": []})
    cutoff = sp["meta"]["cutoff"]
    focus = {b["num"] for b in be["upcoming"]}

    grants = defaultdict(list)
    all_since = defaultdict(float)  # every riding's total since the election, for ranks
    with gzip.open(DATA / "ledger" / "federal_grants_since_election.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not r["riding"]:
                continue
            v = float(r["value"] or 0)
            if r["in_source"] == "1" and not r["flag"]:
                all_since[r["riding"]] += v
            if r["riding"] in focus:
                grants[r["riding"]].append({"v": round(v), "who": r["recipient"], "dept": r["dept"], "prog": r["program"], "title": r["title"],
                                            "date": r["start"], "city": r["city"], "flag": r["flag"], "how": r["how"], "org": r["org"], "ref": r["ref"],
                                            "in_source": r["in_source"] == "1", "late": r["start"] > cutoff, "first": r.get("value_first_seen")})
    pop = {n: r["population"] or 1 for n, r in sp["ridings"].items()}
    pc_all = {n: all_since.get(n, 0) / pop[n] for n in pop}
    ranked = sorted(pc_all, key=lambda n: -pc_all[n])
    median_pc = statistics.median(pc_all.values())

    out = {"meta": {"cutoff": cutoff, "election": sp["meta"]["election"], "polling_day": be["polling_day"], "called": be["called"],
                    "median_pc_since": round(median_pc, 2), "ridings_ranked": len(ranked), "sources": be["sources"], "note": be["note"]},
           "held": be["held"], "ridings": {}}
    for b in be["upcoming"]:
        n = b["num"]
        r = sp["ridings"][n]
        gs = sorted(grants[n], key=lambda g: (g["date"], g["v"]), reverse=True)
        live = [g for g in gs if g["in_source"]]
        adj = [g for g in live if not g["flag"]]
        by_dept = Counter()
        by_month = Counter()
        for g in adj:
            by_dept[g["dept"]] += g["v"]
            by_month[g["date"][:7]] += g["v"]
        c = ct["ridings"].get(n, {})
        megas = [{"who": m.get("who"), "v": round(m["v"] * m["ridings"][n]), "full": m["v"], "dept": m.get("dept"), "desc": m.get("desc"), "date": m.get("date"),
                  "window": m.get("window")} for m in ct["meta"].get("large", []) if (m.get("ridings") or {}).get(n) and m.get("window") == "after"]
        estimates = []
        for e in est["budgets"]:
            row = e["by_riding"].get(n, {})
            estimates.append({"key": e["key"], "name": e["name"], "date": e["date"], "url": e["url"], "total": row.get("total", 0), "pc": row.get("pc", 0),
                              "by_key": row.get("by_key", {}),
                              "top": [{"measure": e["measures"][i]["measure"], "v": v, "key": e["measures"][i]["key"]} for i, v in row.get("top", [])[:6]]})
        out["ridings"][n] = {**b, "population": r["population"], "party_2025": r["party_2025"], "winner_2025": r["winner_2025"], "runnerup_2025": r["runnerup_2025"],
                             "runnerup_party_2025": r["runnerup_party_2025"], "margin_votes": r["margin_votes"], "margin_pts": r["margin_pts"], "shares_2025": r["shares_2025"],
                             "close": r["margin_pts"] < sp["meta"]["close_margin"],
                             "grants_since": round(sum(g["v"] for g in adj)), "grants_since_all": round(sum(g["v"] for g in live)), "grants_n": len(live),
                             "grants_reported_late": round(sum(g["v"] for g in adj if g["late"])),
                             "grants_dropped": [g for g in gs if not g["in_source"]],
                             "pc_since": round(pc_all[n], 2), "rank": ranked.index(n) + 1,
                             "window_after_adj": r["after_adj"], "window_before_adj": r["before_adj"], "change_pct": r.get("change_pct"),
                             "by_dept": by_dept.most_common(), "by_month": sorted(by_month.items()), "grants": live,
                             "contracts_after": c.get("after_total", 0), "contracts_n": c.get("after_n", 0), "contracts_top": c.get("top_contracts", [])[:10],
                             "megas": megas, "budget_items": bud["by_riding"].get(n, []), "estimates": estimates}
        print(f'{b["name"]}: {len(live)} grants, ${out["ridings"][n]["grants_since"] / 1e6:,.1f}M since the election (rank {ranked.index(n) + 1}/{len(ranked)} per person), '
              f'{len(megas)} megacontracts, {len(out["ridings"][n]["budget_items"])} budget items')
    json.dump(out, open(DATA / "byelection_detail.json", "w"), ensure_ascii=False)


if __name__ == "__main__":
    main()
