"""Alberta: aggregate provincial grant payments by electoral division.

Reads data/raw/ab/grants-*.csv (Treasury Board and Finance grant payments disclosure)
and data/ab/divisions.json (from ab_prep.py). Writes data/ab/division_spending.json.

Alberta publishes recipient name, program, amount and date, but no address. Each
payment is placed by matching the recipient's name, in this order:
  1. the same name in the federal grants file (which carries postal codes);
  2. the CRA list of registered charities (name -> postal code);
  3. a municipality name ("Town of X", "X County") -> that place's centroid;
  4. a place name inside the recipient's name ("Red Deer Public Library");
  5. an explicit list of province-wide bodies (health, post-secondary, agencies)
     and school divisions, placed at their head office but flagged.
Postal codes and place centroids come from GeoNames and are located in a division
by point-in-polygon on the 2019 boundaries.

Programs that pay individuals (physician fee-for-service, AISH, income support,
seniors' benefits, awards) are excluded: the recipients are people, not places.
Province-wide bodies (health, post-secondary, school divisions, agencies) and the
governments of cities that span several divisions are flagged, like national HQs in
the federal map, so the adjusted totals show grants to local recipients.

Windows: "after" runs from the day after the 29 May 2023 election to the latest
payment date; "before" is the same number of days ending on election day.
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

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "ab"
sys.path.insert(0, str(ROOT / "scripts"))
from geo import RidingIndex, load_centroids
from build_spending import recipient_table, formula_matcher  # noqa: E402

ELECTION = date(2023, 5, 29)
CLOSE_MARGIN = 10.0
# open.alberta.ca "Grant payments disclosure": one CSV resource per fiscal year. The alberta.ca
# disclosure table has no recipient deep link (its search form posts), so top_grants.src is the
# resource page of the year of the recipient's largest payment.
RESOURCES = {
    "2020-21": "ef6f0f85-7f5e-449e-8a54-3d45e37f3dc4", "2021-22": "bda2903e-8106-47be-824e-2b22636c8a05",
    "2022-23": "a9a92ce7-c005-418d-a411-b663254c601a", "2023-24": "0c7e93c1-1c28-460d-92eb-f6934e9ba4a8",
    "2024-25": "f4197a5a-b3c3-4045-b2ce-7f77d700935f", "2025-26": "1e95ba75-b4b1-44df-9426-988d60b6cff7",
}
DATASET_URL = "https://open.alberta.ca/dataset/grant-disclosure"
SEARCH_URL = "https://duckduckgo.com/?q={q}+Alberta+grant"  # {q}: the recipient, URL-encoded by the page


def source_url(r):
    """The disclosure CSV's page for the fiscal year of the payment (the dataset page when the year is not listed)."""
    d = r["date"]
    start = d.year if d.month >= 4 else d.year - 1
    rid = RESOURCES.get(f"{start}-{str(start + 1)[2:]}")
    return f"{DATASET_URL}/resource/{rid}" if rid else DATASET_URL

INDIVIDUAL_PROGRAMS = re.compile(
    r"FFS|FEE.FOR.SERVICE|PHYSICIAN|AISH|INCOME SUPPORT|SENIORS? (DRUG )?BENEFIT|SENIORS BENEFIT|ALBERTA SENIORS|"
    r"AWARDS?( AND MEDALS)?|SCHOLARSHIP|BURSAR|STUDENT (AID|GRANT|LOAN)|CHILD CARE SUBSIDY|AFFORDABILITY|"
    r"DISASTER RECOVERY|EVACU|FOSTER|KINSHIP|ADOPTION|CAREGIVER|PDD INDIVIDUAL|FSCD|SPECIAL NEEDS ASSIST|"
    r"EMPLOYMENT AND TRAINING|SKILLS DEVELOPMENT|RELIEF|BLUE CROSS|DRUG|DENTAL|OPTICAL|HEALTH BENEFIT|"
    r"MEDICAL (ASSOC|BENEFIT)|ALLIED HEALTH|FARM FUEL|AGRISTABILITY|AGRIINSURANCE|AGRIINVEST|CROP INSURANCE",
    re.I)
PROVINCEWIDE = re.compile(
    r"ALBERTA HEALTH SERVICES|ACUTE CARE ALBERTA|RECOVERY ALBERTA|PRIMARY CARE ALBERTA|ASSISTED LIVING ALBERTA|"
    r"ALBERTA BLUE CROSS|AGRICULTURE FINANCIAL SERVICES|ALBERTA INNOVATES|TRAVEL ALBERTA|CANADIAN BLOOD SERVICES|"
    r"LEGAL AID SOCIETY|ALBERTA MEDICAL ASSOCIATION|CLIMATE CHANGE AND EMISSIONS|ALBERTA LAW ENFORCEMENT|"
    r"COVENANT HEALTH|ALBERTA GAMING|ALBERTA PENSIONS|ALBERTA TEACHERS|ALBERTA SCHOOL|ALBERTA MUNICIPALITIES|"
    r"RURAL MUNICIPALITIES OF ALBERTA|ALBERTA ENERGY REGULATOR|CARBON|HEARTLAND PETROCHEMICAL|"
    r"UNIVERSITY OF (ALBERTA|CALGARY|LETHBRIDGE)|MACEWAN UNIVERSITY|MOUNT ROYAL UNIVERSITY|ATHABASCA UNIVERSITY|"
    r"INSTITUTE OF TECHNOLOGY|POLYTECHNIC|COLLEGE$|SCHOOL DIVISION|SCHOOL DISTRICT|REGIONAL DIVISION|"
    r"CATHOLIC SEPARATE|FRANCOPHONE EDUCATION|CONSEIL SCOLAIRE|CHARTER (SCHOOL|ACADEMY)|PUBLIC SCHOOLS?$|"
    r"ALBERTA$|ALBERTA (ASSOCIATION|COUNCIL|FOUNDATION|SOCIETY|FEDERATION)",
    re.I)
MUNI = re.compile(r"^(CITY|TOWN|VILLAGE|SUMMER VILLAGE|MUNICIPAL DISTRICT|MD|COUNTY|MUNICIPALITY|REGIONAL MUNICIPALITY|"
                  r"SPECIALIZED MUNICIPALITY|IMPROVEMENT DISTRICT) (OF )?(.+?)( NO \d+| \d+)?( FINANCE.*| LIBRARY.*| TREASURY.*)?$")
MUNI2 = re.compile(r"^(.+?) (COUNTY|MUNICIPAL DISTRICT)( NO \d+| \d+)?$")


def upper(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(THE|OF|INC|LTD|LIMITED|CORP|CORPORATION|SOCIETY|ASSOCIATION|ASSN|FOUNDATION)\b", " ", s)
    # "Rocky View School Division No 41", "#75", "Secretary Treasurer" suffixes all name the same body.
    s = re.sub(r"\b(NO|NUMBER)\s*\d+\b|#\s*\d+|\bSECRETARY TREASURER\b|\bFINANCE BRANCH.*|\bTREASURY SECTION\b|\bREGIONAL DIVISION\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def parse_date(s):
    """Older files use M/D/YYYY, newer ones ISO."""
    s = (s or "").strip()[:10]
    if not s:
        return None
    if "/" in s:
        m, d, y = s.split("/")
        return date(int(y), int(m), int(d))
    return date.fromisoformat(s)


def read_rows():
    rows = []
    for path in sorted(RAW.glob("ab/grants-*.csv")):
        raw = open(path, "rb").read()
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = raw.decode("cp1252")
        for r in csv.DictReader(txt.splitlines()):
            r["date"] = parse_date(r["PaymentDate"])
            rows.append(r)
    return rows


def main():
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()

    # Name -> postal code sources.
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("AB|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "AB":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[4] == "AB":
                try:
                    places[norm(r[2])].append((float(r[9]), float(r[10])))
                except ValueError:
                    pass
    place_names = sorted((p for p in places if len(p) >= 5), key=len, reverse=True)

    loc_cache = {}

    def locate_pc(pc):
        if pc in centroids:
            return index.locate(*centroids[pc])[0]
        return None

    def locate_place(key):
        pts = places.get(key)
        if not pts:
            return None
        return index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))[0]

    def place(name):
        """-> (division number or None, method)."""
        n = norm(name)
        if n in loc_cache:
            return loc_cache[n]
        res = (None, "unmatched")
        if not n or "WITHHELD" in n or "PRIVACY" in n:
            res = (None, "withheld")
        elif n in name_pc and locate_pc(name_pc[n]):
            res = (locate_pc(name_pc[n]), "postal code from federal or charity records")
        else:
            m = MUNI.match(n) or MUNI2.match(n)
            if m:
                key = m.group(3) if m.re is MUNI else m.group(1)
                d = locate_place(key)
                if d:
                    res = (d, "municipality")
            if res[0] is None and not re.search(r"\bALBERTA\b|\bCANADA\b", n):
                for p in place_names:
                    if f" {p} " in f" {n} ":
                        d = locate_place(p)
                        if d:
                            res = (d, "place name in recipient (approx.)")
                            break
            if res[0] is None and len(n.split()) <= 3 and not re.search(
                    r"\b(INC|LTD|SCHOOL|DIVISION|SOCIETY|CLUB|CHURCH|CENTRE|SERVICES|NATION|BAND|COUNCIL|GROUP|CO|FARMS|RANCH|CORP)\b", n):
                res = (None, "individual")
        loc_cache[n] = res
        return res

    def divisions_of_place(key, limit=60):
        pts = places.get(key) or []
        step = max(1, len(pts) // limit)
        return {index.locate(*p)[0] for p in pts[::step]} - {None}

    multi_division = {}

    def flag_for(name, how):
        """Why a placed payment is left out of the adjusted totals, or ""."""
        u = upper(name)
        if PROVINCEWIDE.search(u):
            return "province-wide"
        n = norm(name)
        m = MUNI.match(n) or MUNI2.match(n)
        if m:
            key = m.group(3) if m.re is MUNI else m.group(1)
            if key not in multi_division:
                multi_division[key] = len(divisions_of_place(key)) > 1
            if multi_division[key]:
                return "other government"  # a city spread over several divisions
        return ""

    rows = read_rows()
    cutoff = max(r["date"] for r in rows if r["date"])
    span = (cutoff - ELECTION).days
    before_start = ELECTION - timedelta(days=span)
    years = span / 365.25

    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": [], "series": Counter()} for num in divisions}
    is_formula = formula_matcher("alberta")
    quarters = sorted({(r["date"].year, (r["date"].month - 1) // 3) for r in rows if r["date"]})
    quarters = [q for q in quarters if q <= (date.today().year, (date.today().month - 1) // 3)]  # a few agreements carry start dates in the future
    qlabel = lambda q: f"{q[0]}Q{q[1] + 1}"
    method_counts = Counter()
    excluded = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    for r in rows:
        v = float(r["Amount"] or 0)
        if v <= 0 or not r["date"]:
            continue
        d = r["date"]
        if before_start <= d <= ELECTION:
            window = "before"
        elif ELECTION < d <= cutoff:
            window = "after"
        else:
            window = None  # outside both windows, but still part of the quarterly series
        program = r["Program"]
        if INDIVIDUAL_PROGRAMS.search(program):
            if window:
                excluded[(window, "individual programs")] += v
            continue
        num, how = place(r["Recipient"])
        if how == "withheld":
            if window:
                excluded[(window, "withheld")] += v
            continue
        if how == "individual":
            if window:
                excluded[(window, "individuals")] += v
            continue
        if num is None:
            # Province-wide bodies with no match still don't belong to any one division.
            kind = "province-wide bodies" if PROVINCEWIDE.search(upper(r["Recipient"])) else "unmatched"
            if window:
                excluded[(window, kind)] += v
            if window == "after" and kind == "unmatched":
                unmatched[r["Recipient"]] += v
            continue
        flag = flag_for(r["Recipient"], how)
        if not flag:
            per[num]["series"][qlabel((d.year, (d.month - 1) // 3))] += v
        if not window:
            continue
        method_counts[(window, how)] += 1
        p = per[num]
        p[window]["total"] += v
        p[window]["n"] += 1
        label = f'{r["Ministry"].title()}: {program.title()}'
        r["formula"] = bool(is_formula(label))
        if not flag:
            p[window]["adj"] += v
            p[window]["adj_n"] += 1
            if r["formula"]:
                p[window]["formula"] += v
        else:
            flagged_total[(window, r["Recipient"])] += v
        if window == "after":
            p["progs"][label] += v
            if not flag:
                prog_totals[label][num] += v
            p["grants"].append((v, r, flag, how))

    out = {}
    for num, dv in divisions.items():
        p = per[num]
        pop = dv["population"] or 1
        a, b = p["after"], p["before"]
        rec = dict(dv)
        # Group the largest recipients rather than listing every payment.
        by_recipient = defaultdict(lambda: {"v": 0.0, "n": 0, "progs": Counter(), "flag": "", "how": "", "last": "", "formula": False, "src_v": 0.0, "src": None})
        for v, r, fl, how in p["grants"]:
            g = by_recipient[r["Recipient"]]
            g["v"] += v
            g["n"] += 1
            if v > g["src_v"]:  # the link points at the recipient's largest row
                g["src_v"], g["src"] = v, source_url(r)
            g["formula"] = g["formula"] or bool(r.get("formula"))
            g["progs"][f'{r["Program"].title()} ({r["Ministry"].title()})'] += v
            g["flag"], g["how"], g["last"] = fl, how, max(g["last"], r["date"].isoformat())
        top = sorted(by_recipient.items(), key=lambda kv: -kv[1]["v"])[:10]
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"], "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]), "after_formula": round(a["formula"]), "before_formula": round(b["formula"]),
            "pc_after": round(a["adj"] / pop / years, 2), "pc_after_all": round(a["total"] / pop / years, 2),
            "pc_before": round(b["adj"] / pop / years, 2),
            "close": dv["margin_pts"] < CLOSE_MARGIN,
            "gov_won": dv["party_2023"] == "UCP",
            "top_progs": [[k, round(v)] for k, v in p["progs"].most_common(4)],
            "top_grants": [{"v": round(g["v"]), "who": who[:80], "n": g["n"], "prog": "; ".join(k for k, _ in g["progs"].most_common(2))[:120],
                            "date": g["last"], "flag": g["flag"], "how": g["how"], "formula": g["formula"],
                            **({"src": g["src"]} if g["src"] else {})} for who, g in top],
        })
        rec["change_pct"] = round(100 * (a["adj"] - b["adj"]) / b["adj"], 1) if b["adj"] > 0 else None
        rec["series"] = [round(p["series"].get(qlabel(q), 0)) for q in quarters]
        out[num] = rec
    med = statistics.median(x["pc_after"] for x in out.values())
    for x in out.values():
        x["score"] = round(x["pc_after"] / med, 2) if med else None
        x["group"] = ("Close" if x["close"] else "Safe") + (" UCP" if x["gov_won"] else " NDP")
    groups = {}
    for g in ["Close UCP", "Close NDP", "Safe UCP", "Safe NDP"]:
        xs = [x for x in out.values() if x["group"] == g]
        chg = [x["change_pct"] for x in xs if x["change_pct"] is not None]
        groups[g] = {"ridings": len(xs), "median_pc_after": round(statistics.median(x["pc_after"] for x in xs), 2) if xs else None,
                     "median_pc_before": round(statistics.median(x["pc_before"] for x in xs), 2) if xs else None,
                     "median_change_pct": round(statistics.median(chg), 1) if chg else None,
                     "total_adj_after": round(sum(x["after_adj"] for x in xs))}
    total_after = sum(v for (w, _), v in excluded.items() if w == "after") + sum(x["after_total"] for x in out.values())
    meta = {
        "generated": date.today().isoformat(), "election": ELECTION.isoformat(), "cutoff": cutoff.isoformat(),
        "before_start": before_start.isoformat(), "before_end": ELECTION.isoformat(), "years_per_window": round(years, 3),
        "close_margin": CLOSE_MARGIN, "median_pc_after": med,
        "search_url": SEARCH_URL,
        "methods": {f"{w}|{m}": v for (w, m), v in method_counts.items()},
        "excluded_after": {m: round(v) for (w, m), v in excluded.items() if w == "after"},
        "placed_after": round(sum(x["after_total"] for x in out.values())),
        "total_after": round(total_after),
        "series": {"kind": "quarter", "labels": [qlabel(q) for q in quarters], "complete": sum(1 for q in quarters if date(q[0], q[1] * 3 + 1, 1) <= cutoff),
                   "election_index": sum(1 for q in quarters if date(q[0], q[1] * 3 + 1, 1) <= ELECTION) - 1},
        "top_flagged": [[k, round(v)] for (w, k), v in sorted(flagged_total.items(), key=lambda kv: -kv[1]) if w == "after"][:20],
        "top_unmatched": [[k, round(v)] for k, v in unmatched.most_common(40)],
        "programs": sorted(prog_totals, key=lambda d: -sum(prog_totals[d].values()))[:60],
    }
    json.dump({"meta": meta, "groups": groups, "ridings": out, "recipients": recipient_table(per, lambda g: g["Recipient"][:80]),
               "prog_by_riding": {k: {n: round(v) for n, v in m.items()} for k, m in prog_totals.items() if k in meta["programs"]}},
              open(OUT / "division_spending.json", "w"), ensure_ascii=False)
    print(json.dumps({k: v for k, v in meta.items() if k not in ("programs",)}, indent=1, ensure_ascii=False))
    print(json.dumps(groups, indent=1))


if __name__ == "__main__":
    main()
