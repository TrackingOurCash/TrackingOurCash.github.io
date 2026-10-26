"""Manitoba: aggregate provincial payments by electoral division.

Reads the "Vendor Payments over $50,000" statements (data/raw/mb/dl/vendor_<year>.pdf)
and data/mb/divisions.json (from mb_prep.py). Writes data/mb/division_spending.json
and, for inspection, data/raw/mb/payees_<year>.csv with every parsed row.

Source. Manitoba publishes no grant-recipient file. With each year's Public Accounts
it issues a PDF listing, per department or special operating agency, every payee
whose payments from that department exceeded $50,000: goods and services, grants,
loans and refunds together, with no program and no dates. Each line is
"PAYEE NAME [TOWN [PROV]] $amount" in two columns; the town is appended to the
name with no delimiter and omitted when the payee's address is in Winnipeg
(preamble note 6). mb_pdf.py turns each page into positioned strings; this script
splits the columns at x = 300, reads each column top to bottom (left column, right
column, next page), joins names that wrap over several lines until the line that
carries the amount, and separates the town from the name by the longest matching
place-name suffix. Place names come from the Canadian Geographical Names Database
(cgn_mb_csv_eng.csv: cities, towns, villages, communities, localities and rural
municipalities, but not Winnipeg neighbourhoods) plus the GeoNames postal-code
places; a two-letter province or US state code after the town marks an
out-of-province payee. When the suffix leaves a name ending in "OF", "DE" and the
like ("CITY OF WINNIPEG", "TOWN OF ALTONA": the statement does not repeat a town
that already ends the name), the name is kept whole and the place is still used
for location.

Windows. The election was 3 October 2023. The statements are annual (April to
March) and undated, so no finer split is possible: "after" = fiscal 2025-26
(1 April 2025 to 31 March 2026, the latest statement), "before" = fiscal 2022-23
(1 April 2022 to 31 March 2023, the last full year before the election);
years_per_window = 1.0. 2023-24 (which straddles the election) and 2024-25 are
parsed too, for the CSVs and the coverage table, but not used in the totals.

Placing a payee:
  1. with a town: the town's centroid, located in a division by point-in-polygon
     (geo.RidingIndex over data/mb/divisions_geo.json);
  2. without a town (a Winnipeg address): the same name in the federal grants file
     (data/name_postal.json, "MB|" keys) or the CRA charity list (Province == MB),
     via its postal code; else a municipality name in the payee ("CITY OF X",
     "R M OF X", "X COMMUNITY COUNCIL"); else a place name inside the payee's name,
     Winnipeg neighbourhoods included ("ST BONIFACE HOSPITAL", "approx.");
  3. a payee with "WINNIPEG" in its name that still has no match is put at the
     city's centroid, flagged "winnipeg (approx.)" and left out of the adjusted
     totals (the flag is there so one division does not collect every unmatched
     Winnipeg body); everything else goes to "unmatched".
Flags and exclusions, in this order:
  * the Public Debt department (about $120 billion a year of payments to banks and
    bondholders, mostly debt rolled over) is left out of the totals altogether and
    reported in meta.not_counted_after, so total_after means every other payment;
  * Employee Pensions and Other Costs, Tax Credits (education property tax credits
    that flow through school divisions and municipalities) and pension funds are
    excluded as "pensions and tax credits"; program aggregate lines that pay people
    ("EMPLOYMENT AND INCOME ASSISTANCE", "MANITOBA SHELTER BENEFIT PROGRAM") as
    "individual programs"; refunds and government trust funds as "refunds and
    trust funds"; payees with an address outside Manitoba as "outside Manitoba";
  * payees that look like a person ("THOMSON DR GLEN", "ACEBUQUE MARIA SOCORRO", an
    MLA's expense account) and physicians' medical corporations are excluded as
    "individuals" (the statement is by department, not program, so this is the only
    way individual-benefit payments can be identified);
  * province-wide bodies (Shared Health, the regional health authorities,
    CancerCare, Manitoba Hydro, MPI, Liquor & Lotteries, universities and colleges,
    school divisions, Crown corporations, "Government of", "Province of", the
    Receiver General) are placed where their head office is but flagged
    "province-wide"; the City of Winnipeg and City of Brandon, which span several
    divisions, are flagged "other government";
  * obvious suppliers of goods and services (LTD, CORP, LP, LLP, LLC, ULC,
    construction, consulting, engineering, software, pharmacies, telecoms, banks,
    hotels, fuel, equipment, numbered companies, purchasing-card totals) are
    excluded as "suppliers", unless the name also carries a non-profit or public
    word (society, association, centre, council, community, school, First Nation,
    child care, ...). "INC" alone does not mark a supplier: Manitoba's non-profits
    are almost all "... INC".
Everything that remains, placed in a division, counts as a grant-like payment.
Brandon spans two divisions, so a Brandon payee is placed by its own postal code
when the federal or charity records have one; the rest fall at the city's centroid
(Brandon East). Winnipeg payees are placed only when a name match gives a postal
code, so divisions with many agency head offices (Point Douglas, St. James,
Wolseley) read high, as in the other provinces.
"""
import csv
import json
import re
import statistics
import sys
import unicodedata
import urllib.request
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MB = RAW / "mb"
DL = MB / "dl"
OUT = ROOT / "data" / "mb"
sys.path.insert(0, str(ROOT / "scripts"))
from geo import RidingIndex, load_centroids  # noqa: E402
from mb_pdf import pdf_items  # noqa: E402

ELECTION = date(2023, 10, 3)
CLOSE_MARGIN = 10.0
GOV_PARTY = "NDP"
OPP_PARTY = "PC"
AFTER_FY, BEFORE_FY = "2025-26", "2022-23"
STATEMENTS = {
    "2025-26": "https://www.gov.mb.ca/asset_library/en/finances/vendor-payments-over-50k-2025-26.pdf",
    "2024-25": "https://manitoba.ca/asset_library/en/proactive/20242025/publicaccounts/VendorPaymentsover50k2024-25.pdf",
    "2023-24": "https://manitoba.ca/asset_library/en/proactive/20232024/publicaccounts/VendorPaymentsover50k2023-2024.pdf",
    "2022-23": "https://manitoba.ca/asset_library/en/publicaccounts2023/VendorPaymentsover50k2022-2023.pdf",
}
CGN_URL = "https://ftp.maps.canada.ca/pub/nrcan_rncan/vector/geobase_cgn_toponyme/prov_csv_eng/cgn_mb_csv_eng.zip"
COLUMN_SPLIT = 300  # x coordinate of the gutter between the two columns

NOT_COUNTED = re.compile(r"^PUBLIC DEBT$")  # payments to banks and bondholders: left out of the totals altogether
EXCLUDED_DEPARTMENTS = re.compile(r"^(EMPLOYEE PENSIONS AND OTHER COSTS|TAX CREDITS)$")
INDIVIDUAL_PROGRAMS = re.compile(
    r"INCOME ASSISTANCE|SHELTER BENEFIT|HOUSING BENEFIT|BENEFIT PROGRAM|SOCIAL ASSISTANCE|SOCIAL ALLOWANCE|SPECIAL ALLOWANCE|"
    r"DISABILITY SERVICES PROGRAM|VICTIMS OF CRIME|RENT ASSIST|SUBSID|STUDENT AID|BURSAR|SCHOLARSHIP|\bEIA\b|FOSTER|ADOPTION|"
    r"AGRISTABILITY|AGRIINVEST|AGRIINSURANCE|CROP INSURANCE|WILDLIFE DAMAGE|DISASTER FINANCIAL ASSISTANCE|ASSISTANCE -TOTAL|-TOTAL$",
    re.I)
PENSIONS = re.compile(r"RETIREMENT ALLOWANCES FUND|PENSION|SUPERANNUATION", re.I)
INTERNAL = re.compile(r"TRUST FUND|TRUST ACCOUNT|^REFUNDS?\b|^REFUND -|^MUNICIPALITIES -", re.I)
PROVINCES = r"ON|AB|BC|SK|QC|NB|NS|PE|PEI|NL|NT|NU|YT"
AMT = re.compile(r"^(?P<name>.*?)\s*\$\s*(?P<amt>\d[\d, ]*)\s*$")
PERSON = re.compile(r"^(?:[A-Z][A-Z'\-]+ ){1,3}(?:DR |MR |MRS |MS )?[A-Z][A-Z'\-]*\.?(?: [A-Z]\.?)?$")
CONNECTOR = re.compile(r"\b(OF|DE|DU|DES|LA|LE|LES|THE|AND|&|FOR|AT|IN|ON|TO|A|AU|AUX|D|L|ET|FROM)$")
MUNI_PREFIX = re.compile(r"^(CITY|TOWN|VILLAGE|R ?M|RURAL MUNICIPALITY|MUNICIPALITY|L ?G ?D|LOCAL GOVERNMENT DISTRICT|INCORPORATED COMMUNITY|NORTHERN AFFAIRS COMMUNITY) OF (.+?)$")
MUNI_SUFFIX = re.compile(r"^(.+?) (MUNICIPALITY|COMMUNITY COUNCIL|FIRST NATION|CREE NATION|OJIBWAY NATION|DAKOTA NATION|ANISHINAABE NATION|BAND|COMMUNITY)$")
PROVINCEWIDE = re.compile(
    r"SHARED HEALTH|REGIONAL HEALTH AUTHORITY|SOUTHERN HEALTH|PRAIRIE MOUNTAIN HEALTH|INTERLAKE.EASTERN|NORTHERN HEALTH REGION|"
    r"CANCERCARE|CANCER CARE MANITOBA|ADDICTIONS FOUNDATION OF MANITOBA|CANADIAN BLOOD SERVICES|DIAGNOSTIC SERVICES|"
    r"MANITOBA HYDRO|MANITOBA PUBLIC INSURANCE|\bMPI\b|MANITOBA LIQUOR|LIQUOR . LOTTERIES|EFFICIENCY MANITOBA|MANITOBA HOUSING|"
    r"MANITOBA AGRICULTURAL SERVICES|\bMASC\b|TRAVEL MANITOBA|RESEARCH MANITOBA|MANITOBA ARTS COUNCIL|SPORT MANITOBA|"
    r"MANITOBA FILM|MANITOBA CENTENNIAL CENTRE|MANITOBA WATER SERVICES BOARD|COMMUNITIES ECONOMIC DEVELOPMENT FUND|"
    r"MANITOBA DEVELOPMENT CORP|MANITOBA STUDENT AID|LEGAL AID MANITOBA|WORKERS COMPENSATION BOARD|CIVIL SERVICE SUPERANNUATION|"
    r"PUBLIC SERVICE GROUP INSURANCE|MANITOBA BLUE CROSS|MANITOBA LOTTERIES|MANITOBA HABITAT|MANITOBA HERITAGE TRUST|"
    r"UNIVERSITY OF (MANITOBA|WINNIPEG)|BRANDON UNIVERSITY|UNIVERSITE DE SAINT BONIFACE|UNIVERSITY COLLEGE OF THE NORTH|"
    r"RED RIVER COLLEGE|ASSINIBOINE COMMUNITY COLLEGE|MANITOBA INSTITUTE OF TRADES|CANADIAN MENNONITE UNIVERSITY|"
    r"BOOTH UNIVERSITY|PROVIDENCE (UNIVERSITY )?COLLEGE|SCHOOL DIVISION|SCHOOL DISTRICT|DIVISION SCOLAIRE|"
    r"MANITOBA (TEACHERS|SCHOOL BOARDS|MEDICAL ASSOCIATION|NURSES|FEDERATION OF LABOUR)|DOCTORS MANITOBA|"
    r"ASSOCIATION OF MANITOBA MUNICIPALITIES|\bAMBM\b|MANITOBA METIS FEDERATION|ASSEMBLY OF MANITOBA CHIEFS|"
    r"SOUTHERN CHIEFS ORGANIZATION|MANITOBA KEEWATINOWI OKIMAKANAK|\bMKO\b|"
    r"^GOVERNMENT OF|^PROVINCE OF|^MINISTER OF FINANCE|RECEIVER GENERAL|GOVERNMENT OF CANADA|^MANITOBA FINANCE\b|"
    r"MANITOBA (ASSOCIATION|COUNCIL|FEDERATION|FOUNDATION|SOCIETY|ALLIANCE|NETWORK|CHAMBER|COALITION)|"
    r"\bMANITOBA$|\bMANITOBA INC$|^MANITOBA .*(CORP|CORPORATION|AGENCY|AUTHORITY|COMMISSION|BOARD|CENTRE|INSTITUTE)$|"
    r"SHOCK TRAUMA AIR RESCUE|\bSTARS\b|UNITED WAY|CANADIAN RED CROSS|SALVATION ARMY|^NDP CAUCUS|^PC CAUCUS|CAUCUS$|"
    r"NETWORK OF CARE|CHILD (AND|&) FAMILY SERVICES AUTHORITY|CFS AUTHORITY|ANIMIKII OZOSON",
    re.I)
OTHER_GOVERNMENT = re.compile(r"^CITY OF (WINNIPEG|BRANDON)\b", re.I)
PHYSICIAN = re.compile(r"\b(MEDICAL (PROF(ESSIONAL)? )?CORP(ORATION)?|MED(ICAL)? PROF CORP|\bDR\b|PHYSICIAN|M\.?D\.?)\b", re.I)
SUPPLIER = re.compile(
    r"\b(LTD|LTEE|LIMITED|CORP|CORPORATION|L ?P|LLP|LLC|ULC|PLLC|GMBH|PLC|CO|COMPANY|BROS|& SONS?|HOLDINGS|ENTERPRISES|INDUSTRIES|"
    r"CONSTRUCTION|CONTRACTING|CONTRACTORS?|BUILDERS|CONSULTING|CONSULTANTS?|ENGINEERING|ENGINEERS|ARCHITECTS?|ARCHITECTURE|SURVEYS?|"
    r"SOFTWARE|TECHNOLOG(Y|IES)|SYSTEMS|SOLUTIONS|DIGITAL|DATA|COMPUTERS?|TELECOM|COMMUNICATIONS|BELL MTS|BELL CANADA|BELL MOBILITY|ROGERS|SHAW|TELUS|"
    r"MICROSOFT|IBM|ORACLE|SAP|PHARMA\w*|PHARMACY|PHARMACIES|DRUG MART|DRUGS|APOTHECARY|LABORATOR(Y|IES)|MEDICAL (PRODUCTS|SUPPL\w*|EQUIPMENT)|"
    r"SUPPL(Y|IES|IERS?)|EQUIPMENT|ELECTRIC(AL)?|PLUMBING|HEATING|MECHANICAL|ROOFING|PAVING|EXCAVAT\w*|GRAVEL|CONCRETE|LUMBER|STEEL|WELDING|"
    r"TRUCKING|TRANSPORT(ATION)?|FREIGHT|LOGISTICS|AVIATION|AIR(WAYS|LINES?)?|HELICOPTERS?|FUELS?|PETROLEUM|OIL|GAS|ENERGY|MOTORS|AUTO|"
    r"LEASING|RENTALS?|PROPERTIES|REALTY|REAL ESTATE|DEVELOPMENTS?|MANUFACTURING|PRINTING|PRINTERS|PUBLISHING|MEDIA|ADVERTISING|MARKETING|"
    r"STAFFING|PERSONNEL|INSURANCE|ASSURANCE|BANK|BANQUE|FINANCIAL|SECURITIES|CAPITAL|INVESTMENTS?|TRUST COMPANY|TRUSTCO|MORTGAGE|"
    r"BARRISTERS?|SOLICITORS?|LAW|LEGAL|HOTELS?|INN|MOTEL|SUITES|LODGING|RESTAURANT|CATERING|FOOD SERVICES?|SECURITY|CLEANING|JANITORIAL|"
    r"WASTE|DISPOSAL|SANITATION|ENVIRONMENTAL SERVICES|LANDSCAPING|SIGNS?|UNIFORMS?|OFFICE|FURNITURE|OFFICEMAX|STAPLES|GRAND & TOY|AMAZON|"
    r"CANADA POST|PURCHASING CARD|PURCHASE CARD|TRAVEL|TOURS|TAXI|CAB|BUS LINES|COACH|COURIER|MOVING|STORAGE|"
    r"FARMS?|RANCH|COLONY|SEEDS?|FEEDS?|GRAIN|CATTLE|LIVESTOCK|NURSER(Y|IES) LTD|GREENHOUSES?|"
    r"DIV OF|DIVISION OF|A DIVISION|DBA|O/A|CONSTRUCTORS|GROUP|PAYWORKS|PAYROLL|BUILDING|REDI-MIX|CALL CENTRE|AON|TRAFFIC|CONTROLS|SYS|ORTHOPEDIC|ORTHOTIC|PROSTHETIC|"
    r"APPLIANCES|DESIGN|CONVENTION CENTRE|MERCK|FROSST|PFIZER|NOVARTIS|GILEAD|ASTRAZENECA|JANSSEN|ROCHE|SANOFI|BAYER|ABBVIE|AMGEN|TAKEDA|"
    r"GLAXO\w*|LILLY|BIOGEN|PARTNERSHIP|ACCOUNTANTS|CHARTERED|KPMG|DELOITTE|PWC|PRICEWATERHOUSE|ERNST|MNP|BDO|RENT A CAR|OUTFITTERS|"
    r"GEOMATICS|AIRCRAFT|RAILWAY|RAIL|MAINTENANCE|HAULING|DIESEL|INTERIOR|PRODUCTS|CHEV|CHEVROLET|FORD|TOYOTA|DODGE|HONDA|NISSAN|"
    r"TRUCK CENTRE|TRUCKS?|TIRE|IT INC)\b|^\d{5,}\b|\(\d{4}\)",
    re.I)
# Marks a supplier even when a non-profit word is present ("WESTERN SURGERY CENTRE INC", "RED RIVER COOPERATIVE LTD").
SUPPLIER_OVERRIDE = re.compile(r"PHARMAC|DRUG MART|CONVENTION CENTRE|SURGERY CENTRE|CALL CENTRE|TRUCK CENTRE|\bLTD\b|\bLIMITED\b|\bLTEE\b|"
                               r"\bLLP\b|\bL ?P$|\bULC\b|\bLLC\b|CANADA (INC|CORP|CO)$|COMPANIES|LIMITED PARTNERSHIP", re.I)
NONPROFIT = re.compile(
    r"\b(SOCIETY|SOCIETE|ASSOCIATION|ASSN|ASSOC|FOUNDATION|FONDATION|INSTITUTE|INSTITUT|FEDERATION|ALLIANCE|COALITION|NETWORK|"
    r"COUNCIL|CONSEIL|COMMITTEE|COMITE|COMMISSION|BOARD|AUTHORITY|AGENCY|DISTRICT|DIVISION SCOLAIRE|SCHOOL|ECOLE|COLLEGE|UNIVERSIT[YE]|"
    r"ACADEMY|LEARNING|LITERACY|EDUCATION|EMPLOYMENT|TRAINING|SKILLS|IMMIGRANT|NEWCOMERS?|SETTLEMENT|RESOURCE|SUPPORT|"
    r"CENTRE|CENTER|CENTRES|CLUB|CHURCH|PARISH|DIOCESE|MINISTRIES|MISSION|GOSPEL|MENNONITE|CATHOLIC|LUTHERAN|UNITED|ANGLICAN|"
    r"SALVATION ARMY|YMCA|YWCA|LEGION|KINSMEN|KINETTE|LIONS|ROTARY|ELKS|KIWANIS|SCOUTS|GUIDES|CADETS|"
    r"CHAMBER OF COMMERCE|BOARD OF TRADE|ECONOMIC DEVELOPMENT|COMMUNITY DEVELOPMENT|DEVELOPMENT CORP(ORATION)?|\bCDC\b|RENEWAL|REVITALIZATION|"
    r"NEIGHBOURHOOD|COMMUNITY|VOLUNTEER|CHARIT\w*|UNITED WAY|RED CROSS|HOSPICE|PALLIATIVE|CANCER|DIABETES|HEART|STROKE|ALZHEIMER|AUTISM|"
    r"EPILEPSY|ARTHRITIS|KIDNEY|LUNG|MS SOCIETY|PARKINSON|SPINAL CORD|DISABILIT\w*|ABILITIES|INCLUSION|INDEPENDENT LIVING|"
    r"MENTAL HEALTH|WELLNESS|RECOVERY|ADDICTIONS?|TREATMENT|COUNSELLING|CRISIS|SHELTER|HOMELESS|HOUSING|HOMES|HOME|LODGE|MANOR|VILLA|"
    r"PERSONAL CARE|CARE HOME|LONG TERM CARE|SENIORS?|ELDERS?|AGING|WOMEN|WOMEN'?S|MEN'?S|GIRLS|BOYS|CHILD|CHILDREN|CHILDREN'?S|KIDS|"
    r"FAMILY|FAMILIES|YOUTH|TEEN|DAYCARE|DAY CARE|CHILD CARE|CHILDCARE|NURSERY SCHOOL|PRESCHOOL|PRE-SCHOOL|EARLY LEARNING|EARLY YEARS|"
    r"PLAYSCHOOL|GARDERIE|HEADSTART|HEAD START|MONTESSORI|FRIENDSHIP|FIRST NATIONS?|NATION|CREE|OJIBWAY|OJIBWE|ANISHINAABE|DAKOTA|DENE|"
    r"METIS|INDIGENOUS|ABORIGINAL|TRIBAL|BAND|TREATY|CHIEFS?|CULTURAL|CULTURE|HERITAGE|HISTORICAL|HISTORIC|MUSEUM|MUSEE|LIBRARY|BIBLIOTHEQUE|"
    r"ARCHIVES|ARTS?|THEATRE|THEATER|DANCE|BALLET|MUSIC|ORCHESTRA|SYMPHONY|OPERA|CHOIR|CHORAL|FESTIVAL|GALLERY|FOLK|FILM FESTIVAL|"
    r"SPORTS?|ATHLETIC|HOCKEY|CURLING|SKATING|SKI|SWIM|AQUATIC|POOL|ARENA|RECREATION|REC|PARKS?|TRAILS?|CONSERVATION|CONSERVANCY|"
    r"WILDLIFE|WATERSHED|NATURALISTS|GARDEN|ZOO|FOOD BANK|HARVEST|SOUP|MEALS|HABITAT FOR HUMANITY|AGRICULTURAL SOCIETY|AG SOCIETY|"
    r"FAIR|EXHIBITION|RODEO|HOSPITAL|HEALTH CENTRE|HEALTH CENTER|NURSING STATION|CLINIC INC|MUNICIPALITY|TOWN|CITY|VILLAGE|"
    r"R ?M OF|RURAL MUNICIPALITY|L ?G ?D|COMMUNITY COUNCIL|CAMP|CAMPS|RETREAT|SANCTUARY|PROGRAM|PROGRAMS|PROJECT|"
    r"INITIATIVE|SERVICES? CORP|FRANCO\w*|FRANCOPHONE)\b",
    re.I)
ORG_WORDS = re.compile(r"\b(INC|LTD|LTEE|LLP|LP|CORP|CO|SCHOOL|DIVISION|SOCIETY|CLUB|CHURCH|CENTRE|CENTER|SERVICES?|NATION|BAND|COUNCIL|"
                       r"GROUP|COOP|FARMS?|RANCH|ASSOCIATION|FOUNDATION|BOARD|AUTHORITY|AGENCY|COMMITTEE|UNIVERSITY|COLLEGE|INSTITUTE|"
                       r"HOSPITAL|LIBRARY|MUSEUM|THEATRE|SOCIETE|FIRST|TRIBAL|HOLDINGS|ENTERPRISES|INDUSTRIES|COMMUNITY|TOWN|CITY|VILLAGE|"
                       r"RM|OF|THE|AND|CANADA|MANITOBA|WINNIPEG|PRESS|DESIGN|TABLE|STUDIO|MEDIA|INTERACTIVE|TACTICAL|VISIBLE|SOLUTIONS|"
                       r"SYSTEMS|TECHNOLOGIES|PHARMACY|CLINIC|LAW|CONSULTING|CARE|HOUSE|HOME|HOMES|PLACE|PROJECT|FUND|TRUST|CAUCUS|"
                       r"CONSTRUCTION|TRUCKING|ELECTRIC|SUPPLY|STORE|SHOP|CAFE|RESTAURANT|HOTEL|INN|MOTEL|LODGE|GARAGE|MOTORS|TIRE|"
                       r"BROS|SONS|PARTNERS|TEAM|DAYCARE|DOMINION|GENERAL|NATIONAL|GLOBAL|NORTHERN|SOUTHERN|WESTERN|EASTERN|PRAIRIE|"
                       r"INTERLAKE|PARKLAND|WESTMAN|EASTMAN|PEMBINA|ASSINIBOINE|SASKATCHEWAN|ONTARIO|ALBERTA|MISSION|OUTREACH|TRADING|POST|"
                       r"HOCKEY|CURLING|GOLF|SKI|CAMP|KIDS|CHILD|CHILDREN|CHILDRENS|FAMILY|YOUTH|SENIORS|WOMEN|WOMENS|MENS|GIRLS|BOYS)\b")
GENERIC_PRIORITY = ["City", "Town", "Village", "Local Urban District", "Urban Community", "Community", "Northern Community",
                    "Hamlet", "Locality", "Post Office", "Rural Municipality", "Neighbourhood"]
WINNIPEG = (49.8844, -97.147)


def upper(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def pnorm(s):
    """Place-name form: 'St. Pierre-Jolys' and 'ST PIERRE JOLYS' both -> 'ST PIERRE JOLYS'."""
    s = upper(s)
    s = re.sub(r"[-./'’,()]", " ", s)
    s = re.sub(r"\bSAINTE\b", "STE", re.sub(r"\bSAINT\b", "ST", s))
    return re.sub(r"\s+", " ", s).strip()


def norm(s):
    """Name-matching form shared with the federal file and the CRA list."""
    s = upper(s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(THE|OF|INC|LTD|LIMITED|CORP|CORPORATION|SOCIETY|ASSOCIATION|ASSN|FOUNDATION)\b", " ", s)
    s = re.sub(r"\b(NO|NUMBER)\s*\d+\b|#\s*\d+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ downloads

def fetch(url, path, binary_check=None):
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
    if binary_check and not data.startswith(binary_check):
        print("  unexpected content, skipped", file=sys.stderr)
        return False
    path.write_bytes(data)
    return True


# ------------------------------------------------------------------ places

def load_places():
    """-> ({MB place name: (lat, lon)}, {MB neighbourhood: (lat, lon)}, {province: set of place names})."""
    DL.mkdir(parents=True, exist_ok=True)
    zpath = DL / "cgn_mb_csv_eng.zip"
    cand = defaultdict(list)  # name -> [(priority, lat, lon)]
    hoods = {}
    if fetch(CGN_URL, zpath, b"PK"):
        with zipfile.ZipFile(zpath) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            text = z.read(name).decode("utf-8-sig")
        for r in csv.DictReader(text.splitlines()):
            term = r["Generic Term"]
            if term not in GENERIC_PRIORITY:
                continue
            key = pnorm(r["Geographical Name"])
            if not key or key == "MANITOBA" or len(key) < 3:
                continue
            try:
                lat, lon = float(r["Latitude"]), float(r["Longitude"])
            except ValueError:
                continue
            if term == "Neighbourhood":
                hoods.setdefault(key, (lat, lon))
            else:
                cand[key].append((GENERIC_PRIORITY.index(term), lat, lon))
    places = {k: (v[0][1], v[0][2]) for k, v in ((k, sorted(v)) for k, v in cand.items())}
    # GeoNames postal-code places: Manitoba names fill gaps; other provinces give the
    # town list used to strip the location from out-of-province payees.
    by_prov = defaultdict(set)
    pc_pts = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            try:
                key = pnorm(r[2])
                by_prov[r[4]].add(key)
                if r[4] == "MB":
                    pc_pts[key].append((float(r[9]), float(r[10])))
            except (IndexError, ValueError):
                continue
    for key, pts in pc_pts.items():
        if key not in places and len(key) >= 3:
            places[key] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    return places, hoods, by_prov, pc_pts


# ------------------------------------------------------------------ PDF parsing

def join_items(line_items):
    """Join the strings on one baseline in one column, deciding spaces from the gaps."""
    s, end_x = "", None
    for y, x, fs, text in sorted(line_items, key=lambda it: it[1]):
        if not text.strip():
            continue
        if end_x is not None and x - end_x > 0.3 * fs and not s.endswith(" ") and not text.startswith(" "):
            s += " "
        elif end_x is not None and x - end_x < -1.5 * fs and s and text.strip():
            s += " "
        s += text
        end_x = x + 0.55 * fs * len(text)
    return re.sub(r"[ \t ]+", " ", s).strip()


def baselines(items, y_tol=2.0):
    items = sorted(items, key=lambda it: (-it[0], it[1]))
    out, cur, cur_y = [], [], None
    for it in items:
        if cur_y is None or abs(it[0] - cur_y) > y_tol:
            if cur:
                out.append(cur)
            cur, cur_y = [], it[0]
        cur.append(it)
    if cur:
        out.append(cur)
    return out


def parse_statement(path, fy):
    """-> (rows, bad). rows: dicts with fiscal_year, department, payee_raw, amount."""
    rows = []
    bad = Counter()
    department = None
    soa = False
    pending = []

    def flush_pending(reason):
        nonlocal pending
        if pending:
            bad[(department or "?", reason)] += 1
            pending = []

    def take(text):
        nonlocal pending
        text = re.sub(r"^Page \d+\s*of \d+\s*", "", text)
        if not text or text.startswith("NO REPORTING VENDORS") or text.startswith("*PURCHASING CARD"):
            return
        m = AMT.match(text)
        if not m:
            pending.append(text)
            if len(pending) > 4:
                flush_pending("name without amount")
            return
        name = " ".join(pending + [m.group("name")]).strip()
        pending = []
        amt = int(re.sub(r"[^\d]", "", m.group("amt")) or 0)
        if not name:
            bad[(department or "?", "amount without name")] += 1
            return
        if department is None:
            bad[("?", "payee before first department")] += 1
            return
        rows.append({"fiscal_year": fy, "department": department, "payee_raw": re.sub(r"\s+", " ", name), "amount": amt})

    for items in pdf_items(path):
        if not items:
            continue
        segments = [[]]  # runs of payee lines between headings, each a list of (left, right) texts
        for line in baselines(items):
            texty = [it for it in line if it[3].strip()]
            if not texty:
                continue
            size = max(it[2] for it in texty)
            text = join_items(texty)
            if size >= 9.5:
                if text.startswith("VENDOR ") or text.startswith("Vendor") or re.match(r"^For the (fiscal )?year", text):
                    continue
                if text.startswith("SPECIAL OPERATING AGENCIES"):
                    segments.append(("heading", None, True))
                    segments.append([])
                    continue
                segments.append(("heading", text, soa))
                segments.append([])
                continue
            left = join_items([it for it in texty if it[1] < COLUMN_SPLIT])
            right = join_items([it for it in texty if it[1] >= COLUMN_SPLIT])
            segments[-1].append((left, right))
        for seg in segments:
            if isinstance(seg, tuple):
                _, text, was_soa = seg
                if text is None:
                    soa = True
                    continue
                flush_pending("name without amount at heading")
                name = re.sub(r"\s*\([IVXL ]+\)\s*$", "", text).strip(" .")
                name = re.sub(r"\s+\)", ")", name)
                department = ("SOA: " if soa else "") + name.title().replace("'S", "'s").replace(" And ", " and ").replace(" Of ", " of ")
                continue
            for left, _ in seg:
                take(left)
            for _, right in seg:
                take(right)
    flush_pending("name without amount at end")
    return rows, bad


# ------------------------------------------------------------------ name / town split

class Splitter:
    def __init__(self, places, by_prov):
        self.places = places
        self.by_prov = by_prov
        self.mb_names = sorted(places, key=len, reverse=True)
        self.by_last = defaultdict(list)
        for p in self.mb_names:
            self.by_last[p.split()[-1]].append(p)
        self.other_last = {prov: defaultdict(list) for prov in by_prov}
        for prov, names in by_prov.items():
            for p in sorted(names, key=len, reverse=True):
                if p:
                    self.other_last[prov][p.split()[-1]].append(p)

    @staticmethod
    def suffix(words, cands):
        """Longest candidate place (as word list) ending the word list, leaving at least one word."""
        for p in cands:
            pw = p.split()
            if len(pw) < len(words) and words[-len(pw):] == pw:
                return p
        return None

    def split(self, raw):
        """-> (payee name, town, province). province '' = Manitoba, 'XX' = elsewhere."""
        text = re.sub(r"\s*-\s*", "-", raw)
        words = pnorm(text).split()
        if not words:
            return raw, "", ""
        province = ""
        m = re.match(r"^(.*?)\s+([A-Z]{2})\s+(US|USA)$", " ".join(words))
        if m and len(words) >= 4:
            province = m.group(2) + " US"
            words = m.group(1).split()
            return self.clean(raw, len(words) - 1), words[-1], province
        if len(words) >= 3 and re.fullmatch(PROVINCES, words[-1]) and words[-2] not in ("CARRIED", "GROUND", "WHEELS", "HANDS"):
            province = {"PEI": "PE"}.get(words[-1], words[-1])
            words = words[:-1]
            town = self.suffix(words, self.other_last.get(province, {}).get(words[-1], []))
            if town:
                return self.clean(raw, len(words) - len(town.split())), town, province
            return self.clean(raw, len(words) - 1), words[-1], province
        m = re.match(r"^(.*?)\s+(UK|GB|AU|NZ|DE|FR|IE|IN|CH|JP|SG|NL|BE|IT|ES|SE|DK|NO|FI|IL|MX|BR|ZA|KR|CN|HK)$", " ".join(words))
        if m and len(words) >= 3:
            return self.clean(raw, len(words) - 2), words[-2], m.group(2)
        town = self.suffix(words, self.by_last.get(words[-1], []))
        if not town or town == "WINNIPEG":
            # Winnipeg is never printed as a location (note 6): "UNITED WAY WINNIPEG" is a name.
            return raw.strip(), "", ""
        rest = words[:-len(town.split())]
        if CONNECTOR.search(" ".join(rest)):
            # "TOWN OF ALTONA", "FRIENDS OF GIMLI": the statement does not repeat a town that ends the name.
            return raw.strip(), town, ""
        return self.clean(raw, len(rest)), town, ""

    @staticmethod
    def clean(raw, nwords):
        """The first nwords words of the raw name (words as pnorm counts them)."""
        text = re.sub(r"\s*-\s*", "-", raw)
        toks = text.split()
        out, count = [], 0
        for t in toks:
            n = len(pnorm(t).split())
            if count + n > nwords and count >= nwords:
                break
            out.append(t)
            count += n
            if count >= nwords:
                break
        return " ".join(out).strip(" ,")


# ------------------------------------------------------------------ main

def load_rows(fy, path, splitter):
    rows, bad = parse_statement(path, fy)
    for r in rows:
        r["payee"], r["town"], r["province"] = splitter.split(r["payee_raw"])
    with open(MB / f"payees_{fy}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fiscal_year", "department", "payee", "town", "province", "amount", "payee_raw"])
        w.writeheader()
        w.writerows(rows)
    by_dept = defaultdict(lambda: [0, 0, 0, 0])
    for r in rows:
        d = by_dept[r["department"]]
        d[0] += 1
        d[1] += r["amount"]
        d[2] += bool(r["town"]) and not r["province"]
        d[3] += bool(r["province"])
    total = sum(r["amount"] for r in rows)
    print(f"\n{fy}: {len(rows)} payee rows, ${total:,.0f}; {sum(bad.values())} lines skipped "
          f"({', '.join(f'{k[1]} in {k[0]}: {v}' for k, v in bad.most_common(5)) or 'none'})")
    print(f"  {'department':52} {'rows':>5} {'MB town':>7} {'outside':>7} {'parsed $':>18}")
    for dept, (n, v, t, o) in sorted(by_dept.items(), key=lambda kv: -kv[1][1]):
        print(f"  {dept[:52]:52} {n:5} {t:7} {o:7} {v:18,.0f}")
    return rows


def main():
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()
    places, hoods, by_prov, pc_pts = load_places()
    splitter = Splitter(places, by_prov)

    DL.mkdir(parents=True, exist_ok=True)
    years = {}
    for fy, url in STATEMENTS.items():
        if fetch(url, DL / f"vendor_{fy}.pdf", b"%PDF"):
            years[fy] = DL / f"vendor_{fy}.pdf"
    after_fy = AFTER_FY if AFTER_FY in years else max(years)
    if BEFORE_FY in years:
        before_fy = BEFORE_FY
        window_note = (f"after = fiscal {after_fy} (the latest statement, entirely after the 3 October 2023 election); "
                       f"before = fiscal {before_fy} (the last full year before it); the statements carry no dates, so the "
                       f"windows are whole fiscal years and 2023-24, which straddles the election, is left out")
    else:
        before_fy = "2023-24" if "2023-24" in years else min(years)
        window_note = (f"after = fiscal {after_fy}; before = fiscal {before_fy}, which straddles the 3 October 2023 election "
                       f"(the 2022-23 statement could not be downloaded)")
    print("windows:", window_note)

    # Name -> postal code sources (Winnipeg payees carry no town).
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("MB|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "MB":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    place_names = sorted((p for p in list(places) + list(hoods) if len(p) >= 5), key=len, reverse=True)
    winnipeg_div = index.locate(*WINNIPEG)[0]

    loc_cache = {}

    def locate_pc(pc):
        return index.locate(*centroids[pc])[0] if pc in centroids else None

    def locate_place(key):
        pt = places.get(key) or hoods.get(key)
        return index.locate(*pt)[0] if pt else None

    town_divisions = {}

    def divisions_of_town(key, limit=80):
        """Divisions a town's postal codes fall in (Brandon and the Winnipeg-area towns span more than one)."""
        if key not in town_divisions:
            pts = pc_pts.get(key) or []
            step = max(1, len(pts) // limit)
            town_divisions[key] = {index.locate(*p)[0] for p in pts[::step]} - {None}
        return town_divisions[key]

    def looks_individual(name):
        u = upper(name).strip()
        n = pnorm(name)
        if ORG_WORDS.search(n) or norm(name) in name_pc:
            return False
        parts = [p.strip() for p in re.split(r"\bAND\b|&", u) if p.strip()]
        return all(PERSON.match(p) for p in parts) or bool(PHYSICIAN.search(u))

    def place(r):
        """-> (division number or None, method)."""
        key = (r["payee"], r["town"], r["province"])
        if key in loc_cache:
            return loc_cache[key]
        res = (None, "unmatched")
        n = norm(r["payee"])
        if r["province"]:
            res = (None, "outside Manitoba")
        elif r["town"]:
            key = pnorm(r["town"])
            d = locate_place(key)
            if len(divisions_of_town(key)) > 1 and n in name_pc and locate_pc(name_pc[n]) in divisions_of_town(key):
                # A town split between divisions (Brandon): the payee's own postal code decides.
                res = (locate_pc(name_pc[n]), "postal code from federal or charity records")
            else:
                res = (d, "town printed with payee") if d else (None, "unmatched")
        else:
            if n in name_pc and locate_pc(name_pc[n]):
                res = (locate_pc(name_pc[n]), "postal code from federal or charity records")
            if res[0] is None:
                pn = pnorm(r["payee"])
                m = MUNI_PREFIX.match(pn) or MUNI_SUFFIX.match(pn)
                if m:
                    d = locate_place(m.group(2) if m.re is MUNI_PREFIX else m.group(1))
                    if d:
                        res = (d, "municipality")
            if res[0] is None and not re.search(r"\bMANITOBA\b|\bCANADA\b", n):
                pn = pnorm(r["payee"])
                for p in place_names:
                    if f" {p} " in f" {pn} ":
                        d = locate_place(p)
                        if d:
                            res = (d, "place name in payee (approx.)")
                            break
            if res[0] is None and re.search(r"\bWINNIPEG\b", n) and winnipeg_div:
                res = (winnipeg_div, "winnipeg (approx.)")
        loc_cache[key] = res
        return res

    def flag_for(r, how):
        u = upper(r["payee"])
        if OTHER_GOVERNMENT.search(u):
            return "other government"
        if PROVINCEWIDE.search(u):
            return "province-wide"
        if how == "winnipeg (approx.)":
            return "winnipeg (approx.)"
        return ""

    def is_supplier(name):
        u = upper(name)
        return bool(SUPPLIER_OVERRIDE.search(u)) or (bool(SUPPLIER.search(u)) and not NONPROFIT.search(u))

    rows = []
    for fy in sorted(years):
        parsed = load_rows(fy, years[fy], splitter)
        if fy in (before_fy, after_fy):
            rows += parsed
    windows = {before_fy: "before", after_fy: "after"}
    years_per_window = 1.0

    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": []} for num in divisions}
    method_counts = Counter()
    excluded = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    suppliers = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    not_counted = Counter()
    for r in rows:
        v = float(r["amount"])
        window = windows.get(r["fiscal_year"])
        if v <= 0 or not window:
            continue
        u = upper(r["payee"])
        if NOT_COUNTED.match(upper(r["department"])):
            not_counted[(window, r["department"])] += v
            continue
        if EXCLUDED_DEPARTMENTS.match(upper(r["department"])) or PENSIONS.search(u):
            excluded[(window, "pensions and tax credits")] += v
            continue
        if INDIVIDUAL_PROGRAMS.search(u):
            excluded[(window, "individual programs")] += v
            continue
        if INTERNAL.search(u):
            excluded[(window, "refunds and trust funds")] += v
            continue
        if looks_individual(r["payee"]):
            excluded[(window, "individuals")] += v
            continue
        pw = PROVINCEWIDE.search(upper(r["payee"])) or OTHER_GOVERNMENT.search(upper(r["payee"]))
        if not pw and is_supplier(r["payee"]):
            excluded[(window, "suppliers")] += v
            if window == "after":
                suppliers[r["payee"]] += v
            continue
        num, how = place(r)
        if how == "outside Manitoba":
            excluded[(window, "outside Manitoba")] += v
            continue
        if num is None:
            kind = "province-wide bodies" if pw else "unmatched"
            excluded[(window, kind)] += v
            if window == "after" and kind == "unmatched":
                unmatched[r["payee"]] += v
            continue
        flag = flag_for(r, how)
        method_counts[(window, how)] += 1
        p = per[num]
        p[window]["total"] += v
        p[window]["n"] += 1
        if not flag:
            p[window]["adj"] += v
            p[window]["adj_n"] += 1
        else:
            flagged_total[(window, r["payee"])] += v
        if window == "after":
            label = r["department"]
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
        by_recipient = defaultdict(lambda: {"v": 0.0, "n": 0, "progs": Counter(), "flag": "", "how": "", "last": "", "town": ""})
        for v, r, fl, how in p["grants"]:
            g = by_recipient[r["payee"]]
            g["v"] += v
            g["n"] += 1
            g["progs"][r["department"]] += v
            g["flag"], g["how"], g["last"], g["town"] = fl, how, max(g["last"], r["fiscal_year"]), r["town"]
        top = sorted(by_recipient.items(), key=lambda kv: -kv[1]["v"])[:10]
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"], "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]),
            "pc_after": round(a["adj"] / pop / years_per_window, 2), "pc_after_all": round(a["total"] / pop / years_per_window, 2),
            "pc_before": round(b["adj"] / pop / years_per_window, 2),
            "close": dv["margin_pts"] < CLOSE_MARGIN,
            "gov_won": dv["party_2023"] == GOV_PARTY,
            "top_progs": [[k, round(v)] for k, v in p["progs"].most_common(4)],
            "top_grants": [{"v": round(g["v"]), "who": (who + (f" ({g['town'].title()})" if g["town"] else ""))[:80], "n": g["n"],
                            "prog": "; ".join(k for k, _ in g["progs"].most_common(2))[:120],
                            "date": g["last"], "flag": g["flag"], "how": g["how"]} for who, g in top],
        })
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
        "top_suppliers": [[k, round(v)] for k, v in suppliers.most_common(20)],
        "not_counted_after": {f"{d} (payments to banks and bondholders, left out of total_after)": round(v) for (w, d), v in not_counted.items() if w == "after"},
        "programs": sorted(prog_totals, key=lambda d: -sum(prog_totals[d].values()))[:60],
    }
    json.dump({"meta": meta, "groups": groups, "ridings": out,
               "prog_by_riding": {k: {n: round(v) for n, v in m.items()} for k, m in prog_totals.items() if k in meta["programs"]}},
              open(OUT / "division_spending.json", "w"), ensure_ascii=False)
    print(json.dumps({k: v for k, v in meta.items() if k not in ("programs",)}, indent=1, ensure_ascii=False))
    print(json.dumps(groups, indent=1))
    placed = meta["placed_after"]
    print(f"\nafter window {after_fy}: ${total_after:,.0f} parsed, ${placed:,.0f} placed ({100 * placed / total_after:.0f}%), "
          f"adjusted ${sum(x['after_adj'] for x in out.values()):,.0f}")


if __name__ == "__main__":
    main()
