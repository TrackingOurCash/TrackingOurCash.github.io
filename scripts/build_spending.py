"""Aggregate federal grants and contributions by 2023-order riding.

Reads data/raw/grants.csv (Proactive Disclosure - Grants and Contributions) and
data/ridings.json (from prep_ridings.py). Writes data/riding_spending.json.

Method, in order:
  1. Amendments: rows sharing (owner_org, ref_number) are one agreement. The
     highest amendment_number carries the agreement's current total value, so
     that row's value is used; the start date comes from the original.
  2. Riding: the record's own federal riding field when it names a 2023-order
     riding (rarely filled in); otherwise the recipient postal code's GeoNames
     centroid placed inside the 2023 boundaries; otherwise the centroid of its
     first three characters (FSA), or the recipient's city when that city maps
     to one riding. The last two are marked approximate.
  3. National / other-government flag: recipients whose money is booked at a
     head office (national associations, provincial governments) are flagged
     so totals can be shown with and without them. Treaty and specific-claim
     settlements are flagged the same way, since they are legal obligations.
  4. Windows: "after" runs from election day (2025-04-28) to the end of the last
     quarter that looks fully reported; "before" is the same calendar dates one
     year earlier (2024-04-28 onward), so both hold the same season.
     Both are annualized and divided by 2021 population.
"""
import csv
import json
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from geo import RidingIndex, load_centroids

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"
ELECTION = date(2025, 4, 28)
KEEP_FROM = "2024-01-01"  # earliest start date that can fall in the "before" window
CLOSE_MARGIN = 10.0

csv.field_size_limit(sys.maxsize)

NATIONAL_NAME = re.compile(
    r"\b(canada|canadian|canadienne?s?|national|nationale?|of canada|du canada|federation|fédération|"
    r"association of|confederation|congress)\b",
    re.I,
)
INTERNATIONAL = re.compile(r"international development|international assistance|humanitarian|weapon threat|peace and stabilization|"
                           r"counter-terrorism capacity|international humanitarian", re.I)
SETTLEMENT = re.compile(r"treaties and aboriginal government|specific claims?|claims? settlement|litigation", re.I)
OTHER_GOV = re.compile(
    r"\b(government of|gouvernement d|province of|ministry|minister|ministère|ministre|"
    r"receiver general|treasurer|minister of finance|his majesty|her majesty|crown in right)\b",
    re.I,
)


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def first(v):
    """Some departments publish 'English | French' in one field; keep the English."""
    return (v or "").split("|")[0].strip()


PROVINCES = {norm_p for norm_p in [
    "ontario", "quebec", "province of quebec", "british columbia", "alberta", "saskatchewan", "manitoba",
    "nova scotia", "new brunswick", "prince edward island", "newfoundland and labrador", "yukon",
    "northwest territories", "nunavut",
]}


def flag_reason(rec, multi_riding_cities):
    """Why an award is left out of the adjusted totals, or "" to keep it."""
    # National bodies booked at a head office. Indigenous governments ("... National
    # Government") and companies ("Ford of Canada") are local, so only non-profits and
    # other non-commercial recipients are judged by name.
    if rec["rtype"] not in ("A", "F") and (NATIONAL_NAME.search(rec["legal"]) or NATIONAL_NAME.search(rec["recipient"])):
        return "national"
    if (OTHER_GOV.search(rec["legal"]) or norm(rec["legal"]) in PROVINCES
            or (rec["rtype"] == "G" and (norm(rec["city"]), rec["prov"]) in multi_riding_cities)):
        return "government"
    # Specific-claim and treaty settlements are legal obligations, not discretionary grants.
    if SETTLEMENT.search(rec["program"]):
        return "settlement"
    # Foreign aid is spent abroad, whatever the Canadian partner's address.
    if INTERNATIONAL.search(rec["program"]):
        return "international"
    return ""


def clean_postal(pc):
    pc = re.sub(r"[^A-Za-z0-9]", "", pc or "").upper()
    return pc if re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", pc) else ""


def to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def formula_matcher(level):
    """-> f(label) that says whether a payment is "formula" money (allocated by a published rule)
    per data/formula_programs.json. The label is what that file's level says it matches:
    "Department | Program" for federal, the 'Ministry: Program' label for Alberta and
    Saskatchewan, "Department | Recipient" for the provinces whose statements carry no program."""
    path = ROOT / "data" / "formula_programs.json"
    if not path.exists():
        return lambda label: False
    lv = json.load(open(path))["levels"].get(level)
    if not lv:
        return lambda label: False
    pats = [re.compile(e["re"], re.I) for e in lv["formula"]]
    return lambda label: any(p.search(label) for p in pats)


def recipient_table(per, name_of, cap=5000, floor=100000):
    """Every recipient's after-window total across ridings: [name, total, awards, flag, {riding: dollars}],
    largest first, for the page's recipient search and top-50 list."""
    agg = {}
    for num, p in per.items():
        for v, g, flag, how in p["grants"]:
            name = name_of(g)
            a = agg.setdefault(name, {"v": 0.0, "n": 0, "flag": flag, "r": {}})
            a["v"] += v
            a["n"] += 1
            a["r"][num] = a["r"].get(num, 0) + v
            if flag:
                a["flag"] = flag
    rows = sorted(agg.items(), key=lambda kv: -kv[1]["v"])
    return [[k, round(a["v"]), a["n"], a["flag"], {n: round(v) for n, v in sorted(a["r"].items(), key=lambda kv: -kv[1])[:12]}]
            for i, (k, a) in enumerate(rows[:cap]) if a["v"] >= floor or i < 500]


def amend_no(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def main():
    ridings = json.load(open(OUT / "ridings.json"))
    name_to_num = {}
    for num, r in ridings.items():
        name_to_num[norm(r["name"])] = num
        name_to_num[norm(r["current_name"])] = num
    for o in json.load(open(RAW / "fed2023_list.json"))["objects"]:
        name_to_num[norm(o["name"])] = o["external_id"]

    def riding_from_fields(row):
        nm = row["federal_riding_name_en"].strip()
        if nm:
            return name_to_num.get(norm(nm))
        return None

    agreements = {}
    addr_votes = defaultdict(Counter)
    stats = Counter()
    latest_start = ""

    with open(RAW / "grants.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            if None in row or row.get("owner_org_title") is None:
                stats["malformed_rows"] += 1
                continue
            pc = clean_postal(row["recipient_postal_code"])
            rnum = riding_from_fields(row)
            bn = re.sub(r"\D", "", row["recipient_business_number"] or "")[:9]
            if pc:
                # Remember where each recipient has been seen with a postal code, so a later
                # award for the same body with no postal code can be placed.
                if bn:
                    addr_votes[("bn", bn)][pc] += 1
                addr_votes[("name", norm(first(row["recipient_legal_name"])), row["recipient_province"])][pc] += 1
            if row["federal_riding_name_en"].strip() or row["federal_riding_number"].strip():
                stats["rows_with_riding_field"] += 1
                stats["rows_with_2023_riding" if rnum else "rows_with_other_riding"] += 1

            start = (row["agreement_start_date"] or "")[:10]
            if start < KEEP_FROM:
                continue
            key = (row["owner_org"], row["ref_number"].strip())
            a_no = amend_no(row["amendment_number"])
            prev = agreements.get(key)
            rec = {
                "a": a_no,
                "start": start,
                "value": to_float(row["agreement_value"]),
                "dept": row["owner_org_title"].split("|")[0].strip(),
                "recipient": first(row["recipient_operating_name"] or row["recipient_legal_name"]),
                "legal": first(row["recipient_legal_name"]),
                "rtype": row["recipient_type"],
                "country": row["recipient_country"],
                "city": first(row["recipient_city"]),
                "prov": row["recipient_province"],
                "pc": pc,
                "bn": bn,
                "org": row["owner_org"],
                "ref": row["ref_number"].strip(),
                "riding": rnum,
                "program": first(row["prog_name_en"]),
                "title": (row["agreement_title_en"] or "").strip()[:140],
                "coverage": row.get("coverage", ""),
            }
            if prev is None:
                agreements[key] = rec
                continue
            stats["amendment_rows_merged"] += 1
            first_start = min(prev["start"], start)
            if a_no >= prev["a"]:
                rec["riding"] = rec["riding"] or prev["riding"]
                rec["pc"] = rec["pc"] or prev["pc"]
                agreements[key] = rec
            agreements[key]["start"] = first_start

    # Recipients with no postal code: borrow the one their other awards carry
    # (same business number, else same legal name in the same province).
    addr_best = {k: c.most_common(1)[0][0] for k, c in addr_votes.items()}
    for rec in agreements.values():
        if rec["pc"] or rec["riding"]:
            continue
        pc = addr_best.get(("bn", rec["bn"])) if rec["bn"] else None
        pc = pc or addr_best.get(("name", norm(rec["legal"]), rec["prov"]))
        if pc:
            rec["pc"], rec["pc_borrowed"] = pc, True
            stats["postal_codes_borrowed"] += 1

    # Postal code -> riding by point-in-polygon on GeoNames centroids.
    centroids = load_centroids()
    fsa_pts = defaultdict(list)
    for pc, (lat, lon) in centroids.items():
        fsa_pts[pc[:3]].append((lat, lon))
    index = RidingIndex()
    needed = {rec["pc"] for rec in agreements.values() if rec["pc"] and not rec["riding"]}
    postal_to_riding, fsa_to_riding = {}, {}
    for pc in needed:
        if pc in centroids:
            num, _ = index.locate(*centroids[pc])
            if num:
                postal_to_riding[pc] = num
    for fsa in {pc[:3] for pc in needed if pc not in postal_to_riding}:
        pts = fsa_pts.get(fsa)
        if pts:
            num, _ = index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            if num:
                fsa_to_riding[fsa] = num
    stats["postal_codes_needed"] = len(needed)
    stats["postal_codes_located"] = len(postal_to_riding)

    # Place-name centroids from GeoNames (mean of the place's postal codes), for
    # records that carry only a city.
    place_pts = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            try:
                place_pts[(norm(row[2]), row[4])].append((float(row[9]), float(row[10])))
            except (IndexError, ValueError):
                continue

    # City fallback for records with no usable postal code: only when the city's
    # other records place it in one riding at least 80% of the time.
    city_votes = defaultdict(Counter)
    for rec in agreements.values():
        num = rec["riding"] or postal_to_riding.get(rec["pc"])
        if num and rec["city"]:
            city_votes[(norm(rec["city"]), rec["prov"])][num] += 1
    city_to_riding = {}
    # Cities split across several ridings: a city government's grant can't be pinned to one.
    multi_riding_cities = {k for k, c in city_votes.items()
                           if sum(1 for n in c.values() if n >= 0.1 * sum(c.values())) >= 2}
    for k, c in city_votes.items():
        num, n = c.most_common(1)[0]
        if n >= 3 and n / sum(c.values()) >= 0.8:
            city_to_riding[k] = num
    for rec in agreements.values():
        k = (norm(rec["city"]), rec["prov"])
        if rec["riding"] or rec["pc"] or not rec["city"] or k in city_to_riding or k in multi_riding_cities:
            continue
        pts = place_pts.get(k)
        if pts:
            num, _ = index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            if num:
                city_to_riding[k] = num

    for rec in agreements.values():
        latest_start = max(latest_start, rec["start"])

    # Cutoff: end of the newest calendar quarter whose agreement count reaches 70% of
    # the same quarter a year earlier. Grants are very seasonal (summer jobs start in
    # Q2), so a quarter is judged against its own season, and late reporting leaves the
    # newest quarters thin.
    q_counts = Counter()
    for rec in agreements.values():
        y, m = int(rec["start"][:4]), int(rec["start"][5:7])
        q_counts[(y, (m - 1) // 3)] += 1
    election_q = (ELECTION.year, (ELECTION.month - 1) // 3)
    passing = [q for q in q_counts if q >= election_q and q_counts[q] >= 0.7 * q_counts[(q[0] - 1, q[1])]]
    cy, cq = max(passing)
    cutoff = date(cy + (cq == 3), (cq * 3 + 3) % 12 + 1, 1) - timedelta(days=1)
    # "Before" is the same calendar dates one year earlier, so both windows hold the same season.
    before_start = ELECTION.replace(year=ELECTION.year - 1)
    before_end = cutoff.replace(year=cutoff.year - 1)
    span = (cutoff - ELECTION).days + 1
    years = span / 365.25

    per = {num: {"after": Counter(), "before": Counter(), "depts": Counter(), "grants": [], "series": Counter()} for num in ridings}
    is_formula = formula_matcher("federal")
    quarters = sorted({(int(r["start"][:4]), (int(r["start"][5:7]) - 1) // 3) for r in agreements.values()})
    quarters = [q for q in quarters if q <= (date.today().year, (date.today().month - 1) // 3)]  # a few agreements carry start dates in the future
    qlabel = lambda q: f"{q[0]}Q{q[1] + 1}"
    dept_totals = defaultdict(lambda: defaultdict(float))
    dept_before = defaultdict(lambda: defaultdict(float))
    method_counts = Counter()
    natl_examples = Counter()
    unmapped = []

    for rec in agreements.values():
        if rec["value"] <= 0 or (rec["country"] and rec["country"] != "CA") or rec["rtype"] == "I":
            stats["skipped_nonpositive_or_foreign"] += 1
            continue
        d = date.fromisoformat(rec["start"])
        if before_start <= d <= before_end:
            window = "before"
        elif ELECTION <= d <= cutoff:
            window = "after"
        else:
            window = None  # still counted in the quarterly series
        num, method = rec["riding"], "riding field"
        if not num and rec["pc"] in postal_to_riding:
            num, method = postal_to_riding[rec["pc"]], "recipient's address on other awards" if rec.get("pc_borrowed") else "postal code"
        if not num and rec["pc"][:3] in fsa_to_riding:
            num, method = fsa_to_riding[rec["pc"][:3]], "postal area (approx.)"
        if not num and (norm(rec["city"]), rec["prov"]) in city_to_riding:
            num, method = city_to_riding[(norm(rec["city"]), rec["prov"])], "city (approx.)"
        if not num:
            if window:
                method_counts[(window, "unmapped")] += 1
                method_counts[(window, "unmapped $")] += rec["value"]
            if window == "after":
                unmapped.append(rec)
            continue
        flagged = flag_reason(rec, multi_riding_cities)
        if not flagged:
            per[num]["series"][qlabel((d.year, (d.month - 1) // 3))] += rec["value"]
        if not window:
            continue
        method_counts[(window, method)] += 1
        if flagged and window == "after":
            natl_examples[rec["recipient"]] += rec["value"]
        p = per[num]
        p[window]["total"] += rec["value"]
        p[window]["n"] += 1
        formula = bool(is_formula(f'{rec["dept"]} | {rec["program"]}'))
        if not flagged:
            p[window]["adj"] += rec["value"]
            p[window]["adj_n"] += 1
            if formula:
                p[window]["formula"] += rec["value"]
        rec["formula"] = formula
        if window == "before" and not flagged:
            dept_before[rec["dept"]][num] += rec["value"]
        if window == "after":
            p["depts"][rec["dept"]] += rec["value"]
            if not flagged:
                dept_totals[rec["dept"]][num] += rec["value"]
            p["grants"].append((rec["value"], rec, flagged, method))

    out = {}
    for num, r in ridings.items():
        p = per[num]
        pop = r["population"] or 1
        a, b = p["after"], p["before"]
        rec = dict(r)
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"],
            "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]),
            "after_formula": round(a["formula"]), "before_formula": round(b["formula"]),
            "pc_after": round(a["adj"] / pop / years, 2),
            "pc_after_all": round(a["total"] / pop / years, 2),
            "pc_before": round(b["adj"] / pop / years, 2),
            "close": r["margin_pts"] < CLOSE_MARGIN,
            "lib_won": r["party_2025"] == "LPC",
            "top_depts": [[d, round(v)] for d, v in p["depts"].most_common(4)],
            "top_grants": [
                {"v": round(v), "who": g["recipient"][:80], "dept": g["dept"][:60], "prog": g["program"][:80],
                 "date": g["start"], "city": g["city"], "flag": fl, "how": how, "org": g["org"], "ref": g["ref"], "formula": g.get("formula", False)}
                for v, g, fl, how in sorted(p["grants"], key=lambda t: -t[0])[:10]
            ],
            # The ten most recent awards (by agreement start date), and the date of the newest one, for the "latest" view.
            "latest_grants": [
                {"v": round(v), "who": g["recipient"][:80], "dept": g["dept"][:60], "prog": g["program"][:80],
                 "date": g["start"], "city": g["city"], "flag": fl, "how": how, "org": g["org"], "ref": g["ref"], "formula": g.get("formula", False)}
                for v, g, fl, how in sorted(p["grants"], key=lambda t: (t[1]["start"], t[0]), reverse=True)[:10]
            ],
            "latest_date": max((g["start"] for _, g, _, _ in p["grants"]), default=None),
        })
        rec["series"] = [round(p["series"].get(qlabel(q), 0)) for q in quarters]
        rec["change_pc"] = round(rec["pc_after"] - rec["pc_before"], 2)
        rec["change_pct"] = (round(100 * (a["adj"] - b["adj"]) / b["adj"], 1) if b["adj"] > 0 else None)
        out[num] = rec

    med_pc = statistics.median(x["pc_after"] for x in out.values())
    for x in out.values():
        x["score"] = round(x["pc_after"] / med_pc, 2) if med_pc else None
        x["group"] = ("Close" if x["close"] else "Safe") + (" Liberal" if x["lib_won"] else " opposition")

    groups = {}
    for g in ["Close Liberal", "Close opposition", "Safe Liberal", "Safe opposition"]:
        xs = [x for x in out.values() if x["group"] == g]
        chg = [x["change_pct"] for x in xs if x["change_pct"] is not None]
        groups[g] = {
            "ridings": len(xs),
            "median_pc_after": round(statistics.median(x["pc_after"] for x in xs), 2),
            "median_pc_before": round(statistics.median(x["pc_before"] for x in xs), 2),
            "median_change_pct": round(statistics.median(chg), 1) if chg else None,
            "median_score": round(statistics.median(x["score"] or 0 for x in xs), 2),
            "total_adj_after": round(sum(x["after_adj"] for x in xs)),
        }

    meta = {
        "generated": date.today().isoformat(),
        "election": ELECTION.isoformat(), "cutoff": cutoff.isoformat(), "before_start": before_start.isoformat(), "before_end": before_end.isoformat(),
        "latest_start_in_file": latest_start, "years_per_window": round(years, 3), "close_margin": CLOSE_MARGIN,
        "median_pc_after": med_pc, "stats": dict(stats),
        "methods": {f"{w}|{m}": round(v) for (w, m), v in method_counts.items()},
        "fsas_used": len(fsa_to_riding), "cities_used": len(city_to_riding),
        # Quarterly series of adjusted dollars per riding (rec["series"]), every quarter in the file since KEEP_FROM;
        # quarters after the cutoff are shown but marked as still filling in.
        "series": {"kind": "quarter", "labels": [qlabel(q) for q in quarters], "complete": sum(1 for q in quarters if date(q[0], q[1] * 3 + 1, 1) <= cutoff),
                   "election_index": sum(1 for q in quarters if date(q[0], q[1] * 3 + 1, 1) <= ELECTION) - 1},
        "top_flagged_recipients": [[k, round(v)] for k, v in natl_examples.most_common(25)],
        # Money with no usable location (no postal code, no address on other awards, no single-riding city), by recipient.
        "top_unmapped": [[k[0], round(v), k[1], k[2]] for k, v in sorted(
            sum((Counter({(r["recipient"][:80], r["dept"][:50], r["city"]): r["value"]}) for r in unmapped), Counter()).items(), key=lambda kv: -kv[1])[:25]],
        "excluded_after": {"no location found": round(method_counts[("after", "unmapped $")])},
        "departments": sorted(dept_totals, key=lambda d: -sum(dept_totals[d].values())),
    }
    with open(ROOT / "output" / "unmapped_after_election.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["value", "recipient", "type", "city", "province", "department", "program", "start"])
        for rec in sorted(unmapped, key=lambda r: -r["value"]):
            w.writerow([round(rec["value"]), rec["legal"], rec["rtype"], rec["city"], rec["prov"], rec["dept"], rec["program"], rec["start"]])

    dept_matrix = {d: {n: round(v) for n, v in m.items()} for d, m in dept_totals.items()}
    dept_matrix_before = {d: {n: round(v) for n, v in m.items()} for d, m in dept_before.items()}
    json.dump({"meta": meta, "groups": groups, "ridings": out, "dept_by_riding": dept_matrix,
               "dept_by_riding_before": dept_matrix_before, "recipients": recipient_table(per, lambda g: g["recipient"][:80])},
              open(OUT / "riding_spending.json", "w"), ensure_ascii=False)
    print(json.dumps({"meta": {k: v for k, v in meta.items() if k != "departments"}, "groups": groups}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
