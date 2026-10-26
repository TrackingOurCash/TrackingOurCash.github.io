"""British Columbia: aggregate provincial government transfers by electoral district.

Reads data/raw/bc/transfers-fye*.csv (Public Accounts, Consolidated Revenue Fund detailed
schedules of payments, "Government Transfers": every payee receiving $25,000 or more from a
ministry in a fiscal year) and data/bc/divisions.json (from bc_prep.py). Writes
data/bc/division_spending.json with the same shape as the Alberta file.

The schedules give NAME, MINISTRY and AMOUNT only: no address, no program, no date. So:
  * MINISTRY stands in for the program: the program labels (top_progs, programs,
    prog_by_riding, top_grants.prog) are ministry names, and top_grants.date is the fiscal
    year label "FY2025-26" since no payment dates exist.
  * Windows are whole fiscal years. The election was 19 October 2024, so "after" is the
    fiscal year ending 31 March 2026 (FYE2026, the latest published) and "before" is
    FYE2024 (1 April 2023 to 31 March 2024, the last full year before the election);
    years_per_window = 1.0. FYE2025 straddles the election and FYE2023 is older, so both
    are downloaded but not counted. The meta dates (election 2024-10-19, cutoff 2026-03-31,
    before_start 2023-04-01, before_end 2024-03-31) describe those windows.
  * Amounts are quoted with commas; negatives are in parentheses and "-" means nil; these
    and the FYE2024 file's trailing empty columns are handled on read. Payments <= 0 skip.

Each payment is placed by the recipient's name, in this order (as ab_spending.py does):
  1. the same name in the federal grants file, data/name_postal.json ("BC|name" keys);
  2. the CRA list of registered charities with Province BC (name -> postal code);
  3. a municipality name ("City of X", "District of X", "Village of X", "Town of X",
     "Township of X", "Resort Municipality of X", "Corporation of the City of X") or a
     First Nation / band name ("X First Nation", "X Indian Band", "X Nation") -> the
     GeoNames centroid of the place with that name, when one exists;
  4. a place name inside the recipient's name ("Nanaimo Family Life Association").
Postal codes and place names come from GeoNames CA_full.txt (province BC) and are located
by point-in-polygon on the 2023 boundaries in data/bc/divisions_geo.json. A few GeoNames
names that are also ordinary words or regions ("Fraser", "Canoe", "Panorama", "Golden",
"Hope") are not used as place-name hits. PLACE_ALIASES gives hand-set coordinates for the
larger bands and municipalities GeoNames lacks (Carrier Sekani -> Prince George, North
Cowichan -> Duncan, Metchosin, Highlands, Spallumcheen, ...); those are approximate.

Excluded before placing:
  * "individual programs": the schedules' aggregate lines for payments to people (Medical
    Services Plan claims, PharmaCare, income assistance, the child day care program, the
    seniors supplement, youth agreements, foster home program, victim payments);
  * "individuals": payees written "SURNAME, GIVEN NAMES" (foster parents, students, care
    providers). The public accounts list people in that form, so unlike Alberta no
    short-name guess is needed and none is made;
  * "province-wide bodies": health authorities, universities and colleges, school districts,
    BC Housing, Community Living BC, BC Transit, TransLink (South Coast BC Transportation
    Authority), BC Hydro, ICBC, BC Ferries and other Crown corporations, "Province of" /
    "Ministry of" / other governments, regional districts (their money is spread across
    their member municipalities), and bodies named "... British Columbia" or "BC ...".
    These are flagged "province-wide" when they can be placed (so they show in the
    district's top recipients) and counted as excluded when they cannot, exactly as the
    Alberta script does. City governments (20+ postal codes) whose postal codes fall
    materially (over 15% of them) in more than one district (Vancouver, Surrey, Burnaby, ...) are flagged
    "other government".

Groups: "Close NDP", "Close BCC", "Safe NDP", "Safe BCC"; gov_won means the BC NDP (the
governing party) won the seat in 2024; close means a margin under 10 points.
"""
import csv
import json
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "bc"
sys.path.insert(0, str(ROOT / "scripts"))
from geo import RidingIndex, load_centroids  # noqa: E402

ELECTION = date(2024, 10, 19)
CUTOFF = date(2026, 3, 31)
BEFORE_START, BEFORE_END = date(2023, 4, 1), date(2024, 3, 31)
WINDOWS = {2026: "after", 2024: "before"}  # fiscal year ending -> window
YEARS = 1.0
CLOSE_MARGIN = 10.0
GOV_PARTY = "NDP"

INDIVIDUAL_PROGRAMS = re.compile(
    r"^(HS|HR|CF|FC|AG) [A-Z]|MEDICAL SERVICES PLAN|PHARMACARE|INCOME ASSISTANCE|CHILD DAY CARE PROGRAM|"
    r"SENIORS SUPPLEMENT|YOUTH( / YOUNG ADULT)? AGREEMENTS|FOSTER HOME PROGRAM|VICTIM & PROVIDER PAYMENTS|"
    r"MATERNITY BENEFIT PROGRAM|REBATE PROGRAM|DISASTER EVACUEES|RECOVERY BENEFIT|UNALLOCATED SUPPLIER CREDITS",
    re.I)
# "SURNAME, GIVEN NAMES" (one to three words each side, no corporate word): a person.
PERSON = re.compile(r"^[A-Z'\-]+( [A-Z'\-]+){0,2}, [A-Z'\-.]+( [A-Z'\-.]+){0,3}$")
NOT_PERSON = re.compile(r"\b(INC|LTD|LLP|LLC|LP|SCHOOL|SOCIETY|ASSOCIATION|ASSN|CLUB|CHURCH|CENTRE|CENTER|SERVICES?|NATION|BAND|"
                        r"COUNCIL|GROUP|CO|FARMS?|RANCH|CORP|TRUST|CITY|DISTRICT|DIVISION|DAYCARE|CARE|B\.?C\.?|BRITISH COLUMBIA|"
                        r"COLUMBIA|CANADA|CANADIAN|FOUNDATION|INSTITUTE|HOUSE|HOME|PROGRAM|FUND|OFFICE|CONGREGATION|PORT)\b")
# GeoNames place names that are also ordinary words or regions: never a place hit.
AMBIGUOUS = {"FRASER", "CANOE", "PANORAMA", "GOLDEN", "HOPE", "FIELD", "VILLAGE", "ISLAND", "CENTRAL"}
# (lat, lon) for bands and municipalities GeoNames has no entry for; keys are normalised names.
PLACE_ALIASES = {
    "CARRIER SEKANI": (53.917, -122.750), "NORTH COWICHAN": (48.823, -123.716), "METCHOSIN": (48.382, -123.536),
    "HIGHLANDS": (48.520, -123.490), "SPALLUMCHEEN": (50.448, -119.196), "DAAJING GIIDS": (53.254, -132.073),
    "MOWACHAHT MUCHALAHT": (49.780, -126.050), "LITTLE SHUSWAP": (50.820, -119.685), "FORT WARE": (57.430, -125.635),
    "KWADACHA": (57.430, -125.635), "KLUSKUS": (52.930, -124.130), "KLAHOOSE": (50.080, -124.830),
    "STK EMLUPSEMC SHUSWAP": (50.700, -120.300), "NEE TAHI BUHN": (54.090, -125.650), "ALEXANDRIA": (52.630, -122.450),
    "PETERS": (49.350, -121.600), "BINCHE WHUT EN": (54.720, -124.700), "UNION BAR": (49.400, -121.420),
    "TLATLASIKWALA": (50.850, -127.650), "AITCHELITZ": (49.130, -122.000), "SCOWLITZ": (49.230, -122.040),
    "SKWAY": (49.160, -121.980), "SETON LAKE": (50.680, -122.020),
}
PROVINCEWIDE = re.compile(
    r"HEALTH AUTHORITY|PROVINCIAL HEALTH SERVICES|HEALTH EMPLOYERS|CANADIAN BLOOD SERVICES|LIFELABS|"
    r"DOCTORS OF BC|MEDICAL ASSOCIATION|NURSES' UNION|BC CANCER|CENTRE FOR DISEASE CONTROL|HEALTH BENEFITS SOCIETY|"
    r"PACIFIC BLUE CROSS|HEALTH EMPLOYERS|CANADIAN MENTAL HEALTH ASSOCIATION, B|\bINBC\b|"
    r"BRITISH COLUMBIA HOUSING|BC HOUSING|COMMUNITY LIVING BRITISH COLUMBIA|COMMUNITY LIVING BC|"
    r"TRANSPORTATION AUTHORITY|TRANSLINK|B ?C TRANSIT|TRANSPORTATION FINANCING|BC FERR|FERRY SERVICES|"
    r"HYDRO AND POWER|BC HYDRO|INSURANCE CORPORATION OF B|\bICBC\b|WORKSAFE|BC ASSESSMENT|LOTTERY CORP|"
    r"PAVILION CORP|KNOWLEDGE NETWORK|ROYAL BRITISH COLUMBIA MUSEUM|DESTINATION B|INNOVATE BC|"
    r"FORESTRY INNOVATION|INFRASTRUCTURE BENEFITS|ENERGY REGULATOR|OIL AND GAS COMMISSION|"
    r"UNIVERSITY|COLLEGE$|COLLEGE\b|INSTITUTE OF TECHNOLOGY|POLYTECHNIC|JUSTICE INSTITUTE|SKILLEDTRADES|"
    r"SCHOOL DISTRICT|BOARD OF EDUCATION|CONSEIL SCOLAIRE|CATHOLIC INDEPENDENT SCHOOLS|SOCIETY OF CHRISTIAN SCHOOLS|"
    r"INDEPENDENT SCHOOLS|PUBLIC EDUCATION BENEFITS TRUST|"
    r"REGIONAL DISTRICT|METRO VANCOUVER|GREATER VANCOUVER (REGIONAL|SEWERAGE|WATER)|CAPITAL REGIONAL|"
    r"\bPROVINCE OF\b|\bMINISTRY OF\b|\bMINISTER OF\b|\bGOVERNMENT OF\b|RECEIVER GENERAL|HEALTH CARE INSURANCE PLAN|"
    r"UNION OF BRITISH COLUMBIA MUNICIPALITIES|UNION OF BC MUNICIPALITIES|\bUBCM\b|LEGAL SERVICES SOCIETY|LEGAL AID BC|"
    r"NEW RELATIONSHIP TRUST|FIRST NATIONS (HEALTH|SUMMIT|LEADERSHIP|TECHNOLOGY|JUSTICE|EDUCATION|PUBLIC SERVICE|FINANCE)|"
    r"FIRST PEOPLES' (HERITAGE|CULTURAL)|METIS (NATION|PROVINCIAL COUNCIL)|DEVELOPMENT INITIATIVE TRUST|"
    r"UNITED WAY BRITISH COLUMBIA|UNITED WAY BC|YMCA BC|YWCA (BRITISH COLUMBIA|BC)|GENOME BRITISH COLUMBIA|"
    r"BRITISH COLUMBIA$|\bB\.? ?C\.?$|COLOMBIE.BRITANNIQUE|"
    r"(BRITISH COLUMBIA|\bBC|\bB\.C\.) (ASSOCIATION|COUNCIL|FOUNDATION|SOCIETY|FEDERATION|CONFERENCE|CENTRE|INSTITUTE|NETWORK|ALLIANCE|COALITION|TRUST)|"
    r"^(BRITISH COLUMBIA|BC|B\.C\.) |OF (BRITISH COLUMBIA|B\.?C\.?)$|\(BRITISH COLUMBIA\)|PROVINCIAL (ASSOCIATION|COUNCIL|NETWORK)",
    re.I)
MUNI = re.compile(r"^(?:CORPORATION (?:OF )?)?(CITY|TOWN|VILLAGE|DISTRICT|TOWNSHIP|DISTRICT MUNICIPALITY|RESORT MUNICIPALITY|"
                  r"MOUNTAIN RESORT MUNICIPALITY|ISLAND MUNICIPALITY|REGIONAL MUNICIPALITY|MUNICIPALITY) (OF )?(.+?)"
                  r"( PUBLIC LIBRARY.*| LIBRARY.*| FIRE.*| POLICE.*)?$")
MUNI2 = re.compile(r"^(.+?) (FIRST NATIONS?|INDIAN BAND|BAND|NATION|TRIBAL COUNCIL|TRIBES)$")


def upper(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(THE|OF|INC|LTD|LIMITED|CORP|CORPORATION|SOCIETY|ASSOCIATION|ASSN|FOUNDATION)\b", " ", s)
    s = re.sub(r"\b(NO|NUMBER)\s*\d+\b|#\s*\d+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def amount(s):
    """' 1,234.00 ' -> 1234.0; '(265.00)' -> -265.0; '-' -> 0."""
    s = (s or "").strip().replace(",", "").replace("$", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    if s in ("", "-"):
        return 0.0
    return -float(s) if neg else float(s)


def read_rows():
    rows = []
    for path in sorted(RAW.glob("bc/transfers-fye*.csv")):
        fye = int(re.search(r"fye(\d{4})", path.name).group(1))
        raw = open(path, "rb").read()
        try:
            txt = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            txt = raw.decode("cp1252")
        lines = list(csv.reader(txt.splitlines()))
        header = next(i for i, r in enumerate(lines) if r and r[0].strip() == "NAME")
        for r in lines[header + 1:]:
            if len(r) >= 3 and r[0].strip():
                rows.append({"Recipient": r[0].strip(), "Ministry": r[1].strip(), "Amount": amount(r[2]), "fye": fye})
    return rows


def main():
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()

    # Name -> postal code sources.
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("BC|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "BC":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[4] == "BC":
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
        if key in PLACE_ALIASES:
            return index.locate(*PLACE_ALIASES[key])[0]
        pts = places.get(key)
        if not pts:
            return None
        return index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))[0]

    def muni_key(n):
        m = MUNI.match(n)
        if m:
            return m.group(3)
        m = MUNI2.match(n)
        return m.group(1) if m else None

    def place(name):
        """-> (district code or None, method)."""
        n = norm(name)
        if n in loc_cache:
            return loc_cache[n]
        res = (None, "unmatched")
        if not n or "WITHHELD" in n or "PRIVACY" in n:
            res = (None, "withheld")
        elif PERSON.match(upper(name)) and not NOT_PERSON.search(upper(name)):
            res = (None, "individual")
        elif n in name_pc and locate_pc(name_pc[n]):
            res = (locate_pc(name_pc[n]), "postal code from federal or charity records")
        else:
            key = muni_key(n)
            if key:
                d = locate_place(key)
                if d:
                    res = (d, "municipality")
            if res[0] is None and not re.search(r"\bBRITISH COLUMBIA\b|\bB C\b|\bBC\b|\bCANADA\b", n):
                for p in place_names:
                    if p not in AMBIGUOUS and f" {p} " in f" {n} ":
                        d = locate_place(p)
                        if d:
                            res = (d, "place name in recipient (approx.)")
                            break
        loc_cache[n] = res
        return res

    def spans_districts(key, limit=60):
        """True when a city (20+ postal codes) has over 15% of its postal-code points outside
        its main district. Villages with a handful of coarse rural centroids never count."""
        pts = places.get(key) or []
        if len(pts) < 20:
            return False
        step = max(1, len(pts) // limit)
        hits = Counter(index.locate(*p)[0] for p in pts[::step])
        hits.pop(None, None)
        return bool(hits) and hits.most_common(1)[0][1] < 0.85 * sum(hits.values())

    multi_division = {}

    def flag_for(name, how):
        """Why a placed payment is left out of the adjusted totals, or ""."""
        u = upper(name)
        if PROVINCEWIDE.search(u):
            return "province-wide"
        n = norm(name)
        if MUNI.match(n):
            key = MUNI.match(n).group(3)
            if key not in multi_division:
                multi_division[key] = spans_districts(key)
            if multi_division[key]:
                return "other government"  # a city spread over several districts
        return ""

    rows = read_rows()
    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": []} for num in divisions}
    method_counts = Counter()
    excluded = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    for r in rows:
        v = r["Amount"]
        window = WINDOWS.get(r["fye"])
        if v <= 0 or not window:
            continue
        program = r["Ministry"]
        if INDIVIDUAL_PROGRAMS.search(r["Recipient"]):
            excluded[(window, "individual programs")] += v
            continue
        num, how = place(r["Recipient"])
        if how == "withheld":
            excluded[(window, "withheld")] += v
            continue
        if how == "individual":
            excluded[(window, "individuals")] += v
            continue
        if num is None:
            # Province-wide bodies with no match still don't belong to any one district.
            kind = "province-wide bodies" if PROVINCEWIDE.search(upper(r["Recipient"])) else "unmatched"
            excluded[(window, kind)] += v
            if window == "after" and kind == "unmatched":
                unmatched[r["Recipient"]] += v
            continue
        flag = flag_for(r["Recipient"], how)
        method_counts[(window, how)] += 1
        p = per[num]
        p[window]["total"] += v
        p[window]["n"] += 1
        if not flag:
            p[window]["adj"] += v
            p[window]["adj_n"] += 1
        else:
            flagged_total[(window, r["Recipient"])] += v
        if window == "after":
            label = program.title()
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
        by_recipient = defaultdict(lambda: {"v": 0.0, "n": 0, "progs": Counter(), "flag": "", "how": "", "last": ""})
        for v, r, fl, how in p["grants"]:
            g = by_recipient[r["Recipient"]]
            g["v"] += v
            g["n"] += 1
            g["progs"][r["Ministry"].title()] += v
            g["flag"], g["how"], g["last"] = fl, how, "FY2025-26"
        top = sorted(by_recipient.items(), key=lambda kv: -kv[1]["v"])[:10]
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"], "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]),
            "pc_after": round(a["adj"] / pop / YEARS, 2), "pc_after_all": round(a["total"] / pop / YEARS, 2),
            "pc_before": round(b["adj"] / pop / YEARS, 2),
            "close": dv["margin_pts"] < CLOSE_MARGIN,
            "gov_won": dv["party_2024"] == GOV_PARTY,
            "top_progs": [[k, round(v)] for k, v in p["progs"].most_common(4)],
            "top_grants": [{"v": round(g["v"]), "who": who[:80], "n": g["n"], "prog": "; ".join(k for k, _ in g["progs"].most_common(2))[:120],
                            "date": g["last"], "flag": g["flag"], "how": g["how"]} for who, g in top],
        })
        rec["change_pct"] = round(100 * (a["adj"] - b["adj"]) / b["adj"], 1) if b["adj"] > 0 else None
        out[num] = rec
    med = statistics.median(x["pc_after"] for x in out.values())
    for x in out.values():
        x["score"] = round(x["pc_after"] / med, 2) if med else None
        x["group"] = ("Close" if x["close"] else "Safe") + (" NDP" if x["gov_won"] else " BCC")
    groups = {}
    for g in ["Close NDP", "Close BCC", "Safe NDP", "Safe BCC"]:
        xs = [x for x in out.values() if x["group"] == g]
        chg = [x["change_pct"] for x in xs if x["change_pct"] is not None]
        groups[g] = {"ridings": len(xs), "median_pc_after": round(statistics.median(x["pc_after"] for x in xs), 2) if xs else None,
                     "median_pc_before": round(statistics.median(x["pc_before"] for x in xs), 2) if xs else None,
                     "median_change_pct": round(statistics.median(chg), 1) if chg else None,
                     "total_adj_after": round(sum(x["after_adj"] for x in xs))}
    total_after = sum(v for (w, _), v in excluded.items() if w == "after") + sum(x["after_total"] for x in out.values())
    meta = {
        "generated": date.today().isoformat(), "election": ELECTION.isoformat(), "cutoff": CUTOFF.isoformat(),
        "before_start": BEFORE_START.isoformat(), "before_end": BEFORE_END.isoformat(), "years_per_window": YEARS,
        "windows": "after = fiscal year ending 31 March 2026 (FYE2026); before = FYE2024, the last full fiscal year before the 19 October 2024 election; annual data, no payment dates",
        "close_margin": CLOSE_MARGIN, "median_pc_after": med,
        "methods": {f"{w}|{m}": v for (w, m), v in method_counts.items()},
        "excluded_after": {m: round(v) for (w, m), v in excluded.items() if w == "after"},
        "placed_after": round(sum(x["after_total"] for x in out.values())),
        "total_after": round(total_after),
        "top_flagged": [[k, round(v)] for (w, k), v in sorted(flagged_total.items(), key=lambda kv: -kv[1]) if w == "after"][:20],
        "top_unmatched": [[k, round(v)] for k, v in unmatched.most_common(40)],
        "programs": sorted(prog_totals, key=lambda d: -sum(prog_totals[d].values()))[:60],
    }
    json.dump({"meta": meta, "groups": groups, "ridings": out,
               "prog_by_riding": {k: {n: round(v) for n, v in m.items()} for k, m in prog_totals.items() if k in meta["programs"]}},
              open(OUT / "division_spending.json", "w"), ensure_ascii=False)
    print(json.dumps({k: v for k, v in meta.items() if k not in ("programs",)}, indent=1, ensure_ascii=False))
    print(json.dumps(groups, indent=1))


if __name__ == "__main__":
    main()
