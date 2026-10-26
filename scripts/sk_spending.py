"""Saskatchewan: aggregate provincial transfers by constituency.

Reads the Public Accounts Volume 2 PDFs (data/raw/sk/dl/pa_vol2_<year>.pdf) and
data/sk/divisions.json (from sk_prep.py). Writes data/sk/division_spending.json and,
for inspection, data/raw/sk/transfers_<year>.csv with every parsed row.

Source. Saskatchewan has no open-data file of grant payments. Volume 2 of the Public
Accounts lists, per ministry (one chapter per vote), a "Transfers" section: transfer
expenses of $50,000 or more by program (14 pt heading), sub-program (12 pt heading) and
recipient (8 pt, ALL CAPS, dot leader, amount). sk_pdf.py turns each page into lines
(two columns, left then right); this script walks the lines with a small state
machine: a "(Vote N)" line opens a ministry chapter (N is mapped to the ministry name
through the Schedule of Expense by Object, which also gives each ministry's total
Operating + Capital Transfers for a coverage check); "Transfers" followed by "Listed
by program and recipient" opens the section; "Goods and Services", "Other Expenses",
"Capital Asset Acquisitions" or the next chapter closes it. Recipient names that wrap
over several lines are joined until the line that carries the amount. Lines whose
amount is garbled (two columns run together) are counted and skipped.

Years. 2024-25 is the latest Volume 2 (the publications centre's 2025-2026 category
said "Volume 2: Not available at this time" on 25 October 2026; the script re-checks
and uses a 2025-26 volume as "after" if one has appeared). With no 2025-26 volume:
"after" = 2024-25, which straddles the 28 October 2024 election (seven months before
it, five after), and "before" = 2023-24. years_per_window = 1.0. Transfers carry no
dates, so no finer split is possible.

Placing recipients (name only), as in ab_spending.py:
  1. the same name in the federal grants file (data/name_postal.json, "SK|" keys);
  2. the CRA list of registered charities with Province == SK (name -> postal code);
  3. a municipality name ("ABERDEEN, TOWN OF", "R.M. OF ABERDEEN NO. 373",
     "CITY OF X") -> that place's GeoNames centroid;
  4. a place name inside the recipient's name ("MELFORT AMBULANCE CARE");
located in a constituency by point-in-polygon on the 2022 boundaries (geo.RidingIndex).
Province-wide bodies (Saskatchewan Health Authority, Crown corporations, universities,
Sask Polytechnic, school divisions, government ministries, provincial associations)
are placed where their head office is but flagged "province-wide"; the governments of
Regina and Saskatoon, which span many constituencies, are flagged "other government".
Programs that pay individuals (student aid, income assistance, farm income programs,
physician and drug plan payments) are excluded, and recipients that look like a person
("SMITH, JOHN") are excluded as individuals. Rural municipalities whose name is not a
GeoNames place stay unmatched (listed in meta.top_unmatched).
"""
import csv
import json
import re
import statistics
import sys
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
SK = RAW / "sk"
DL = SK / "dl"
OUT = ROOT / "data" / "sk"
sys.path.insert(0, str(ROOT / "scripts"))
from geo import RidingIndex, load_centroids  # noqa: E402
from sk_pdf import pdf_pages  # noqa: E402

ELECTION = date(2024, 10, 28)
CLOSE_MARGIN = 10.0
GOV_PARTY = "SP"
VOLUMES = {
    "2023-24": "https://saskatchewan.ca/-/media/news-release-backgrounders/2024/oct/2023-24-public-accounts-volume-2.pdf",
    "2024-25": "https://www.saskatchewan.ca/-/media/news-release-backgrounders/2025/oct/2024-25-volume-2---5155.pdf",
}
PUBLICATIONS_CATEGORY = "https://publications.saskatchewan.ca/api/v1/categories/893"  # Public Accounts Documents

INDIVIDUAL_PROGRAMS = re.compile(
    r"STUDENT AID|SCHOLARSHIP|BURSAR|GRADUATE RETENTION|SASKATCHEWAN ASSISTANCE|INCOME SUPPORT|ASSURED INCOME|"
    r"SENIORS INCOME|PERSONAL CARE HOME BENEFIT|CHILD CARE SUBSID|FOSTER|KINSHIP|ADOPTION|EXTENDED FAMILY|"
    r"AGRISTABILITY|AGRIINVEST|CROP INSURANCE|AGRIINSURANCE|LIVESTOCK|FEED PROGRAM|WILDLIFE DAMAGE|"
    r"MEDICAL SERVICES|FEE.FOR.SERVICE|PHYSICIAN|DRUG PLAN|DENTAL|OPTOMETR|SUPPLEMENTARY HEALTH|"
    r"DISASTER ASSISTANCE|EVACU|AFFORDABILITY|TRAINING ALLOWANCE|APPRENTICESHIP TRAINING ALLOWANCE|"
    r"HOME REPAIR|SECONDARY SUITE|FIRST HOME|REFUNDABLE|TAX CREDIT",
    re.I)
PROVINCEWIDE = re.compile(
    r"SASKATCHEWAN HEALTH AUTHORITY|ATHABASCA HEALTH AUTHORITY|SASKATCHEWAN CANCER AGENCY|EHEALTH SASKATCHEWAN|"
    r"3SHEALTH|HEALTH SHARED SERVICES|CANADIAN BLOOD SERVICES|SASKPOWER|SASKTEL|SASKENERGY|SASKWATER|SASKBUILDS|"
    r"\bSGI\b|SASKATCHEWAN GOVERNMENT INSURANCE|SASKATCHEWAN HOUSING|SASKATCHEWAN CROP INSURANCE|"
    r"SASKATCHEWAN RESEARCH COUNCIL|INNOVATION SASKATCHEWAN|TOURISM SASKATCHEWAN|CREATIVE SASKATCHEWAN|"
    r"SASKATCHEWAN ARTS BOARD|SK ARTS|SASKATCHEWAN STUDENT AID|LEGAL AID|SASKATCHEWAN LIQUOR|"
    r"WATER SECURITY AGENCY|GLOBAL TRANSPORTATION HUB|SASKATCHEWAN PUBLIC SAFETY|SASKATCHEWAN APPRENTICESHIP|"
    r"UNIVERSITY OF (REGINA|SASKATCHEWAN)|FIRST NATIONS UNIVERSITY|SASKATCHEWAN POLYTECHNIC|"
    r"GABRIEL DUMONT INSTITUTE|DUMONT TECHNICAL INSTITUTE|SASKATCHEWAN INDIAN INSTITUTE|COLLEGE$|"
    r"SCHOOL DIVISION|BOARD OF EDUCATION|CONSEIL DES ECOLES|CONSEIL DES ÉCOLES|ECOLES FRANSASKOISES|"
    r"^GOVERNMENT OF|^MINISTRY OF|MINISTER OF FINANCE|^PROVINCE OF|GOVERNMENT OF CANADA|RECEIVER GENERAL|"
    r"SASKATCHEWAN URBAN MUNICIPALITIES|SASKATCHEWAN ASSOCIATION OF RURAL MUNICIPALITIES|\bSARM\b|\bSUMA\b|"
    r"FEDERATION OF SOVEREIGN|METIS NATION|SASKATCHEWAN TEACHERS|SASKATCHEWAN SCHOOL BOARDS|"
    r"SASKATCHEWAN MEDICAL ASSOCIATION|SASKATCHEWAN WORKERS|SASKATCHEWAN CHAMBER|"
    r"SASKATCHEWAN (ASSOCIATION|COUNCIL|FOUNDATION|SOCIETY|FEDERATION|ALLIANCE|NETWORK|INSTITUTE|ABILITIES)|"
    r"SASKATCHEWAN$|SASKATCHEWAN INC\.?$|SASKATCHEWAN LTD\.?$|"
    r"SUPERANNUATION|PENSION PLAN|\b(FUND|TRUST|ACCOUNT)$|^SASKATCHEWAN .*(CORPORATION|AGENCY|AUTHORITY|COMMISSION|BOARD|CENTRE)$|"
    r"SHOCK TRAUMA AIR RESCUE|\bSTARS\b|HEALTH QUALITY COUNCIL|HEALTHCARE RECRUITMENT|PROVINCIAL ARCHIVES|DISTANCE LEARNING|"
    r"TRADE . EXPORT PARTNERSHIP|CANADA MORTGAGE|SUN LIFE|GREAT.WEST LIFE|MANULIFE|CANADA LIFE|BLUE CROSS|"
    r"PROVINCIAL CAPITAL COMMISSION|^WORKERS. COMPENSATION|^GOVERNMENT OF|^PROVINCE OF|^MINISTER OF",
    re.I)
PERSON = re.compile(r"^[A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]+)?, [A-Z][A-Z'\-]+(?: [A-Z][A-Z'\-]*\.?)*[ .]*$")
MUNI_TYPES = r"R M|RM|RURAL MUNICIPALITY|CITY|TOWN|VILLAGE|RESORT VILLAGE|NORTHERN VILLAGE|NORTHERN HAMLET|HAMLET|NORTHERN TOWN|DISTRICT"
MUNI = re.compile(rf"^(?:{MUNI_TYPES}) (.+?)$")
MUNI2 = re.compile(rf"^(.+?) (?:{MUNI_TYPES})$")
ORG_WORDS = re.compile(r"\b(INC|LTD|LTEE|LLP|SCHOOL|DIVISION|SOCIETY|CLUB|CHURCH|CENTRE|CENTER|SERVICES?|NATION|BAND|COUNCIL|"
                       r"GROUP|CO|COOP|FARMS?|RANCH|CORP|ASSOCIATION|FOUNDATION|BOARD|AUTHORITY|AGENCY|COMMITTEE|"
                       r"UNIVERSITY|COLLEGE|INSTITUTE|HOSPITAL|LIBRARY|MUSEUM|THEATRE|SOCIETE|FIRST|TRIBAL|HOLDINGS|"
                       r"ENTERPRISES|INDUSTRIES|COMMUNITY|TOWN|CITY|VILLAGE|RM|R|M|OF|THE|AND)\b")

END_HEADINGS = {"Goods and Services", "Other Expenses", "Capital Asset Acquisitions", "Salaries and Benefits",
                "Other", "Revenue", "Capital Asset Acquisitions by Class"}
# Name, dot leader, then one or more amount columns (dots or "$" for empty cells);
# the last number is the amount (the Total column in multi-column tables).
AMT = re.compile(r"^(?P<name>.*?)\s*\.{2,}(?P<cols>(?:[\s.$]|\d{1,3}(?:,\d{3})+)*?)(?P<amt>\d{1,3}(?:,\d{3})+)[\s.$]*$")
MERGED = re.compile(r"\.{2,}[\s.$]*\d[\d,]*\s+[A-Z(]")  # two recipients ran together on one line
CODE_ONLY = re.compile(r"^[\s()A-Z]{0,4}\d{1,2}\s*\)?$")  # "(SR01)", "WS( 01)": the recipient is the heading
ONLY_AMT = re.compile(r"^[\s.$]*(?P<amt>\d{1,3}(?:,\d{3})+)[\s.$]*$")
SCHEDULE_ROW = re.compile(r"^(?P<name>[A-Za-z][A-Za-z ,'&\-]*?)\s*\.{3,}\s*(?P<vote>\d+)\s+(?P<rest>.*)$")


def upper(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def norm(s):
    s = upper(s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(THE|OF|INC|LTD|LIMITED|CORP|CORPORATION|SOCIETY|ASSOCIATION|ASSN|FOUNDATION)\b", " ", s)
    s = re.sub(r"\b(NO|NUMBER)\s*\d+\b|#\s*\d+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ downloads

def fetch(url, path):
    if path.exists() and path.stat().st_size > 0:
        return True
    print("downloading", url, file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (riding-spending; python-urllib)"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        print("  failed:", e, file=sys.stderr)
        return False
    if not data.startswith(b"%PDF"):
        print("  not a PDF, skipped", file=sys.stderr)
        return False
    path.write_bytes(data)
    return True


def check_2025_26():
    """Look in the publications centre for a 2025-26 Volume 2; download it if listed."""
    target = DL / "pa_vol2_2025-26.pdf"
    if target.exists():
        return True
    try:
        req = urllib.request.Request(PUBLICATIONS_CATEGORY, headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            cat = json.load(r)
    except Exception as e:  # noqa: BLE001
        print("publications centre check failed:", e, file=sys.stderr)
        return False
    for child in cat.get("childCategories", []):
        if child.get("nameEnglish") == "2025-2026":
            desc = child.get("longDescriptionEnglish") or ""
            m = re.search(r'href="([^"]+)"[^>]*>\s*Volume 2\s*<', desc)
            if m:
                url = m.group(1).replace("../", "https://publications.saskatchewan.ca/")
                return fetch(url, target)
            print("publications centre: 2025-26 Volume 2 not available yet", file=sys.stderr)
    return False


# ------------------------------------------------------------------ PDF parsing

def parse_schedule(pages):
    """Schedule of Expense by Object -> ({vote: ministry}, {ministry: transfers $})."""
    votes, totals = {}, {}
    active = False
    for page in pages:
        for text, _ in page:
            if text.startswith("Schedule of Expense by Object"):
                active = True
                continue
            if not active:
                continue
            if text.startswith("Total $") or text.startswith("Total "):
                active = False
                break
            m = SCHEDULE_ROW.match(text)
            if not m:
                continue
            cols = []
            for tok in m.group("rest").split():
                if tok == "$":
                    continue
                if set(tok) <= {"."}:
                    cols.append(0)
                elif re.fullmatch(r"\(?[\d,]+\)?", tok):
                    v = int(tok.strip("()").replace(",", ""))
                    cols.append(-v if tok.startswith("(") else v)
            if len(cols) < 3:
                continue
            name = m.group("name").strip()
            votes.setdefault(m.group("vote"), name)
            totals[name] = (cols[1] + cols[2]) * 1000
    return votes, totals


def is_noise(text, size, ministry):
    """Page numbers and running headers (8 pt), e.g. "120 Government Relations"."""
    if text.isdigit() or text.startswith("Public Accounts"):
        return True
    if size >= 10:
        return False
    bare = re.sub(r"[\d\s]", "", text)
    return bool(ministry) and bare == re.sub(r"\s", "", ministry)


def clean_name(s):
    s = re.sub(r"^[\s.$]+", "", s)
    s = re.sub(r"^\d{1,3}(,\d{3})+\s+", "", s)  # a stray amount from the other column
    return re.sub(r"\s+", " ", s).strip(" .")


def parse_transfers(path, fy):
    """-> (rows, stats). rows: dicts with fiscal_year, ministry, vote, program, subprogram,
    recipient, amount. stats: per-ministry counts and the schedule totals."""
    pages = pdf_pages(path, split=300, sizes=True)
    votes, schedule = parse_schedule(pages)
    lines = [(text.strip(), size) for page in pages for text, size in page]
    rows = []
    bad = Counter()
    ministry = vote = None
    in_tr = skip_intro = False
    program = sub = None
    pend_name = []
    pend_from_leader = False  # the pending name came from a leader line with no amount
    head_buf, head_size = [], None

    def flush_heading():
        nonlocal program, sub, head_buf
        if not head_buf:
            return
        text = " ".join(head_buf)
        text = re.sub(r"\s*\((Subvote )?[A-Z]{2}\d{2}\)", "", text).strip()
        if head_size >= 13:
            program, sub = text, None
        else:
            sub = text
        head_buf = []

    by_name = {re.sub(r"\W", "", k).lower(): k for k in schedule}
    for text, size in lines:
        m = re.search(r"\(Vote\s*(\d+)?\s*\)?\s*$", text)
        if m and size >= 10 and len(text) > 6:
            vote = m.group(1)
            name = re.sub(r"\W", "", text[:m.start()]).lower()
            ministry = by_name.get(name) or votes.get(vote) or text[:m.start()].strip()
            if not vote:
                vote = next((v for v, n in votes.items() if n == ministry), "")
            in_tr = False
            continue
        if not ministry or is_noise(text, size, ministry):
            continue
        if not in_tr:
            if text == "Transfers" and size >= 12:
                in_tr = skip_intro = True
                program = sub = None
                pend_name, head_buf = [], []
            continue
        if skip_intro:
            if text.startswith("Listed by") or text.endswith("or more."):
                if text.endswith("or more."):
                    skip_intro = False
                continue
            skip_intro = False
        if size >= 11 and text in END_HEADINGS:
            in_tr = False
            continue
        m = AMT.match(text)
        if m and MERGED.search(text):
            bad[(ministry, "two recipients on one line")] += 1
            pend_name = []
            continue
        if m:
            flush_heading()
            own = clean_name(m.group("name"))
            if own and pend_from_leader:
                # The leader line before this one lost its amount; this row stands alone.
                bad[(ministry, "garbled amount")] += 1
                pend_name = []
            name = " ".join(pend_name + [own]).strip()
            pend_name = []
            pend_from_leader = False
            if CODE_ONLY.match(name):
                name = sub or program or ""  # single-recipient votes name the recipient in the heading
            if name:
                rows.append({"fiscal_year": fy, "ministry": ministry, "vote": vote, "program": program or "",
                             "subprogram": sub or "", "recipient": name,
                             "amount": int(m.group("amt").replace(",", ""))})
            else:
                bad[(ministry, "amount without name")] += 1
            continue
        m = ONLY_AMT.match(text)
        if m and pend_name:
            flush_heading()
            pend_from_leader = False
            rows.append({"fiscal_year": fy, "ministry": ministry, "vote": vote, "program": program or "",
                         "subprogram": sub or "", "recipient": " ".join(pend_name),
                         "amount": int(m.group("amt").replace(",", ""))})
            pend_name = []
            continue
        if size < 10:
            if "...." in text:
                # A dot leader without a readable amount: in wide tables the amounts sit on
                # the next line, so keep the name; otherwise the columns ran together.
                head = clean_name(re.split(r"\.{2,}", text, maxsplit=1)[0])
                if head and head == head.upper() and re.search(r"[A-Z]", head) and not re.search(r"\d,\d", text):
                    flush_heading()
                    pend_name = [head]
                    pend_from_leader = True
                else:
                    bad[(ministry, "garbled amount")] += 1
                    pend_name = []
            elif text == text.upper() and re.search(r"[A-Z]", text):
                flush_heading()
                if pend_from_leader:
                    bad[(ministry, "garbled amount")] += 1
                    pend_name = []
                    pend_from_leader = False
                pend_name.append(clean_name(text))
            continue
        # A heading (program or sub-program).
        if pend_name:
            pend_name = []
        if head_buf and head_size != size:
            flush_heading()
        head_buf.append(text)
        head_size = size
    stats = {"schedule": schedule, "bad": bad}
    return rows, stats


def load_rows(fy, path):
    cache = SK / f"transfers_{fy}.csv"
    rows, stats = parse_transfers(path, fy)
    with open(cache, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fiscal_year", "ministry", "vote", "program", "subprogram", "recipient", "amount"])
        w.writeheader()
        w.writerows(rows)
    by_min = defaultdict(lambda: [0, 0])
    for r in rows:
        by_min[r["ministry"]][0] += 1
        by_min[r["ministry"]][1] += r["amount"]
    print(f"\n{fy}: {len(rows)} transfer rows, ${sum(r['amount'] for r in rows):,.0f} parsed; "
          f"{sum(stats['bad'].values())} lines skipped (garbled amounts)")
    print(f"  {'ministry':48} {'rows':>5} {'parsed $':>16} {'schedule $':>16} {'cover':>6}")
    sched = stats["schedule"]
    grand_s = 0
    for mn, (n, v) in sorted(by_min.items(), key=lambda kv: -kv[1][1]):
        s = sched.get(mn)
        grand_s += s or 0
        cover = f"{100 * v / s:5.0f}%" if s else "   n/a"
        print(f"  {mn[:48]:48} {n:5} {v:16,.0f} {s if s is not None else 0:16,.0f} {cover}")
    missing = {k: v for k, v in sched.items() if k not in by_min and v}
    if missing:
        print("  ministries with transfers in the schedule but no parsed rows:",
              ", ".join(f"{k} (${v:,.0f})" for k, v in missing.items()))
    total_sched = sum(v for v in sched.values() if v)
    print(f"  schedule total transfers ${total_sched:,.0f}; parsed covers {100 * sum(r['amount'] for r in rows) / total_sched:.0f}% "
          f"(recipients under $50,000 and payments to individuals are not itemised)")
    return rows


# ------------------------------------------------------------------ aggregation

def main():
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()

    DL.mkdir(parents=True, exist_ok=True)
    years = {}
    for fy, url in VOLUMES.items():
        if fetch(url, DL / f"pa_vol2_{fy}.pdf"):
            years[fy] = DL / f"pa_vol2_{fy}.pdf"
    if check_2025_26():
        years["2025-26"] = DL / "pa_vol2_2025-26.pdf"
    if "2025-26" in years:
        after_fy, before_fy = "2025-26", "2023-24"
        window_note = ("after = fiscal 2025-26 (the first full year after the 28 October 2024 election); "
                       "before = fiscal 2023-24; 2024-25, which straddles the election, is left out")
    else:
        after_fy, before_fy = "2024-25", "2023-24"
        window_note = ("No 2025-26 Volume 2 was published yet, so after = fiscal 2024-25, which straddles the "
                       "28 October 2024 election (April to October before it, November to March after); before = fiscal 2023-24")
    print("windows:", window_note)

    # Name -> postal code sources.
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("SK|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "SK":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[4] == "SK":
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

    def muni_key(n):
        m = MUNI.match(n) or MUNI2.match(n)
        return m.group(1) if m else None

    def looks_individual(raw, n):
        """'LEMAIGRE, JIM G.' is a person; 'ABERDEEN, TOWN OF' and 'MNP LTD.' are not."""
        return bool(PERSON.match(raw.strip())) and not ORG_WORDS.search(n)

    def place(name):
        """-> (constituency number or None, method)."""
        n = norm(name)
        if n in loc_cache:
            return loc_cache[n]
        res = (None, "unmatched")
        if not n:
            res = (None, "withheld")
        elif n in name_pc and locate_pc(name_pc[n]):
            res = (locate_pc(name_pc[n]), "postal code from federal or charity records")
        else:
            key = muni_key(n)
            if key:
                d = locate_place(key)
                if d:
                    res = (d, "municipality")
            if res[0] is None and not re.search(r"\bSASKATCHEWAN\b|\bCANADA\b", n):
                for p in place_names:
                    if f" {p} " in f" {n} ":
                        d = locate_place(p)
                        if d:
                            res = (d, "place name in recipient (approx.)")
                            break
            if res[0] is None and looks_individual(name, n):
                res = (None, "individual")
        loc_cache[n] = res
        return res

    def divisions_of_place(key, limit=60):
        pts = places.get(key) or []
        step = max(1, len(pts) // limit)
        return {index.locate(*p)[0] for p in pts[::step]} - {None}

    multi_division = {}

    def flag_for(name):
        """Why a placed payment is left out of the adjusted totals, or ""."""
        if PROVINCEWIDE.search(upper(name)):
            return "province-wide"
        key = muni_key(norm(name))
        if key:
            if key not in multi_division:
                multi_division[key] = len(divisions_of_place(key)) > 1
            if multi_division[key]:
                return "other government"  # a city spread over several constituencies
        return ""

    rows = []
    for fy in (before_fy, after_fy):
        rows += load_rows(fy, years[fy])
    windows = {before_fy: "before", after_fy: "after"}
    years_per_window = 1.0

    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": []} for num in divisions}
    method_counts = Counter()
    excluded = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    for r in rows:
        v = float(r["amount"])
        window = windows.get(r["fiscal_year"])
        if v <= 0 or not window:
            continue
        program = r["program"] + (" - " + r["subprogram"] if r["subprogram"] else "")
        if INDIVIDUAL_PROGRAMS.search(program) or INDIVIDUAL_PROGRAMS.search(r["subprogram"]):
            excluded[(window, "individual programs")] += v
            continue
        num, how = place(r["recipient"])
        if how == "withheld":
            excluded[(window, "withheld")] += v
            continue
        if how == "individual":
            excluded[(window, "individuals")] += v
            continue
        if num is None:
            kind = "province-wide bodies" if PROVINCEWIDE.search(upper(r["recipient"])) else "unmatched"
            excluded[(window, kind)] += v
            if window == "after" and kind == "unmatched":
                unmatched[r["recipient"]] += v
            continue
        flag = flag_for(r["recipient"])
        method_counts[(window, how)] += 1
        p = per[num]
        p[window]["total"] += v
        p[window]["n"] += 1
        if not flag:
            p[window]["adj"] += v
            p[window]["adj_n"] += 1
        else:
            flagged_total[(window, r["recipient"])] += v
        if window == "after":
            label = f'{r["ministry"]}: {program}'
            p["progs"][label] += v
            if not flag:
                prog_totals[label][num] += v
            p["grants"].append((v, r, flag, how, program))

    out = {}
    for num, dv in divisions.items():
        p = per[num]
        pop = dv["population"] or 1
        a, b = p["after"], p["before"]
        rec = dict(dv)
        by_recipient = defaultdict(lambda: {"v": 0.0, "n": 0, "progs": Counter(), "flag": "", "how": "", "last": ""})
        for v, r, fl, how, program in p["grants"]:
            g = by_recipient[r["recipient"]]
            g["v"] += v
            g["n"] += 1
            g["progs"][f'{program} ({r["ministry"]})'] += v
            g["flag"], g["how"], g["last"] = fl, how, max(g["last"], r["fiscal_year"])
        top = sorted(by_recipient.items(), key=lambda kv: -kv[1]["v"])[:10]
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"], "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]),
            "pc_after": round(a["adj"] / pop / years_per_window, 2), "pc_after_all": round(a["total"] / pop / years_per_window, 2),
            "pc_before": round(b["adj"] / pop / years_per_window, 2),
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
        x["group"] = ("Close" if x["close"] else "Safe") + (f" {GOV_PARTY}" if x["gov_won"] else " NDP")
    groups = {}
    for g in [f"Close {GOV_PARTY}", "Close NDP", f"Safe {GOV_PARTY}", "Safe NDP"]:
        xs = [x for x in out.values() if x["group"] == g]
        chg = [x["change_pct"] for x in xs if x["change_pct"] is not None]
        groups[g] = {"ridings": len(xs), "median_pc_after": round(statistics.median(x["pc_after"] for x in xs), 2) if xs else None,
                     "median_pc_before": round(statistics.median(x["pc_before"] for x in xs), 2) if xs else None,
                     "median_change_pct": round(statistics.median(chg), 1) if chg else None,
                     "total_adj_after": round(sum(x["after_adj"] for x in xs))}
    total_after = sum(v for (w, _), v in excluded.items() if w == "after") + sum(x["after_total"] for x in out.values())
    fy_start = lambda fy: f"{fy[:4]}-04-01"
    fy_end = lambda fy: f"{int(fy[:4]) + 1}-03-31"
    meta = {
        "generated": date.today().isoformat(), "election": ELECTION.isoformat(),
        "after_year": after_fy, "before_year": before_fy,
        "after_start": fy_start(after_fy), "cutoff": fy_end(after_fy),
        "before_start": fy_start(before_fy), "before_end": fy_end(before_fy), "years_per_window": years_per_window,
        "window_note": window_note,
        "population_basis": next(iter(divisions.values())).get("population_basis", ""),
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
