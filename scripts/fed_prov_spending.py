"""Federal grants and contributions placed in a province's provincial ridings, for provinces
that publish no payee list of their own.

  python3 fed_prov_spending.py pe     Prince Edward Island (27 districts)
  python3 fed_prov_spending.py qc     Quebec (127 ridings of the 2026 map)

PEI's Public Accounts Volume II and Quebec's Comptes publics Volume 2 itemise transfers by
department, program and beneficiary *category* ("Operating Grant", "Pharmacare",
"Municipalités", "Organismes à but non lucratif"), never by named recipient, so provincial
payments cannot be placed. These pages therefore show where *federal* money lands, riding by
riding, set against the latest provincial result. The data, windows and flags are exactly the
federal page's (build_spending.py); only the shapes differ:

  * agreements from data/raw/grants.csv whose recipient is in the province (province code, or
    a postal code with the province's first letter), amendments merged as on the federal page;
  * placed by the recipient postal code's GeoNames centroid inside the riding shapes
    (data/<dir>/divisions_geo.json), else the postal area's (FSA) centroid, else the city's
    centroid when the city sits in one riding ("approx.");
  * "after" = federal election day (28 April 2025) to the federal page's cutoff (the last
    quarter that looks fully reported); "before" = the same dates a year earlier; both
    annualized;
  * flags as on the federal page: national bodies, other governments (the province itself is
    the big one), treaty settlements and foreign aid are left out of the adjusted totals.
Writes data/<dir>/division_spending.json in the provincial-page schema, with the
open.canada.ca record keys (org, ref) kept on each grant so the page can link them.
"""
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT / "scripts"))
from build_spending import ELECTION, KEEP_FROM, CLOSE_MARGIN, norm, first, flag_reason, clean_postal, to_float, amend_no, recipient_table  # noqa: E402
from geo import RidingIndex, load_centroids  # noqa: E402

PROFILES = {
    "pe": {"dir": "pe", "prov": "PE", "postal": "C", "year": "2023", "gov": "PC", "opp": "opposition", "provincial_election": "2023-04-03",
           "multi_city": ["Charlottetown", "Summerside", "Stratford", "Cornwall"]},
    "qc": {"dir": "qc", "prov": "QC", "postal": "GHJ", "year": "2026", "gov": "PQ", "opp": "opposition", "provincial_election": "2026-10-05",
           "multi_city": ["Montréal", "Québec", "Laval", "Gatineau", "Longueuil", "Sherbrooke", "Lévis", "Saguenay", "Trois-Rivières", "Terrebonne",
                          "Repentigny", "Brossard", "Saint-Jean-sur-Richelieu", "Drummondville", "Saint-Jérôme", "Granby", "Blainville", "Mirabel", "Châteauguay"]},
}

csv.field_size_limit(sys.maxsize)


def main():
    P = PROFILES[sys.argv[1] if len(sys.argv) > 1 else "pe"]
    OUT = ROOT / "data" / P["dir"]
    GOV_PARTY, OPP_PARTY, YEAR = P["gov"], P["opp"], P["year"]
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    fed = json.load(open(ROOT / "data" / "riding_spending.json"))["meta"]
    cutoff = date.fromisoformat(fed["cutoff"])
    before_start, before_end = date.fromisoformat(fed["before_start"]), date.fromisoformat(fed["before_end"])
    years = fed["years_per_window"]

    agreements = {}
    addr_votes = defaultdict(Counter)
    with open(RAW / "grants.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if None in row or row.get("owner_org_title") is None:
                continue
            pc = clean_postal(row["recipient_postal_code"])
            if row["recipient_province"] != P["prov"] and not (pc and pc[0] in P["postal"]):
                continue
            bn = "".join(ch for ch in (row["recipient_business_number"] or "") if ch.isdigit())[:9]
            if pc:
                if bn:
                    addr_votes[("bn", bn)][pc] += 1
                addr_votes[("name", norm(first(row["recipient_legal_name"])))][pc] += 1
            start = (row["agreement_start_date"] or "")[:10]
            if start < KEEP_FROM:
                continue
            key = (row["owner_org"], row["ref_number"].strip())
            a_no = amend_no(row["amendment_number"])
            prev = agreements.get(key)
            rec = {"a": a_no, "start": start, "value": to_float(row["agreement_value"]), "dept": row["owner_org_title"].split("|")[0].strip(),
                   "recipient": first(row["recipient_operating_name"] or row["recipient_legal_name"]), "legal": first(row["recipient_legal_name"]),
                   "rtype": row["recipient_type"], "country": row["recipient_country"], "city": first(row["recipient_city"]), "prov": row["recipient_province"],
                   "pc": pc, "bn": bn, "org": row["owner_org"], "ref": row["ref_number"].strip(), "program": first(row["prog_name_en"])}
            if prev is None:
                agreements[key] = rec
                continue
            first_start = min(prev["start"], start)
            if a_no >= prev["a"]:
                rec["pc"] = rec["pc"] or prev["pc"]
                agreements[key] = rec
            agreements[key]["start"] = first_start
    addr_best = {k: c.most_common(1)[0][0] for k, c in addr_votes.items()}
    for rec in agreements.values():
        if rec["pc"]:
            continue
        pc = (addr_best.get(("bn", rec["bn"])) if rec["bn"] else None) or addr_best.get(("name", norm(rec["legal"])))
        if pc:
            rec["pc"], rec["pc_borrowed"] = pc, True

    centroids = load_centroids()
    fsa_pts, place_pts = defaultdict(list), defaultdict(list)
    for pc, pt in centroids.items():
        if pc[0] in P["postal"]:
            fsa_pts[pc[:3]].append(pt)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            if row[4] == P["prov"]:
                try:
                    place_pts[norm(row[2])].append((float(row[9]), float(row[10])))
                except (IndexError, ValueError):
                    continue

    def at(pts):
        return index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))[0] if pts else None
    loc = {}

    def place(rec):
        if rec["pc"] in centroids:
            num = loc.setdefault(rec["pc"], index.locate(*centroids[rec["pc"]])[0])
            if num:
                return num, "recipient's address on other awards" if rec.get("pc_borrowed") else "postal code"
        if rec["pc"] and rec["pc"][:3] in fsa_pts:
            num = loc.setdefault(rec["pc"][:3], at(fsa_pts[rec["pc"][:3]]))
            if num:
                return num, "postal area (approx.)"
        if rec["city"]:
            num = loc.setdefault("city:" + norm(rec["city"]), at(place_pts.get(norm(rec["city"]))))
            if num:
                return num, "city (approx.)"
        return None, "unmapped"

    # City governments spanning several districts can't be pinned to one.
    multi = {(norm(c), P["prov"]) for c in P["multi_city"]}
    per = {num: {"after": Counter(), "before": Counter(), "depts": Counter(), "grants": [], "series": Counter()} for num in divisions}
    quarters = sorted({(int(r["start"][:4]), (int(r["start"][5:7]) - 1) // 3) for r in agreements.values()})
    quarters = [q for q in quarters if q <= (date.today().year, (date.today().month - 1) // 3)]  # a few agreements carry start dates in the future
    qlabel = lambda q: f"{q[0]}Q{q[1] + 1}"
    dept_totals = defaultdict(lambda: defaultdict(float))
    methods, excluded, flagged_total, unmatched = Counter(), Counter(), Counter(), Counter()
    for rec in agreements.values():
        if rec["value"] <= 0 or (rec["country"] and rec["country"] != "CA") or rec["rtype"] == "I":
            continue
        d = date.fromisoformat(rec["start"])
        window = "before" if before_start <= d <= before_end else "after" if ELECTION <= d <= cutoff else None
        num, how = place(rec)
        if not num:
            if window:
                methods[(window, "unmapped")] += 1
                excluded[(window, "unmatched")] += rec["value"]
            if window == "after":
                unmatched[rec["recipient"]] += rec["value"]
            continue
        flag = flag_reason(rec, multi)
        if not flag:
            per[num]["series"][qlabel((d.year, (d.month - 1) // 3))] += rec["value"]
        if not window:
            continue
        methods[(window, how)] += 1
        p = per[num]
        p[window]["total"] += rec["value"]
        p[window]["n"] += 1
        if not flag:
            p[window]["adj"] += rec["value"]
            p[window]["adj_n"] += 1
        else:
            flagged_total[(window, rec["recipient"])] += rec["value"]
        if window == "after":
            p["depts"][rec["dept"]] += rec["value"]
            if not flag:
                dept_totals[rec["dept"]][num] += rec["value"]
            p["grants"].append((rec["value"], rec, flag, how))

    out = {}
    for num, dv in divisions.items():
        p = per[num]
        pop = dv["population"] or 1
        a, b = p["after"], p["before"]
        rec = dict(dv)
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"], "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]),
            "pc_after": round(a["adj"] / pop / years, 2), "pc_after_all": round(a["total"] / pop / years, 2), "pc_before": round(b["adj"] / pop / years, 2),
            "close": dv["margin_pts"] < CLOSE_MARGIN, "gov_won": dv[f"party_{YEAR}"] == GOV_PARTY,
            "top_progs": [[k, round(v)] for k, v in p["depts"].most_common(4)],
            "top_grants": [{"v": round(v), "who": g["recipient"][:80], "dept": g["dept"][:60], "prog": g["program"][:80], "date": g["start"],
                            "city": g["city"], "flag": fl, "how": how, "org": g["org"], "ref": g["ref"]}
                           for v, g, fl, how in sorted(p["grants"], key=lambda t: -t[0])[:10]],
        })
        rec["series"] = [round(p["series"].get(qlabel(q), 0)) for q in quarters]
        rec["change_pct"] = round(100 * (a["adj"] - b["adj"]) / b["adj"], 1) if b["adj"] > 0 else None
        out[num] = rec
    med = statistics.median(x["pc_after"] for x in out.values())
    for x in out.values():
        x["score"] = round(x["pc_after"] / med, 2) if med else None
        x["group"] = ("Close" if x["close"] else "Safe") + (f" {GOV_PARTY}" if x["gov_won"] else f" {OPP_PARTY}")
    groups = {}
    for g in [f"Close {GOV_PARTY}", f"Close {OPP_PARTY}", f"Safe {GOV_PARTY}", f"Safe {OPP_PARTY}"]:
        xs = [x for x in out.values() if x["group"] == g]
        chg = [x["change_pct"] for x in xs if x["change_pct"] is not None]
        groups[g] = {"ridings": len(xs), "median_pc_after": round(statistics.median(x["pc_after"] for x in xs), 2) if xs else None,
                     "median_pc_before": round(statistics.median(x["pc_before"] for x in xs), 2) if xs else None,
                     "median_change_pct": round(statistics.median(chg), 1) if chg else None,
                     "total_adj_after": round(sum(x["after_adj"] for x in xs))}
    flagged_after = sum(x["after_total"] - x["after_adj"] for x in out.values())
    meta = {
        "generated": date.today().isoformat(), "election": ELECTION.isoformat(), "federal_election": ELECTION.isoformat(),
        "provincial_election": P["provincial_election"], "cutoff": cutoff.isoformat(),
        "before_start": before_start.isoformat(), "before_end": before_end.isoformat(), "years_per_window": years,
        "population_basis": next(iter(divisions.values())).get("population_basis", ""),
        "close_margin": CLOSE_MARGIN, "median_pc_after": med,
        "methods": {f"{w}|{m}": v for (w, m), v in methods.items()},
        "excluded_after": {"unmatched": round(excluded[("after", "unmatched")]), "flagged": round(flagged_after)},
        "placed_after": round(sum(x["after_total"] for x in out.values())),
        "total_after": round(sum(x["after_total"] for x in out.values()) + excluded[("after", "unmatched")]),
        "top_flagged": [[k, round(v)] for (w, k), v in sorted(flagged_total.items(), key=lambda kv: -kv[1]) if w == "after"][:20],
        "top_unmatched": [[k, round(v)] for k, v in unmatched.most_common(20)],
        "programs": sorted(dept_totals, key=lambda d: -sum(dept_totals[d].values()))[:60],
        "series": {"kind": "quarter", "labels": [qlabel(q) for q in quarters], "complete": sum(1 for q in quarters if date(q[0], q[1] * 3 + 1, 1) <= cutoff),
                   "election_index": sum(1 for q in quarters if date(q[0], q[1] * 3 + 1, 1) <= ELECTION) - 1},
    }
    json.dump({"meta": meta, "groups": groups, "ridings": out, "recipients": recipient_table(per, lambda g: g["recipient"][:80]),
               "prog_by_riding": {k: {n: round(v) for n, v in m.items()} for k, m in dept_totals.items() if k in meta["programs"]}},
              open(OUT / "division_spending.json", "w"), ensure_ascii=False)
    print(json.dumps({k: v for k, v in meta.items() if k != "programs"}, indent=1, ensure_ascii=False))
    print(json.dumps(groups, indent=1))


if __name__ == "__main__":
    main()
