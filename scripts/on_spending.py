"""Ontario: aggregate provincial payments by riding.

Reads data/raw/on/dl/payments-YYYY-YY-en.csv (data.ontario.ca "Public Accounts: Detailed
Schedule of Payments", dataset 56c9a95f-c7b6-40ee-a4b8-d2343e51c83d, one CSV per fiscal
year; columns Amount $, Ministry, Category, Payment Detail, Recipient, Statutory,
Additional Detail) and data/on/divisions.json (from on_prep.py). Writes
data/on/division_spending.json with the same shape as the New Brunswick file.

What the schedule contains. Every ministry's payments for the year, by recipient, above
the Public Accounts thresholds: transfer-payment recipients of $120,000 or more,
suppliers (goods and services) of $50,000 or more, with the remainder rolled into
"Accounts Under $120,000" / "Accounts Under $50,000" lines. No address, no program (the
"Payment Detail" field names a vote item for Health and a few other ministries and is
"No Value" for most), no date. The Category values and how they are treated here:
  * "Transfer Payments" (2025-26: $189.4 B over 8,810 lines) and "Statutory Payments"
    whose Payment Detail is "Transfer Payments" ($0.4 B, statutory grants to
    municipalities): the grants. These are placed and counted, subject to the
    classification below.
  * "Other Payments" ($12.4 B, 5,330 lines): the supplier list, operating expenses paid to
    vendors (also "Loans Receivable", "Tangible Capital Assets", "Other Transactions").
    Placed when they can be and flagged "supplier", as nb_spending.py flags suppliers it
    finds by name among the grants: they appear in a riding's top recipients and in
    pc_after_all but not in the adjusted totals.
  * "Treasury Program" (interest on debt, $16.3 B), "Statutory Payments" other than
    transfers (the Ontario Teachers' retirement compensation arrangement, the Building
    Ontario Fund, the English and Wabigoon River mercury settlement, ministers'
    salaries, $4.8 B), "Employee Benefits" ($2.8 B), "Travel Expenses" ($77 M, named
    employees and members), "Salaries And Wages" (temporary help, $71 M), "Election
    Expense Subsidies Payments" ($21 M, Elections Ontario's rebates to candidates and
    parties), "Recoveries", "Other Transactions": not payees in the grant sense; dropped,
    with their totals in meta.other_payment_types_after. The 2024-25 file also writes
    "Advances Under Education Act" ($26 M to school boards) and stray trailing-space
    variants of the category names, which are stripped.
  * Lines that are programme aggregates rather than payees: "Payments Made For Services
    And Care Provided By Physicians And Practitioners" (OHIP fee-for-service, $21.2 B),
    "Odb" (Ontario Drug Benefit claims, $10.4 B), "Assistive Devices And Supplies
    Program" ($120 M), "Student Loan Receivable" count under excluded_after
    ["individuals"]; "Accounts Under $120,000" / "$50,000" ($7.6 B) under
    excluded_after["accounts under threshold"]; "Less: ..." recoveries are negative and
    skipped.
So:
  * Ministry stands in for the program: the program labels (top_progs, programs,
    prog_by_riding, top_grants.prog) are ministry names ("Ministry of Health"), and
    top_grants.date is the fiscal-year label "FY2025-26".
  * Windows are whole fiscal years. The election was 27 February 2025. "after" is fiscal
    2025-26 (1 April 2025 to 31 March 2026), the first full year after the vote; "before"
    is fiscal 2023-24 (1 April 2023 to 31 March 2024), the last full year before it.
    Fiscal 2024-25 straddles the election (eleven months before, one after) and is read
    for the coverage table (meta.coverage, totals by category for each year) and the
    series, not the windows. Every year read feeds a per-riding time series of adjusted
    dollars (ridings[num].series, aligned to meta.series.labels), placed and flagged
    exactly as the windows are.
    years_per_window = 1.0. meta: election 2025-02-27, cutoff 2026-03-31,
    before_start/before_end = the before year.

Each payment is placed by the recipient's name, in this order (as nb_spending.py does):
  1. the same name in the federal grants file, data/name_postal.json ("ON|name" keys,
     114,000 Ontario recipients of federal grants with their postal code);
  2. the CRA list of registered charities with Province ON (name -> postal code);
  3. a municipality name ("City of X", "The Corporation of the Town of X (O/A Town of
     X)", "Corp of the Township of X", "Municipality of X", "County of X", "Regional
     Municipality of X", "United Counties of X", "District Municipality of X", or just
     "X" when the whole payee name is a place with 20+ postal codes) or a First Nation
     ("X First Nation", "Chippewas of X", "Mississaugas of X", "Mohawks of X", "Ojibways
     of X", "X Indian Band", "X Band", "X Nation") -> the centroid of that place's
     GeoNames postal codes, or of the 2021 census subdivision of that name (the reserve
     and township centroids on_prep.py cached for the north), or PLACE_ALIASES
     (hand-set: single-tier municipalities whose name is not a GeoNames place, such as
     Chatham-Kent, Kawartha Lakes, Greater Sudbury, Norfolk County, and First Nations
     whose band name differs from their community's, such as Six Nations -> Ohsweken,
     Kitchenuhmaykoosib Inninuwug -> Big Trout Lake, Nipissing First Nation -> Garden
     Village);
  4. a place name inside the recipient's name ("Wingham & District Hospital", "Community
     Living Fort Frances And District"); when several match, the place with the most
     GeoNames postal codes wins ("Scarborough Centre For Healthy Communities" ->
     Scarborough; "Brockville & Area Community Living Association" -> Brockville).
Postal codes and place names come from GeoNames CA_full.txt (province ON: 1,261 place
names, 298,000 codes; "St"/"Ste" expanded to "Saint"/"Sainte", accents and punctuation
stripped) and are located by point-in-polygon on the riding boundaries in
data/on/divisions_geo.json. Place names that are also surnames, ordinary words, counties
or regions (Simcoe, York, Durham, Dundas, Perth, Cochrane, Scotland, Centre, ...) are
never place hits in step 4; counties and regions reach the map through step 3 instead.

Classification (decided before placing; each bucket's dollars are in meta.buckets_after):
  * "individuals": the programme aggregates above and payees written "Surname, Given";
    never placed, counted under excluded_after["individuals"].
  * "out-of-province": the Government of Canada (Receiver General, Canada Revenue Agency,
    Crown-Indigenous Relations, ...), other provinces and territories and bodies named
    for them, foreign governments and universities elsewhere; never placed. National
    bodies with their head office in Ontario (Canadian Blood Services, Canada Health
    Infoway, Canadian Institute for Health Information, the Salvation Army, March of
    Dimes Canada, VON Canada, ...) are "province-wide" instead, since they are in Ontario.
  * "province-wide": Ontario Health and its agencies (Ontario Health atHome, Public Health
    Ontario, Supply Ontario, the Ontario Government Pharmacy), Metrolinx, the Independent
    Electricity System Operator, Ontario Power Generation, Hydro One, Infrastructure
    Ontario, Ontario Northland, Legal Aid Ontario, the Ontario Trillium Foundation, the
    Ontario Arts Council, Ornge, Agricorp, the Northern Ontario Heritage Fund, the LCBO,
    OLG, the WSIB, the pension plans, the Ontario Medical Association, Crown agencies and
    attractions (Science Centre, ROM, AGO, Ontario Place, Heritage Trust), school boards
    (District School Board, Conseil scolaire, School Authority), universities and
    colleges (and their governing councils, the Michener Institute, NOSM), provincial
    Indigenous political organisations and tribal councils (Chiefs of Ontario, Nishnawbe
    Aski Nation, Métis Nation of Ontario, Anishinabek Nation, Grand Council Treaty #3,
    Matawa, Keewaytinook Okimakanak, Mushkegowuk Council, Windigo, Shibogama, ...),
    bodies named "... of Ontario" / "Ontario ..." / "de l'Ontario" (associations,
    federations, foundations, councils, divisions of national charities), "Province of",
    "Government of", "Ministry of". Hospitals are NOT province-wide: they are placed and
    counted where they stand, including the big Toronto, Hamilton, London and Ottawa
    academic centres, so the ridings that hold a teaching hospital carry its whole
    operating grant. Province-wide bodies are placed when a location is known (so they
    show in the riding's top recipients, flagged) and excluded from the adjusted totals;
    when they cannot be placed they count under excluded_after["province-wide bodies"].
  * "other government": the governments of Toronto, Ottawa, Mississauga, Brampton,
    Hamilton, London, Markham, Vaughan, Kitchener and Windsor (always), every regional
    municipality, county, united counties, district municipality, district social
    services administration board and district services board, public health units,
    conservation authorities, municipal police, transit, library, housing and paramedic
    boards of those bodies, and any other municipality whose GeoNames postal codes fall
    materially (over 15%) outside one riding (Oakville, Burlington, Barrie, Oshawa,
    Kingston, Greater Sudbury, Thunder Bay, Chatham-Kent, ...). Placed and flagged.
  * "supplier": every "Other Payments" line, and among the transfer payments the obvious
    suppliers of goods and services: names ending in Ltd, Limited, Corp, LLC, LLP, LP,
    Limited Partnership or GP Inc; names with an industry word (construction, paving,
    consulting, engineering, software, pharma, laboratories, telecom, energy, equipment,
    sales, rentals, manufacturing, trucking, insurance, banks, law firms, "in trust");
    numbered companies ("2617322 Ontario Inc", "Ontario Corporation # 1961052, ...");
    the for-profit long-term-care and home-care chains booked at a head office
    (Extendicare, Schlegel, Sienna/Leisureworld, Southbridge/CVH, Revera, Chartwell,
    Axium, Kindera, Omni, Regency, Caressant Care, Vigour, Responsive, Jarlette,
    Primacare, Bayshore, ParaMed, SE Health, CarePartners, Closing the Gap, Spectrum, VHA
    Home HealthCare); the Assistive Devices Program's vendors (hearing clinics, Motion,
    Praxair, Dexcom, Costco); private laboratories (LifeLabs, Dynacare, Alpha); and the
    student-loan servicer D+H. A care or community word (home, manor, lodge, villa,
    centre, care, housing, co-op, association, society, club, church, festival, museum,
    school, First Nation, ...) overrides the Ltd/industry tests, because many of Ontario's
    non-profit homes, child-care centres and community agencies are incorporated; but a
    strong supplier word (construction, paving, truck, leasing, equipment, hotel,
    insurance, bank, in trust, holdings, limited partnership, "Homes Inc", ...) is a
    supplier whatever else the name says. Suppliers are placed when they can be and
    flagged (so pc_after_all keeps them and pc_after leaves them out); unplaced ones
    count under excluded_after["suppliers"].
  * everything else (hospitals, community health centres, Children's Aid Societies,
    community living agencies, non-profit long-term-care homes, child-care centres,
    municipalities inside one riding, First Nations, conservation groups, local arts and
    sports bodies, small businesses paid by Agriculture, Northern Development or
    Economic Development) counts in the adjusted totals.

Groups: "Close PC", "Close opposition", "Safe PC", "Safe opposition"; gov_won means the Progressive
Conservatives (who won government in 2025) won the seat; close means a margin under 10
points. Liberal, Green and Independent seats fall in the "NDP" (not government) groups.

Checking the rules: ON_PLACEMENTS=/path/to/file.tsv python3 scripts/on_spending.py also
writes every row's window, ministry, category, recipient, amount, riding, method and flag.

Result on 26 October 2026 (FY2025-26 as "after", $202.1 B of transfer and other payments):
63% of the dollars placed in a riding (most of it school boards, Metrolinx, the IESO,
universities and the big-city governments, flagged), 24% counted in the adjusted
per-person figures (hospitals are two thirds of that), 16% programme aggregates that pay
individuals (OHIP physician billings, the Ontario Drug Benefit, student loans), 9%
province-wide bodies that could not be placed (Ontario Health, Infrastructure Ontario,
Agricorp, Legal Aid, several school boards and colleges), 7% suppliers that could not be
placed, 4% accounts under the reporting thresholds, 0.5% unmatched (mostly long-term-care
homes with no place in their name), 0.1% out of province. meta.coverage has each year's
totals by category.
"""
import csv
import json
import os
import re
import statistics
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DL = RAW / "on" / "dl"
OUT = ROOT / "data" / "on"
sys.path.insert(0, str(ROOT / "scripts"))
from geo import RidingIndex, load_centroids  # noqa: E402
from build_spending import formula_matcher, recipient_table  # noqa: E402

ELECTION = date(2025, 2, 27)
CUTOFF = date(2026, 3, 31)
BEFORE_START, BEFORE_END = date(2023, 4, 1), date(2024, 3, 31)
YEARS = 1.0
CLOSE_MARGIN = 10.0
GOV_PARTY = "PC"
OPP_LABEL = "opposition"  # the NDP, Liberals, Greens and independents together, as on the federal page
# Fiscal year ending -> window; 2025 (which straddles the election) is read for the coverage table and the series only.
WINDOWS = {2026: "after", 2024: "before"}
COVERAGE_YEARS = [2024, 2025, 2026]
# data.ontario.ca resource ids of the English CSV for each fiscal year ending; the CSVs are loaded in
# the CKAN datastore, so top_grants.src is a datastore_search for the recipient's exact name.
DATASET_URL = "https://data.ontario.ca/dataset/public-accounts-detailed-schedule-of-payments"
RESOURCES = {2024: "e594c01c-395f-4143-9a6b-bfb9bd4bcac3", 2025: "1677dc37-00e5-437a-bb39-c918b243f9a9",
             2026: "3ab37bb7-4f51-4d90-951b-b9d566f65898"}
SEARCH_URL = "https://duckduckgo.com/?q={q}+Ontario+grant"  # {q}: the recipient, URL-encoded by the page


def source_url(r):
    """The row's lines in the datastore of the year's CSV (the dataset page when the year is not listed)."""
    rid = RESOURCES.get(r["fye"])
    if not rid:
        return DATASET_URL
    return "https://data.ontario.ca/api/3/action/datastore_search?" + urlencode(
        {"resource_id": rid, "filters": json.dumps({"Recipient": r["Recipient"]})})
WINDOW_NOTE = ("after = FY2025-26 (1 April 2025 to 31 March 2026), the first full fiscal year after the 27 February 2025 election; "
               "before = FY2023-24 (1 April 2023 to 31 March 2024), the last full fiscal year before it; FY2024-25 straddles the "
               "election and is read for the coverage table only; annual data, no payment dates")

AGGREGATE_INDIVIDUALS = re.compile(r"^PAYMENTS MADE FOR SERVICES AND CARE|^ODB\b|^ASSISTIVE DEVICES AND SUPPLIES PROGRAM$|"
                                   r"STUDENT LOAN RECEIVABLE|^ONTARIO STUDENT ASSISTANCE|^LOANS? RECEIVABLE$|^OTHER TRANSACTIONS$|"
                                   r"^GAINS\b|GAINSTPS|GUARANTEED ANNUAL INCOME|NORTHERN HEALTH TRAVEL GRANT|^IHF$|INDEPENDENT HEALTH FACILIT|"
                                   r"RMIS MVAC|MVAC CLAIM|MOTOR VEHICLE ACCIDENT CLAIMS|ONTAXREBAT|TAX REBATE|TAX CREDIT|ONTARIO CHILD BENEFIT|"
                                   r"^ONTARIO WORKS$|^ODSP$|ONTARIO DISABILITY SUPPORT PROGRAM$|^TRILLIUM DRUG|^OHIP\b", re.I)
# Recipients whose postal code in the federal file is a branch, not the head office (Hamilton Health
# Sciences -> West Lincoln Memorial in Grimsby, William Osler -> Peel Memorial, Sinai Health -> a PO box).
RECIPIENT_POSTAL = {"HAMILTON HEALTH SCIENCES CORP": "L8L2X2", "HAMILTON HEALTH SCIENCES": "L8L2X2",
                    "WILLIAM OSLER HEALTH SYSTEM": "L6R3J7", "SINAI HEALTH SYSTEM": "M5G1X5", "SINAI HEALTH": "M5G1X5"}
# Recipients that no name list places: head-office town (place_norm keys).
RECIPIENT_PLACES = {"BRUYERE HEALTH": "OTTAWA", "BRUYERE CONTINUING CARE": "OTTAWA", "UNISON HEALTH COMMUNITY SERVICES": "NORTH YORK",
                    "SERVICE COORDINATION FOR PERSONS WITH SPECIAL NEEDS": "OTTAWA", "KINARK CHILD FAMILY SERVICES": "MARKHAM",
                    "CHILDREN FAMILY SERVICES FOR YORK REGION": "NEWMARKET", "ST JOSEPHS GENERAL HOSPITAL": "ELLIOT LAKE",
                    "HOMEWOOD HEALTH CENTRE": "GUELPH", "RUNNYMEDE LONG TERM CARE": "TORONTO", "RUNNYMEDE HEALTHCARE CENTRE": "TORONTO",
                    "CANADIAN MENTAL HEALTH ASSOC CMHA YORK REGION": "NEWMARKET", "EAST NIPISSING DISTRICT HOME FOR AGED": "NORTH BAY",
                    "FAIRHAVEN HOME FOR SENIOR CITIZENS": "PETERBOROUGH", "TREATY THREE POLICE SERVICES": "KENORA", "FAIRVIEW LODGE": "WHITBY",
                    "NORWEST COMMUNITY HEALTH CENTRE": "THUNDER BAY", "TENDERCARE LIVING CENTRE": "SCARBOROUGH", "HERITAGE NURSING HOME": "TORONTO",
                    "COMMUNITY HOME ASSISTANCE TO SENIORS": "TORONTO", "WAASEGIIZHIG NANAANDAWE IYEWIGAMIG HEALTH ACCESS CENTRE": "KENORA",
                    "MAPLEWOOD NURSING HOME": "BRIGHTON", "ANISHINABEK POLICE SERVICES": "GARDEN RIVER", "NISHNAWBE ASKI POLICE": "THUNDER BAY",
                    "HOTEL DIEU GRACE HEALTHCARE": "WINDSOR", "PROVIDENCE CARE": "KINGSTON", "ST JOSEPH S CARE GROUP CORP": "THUNDER BAY",
                    "WEENEEBAYKO AREA HEALTH AUTHORITY": "MOOSE FACTORY", "HEALTH SCIENCES NORTH": "SUDBURY", "SOUTHLAKE HEALTH": "NEWMARKET",
                    "QUINTE HEALTH": "BELLEVILLE", "BRIGHTSHORES HEALTH SYSTEM": "OWEN SOUND", "HUMBER RIVER HEALTH": "NORTH YORK",
                    "PEOPLECARE NOT FOR PROFIT HOMES PERLEY RIDEAU VETERANS HEALTH CENTRE": "OTTAWA", "PERLEY RIDEAU VETERANS HEALTH CENTRE": "OTTAWA",
                    "PERLEY HEALTH": "OTTAWA", "CASSELLHOLME": "NORTH BAY", "VHA HEALTH HOME SUPPORT": "TORONTO", "HENLEY HOUSE": "ST CATHARINES",
                    "GEORGE HULL CENTRE FOR CHILDREN FAMILIES": "ETOBICOKE", "ROBERTA PLACE": "BARRIE", "ALEXANDER PLACE": "WATERDOWN",
                    "EASTERN ONTARIO REGIONAL LABORATORY ASSOCIATION EORLA": "OTTAWA", "NIAGARA CHILDRENS CENTRE": "ST CATHARINES",
                    "O NEILL CENTRE": "TORONTO", "VALLEY EAST LONG TERM CARE CENTRE": "HANMER", "FINLANDIA NURSING HOME": "THUNDER BAY",
                    "VILLA MARCONI": "OTTAWA", "MIZIWE BIIK DEVELOPMENT": "TORONTO", "LEEDS GRENVILLE LANARK": "BROCKVILLE",
                    "CHIPPAWA CREEK CARE CENTRE": "NIAGARA FALLS", "HILLCREST VILLAGE": "MIDLAND", "WORKPLACE SAFETY NORTH": "NORTH BAY"}
UNDER_THRESHOLD = re.compile(r"ACCOUNTS UNDER|COMPTES INFERIEURS|^LESS:", re.I)
# "Surname, Given" (one to three words each side, no corporate word): a person.
PERSON = re.compile(r"^[A-Z'\-]+( [A-Z'\-]+){0,2}, [A-Z'\-.]+( [A-Z'\-.]+){0,3}$")
NOT_PERSON = re.compile(r"\b(INC|LTD|LLP|LLC|LP|ULC|LIMITED|CORP|CO|DIVISION|PLAN|OFFICE|SERVICES?|GROUP|TRUST|PARTNERS|CONSULTANTS?|CONSULTING|"
                        r"ASSOCIATES|CANADA|ONTARIO|CENTRE|CENTER|FARMS?|HOLDINGS|ENTERPRISES|AGENCY|CLINIC|COMMUNITY|INITIATIVE|RESOURCES|"
                        r"PHARMACY|FOUNDATION|DEPARTMENT|HOSPITALS?|UNIVERSITY|CITY|TOWN|VILLAGE|OCULARIST|AUDIOLOG\w*|HEARING|SUPPORTS?|"
                        r"YOUTH|FAMILY|CHILD|THE|OF|AND)\b")
OUT_OF_PROVINCE = re.compile(
    r"RECEIVER GENERAL|CANADA REVENUE|GOVERNMENT OF (CANADA|ALBERTA|YUKON|QUEBEC|NOVA SCOTIA|MANITOBA|SASKATCHEWAN|BRITISH COLUMBIA|"
    r"PRINCE EDWARD ISLAND|NEWFOUNDLAND|NUNAVUT|NORTHWEST|THE NORTHWEST|NEW BRUNSWICK)|GOUVERNEMENT DU (CANADA|QUEBEC)|"
    r"HIS MAJESTY|HER MAJESTY|MINISTER OF FINANCE - |CROWN-INDIGENOUS|INDIGENOUS SERVICES CANADA|PUBLIC HEALTH AGENCY OF CANADA|"
    r"HEALTH CANADA|TRANSPORT CANADA|NATURAL RESOURCES CANADA|ENVIRONMENT (AND CLIMATE CHANGE )?CANADA|EMPLOYMENT AND SOCIAL DEVELOPMENT|"
    r"STATISTICS CANADA|CANADA MORTGAGE|\bCMHC\b|INFRASTRUCTURE CANADA|CANADIAN ARMED FORCES|DEPARTMENT OF NATIONAL DEFENCE|"
    r"ROYAL CANADIAN MOUNTED|\bRCMP\b|CANADA BORDER|CORRECTIONAL SERVICE CANADA|CANADA POST|POSTES CANADA|"
    r"MINISTRY OF FINANCE (QUEBEC|MANITOBA)|MINISTERE DES FINANCES DU QUEBEC|MINISTRE DES FINANCES DU QUEBEC|REGIE DE L'ASSURANCE|"
    r"\bNOVA SCOTIA\b|\bQUEBEC\b|\bPRINCE EDWARD ISLAND\b|\bNEWFOUNDLAND\b|\bALBERTA\b|\bBRITISH COLUMBIA\b|\bMANITOBA\b|\bSASKATCHEWAN\b|"
    r"\bYUKON\b|\bNUNAVUT\b|NORTHWEST TERRITORIES|\bNEW BRUNSWICK\b|"
    r"MCGILL|DALHOUSIE|UNIVERSITE DE MONTREAL|UNIVERSITE LAVAL|UNIVERSITE DU QUEBEC|UNIVERSITY OF (ALBERTA|BRITISH COLUMBIA|MANITOBA|"
    r"SASKATCHEWAN|CALGARY|VICTORIA|NEW BRUNSWICK)|SIMON FRASER|MEMORIAL UNIVERSITY|CONCORDIA UNIVERSITY|"
    r"STATE OF|UNITED STATES|U\.S\.|TREASURER OF|CITY OF (MONTREAL|GATINEAU|DETROIT|BUFFALO|WINNIPEG)|VILLE DE|"
    r"COUNCIL OF THE FEDERATION|CANADIAN COUNCIL OF MINISTERS|INTERPROVINCIAL|INTERNATIONAL REGISTRATION PLAN|UNITED NATIONS|WORLD HEALTH",
    re.I)
PROVINCEWIDE = re.compile(
    r"^ONTARIO HEALTH\b|ONTARIO HEALTH AT ?HOME|HOME AND COMMUNITY CARE SUPPORT SERVICES|LOCAL HEALTH INTEGRATION NETWORK|\bLHIN\b|"
    r"ONTARIO AGENCY FOR HEALTH PROTECTION|PUBLIC HEALTH ONTARIO|CENTRALIZED SUPPLY CHAIN|SUPPLY ONTARIO|ONTARIO GOVERNMENT PHARMACY|"
    r"CANCER CARE ONTARIO|TRILLIUM GIFT OF LIFE|HEALTH SHARED SERVICES|HEALTHFORCEONTARIO|HEALTH QUALITY ONTARIO|EHEALTH ONTARIO|"
    r"ONTARIO TELEMEDICINE|ONTARIO MEDICAL ASSOCIATION|ONTARIO PHYSICIAN SERVICES|ONTARIO HOSPITAL ASSOCIATION|ONTARIO NURSES|"
    r"ONTARIO PHARMACISTS|ONTARIO DENTAL|ONTARIO LONG TERM CARE ASSOCIATION|ADVANTAGE ONTARIO|ASSOCIATION OF MUNICIPALITIES OF ONTARIO|"
    r"^METROLINX|INDEPENDENT ELECTRICITY SYSTEM OPERATOR|\bIESO\b|ONTARIO POWER GENERATION|HYDRO ONE|ONTARIO ELECTRICITY FINANCIAL|"
    r"ONTARIO ENERGY BOARD|ONTARIO INFRASTRUCTURE AND LANDS|INFRASTRUCTURE ONTARIO|ONTARIO NORTHLAND|ONTARIO CLEAN WATER|"
    r"LIQUOR CONTROL BOARD|\bLCBO\b|ONTARIO LOTTERY|\bOLG\b|ONTARIO CANNABIS|ONTARIO FINANCING AUTHORITY|ONTARIO SECURITIES|"
    r"ONTARIO TEACHERS|TEACHERS' PENSION|TEACHERS PENSION|\bOMERS\b|PENSION PLAN|PENSION BOARD|RETIREMENT COMPENSATION|"
    r"WORKPLACE SAFETY (AND|&) INSURANCE|\bWSIB\b|LEGAL AID ONTARIO|AIDE JURIDIQUE ONTARIO|ONTARIO TRILLIUM FOUNDATION|FONDATION TRILLIUM|"
    r"ONTARIO ARTS COUNCIL|CONSEIL DES ARTS DE L'ONTARIO|ONTARIO MEDIA DEVELOPMENT|ONTARIO CREATES|\bORNGE\b|^AGRICORP|"
    r"NORTHERN ONTARIO HERITAGE FUND|ONTARIO SCIENCE CENTRE|ROYAL ONTARIO MUSEUM|ART GALLERY OF ONTARIO|ONTARIO PLACE|ONTARIO HERITAGE TRUST|"
    r"MCMICHAEL CANADIAN|SCIENCE NORTH|DESTINATION ONTARIO|INVEST ONTARIO|ONTARIO CENTRE OF INNOVATION|ONTARIO CENTRES OF EXCELLENCE|"
    r"ONTARIO RESEARCH FUND|ONTARIO GENOMICS|ONTARIO INSTITUTE FOR CANCER|ONTARIO BRAIN INSTITUTE|ONTARIO INSTITUTE FOR|"
    r"TECHNICAL STANDARDS (AND|&) SAFETY|ELECTRICAL SAFETY AUTHORITY|ONTARIO ONE CALL|TARION|BUILDING ONTARIO FUND|"
    r"ONTARIO EDUCATIONAL COMMUNICATIONS|\bTVO\b|\bTFO\b|GROUPE MEDIA TFO|EDUCATION QUALITY AND ACCOUNTABILITY|ONTARIO COLLEGE OF TEACHERS|"
    r"ONTARIO STUDENT|ONTARIO UNIVERSITIES|COUNCIL OF ONTARIO UNIVERSITIES|COLLEGES ONTARIO|ECAMPUSONTARIO|CONTACT NORTH|"
    r"DISTRICT SCHOOL BOARD|SCHOOL BOARD|BOARD OF EDUCATION|SCHOOL AUTHORITY|CONSEIL SCOLAIRE|CONSEIL DES ECOLES|SCHOOL DISTRICT|"
    r"UNIVERSITY|UNIVERSITE|GOVERNING COUNCIL OF THE UNIVERSITY|COLLEGE OF APPLIED ARTS|INSTITUTE OF TECHNOLOGY|POLYTECHNIC|"
    r"COLLEGE D'ARTS APPLIQUES|COLLEGE BOREAL|LA CITE COLLEGIALE|^LA CITE\b|MICHENER INSTITUTE|NORTHERN ONTARIO SCHOOL OF MEDICINE|"
    r"\bNOSM\b|ROYAL MILITARY COLLEGE|"
    r"CHIEFS OF ONTARIO|NISHNAWBE ASKI|NISHNAWBE-ASKI|METIS NATION OF ONTARIO|ANISHINABEK NATION|UNION OF ONTARIO INDIANS|"
    r"GRAND COUNCIL TREATY|ASSOCIATION OF IROQUOIS|INDEPENDENT FIRST NATIONS ALLIANCE|ONTARIO FEDERATION OF INDIGENOUS FRIENDSHIP|"
    r"ONTARIO NATIVE WOMEN|ONTARIO ABORIGINAL HOUSING|ONTARIO FIRST NATIONS|FIRST NATIONS (OF ONTARIO|TECHNICAL|HEALTH|EDUCATION)|"
    r"TRIBAL COUNCIL|KEEWAYTINOOK OKIMAKANAK|NORTHERN CHIEFS|MATAWA|MUSHKEGOWUK COUNCIL|WINDIGO FIRST NATIONS|SHIBOGAMA|BIMOSE|WABUN|"
    r"WAABNOONG|UNITED CHIEFS (AND|&) COUNCILS|MAMAWESWEN|NOKIIWIN|OGEMAWAHJ|KENORA CHIEFS ADVISORY|SIOUX LOOKOUT FIRST NATIONS HEALTH|"
    r"ANISHINAABE ABINOOJII|TIKINAGAN|PAYUKOTAYNO|DILICO|WEECHI-IT-TE-WIN|NOGDAWINDAMIN|KUNUWANIMANO|NIIJAANSINAANIK|"
    r"\bPROVINCE OF\b|\bGOVERNMENT OF\b|\bMINISTER OF\b|\bMINISTRY OF\b|\bMINISTERE\b|TREASURY BOARD|OFFICE OF THE|LEGISLATIVE ASSEMBLY|"
    r"FAMILY SERVICE TORONTO|KARIS DISABILITY|CHRISTIAN HORIZONS|COMMUNITY LIVING ONTARIO|CONSORTIUM CENTRE JULES-LEGER|CENTRE JULES-LEGER|"
    r"INFRASTRUCTURE HEALTH AND SAFETY|WORKPLACE SAFETY (AND|&) PREVENTION|WORKPLACE SAFETY NORTH|PUBLIC SERVICES HEALTH (AND|&) SAFETY|FAIR HYDRO TRUST|"
    r"ONTARIO ELECTRICITY REBATE|PROVINCIAL SCHOOLS|CENTRE FRANCOPHONE DE TORONTO|"
    r"TEACHERS.? FEDERATION|FEDERATION OF TEACHERS|ELEMENTARY TEACHERS|SECONDARY SCHOOL TEACHERS|\bOSSTF\b|\bETFO\b|\bOECTA\b|\bAEFO\b|"
    r"\bCUPE\b|\bSCFP\b|\bOPSEU\b|\bSEFPO\b|ONTARIO NURSES|UNIFOR\b|"
    r"ONTARIO (ASSOCIATION|FEDERATION|SOCIETY|COUNCIL|FOUNDATION|COMMISSION|NETWORK|COALITION|ALLIANCE|INSTITUTE|UNION|TRUST|AGENCY|"
    r"CENTRE OF|CENTRE FOR|CHAMBER|BOARD|AUTHORITY|CORPORATION|HOCKEY|SOCCER|BASKETBALL|BASEBALL|VOLLEYBALL|CURLING|SKI|SPORTS?|"
    r"PARASPORT|SPECIAL OLYMPICS|4-H|FEDERATION OF AGRICULTURE|AGRI|CATTLE|PORK|SHEEP|CHICKEN|EGG|DAIRY|MILK|GRAIN|BEAN|SOYBEAN|"
    r"FRUIT|VEGETABLE|APPLE|GREENHOUSE|FORESTRY|FOREST|WOODLOT|TRAILS|SNOWMOBILE|ATV|LUNG|HEART|CANCER|STROKE|DIABETES|BRAIN|"
    r"LIBRARY|LIBRARIES|MUSEUM|HISTORICAL|GENEALOGICAL|ARTS|MUSIC|FILM|LITERACY|NONPROFIT|NON-PROFIT|CARIBBEAN|BLACK|JEWISH|"
    r"MULTICULTURAL|SENIORS|WOMEN|MEN|YOUTH|CHILDREN|FAMILY|DISABILITY|AUTISM|BRAIN INJURY|MARCH OF DIMES|SHORES|MEDICAL|"
    r"PHARMAC|DENTAL|CHIROPRACT|PSYCHOLOG|SOCIAL WORK|HOSPITAL ASSOCIATION|LONG TERM CARE ASSOCIATION|RETIREMENT COMMUNITIES|"
    r"HOME CARE ASSOCIATION|COMMUNITY SUPPORT ASSOCIATION|PUBLIC HEALTH ASSOCIATION|HEALTH COALITION|SALMON|WILDLIFE|NATURE|"
    r"LAND TRUST|INVASIVE|STEWARDSHIP|ENVIRONMENT|CLEAN|WATERPOWER|ENERGY|ROAD BUILDERS|HOME BUILDERS|GOOD ROADS|"
    r"MUNICIPAL|MUNICIPALITIES|RURAL|SMALL URBAN|NORTHERN|FRANCOPHON|FRANCO-ONTARI|ACFO|VOLUNTEER|CHARITABLE|"
    r"COMMUNITY (SUPPORT|HEALTH|LIVING|LEGAL|FUTURES|FOUNDATIONS?)|LEGAL CLINICS|POVERTY|HOUSING|TRANSIT|TOURISM|CRAFT|REAL ESTATE|"
    r"TRUCKING|CONSTRUCTION|TRADES|APPRENTICE|SKILLS|LEARN|LITERACY|SCIENCE|STEM|ROBOT|CODING|ENGINEERS|ARCHITECTS|PLANNERS|GEOLOG)|"
    r"(ASSOCIATION|FEDERATION|SOCIETY|SOCIETE|COUNCIL|CONSEIL|FOUNDATION|FONDATION|INSTITUTE|INSTITUT|NETWORK|RESEAU|COALITION|ALLIANCE|"
    r"ASSEMBLY|CHAMBER|BOARD|OFFICE|COMMISSION|CORPORATION|LEAGUE|CONFERENCE|UNION|TRUST|AUTHORITY|AGENCY|CENTRE|CENTER|DIVISION|"
    r"BRANCH|CHAPTER|REGION|PARTNERS|PARTNERSHIP|ORGANIZATION|ORGANISATION|COLLEGE|CONGRESS|BUREAU|SERVICE) "
    r"(OF|FOR|DU|DE|DES|POUR|IN) .*\bONTARIO\b|"
    r"\bONTARIO (DIVISION|BRANCH|CHAPTER|REGION|SECTION|COUNCIL)\b|, ONTARIO$|DE L'ONTARIO$|D'ONTARIO$|\bONTARIO$|^ONTARIO\b|"
    r"CANADIAN BLOOD SERVICES|CANADA HEALTH INFOWAY|CANADIAN INSTITUTE FOR HEALTH|CANADIAN MENTAL HEALTH ASSOCIATION,? ONTARIO|"
    r"CANADIAN RED CROSS|CROIX-ROUGE|SALVATION ARMY IN CANADA|MARCH OF DIMES CANADA|VICTORIAN ORDER OF NURSES|\bVON CANADA\b|"
    r"YMCA CANADA|BIG BROTHERS BIG SISTERS OF CANADA|UNITED WAY CENTRAIDE CANADA|CANADIAN CANCER SOCIETY|HEART (AND|&) STROKE FOUNDATION OF CANADA|"
    r"ALZHEIMER SOCIETY OF ONTARIO|CANADIAN NATIONAL INSTITUTE FOR THE BLIND|\bCNIB\b|CANADIAN HEARING|CANADIAN PARAPLEGIC|SPINAL CORD INJURY ONTARIO|"
    r"KIDS HELP PHONE|TELEHEALTH|CANADIAN STANDARDS|CANADIAN AGENCY FOR DRUGS|CANADA'S DRUG|MITACS|GENOME CANADA|CANADIAN FOUNDATION|"
    r"CANADIAN (ASSOCIATION|FEDERATION|SOCIETY|COUNCIL|INSTITUTE|NETWORK|ALLIANCE|COALITION|CENTRE|UNION) (OF|FOR) |"
    r"COMMISSIONAIRES|SKILLS CANADA|JUNIOR ACHIEVEMENT|SPECIAL OLYMPICS|SCOUTS CANADA|GIRL GUIDES OF CANADA|CANADIAN FORCES",
    re.I)
# "City of X" and friends; the payee name has had its parentheticals and "/" halves split off.
MUNI = re.compile(r"^(?:THE )?(?:CORPORATION OF |CORP OF |CORP\. OF |CORPORATION DE |MUNICIPAL CORPORATION OF )?(?:THE )?"
                  r"(CITY|TOWN|TOWNSHIP|TOWNSHIPS|VILLAGE|MUNICIPALITY|COUNTY|UNITED COUNTIES|REGIONAL MUNICIPALITY|DISTRICT MUNICIPALITY|"
                  r"UNITED TOWNSHIPS|INCORPORATED VILLAGE|IMPROVEMENT DISTRICT|VILLE|CITE|CANTON|MUNICIPALITE|COMTE|COMTES UNIS|"
                  r"MUNICIPALITE REGIONALE) (?:OF |DE |DES |DU |D |LA |LE |LES )?(.+?)(?: FOR | POUR |$)")
REGIONAL = re.compile(r"\b(REGIONAL MUNICIPALITY|REGION OF|COUNTY OF|COUNTIES OF|UNITED COUNTIES|DISTRICT MUNICIPALITY|"
                      r"DISTRICT SOCIAL SERVICES|SOCIAL SERVICES ADMIN(ISTRATION)? BOARD|DISTRICT SERVICES BOARD|\bDSSAB\b|REGIONAL NETWORK|"
                      r"HEALTH UNIT|PUBLIC HEALTH|BOARD OF HEALTH|CONSERVATION AUTHORITY|POLICE SERVICES? BOARD|POLICE SERVICE\b|"
                      r"TRANSIT COMMISSION|OC TRANSPO|PUBLIC LIBRARY BOARD|PARAMEDIC SERVICES?|EMERGENCY MEDICAL SERVICES|"
                      r"COMMUNITY HOUSING CORPORATION|HOUSING CORPORATION|HOUSING SERVICES CORPORATION|SERVICES BOARD)\b")
FIRST_NATION = re.compile(r"^(.+?) (FIRST NATION|FIRST NATIONS|INDIAN BAND|BAND COUNCIL|BAND|NATION|UNCEDED TERRITORY|CREE NATION|"
                          r"ANISHINABEK|ANISHINAABEK|ANISHNAWBEK|OJIBWAY NATION)(?:'S| S| OF .*)?\b|"
                          r"^(?:THE )?(?:CHIPPEWAS|MISSISSAUGAS|MOHAWKS|OJIBWAYS|OJIBWAS|OJIBWES|ALGONQUINS|MOHAWK COUNCIL|MOOSE CREE|"
                          r"ONEIDA NATION|DELAWARE NATION|MUNSEE-DELAWARE NATION|IROQUOIS|WAHTA MOHAWKS|SAUGEEN OJIBWAY NATION) "
                          r"(?:OF |AT )(?:THE )?(.+?)(?: FIRST NATION| UNCEDED| INDIAN BAND|$)")
# Spread over several ridings whatever the postal codes say.
BIG_CITIES = {"TORONTO", "OTTAWA", "MISSISSAUGA", "BRAMPTON", "HAMILTON", "LONDON", "MARKHAM", "VAUGHAN", "KITCHENER", "WINDSOR",
              "GREATER SUDBURY", "CHATHAM KENT"}
SUPPLIER_SUFFIX = re.compile(r"\b(LTD|LIMITED|CORP|CORPORATION|LLC|LLP|LP|L P|ULC|CO|COMPANY|GMBH|PLC|SA|AG|INCORPORATED)\b")
INC = re.compile(r"\bINC\b|\bINCORPORATED\b")
NUMBERED = re.compile(r"^\d{5,10} (ONTARIO|ONT|CANADA|CANADA CORPORATION|QUEBEC|ALBERTA|B C)\b|^ONTARIO CORP|^CANADA CORP|ONTARIO CORPORATION (#|NO)|"
                      r"\b\d{6,10} ONTARIO (INC|LTD|LIMITED)|O/A")
INDUSTRY = re.compile(
    r"\b(?:CONSTRUCTION|PAVING|CONTRACT(ING|OR|ORS)|CONSULT(ING|ANT|ANTS)|ENGINEER|ARCHITECT|SOFTWARE|TECHNOLOG|SYSTEMS|SOLUTIONS|"
    r"PHARMA|GLAXO|PFIZER|MERCK|NOVARTIS|SANOFI|ASTRAZENECA|ROCHE|BAYER|ABBVIE|GILEAD|AMGEN|JANSSEN|TAKEDA|NOVO NORDISK|ELI LILLY|"
    r"TELECOM|BELL CANADA|BELL MOBILITY|BELL ALIANT|ROGERS|TELUS|XPLOR|COGECO|ENERG(Y|IE|IES)|FUEL|PETROL|OIL\b|PROPANE|GAS\b|ESSO|SHELL|"
    r"ULTRAMAR|ENBRIDGE|UNION GAS|EQUIPMENT|SUPPL(Y|IES)|SALES|RENTAL|MANUFACTUR|TRUCK|AUTO\b|AUTOMOBILE|MOTORS|\bGMC\b|FORD\b|"
    r"CHEVROLET|TOYOTA|HONDA|NISSAN|HYUNDAI|KIA\b|ELECTRIC\b|ELECTRICAL|PLUMBING|HEATING|HVAC|EXCAVAT|ASPHALT|LUMBER|MACHIN|HOLDINGS|"
    r"ENTERPRISES|VENTURES|REALTY|PROPERTIES|DEVELOPMENTS|INVESTMENTS|INVESTMENT LP|TRADING|INDUSTR|LOGISTIC|TRANSPORT\b|TRANSPORTATION INC|"
    r"TRUCKING|MECHANICAL|STEEL|CONCRETE|ROOFING|WELDING|TOWING|TIRE\b|TIRES|INSURANCE|ASSURANCE|BANK\b|CREDIT UNION|CAISSE|LAW\b|"
    r"LEGAL\b|BARRISTER|IN TRUST|PRINTING|SECURITY|STAFFING|PERSONNEL|FLEXTRACK|IBM\b|MICROSOFT|ORACLE|DELL\b|XEROX|CANON\b|SIEMENS|"
    r"HONEYWELL|JOHNSON CONTROLS|KONE\b|OTIS\b|SCHINDLER|THYSSENKRUPP|MEDICAL SUPPL|DIAGNOSTIC|LABORATOR|LIFELABS|DYNACARE|CLEANING|"
    r"JANITORIAL|LANDSCAP|SNOW|FORESTRY|SAWMILL|PULP|PAPER\b|MINING|MINES\b|QUARR|GRAVEL|SAND\b|AGGREGATE|BUILDERS|BUILDING SUPPL|"
    r"HARDWARE|HOME HARDWARE|CANADIAN TIRE|COSTCO|WALMART|SOBEYS|LOBLAW|SUPERSTORE|METRO INC|STAPLES|GRAND & TOY|AMAZON|UBER|AIR CANADA|"
    r"PORTER|WESTJET|VIA RAIL|HOTEL|MOTEL|\bINN\b|RESTAURANT|PIZZ|CATERING|FOOD SERVICE|CAFETERIA|VENDING|COMPASS GROUP|ARAMARK|SODEXO|"
    r"AVIATION|AIRCRAFT|HELICOPT|MARINE\b|SHIPYARD|DREDG|FENCING|SIGNS?\b|GLASS|WINDOWS|DOORS|FLOOR|PAINT|CARPET|FURNITURE|APPLIANCE|"
    r"RADIO|BROADCAST|MEDIA\b|PUBLISH|ADVERTIS|MARKETING|COMMUNICATIONS? INC|DESIGN INC|STUDIO|PRODUCTIONS|SURVEY|GEOMATIC|"
    r"ENVIRONMENTAL (INC|LTD|SERVICES|CONSULT)|WASTE|RECYCL|DISPOSAL|SEPTIC|WATER TREATMENT|FILTRATION|UNIFORM|APPAREL|GROUP\b|GROUPE\b|"
    r"LEASING|BARRISTER|SOLICITOR|LAW OFFICE|LAW FIRM|PROFESSIONAL CORPORATION|EVISIT|VIRTUAL CARE|MANULIFE|SUN LIFE|CANADA LIFE|"
    r"GREAT-WEST|BLUE CROSS|GREEN SHIELD|DESJARDINS|ROYAL BANK|SCOTIABANK|\bBMO\b|\bTD\b|\bCIBC\b|NATIONAL BANK|APPLE CANADA|GOOGLE|"
    r"META PLATFORMS|FACEBOOK|ADOBE|SAP\b|CGI\b|DELOITTE|KPMG|ERNST & YOUNG|\bEY\b|PRICEWATERHOUSE|\bPWC\b|GRANT THORNTON|MNP\b|"
    r"ACCENTURE|GARTNER|ESRI|PUBLIC RELATIONS|ASSOCIATES INC|& ASSOCIATES|PARTNERS\b|MANAGEMENT INC|MANAGEMENT LTD|CAPITAL INC|"
    r"CAPITAL LTD|FINANCIAL|LEASE\b|RENT-?ALL|HOME DEPOT|RONA\b|LOWE'S|IKEA|BEST BUY|TRANSPORT LTD|TRANSPORT INC|FREIGHT|COURIER|"
    r"PUROLATOR|FEDEX|\bUPS\b|TIMBER|FOREST PRODUCTS|WOODLANDS|ACCERTA|DH CORPORATION|SOCIETE DH|D\+H|XPERA|EMCON|WEBBER|MILLER PAVING|"
    r"AECON|ELLISDON|PCL\b|BIRD CONSTRUCTION|KIEWIT|DUFFERIN CONSTRUCTION|CRH CANADA|LAFARGE|FOWLER|COCO PAVING|GIP PAVING|"
    r"IMOS\b|BREWERS RETAIL|BEER STORE|EXTENDICARE|SCHLEGEL|LEISUREWORLD|SIENNA|SOUTHBRIDGE|\bCVH\b|REVERA|CHARTWELL|AXIUM|KINDERA|"
    r"ROYALE DEVELOPMENT|OMNI HEALTHCARE|REGENCY LTC|CARESSANT|IRIS L\.?P|VIGOUR|RESPONSIVE GROUP|JARLETTE|PRIMACARE|PEOPLECARE|"
    r"STEEVES|RYKKA|APANS|BAYSHORE|PARAMED|SAINT ELIZABETH HEALTH|SE HEALTH|CAREPARTNERS|CLOSING THE GAP|SPECTRUM HEALTH|VHA HOME|"
    r"MOTION LP|PRAXAIR|DEXCOM|INSULET|MEDTRONIC|ABBOTT|INNOMAR|SHOPPERS|REXALL|HEARING|AUDIOLOG|OCULARIST|PROSTHETIC|ORTHOTIC|"
    r"RESPIRATORY|PRORESP|VITALAIRE|MEDIGAS|LINDE|\bLTD\b|\bLIMITED\b|\bCORP\b|\bLLC\b|\bLLP\b|\bULC\b|LIMITED PARTNERSHIP|\bLP\b|GP INC)",
    re.I)
NONPROFIT = re.compile(
    r"\b(?:HOME\b|HOMES\b|VILLA|MANOR|LODGE|FOYER|RESIDENCE|RESIDENCES|\bCARE\b|SOINS|CHILD ?CARE|DAYCARE|DAY CARE|GARDERIE|NURSING HOME|"
    r"NURSING|HOUSING|HABITATION|LOGEMENT|CO-?OP\b|COOPERATIVE|ASSOCIATION|SOCIETY|SOCIETE|FOUNDATION|FONDATION|\bCLUB\b|CHURCH|EGLISE|"
    r"PARISH|PAROISSE|DIOCESE|FESTIVAL|MUSEUM|MUSEE|THEATRE|THEATER|GALLERY|GALERIE|SYMPHONY|ORCHESTR|PHILHARMONIC|CHORAL|CHOIR|BALLET|"
    r"DANCE|DANSE|ARTS?\b|SCHOOL|ECOLE|ACADEMY|ACADEMIE|MONTESSORI|PRESCHOOL|KINDER|LEARNING|LITERACY|COMMUNITY|COMMUNAUTAIRE|COMMUNAUTE|"
    r"CENTRE\b|CENTER\b|COUNCIL|CONSEIL|COMMITTEE|COMITE|HOUSE\b|MAISON|TRANSITION|SHELTER|REFUGE|FAMILY|FAMILLE|YOUTH|JEUNESSE|SENIORS?|"
    r"AINES|LIBRARY|BIBLIOTH|FOOD BANK|BANQUE ALIMENTAIRE|SOUP KITCHEN|HOSPICE|PALLIATI|WELLNESS|MENTAL HEALTH|SANTE MENTALE|ADDICTION|"
    r"RECOVERY|CRISIS|SUPPORT|SOUTIEN|ENTRAIDE|VOLUNTEER|BENEVOL|CHARIT|LEGION|LIONS|KINSMEN|KIWANIS|ROTARY|KNIGHTS OF COLUMBUS|"
    r"SALVATION ARMY|YMCA|YWCA|BOYS AND GIRLS|BGC\b|BIG BROTHERS|SCOUTS|GUIDES|CADETS|4-H|FAIR\b|EXHIBITION|AGRICULTURAL SOCIETY|"
    r"HISTORICAL|HERITAGE|PATRIMOINE|MULTICULTURAL|IMMIGRANT|NEWCOMER|REFUGEE|FIRST NATION|PREMIERE NATION|TRIBAL|ANISHIN|OJIBW|CHIPPEWA|"
    r"MISSISSAUGA|MOHAWK|ONEIDA|ALGONQUIN|\bCREE\b|METIS|INUIT|INDIGENOUS|AUTOCHTONE|ABORIGINAL|NATIVE|FRIENDSHIP|AMITIE|WOMEN|FEMMES|"
    r"MEN'?S|HOMMES|PREGNANCY|DISABILIT|HANDICAP|ABILITY|ABILITIES|AUTISM|DEAF|BLIND|SPECIAL CARE|SPECIAL NEEDS|GROUP HOME|RESIDENTIAL|"
    r"INCLUSION|L'ARCHE|EMPLOYMENT|EMPLOI|ENTERPRISE CENTRE|SMALL BUSINESS CENTRE|CHAMBER OF COMMERCE|CHAMBRE DE COMMERCE|DOWNTOWN|"
    r"BUSINESS IMPROVEMENT|\bBIA\b|TOURISM ASSOC|TOURISME|PARK\b|PARC\b|TRAIL|SENTIER|ARENA|RINK|POOL|RECREATION|LOISIRS|"
    r"SPORTS? (CLUB|ASSOC|COUNCIL|CENTRE)|HOCKEY|SOCCER|CURLING|SKI\b|GOLF|SAILING|ROWING|SWIM|GYMNAST|FIGURE SKAT|SPEED SKAT|BASEBALL|"
    r"SOFTBALL|BASKETBALL|VOLLEYBALL|RUGBY|LACROSSE|JUDO|KARATE|BOXING|ATHLETI|TRACK AND FIELD|SPECIAL OLYMPICS|OLYMPI|PARALYMPI|GAMES\b|"
    r"JEUX\b|CAMP\b|CAMPS\b|BIBLE|GOSPEL|MINISTR|MISSION\b|CATHEDRAL|ABBEY|MONASTERY|CONVENT|SISTERS|SOEURS|CHRISTIAN|CATHOLIC|BAPTIST|"
    r"ANGLICAN|UNITED CHURCH|PENTECOST|MENNONITE|ADVENTIST|MOSQUE|ISLAMIC|MUSLIM|JEWISH|SYNAGOGUE|TEMPLE|SIKH|GURDWARA|HINDU|BUDDHIST|"
    r"HOSPITAL(?!ITY)|HEALTH (CENTRE|CENTER|SCIENCES|NETWORK|SYSTEM|TEAM|SERVICES|PARTNERS|ALLIANCE|CORPORATION|AUTHORITY|UNIT)|HEALTHCARE|"
    r"HEALTH CARE|SANTE|MEDICAL CENTRE|AUXILIARY|RED CROSS|CANCER|DIABETES|HEART AND STROKE|LUNG|KIDNEY|ALZHEIMER|PARKINSON|ARTHRITIS|"
    r"MS SOCIETY|EPILEPS|CEREBRAL|DOWN SYNDROME|CHILDREN'?S|ENFANTS|ENFANCE|PETITE ENFANCE|KIDS|TOTS|TOUT-PETITS|FRIENDS|RAINBOW|SUNSHINE|"
    r"LITTLE|PETIT|TINY|CREATIVE|DISCOVERY|IMAGIN|WONDER|PLAY(?:SCHOOL|GROUP|HOUSE|TIME)?\b|NURSERY|HEADSTART|HEAD START|"
    r"EARLY (LEARNING|CHILDHOOD|YEARS|ON)|EARLYON|AFTER ?SCHOOL|TRANSITION HOUSE|SAFE HOUSE|OUTREACH|DROP-IN|HALFWAY|JOHN HOWARD|"
    r"ELIZABETH FRY|SEXUAL|ASSAULT|VIOLENCE|ABUSE|RESTORATIVE|LEGAL CLINIC|ADVOCACY|CITIZENS|RESIDENTS|RATEPAYERS|FIRE DEPARTMENT|"
    r"VOLUNTEER FIRE|SEARCH AND RESCUE|WATERSHED|CONSERVATION|NATURALIST|NATURE|ENVIRONNEMENT|ENVIRONMENTAL (ASSOC|COUNCIL|NETWORK|TRUST)|"
    r"RIVER (ASSOC|KEEPER|WATCH|INSTITUTE)|WILDLIFE|ANGLERS|HUNTERS|ROD AND GUN|FISH AND GAME|HARBOUR|AIRPORT|FARMERS'? MARKET|MARCHE|"
    r"CARNIVAL|PARADE|CELEBRATION|FETE|JAZZ|BLUES|FOLK|MUSIC|MUSIQUE|FILM|CINEMA|WRITERS|POETS|BOOK|CRAFTS?\b|ARTISAN|POTTERY|QUILT|"
    r"GENEALOG|ARCHIVES|HISTORY|VETERANS|SNOWMOBILE|ATV\b|TRAILS\b|CYCLING|RUNNING|MARATHON|TRIATHLON|HORSE|EQUESTR|RIDING\b|"
    r"THERAPEUTIC|THERAPY|SPEECH|LANGUAGE|FRANCOPHONE|FRANCO|ANGLOPHONE|BILINGU|IMMERSION|FRENCH|FRANCAIS|ENGLISH|TUTOR|MENTOR|"
    r"LEADERSHIP|SKILLS\b|NUMERACY|ADULT LEARN|CONSERVATORY|CEMETERY|MEMORIAL|LIGHTHOUSE|WHARF|MARINA|YACHT|BOAT CLUB|CANOE|KAYAK|"
    r"ANIMAL|SPCA|HUMANE|RESCUE|SANCTUARY|ZOO\b|AQUARIUM|BOTANIC|GARDEN|ARBORETUM|PARTNERSHIP INC|NETWORK|RESEAU|COALITION|ALLIANCE|"
    r"COLLECTIVE|COLLECTIF|COOP\b|CO OP\b|NON-?PROFIT|NON PROFIT|SANS BUT LUCRATIF|OSBL|OBNL|CHARITABLE|BENEVOLENT|RELIEF|AID\b|AIDE\b|"
    r"HELP\b|HOPE\b|ESPOIR|HARVEST|SHARE\b|PARTAGE|CARING|COMPASSION|DIGNITY|INDEPENDENT LIVING|SELF-HELP|PEER|CLUBHOUSE|OPEN DOOR|"
    r"WELCOME|ACCUEIL|SETTLEMENT|NEW CANADIAN|NOUVEAUX ARRIVANTS|CHILDREN'?S AID|CATHOLIC CHILDREN|FAMILY SERVICES?|FAMILY AND CHILDREN|"
    r"CHILD AND FAMILY|FAMILY SUPPORTS?|DEVELOPMENTAL SERVICES|COMMUNITY LIVING|PARTICIPATION HOUSE|CHRISTIAN HORIZONS|KARIS|KERRY'?S PLACE|"
    r"COMMUNITY (HEALTH|CARE|SUPPORT|SERVICES?|RESOURCE|ACTION|FUTURES|FOUNDATION|LEGAL|JUSTICE|LIVING|CENTRE|HOUSE)|HEALTH CENTRE|"
    r"MIDWIVES|MIDWIFERY|SAGE-FEMMES|TREATMENT CENTRE|REHAB|CHILDREN'?S TREATMENT|ERINOAKKIDS|HOLLAND BLOORVIEW|GRANDVIEW|"
    r"LANSDOWNE CHILDREN|THAMES VALLEY CHILDREN|FIVE COUNTIES|KIDSABILITY|ONE KIDS PLACE|PATHWAYS|CMHA|CANADIAN MENTAL HEALTH|"
    r"WOMEN'?S (SHELTER|CENTRE|PLACE|HOUSE|COLLEGE)|INTERVAL HOUSE|SEXUAL ASSAULT|VICTIM SERVICES|DISTRESS CENTRE|LIFELINE|"
    r"STREET HEALTH|HOMELESS|HOUSING HELP|HABITAT FOR HUMANITY|OUT OF THE COLD|SCOTT MISSION|GOOD SHEPHERD|ST VINCENT DE PAUL|"
    r"SOCIAL (PLANNING|SERVICES|ENTERPRISE)|EMPLOYMENT (SERVICES?|CENTRE|RESOURCE|HELP)|JOB(S)? (SKILLS|CENTRE)|CAREER|ENTERPRISE CENTRE|"
    r"INNOVATION (CENTRE|HUB)|ACCELERATOR|INCUBATOR|TECHNOLOGY (CENTRE|ALLIANCE)|REGIONAL INNOVATION|COMMUNITY FUTURES|"
    r"DEVELOPMENT CORPORATION|ECONOMIC DEVELOPMENT|CHAMBER|TOURISM|FAIR BOARD|PLOWMEN|PLOWING MATCH|SOIL AND CROP|CATTLEMEN|"
    r"FEDERATION OF AGRICULTURE|FARMERS|PRODUCERS|GROWERS|MARKETING BOARD|FOOD (BANK|CENTRE|SHARE)|MEALS ON WHEELS|COMMUNITY KITCHEN)",
    re.I)
# Words that make a supplier even when a care or community word is also present
# ("Trillium Health Care Products Inc", "Maple Leaf Homes Inc", "Peel Senior Link" stays).
STRONG_SUPPLIER = re.compile(
    r"\b(?:CONSTRUCTION|PAVING|ASPHALT|CONTRACTING|CONTRACTORS|TRUCK|LEASING|EQUIPMENT|ENGINEERING|ARCHITECTS?\b|IN TRUST|BARRISTER|"
    r"SOLICITOR|INSURANCE|ASSURANCES?\b|BANK\b|HOTEL|MOTEL|INN\b|HOLDINGS|REALTY|PROPERTIES|DEVELOPMENTS|PHARMA(?!CY)|TELECOM|OIL\b|FUEL|"
    r"PETROL|ENERGY INC|ENERGY LTD|LUMBER|HARDWARE|MANUFACTUR|SALES|RENTALS?\b|TOWING|TIRES?\b|AUTO BODY|MOTORS|LOGISTICS|TIMBER|"
    r"FOREST PRODUCTS|PULP|SAWMILL|STEEL|CONCRETE|WELDING|EXCAVAT|PLUMBING|ELECTRICAL|ROOFING|HOMES (INC|LTD|LIMITED)|LAW OFFICE|LAW FIRM|"
    r"PROFESSIONAL CORPORATION|MANAGEMENT (INC|LTD|LIMITED)|LIMITED PARTNERSHIP|\bLP\b|L\.P\.|GP INC|INVESTMENT LP|EXTENDICARE|SCHLEGEL|"
    r"LEISUREWORLD|SIENNA|SOUTHBRIDGE|\bCVH\b|REVERA|CHARTWELL|AXIUM|KINDERA|ROYALE DEVELOPMENT|OMNI HEALTHCARE|REGENCY LTC|CARESSANT|"
    r"IRIS L\.?P|VIGOUR|RESPONSIVE GROUP|JARLETTE|PRIMACARE|PEOPLECARE|STEEVES|RYKKA|APANS|BAYSHORE|PARAMED|SAINT ELIZABETH HEALTH|"
    r"SE HEALTH|CAREPARTNERS|CLOSING THE GAP|SPECTRUM HEALTH|VHA HOME|LIFELABS|DYNACARE|ALPHA LABORATORIES|ACCERTA|DH CORPORATION|"
    r"SOCIETE DH|MOTION LP|PRAXAIR|DEXCOM|INSULET|COSTCO|SHOPPERS|REXALL|INNOMAR|HEARING (CENTRE|CENTRES|CLINIC|CLINICS|CORP|INC|SOLUTIONS|"
    r"SERVICES|BEYOND|INSTITUTE|HEALTH|CARE)|HEAR RIGHT|AUDIOLOG|OCULARIST|PROSTHETIC|ORTHOTIC|VITALAIRE|MEDIGAS|PRORESP|LINDE|"
    r"BREWERS RETAIL|FLEXTRACK|XPERA|EMCON|WEBBER|MILLER PAVING|AECON|ELLISDON|KIEWIT|CRH CANADA|GIP PAVING|COCO PAVING|FOWLER CONSTRUCTION|"
    r"GEM HEALTH CARE|ATK CARE|CROWN RIDGE HEALTH|SERCO|FEDCAP|\bAON\b|RBC INVESTOR|WCG INTERNATIONAL|NETWORKS (INC|LTD|LIMITED)|TELEPHONE|"
    r"FIBRE|BROADBAND|INTERNET|CABLE SYSTEMS|NEXTSTAR|STELLANTIS|HONDA CANADA|VOLKSWAGEN|POWERCO|UMICORE|ALGOMA STEEL|ARCELORMITTAL|"
    r"BELL CANADA|BELL MOBILITY|ROGERS COMMUNICATIONS|TELUS|MICROSOFT|ORACLE|IBM CANADA|CGI\b|DELOITTE|KPMG|ERNST & YOUNG|PRICEWATERHOUSE|"
    r"ACCENTURE|ENBRIDGE|HYDRO ONE NETWORKS|TORONTO HYDRO|ALECTRA|ELEXICON|GREATER SUDBURY HYDRO|SECURITAS|GARDA|PALADIN|COMMISSIONAIRES|"
    r"COMPASS GROUP|ARAMARK|SODEXO|DE HAVILLAND|BOMBARDIER|ALSTOM|SIEMENS|THALES|HITACHI|CROSSLINX|INFRASTRUCTURE ONTARIO)",
    re.I)
# Acute and regional hospitals: local corporations, but each serves a region far larger than its
# riding and carries hundreds of millions, so they are flagged like the other provinces' health
# authorities and shown only when "province-wide" bodies are ticked back in.
ACUTE = re.compile(r"HOSPITAL(?!ITY)|HOPITAL|HEALTH SCIENCES|HEALTH NETWORK|HEALTH SYSTEM|HEALTH PARTNERS|HEALTHCARE|\bHEALTH$|REGIONAL HEALTH CENTRE|"
                   r"HEART INSTITUTE|SICK CHILDREN|CENTRE FOR ADDICTION|BAYCREST|BRUYERE|PROVIDENCE CARE|HOTEL DIEU|ONTARIO SHORES|WAYPOINT|"
                   r"ROYAL OTTAWA|HOMEWOOD|REHABILITATION INSTITUTE|UNITY HEALTH|MACKENZIE HEALTH|HEALTH AUTHORITY", re.I)
NOT_ACUTE = re.compile(r"FOUNDATION|ASSOCIATION|COMMUNITY HEALTH CENTRE|FAMILY HEALTH TEAM|HOSPICE|HEALTH CARE PRODUCTS|HEALTHCARE PRODUCTS|SUPPL", re.I)
HOSPITAL = re.compile(r"HOSPITAL(?!ITY)|HOPITAL|HEALTH SCIENCES|HEALTH CENTRE|HEALTH CARE CENTRE|HEALTH NETWORK|HEALTH SYSTEM|HEALTH PARTNERS|"
                      r"HEALTHCARE|HEALTH SERVICES|\bHEALTH$|HEART INSTITUTE|CHILDREN'?S TREATMENT|CENTRE FOR ADDICTION|SICK CHILDREN|"
                      r"REHABILITATION|HOSPICE|COMMUNITY HEALTH CENTRE|FAMILY HEALTH TEAM|BAYCREST|BRUYERE|PROVIDENCE CARE|HOTEL DIEU|"
                      r"SOLDIERS' MEMORIAL|ONTARIO SHORES|WAYPOINT|ROYAL OTTAWA|HOMEWOOD", re.I)
# GeoNames place names that are also surnames, ordinary words, counties, regions or
# Toronto boroughs: never a place hit in the "place name inside the recipient" step.
AMBIGUOUS = {"YORK", "SIMCOE", "HURON", "BRUCE", "GREY", "PERTH", "WELLINGTON", "DURHAM", "NIAGARA", "ESSEX", "KENT", "LAMBTON",
             "MIDDLESEX", "ELGIN", "OXFORD", "NORFOLK", "HALDIMAND", "BRANT", "DUFFERIN", "LANARK", "FRONTENAC", "HASTINGS",
             "NORTHUMBERLAND", "VICTORIA", "MUSKOKA", "NIPISSING", "ALGOMA", "TIMISKAMING", "RAINY RIVER", "MANITOULIN",
             "GLENGARRY", "STORMONT", "DUNDAS", "GRENVILLE", "LEEDS", "RUSSELL", "HALTON", "PEEL", "SCOTLAND", "IROQUOIS",
             "CENTRE", "CENTER", "CENTRAL", "UNION", "DELTA", "MOUNT", "ALMA", "HOPE", "BATH", "KING", "WARREN", "GORDON",
             "DOUGLAS", "STANLEY", "NEWTON", "GARDEN", "GLOUCESTER", "CUMBERLAND", "WESTON", "LINCOLN", "CLINTON", "HOLLAND",
             "ARTHUR", "VIENNA", "BRIGHTON", "VICTORIA HARBOUR", "ONTARIO"}
# Single-tier municipalities, regions and First Nations whose name is not a GeoNames place:
# (lat, lon) of the main settlement or band office. Keys are place_norm() keys.
PLACE_ALIASES = {
    "GREATER SUDBURY": (46.49, -80.99), "CHATHAM KENT": (42.405, -82.19), "KAWARTHA LAKES": (44.355, -78.74),
    "NORFOLK COUNTY": (42.835, -80.30), "NORFOLK": (42.835, -80.30), "HALDIMAND COUNTY": (42.95, -79.85), "HALDIMAND": (42.95, -79.85),
    "PRINCE EDWARD COUNTY": (44.00, -77.14), "PRINCE EDWARD": (44.00, -77.14), "QUINTE WEST": (44.10, -77.58),
    "CLARINGTON": (43.91, -78.69), "CENTRE WELLINGTON": (43.70, -80.38), "NORTH GRENVILLE": (45.02, -75.64),
    "SOUTH FRONTENAC": (44.45, -76.49), "CENTRAL FRONTENAC": (44.75, -76.75), "NORTH FRONTENAC": (44.99, -76.90),
    "FRONTENAC ISLANDS": (44.19, -76.42), "THE NATION": (45.40, -75.07), "LA NATION": (45.40, -75.07), "CLARENCE ROCKLAND": (45.55, -75.29),
    "NORTH DUNDAS": (45.08, -75.37), "SOUTH DUNDAS": (44.90, -75.19), "NORTH STORMONT": (45.20, -75.00), "SOUTH STORMONT": (45.06, -74.90),
    "NORTH GLENGARRY": (45.31, -74.64), "SOUTH GLENGARRY": (45.10, -74.60), "CHAMPLAIN": (45.57, -74.70), "ALFRED PLANTAGENET": (45.56, -74.88),
    "RUSSELL": (45.27, -75.36), "EAST HAWKESBURY": (45.52, -74.48), "LEEDS AND THE THOUSAND ISLANDS": (44.45, -76.00),
    "ELIZABETHTOWN KITLEY": (44.65, -75.80), "RIDEAU LAKES": (44.70, -76.20), "FRONT OF YONGE": (44.52, -75.86),
    "AUGUSTA": (44.78, -75.60), "EDWARDSBURGH CARDINAL": (44.83, -75.40), "ATHENS": (44.63, -75.95), "MERRICKVILLE WOLFORD": (44.92, -75.84),
    "TAY VALLEY": (44.88, -76.35), "LANARK HIGHLANDS": (45.05, -76.45), "DRUMMOND NORTH ELMSLEY": (44.95, -76.15), "BECKWITH": (45.10, -76.05),
    "MONTAGUE": (44.95, -75.95), "MISSISSIPPI MILLS": (45.22, -76.20), "MCNAB BRAESIDE": (45.45, -76.45), "WHITEWATER REGION": (45.70, -76.75),
    "LAURENTIAN VALLEY": (45.78, -77.20), "NORTH ALGONA WILBERFORCE": (45.70, -77.10), "BONNECHERE VALLEY": (45.45, -77.10),
    "MADAWASKA VALLEY": (45.45, -77.70), "KILLALOE HAGARTY AND RICHARDS": (45.55, -77.42), "BRUDENELL LYNDOCH AND RAGLAN": (45.35, -77.45),
    "GREATER MADAWASKA": (45.20, -76.80), "ADMASTON BROMLEY": (45.55, -76.80), "HORTON": (45.50, -76.65), "HEAD CLARA AND MARIA": (46.20, -77.85),
    "TRENT HILLS": (44.30, -77.80), "ALNWICK HALDIMAND": (44.05, -78.05), "HAMILTON TOWNSHIP": (44.05, -78.20), "CRAMAHE": (44.05, -77.90),
    "TRENT LAKES": (44.60, -78.40), "SELWYN": (44.42, -78.35), "DOURO DUMMER": (44.45, -78.10), "OTONABEE SOUTH MONAGHAN": (44.25, -78.25),
    "ASPHODEL NORWOOD": (44.38, -77.98), "HAVELOCK BELMONT METHUEN": (44.43, -77.88), "NORTH KAWARTHA": (44.75, -78.10),
    "CAVAN MONAGHAN": (44.20, -78.45), "SCUGOG": (44.10, -78.95), "BROCK": (44.30, -79.10), "GEORGINA": (44.30, -79.45),
    "EAST GWILLIMBURY": (44.11, -79.44), "WHITCHURCH STOUFFVILLE": (43.97, -79.25), "KING": (43.93, -79.53), "ADJALA TOSORONTIO": (44.10, -79.85),
    "NEW TECUMSETH": (44.09, -79.87), "BRADFORD WEST GWILLIMBURY": (44.12, -79.56), "ESSA": (44.25, -79.80), "CLEARVIEW": (44.40, -80.10),
    "ORO MEDONTE": (44.55, -79.55), "SEVERN": (44.75, -79.50), "RAMARA": (44.60, -79.30), "TAY": (44.72, -79.75), "TINY": (44.70, -79.95),
    "WASAGA BEACH": (44.52, -80.02), "BLUE MOUNTAINS": (44.50, -80.30), "THE BLUE MOUNTAINS": (44.50, -80.30), "GREY HIGHLANDS": (44.30, -80.50),
    "SOUTHGATE": (44.10, -80.60), "WEST GREY": (44.15, -80.85), "CHATSWORTH": (44.45, -80.90), "GEORGIAN BLUFFS": (44.60, -81.00),
    "MEAFORD": (44.60, -80.59), "SOUTH BRUCE PENINSULA": (44.70, -81.25), "NORTHERN BRUCE PENINSULA": (45.05, -81.35),
    "SAUGEEN SHORES": (44.44, -81.37), "ARRAN ELDERSLIE": (44.40, -81.15), "BROCKTON": (44.17, -81.03), "SOUTH BRUCE": (44.00, -81.20),
    "HURON KINLOSS": (44.05, -81.55), "ASHFIELD COLBORNE WAWANOSH": (43.85, -81.65), "CENTRAL HURON": (43.62, -81.55),
    "HURON EAST": (43.60, -81.25), "BLUEWATER": (43.45, -81.60), "SOUTH HURON": (43.35, -81.50), "HOWICK": (43.85, -81.05),
    "MORRIS TURNBERRY": (43.80, -81.30), "NORTH HURON": (43.90, -81.30), "NORTH PERTH": (43.73, -80.95), "PERTH EAST": (43.50, -80.90),
    "PERTH SOUTH": (43.30, -81.10), "WEST PERTH": (43.47, -81.20), "WELLINGTON NORTH": (43.90, -80.60), "MAPLETON": (43.75, -80.65),
    "MINTO": (43.85, -80.90), "GUELPH ERAMOSA": (43.60, -80.20), "PUSLINCH": (43.45, -80.15), "WOOLWICH": (43.60, -80.55),
    "WILMOT": (43.40, -80.70), "WELLESLEY": (43.47, -80.76), "NORTH DUMFRIES": (43.33, -80.40), "EAST ZORRA TAVISTOCK": (43.30, -80.85),
    "ZORRA": (43.15, -81.00), "SOUTH WEST OXFORD": (43.00, -80.85), "BLANDFORD BLENHEIM": (43.25, -80.60), "NORWICH": (42.98, -80.60),
    "BRANT": (43.15, -80.40), "COUNTY OF BRANT": (43.15, -80.40), "SOUTHWOLD": (42.75, -81.30), "CENTRAL ELGIN": (42.75, -81.10),
    "MALAHIDE": (42.75, -80.95), "BAYHAM": (42.70, -80.80), "DUTTON DUNWICH": (42.65, -81.50), "WEST ELGIN": (42.55, -81.65),
    "THAMES CENTRE": (43.00, -81.05), "MIDDLESEX CENTRE": (43.05, -81.40), "NORTH MIDDLESEX": (43.15, -81.65), "LUCAN BIDDULPH": (43.18, -81.40),
    "ADELAIDE METCALFE": (42.95, -81.70), "STRATHROY CARADOC": (42.95, -81.62), "SOUTHWEST MIDDLESEX": (42.75, -81.70),
    "LAMBTON SHORES": (43.20, -81.90), "PLYMPTON WYOMING": (43.00, -82.10), "ST CLAIR": (42.78, -82.35), "SAINT CLAIR": (42.78, -82.35),
    "DAWN EUPHEMIA": (42.70, -82.00), "BROOKE ALVINSTON": (42.82, -81.85), "ENNISKILLEN": (42.85, -82.15), "WARWICK": (43.00, -81.90),
    "LAKESHORE": (42.25, -82.65), "ESSEX": (42.17, -82.82), "LASALLE": (42.23, -83.07), "TECUMSEH": (42.30, -82.88), "PELEE": (41.78, -82.65),
    "LEAMINGTON": (42.05, -82.60), "KINGSVILLE": (42.03, -82.74), "AMHERSTBURG": (42.10, -83.10), "WEST LINCOLN": (43.05, -79.55),
    "LINCOLN": (43.17, -79.45), "PELHAM": (43.03, -79.33), "WAINFLEET": (42.92, -79.38), "NIAGARA ON THE LAKE": (43.25, -79.07),
    "THOROLD": (43.12, -79.20), "HALTON HILLS": (43.65, -79.92), "MILTON": (43.52, -79.88), "OAKVILLE": (43.45, -79.68),
    "BURLINGTON": (43.33, -79.80), "CALEDON": (43.87, -79.87), "AJAX": (43.85, -79.02), "PICKERING": (43.84, -79.09), "WHITBY": (43.88, -78.94),
    "OSHAWA": (43.90, -78.86), "UXBRIDGE": (44.11, -79.12), "MUSKOKA LAKES": (45.10, -79.57), "LAKE OF BAYS": (45.30, -79.05),
    "GEORGIAN BAY": (44.90, -79.80), "DISTRICT MUNICIPALITY OF MUSKOKA": (45.04, -79.31), "MUSKOKA": (45.04, -79.31),
    "SEGUIN": (45.30, -79.90), "MCDOUGALL": (45.40, -80.00), "CARLING": (45.45, -80.20), "THE ARCHIPELAGO": (45.33, -80.20),
    "ARCHIPELAGO": (45.33, -80.20), "MCKELLAR": (45.50, -79.90), "WHITESTONE": (45.70, -79.95), "MAGNETAWAN": (45.67, -79.63),
    "ARMOUR": (45.65, -79.40), "STRONG": (45.75, -79.40), "MACHAR": (45.85, -79.45), "JOLY": (45.80, -79.25), "PERRY": (45.55, -79.25),
    "KEARNEY": (45.55, -79.22), "RYERSON": (45.65, -79.55), "NIPISSING": (46.05, -79.50), "EAST FERRIS": (46.25, -79.30),
    "BONFIELD": (46.23, -79.15), "CALVIN": (46.25, -78.95), "PAPINEAU CAMERON": (46.30, -78.70), "CHISHOLM": (46.10, -79.20),
    "WEST NIPISSING": (46.37, -79.92), "NIPISSING OUEST": (46.37, -79.92), "SOUTH ALGONQUIN": (45.50, -78.05), "TEMAGAMI": (47.06, -79.78),
    "FRENCH RIVER": (46.20, -80.40), "RIVIERE DES FRANCAIS": (46.20, -80.40), "ST CHARLES": (46.37, -80.45), "SAINT CHARLES": (46.37, -80.45),
    "MARKSTAY WARREN": (46.48, -80.53), "KILLARNEY": (45.97, -81.50), "SABLES SPANISH RIVERS": (46.20, -81.80), "BALDWIN": (46.27, -81.90),
    "NAIRN AND HYMAN": (46.35, -81.65), "ESPANOLA": (46.26, -81.77), "NORTHEASTERN MANITOULIN AND THE ISLANDS": (45.98, -81.93),
    "CENTRAL MANITOULIN": (45.75, -82.10), "ASSIGINACK": (45.75, -81.87), "BILLINGS": (45.85, -82.25), "GORDON BARRIE ISLAND": (45.90, -82.40),
    "GORE BAY": (45.92, -82.47), "BURPEE AND MILLS": (45.80, -82.55), "TEHKUMMAH": (45.65, -81.95), "COCKBURN ISLAND": (45.95, -83.35),
    "HURON SHORES": (46.25, -83.20), "THE NORTH SHORE": (46.22, -82.60), "NORTH SHORE": (46.22, -82.60), "SPANISH": (46.20, -82.35),
    "ELLIOT LAKE": (46.38, -82.65), "BLIND RIVER": (46.19, -82.96), "PLUMMER ADDITIONAL": (46.30, -83.75), "JOHNSON": (46.33, -83.95),
    "TARBUTT": (46.30, -84.00), "LAIRD": (46.42, -84.08), "MACDONALD MEREDITH AND ABERDEEN ADDITIONAL": (46.45, -84.00),
    "PRINCE": (46.55, -84.55), "HILTON": (46.25, -83.90), "ST JOSEPH": (46.25, -83.90), "SAINT JOSEPH": (46.25, -83.90),
    "WAWA": (47.99, -84.77), "WHITE RIVER": (48.60, -85.28), "DUBREUILVILLE": (48.35, -84.53), "HORNEPAYNE": (49.21, -84.78),
    "CHAPLEAU": (47.84, -83.40), "BLACK RIVER MATHESON": (48.53, -80.47), "IROQUOIS FALLS": (48.77, -80.68), "COCHRANE": (49.07, -81.02),
    "SMOOTH ROCK FALLS": (49.28, -81.63), "FAUQUIER STRICKLAND": (49.32, -82.00), "MOONBEAM": (49.35, -82.15), "VAL RITA HARTY": (49.45, -82.55),
    "OPASATIKA": (49.52, -82.88), "MATTICE VAL COTE": (49.62, -83.25), "TIMMINS": (48.48, -81.33), "KAPUSKASING": (49.42, -82.43),
    "HEARST": (49.69, -83.67), "MOOSONEE": (51.27, -80.65), "TEMISKAMING SHORES": (47.51, -79.69), "KIRKLAND LAKE": (48.15, -80.04),
    "ENGLEHART": (47.82, -79.87), "LATCHFORD": (47.33, -79.80), "COBALT": (47.39, -79.68), "COLEMAN": (47.37, -79.73), "HARLEY": (47.68, -79.80),
    "ARMSTRONG": (47.63, -79.77), "HUDSON": (47.65, -79.75), "KERNS": (47.60, -79.80), "CASEY": (47.55, -79.60), "HARRIS": (47.55, -79.65),
    "BRETHOUR": (47.55, -79.55), "HILLIARD": (47.68, -79.75), "CHARLTON AND DACK": (47.80, -79.95), "EVANTUREL": (47.85, -79.80),
    "CHAMBERLAIN": (47.88, -79.90), "MATACHEWAN": (47.95, -80.65), "MCGARRY": (48.10, -79.55), "LARDER LAKE": (48.10, -79.72),
    "GAUTHIER": (48.15, -79.85), "JAMES": (47.65, -80.02), "THORNLOE": (47.70, -79.75), "GREENSTONE": (49.78, -86.95),
    "MARATHON": (48.72, -86.38), "MANITOUWADGE": (49.12, -85.84), "TERRACE BAY": (48.78, -87.10), "SCHREIBER": (48.81, -87.27),
    "NIPIGON": (49.01, -88.27), "RED ROCK": (48.94, -88.25), "DORION": (48.80, -88.55), "SHUNIAH": (48.50, -89.05), "NEEBING": (48.20, -89.40),
    "OLIVER PAIPOONGE": (48.38, -89.55), "GILLIES": (48.25, -89.70), "O CONNOR": (48.30, -89.70), "CONMEE": (48.40, -89.80),
    "THUNDER BAY": (48.38, -89.25), "ATIKOKAN": (48.76, -91.62), "FORT FRANCES": (48.61, -93.40), "RAINY RIVER": (48.72, -94.57),
    "EMO": (48.63, -93.83), "ALBERTON": (48.60, -93.50), "LA VALLEE": (48.60, -93.65), "CHAPPLE": (48.65, -94.00), "MORLEY": (48.75, -94.30),
    "DAWSON": (48.85, -94.60), "LAKE OF THE WOODS": (49.00, -94.50), "KENORA": (49.77, -94.49), "SIOUX NARROWS NESTOR FALLS": (49.40, -94.00),
    "DRYDEN": (49.78, -92.84), "MACHIN": (49.90, -93.20), "IGNACE": (49.42, -91.65), "SIOUX LOOKOUT": (50.10, -91.92), "RED LAKE": (51.03, -93.83),
    "EAR FALLS": (50.63, -93.22), "PICKLE LAKE": (51.47, -90.18),
    # First Nations: band name -> main community.
    "SIX NATIONS": (43.07, -80.12), "SIX NATIONS OF THE GRAND RIVER": (43.07, -80.12), "GRAND RIVER": (43.07, -80.12),
    "MOHAWKS OF THE BAY OF QUINTE": (44.18, -77.15), "BAY OF QUINTE": (44.18, -77.15), "TYENDINAGA": (44.18, -77.15),
    "AKWESASNE": (45.00, -74.65), "ALDERVILLE": (44.18, -78.07), "HIAWATHA": (44.30, -78.20), "CURVE LAKE": (44.47, -78.35),
    "SCUGOG ISLAND": (44.15, -78.90), "NEW CREDIT": (43.07, -80.12), "CREDIT": (43.07, -80.12), "NAWASH": (44.90, -81.00),
    "NEYAASHIINIGMIING": (44.90, -81.00), "SAUGEEN": (44.48, -81.33), "KETTLE AND STONY POINT": (43.20, -81.95), "KETTLE": (43.20, -81.95),
    "AAMJIWNAANG": (42.93, -82.42), "SARNIA": (42.93, -82.42), "WALPOLE ISLAND": (42.57, -82.50), "BKEJWANONG": (42.57, -82.50),
    "CALDWELL": (42.05, -82.60), "DELAWARE NATION": (42.52, -81.90), "MORAVIAN": (42.52, -81.90), "ONEIDA": (42.85, -81.40),
    "THAMES": (42.85, -81.40), "MUNSEE DELAWARE": (42.85, -81.45), "CHIPPEWAS OF THE THAMES": (42.85, -81.45), "RAMA": (44.65, -79.35),
    "MNJIKANING": (44.65, -79.35), "GEORGINA ISLAND": (44.35, -79.30), "BEAUSOLEIL": (44.83, -80.15), "CHRISTIAN ISLAND": (44.83, -80.15),
    "WASAUKSING": (45.30, -80.10), "SHAWANAGA": (45.50, -80.30), "MAGNETAWAN FIRST NATION": (45.75, -80.55), "HENVEY INLET": (45.90, -80.60),
    "DOKIS": (46.15, -80.00), "GARDEN VILLAGE": (46.30, -79.60), "WAHNAPITAE": (46.70, -80.75), "ATIKAMEKSHENG": (46.45, -81.20),
    "WHITEFISH LAKE": (46.45, -81.20), "WHITEFISH RIVER": (46.05, -81.75), "BIRCH ISLAND": (46.05, -81.75), "SAGAMOK": (46.15, -82.05),
    "SERPENT RIVER": (46.20, -82.50), "MISSISSAUGA FIRST NATION": (46.25, -83.05), "MISSISSAUGI": (46.25, -83.05), "THESSALON": (46.25, -83.55),
    "GARDEN RIVER": (46.55, -84.15), "BATCHEWANA": (46.60, -84.30), "RANKIN": (46.60, -84.30), "WIKWEMIKONG": (45.80, -81.70),
    "WIIKWEMKOONG": (45.80, -81.70), "M CHIGEENG": (45.80, -82.20), "MCHIGEENG": (45.80, -82.20), "SHEGUIANDAH": (45.90, -81.90),
    "AUNDECK OMNI KANING": (45.95, -82.00), "SHESHEGWANING": (45.90, -82.65), "ZHIIBAAHAASING": (45.95, -82.70),
    "TEMAGAMI FIRST NATION": (46.95, -80.05), "BEAR ISLAND": (46.95, -80.05), "WAHGOSHIG": (48.55, -80.00), "TAYKWA TAGAMOU": (49.10, -81.05),
    "NEW POST": (49.10, -81.05), "MOOSE CREE": (51.27, -80.60), "MOOSE FACTORY": (51.27, -80.60), "MOCREEBEC": (51.27, -80.60),
    "FORT ALBANY": (52.22, -81.65), "KASHECHEWAN": (52.30, -81.63), "ATTAWAPISKAT": (52.93, -82.43), "WEENUSK": (54.98, -85.43),
    "PEAWANUCK": (54.98, -85.43), "CONSTANCE LAKE": (49.75, -84.05), "CHAPLEAU CREE": (47.85, -83.40), "CHAPLEAU OJIBWE": (47.85, -83.40),
    "BRUNSWICK HOUSE": (47.85, -83.40), "MISSANABIE CREE": (48.32, -84.08), "MATTAGAMI": (47.55, -81.65), "FLYING POST": (48.50, -81.30),
    "MATACHEWAN FIRST NATION": (47.95, -80.65), "BEAVERHOUSE": (48.15, -80.05), "WABASEEMOONG": (50.00, -95.00), "WHITEDOG": (50.00, -95.00),
    "GRASSY NARROWS": (50.10, -93.90), "ASUBPEESCHOSEEWAGONG": (50.10, -93.90), "SHOAL LAKE": (49.55, -95.05), "ISKATEWIZAAGEGAN": (49.55, -95.05),
    "NORTHWEST ANGLE": (49.35, -94.70), "ANIMAKEE WA ZHING": (49.35, -94.70), "ONIGAMING": (49.10, -93.90), "NESTOR FALLS": (49.10, -93.90),
    "NAOTKAMEGWANNING": (49.30, -94.10), "WHITEFISH BAY": (49.30, -94.10), "BIG GRASSY": (48.95, -94.25), "MISHKOSIIMIINIIZIIBING": (48.95, -94.25),
    "BIG ISLAND": (49.05, -94.40), "ANISHINAABEG OF NAONGASHIING": (49.05, -94.40), "RAINY RIVER FIRST NATIONS": (48.72, -94.00),
    "MANITOU RAPIDS": (48.72, -94.00), "COUCHICHING": (48.65, -93.40), "NAICATCHEWENIN": (48.70, -93.75), "NIGIGOONSIMINIKAANING": (48.65, -93.55),
    "MITAANJIGAMIING": (48.80, -93.20), "SEINE RIVER": (48.78, -92.60), "MINE CENTRE": (48.78, -92.60), "LAC LA CROIX": (48.38, -92.17),
    "LAC DES MILLE LACS": (48.85, -90.20), "WAUZHUSHK ONIGUM": (49.75, -94.45), "RAT PORTAGE": (49.75, -94.45), "OCHIICHAGWE BABIGO INING": (49.85, -94.40),
    "DALLES": (49.85, -94.40), "NIISAACHEWAN": (49.80, -94.50), "OBASHKAANDAGAANG": (49.80, -94.50), "WASHAGAMIS BAY": (49.80, -94.50),
    "WABIGOON LAKE": (49.73, -92.65), "EAGLE LAKE": (49.70, -93.10), "WABAUSKANG": (50.40, -93.30), "LAC SEUL": (50.10, -92.20),
    "FRENCHMAN S HEAD": (50.10, -92.20), "KEJICK BAY": (50.10, -92.20), "MISHKEEGOGAMANG": (51.35, -90.30), "OSNABURGH": (51.35, -90.30),
    "SAUGEEN FIRST NATION": (44.48, -81.33), "KIASHKE ZAAGING": (49.85, -89.00), "GULL BAY": (49.85, -89.00), "WHITESAND": (50.30, -89.05),
    "ARMSTRONG STATION": (50.30, -89.05), "FORT WILLIAM": (48.35, -89.25), "RED ROCK INDIAN BAND": (48.95, -88.15), "LAKE HELEN": (48.95, -88.15),
    "PAYS PLAT": (48.88, -87.55), "BIIGTIGONG": (48.65, -86.30), "PIC RIVER": (48.65, -86.30), "HERON BAY": (48.65, -86.30),
    "NETMIZAAGGAMIG": (48.70, -85.65), "PIC MOBERT": (48.70, -85.65), "MOBERT": (48.70, -85.65), "MICHIPICOTEN": (47.95, -84.80),
    "LONG LAKE 58": (49.78, -86.50), "LONG LAKE": (49.78, -86.50), "GINOOGAMING": (49.75, -86.50), "LONGLAC": (49.78, -86.50),
    "AROLAND": (50.20, -86.70), "NAKINA": (50.20, -86.70), "ANIMBIIGOO ZAAGI IGAN": (49.60, -87.85), "BEARDMORE": (49.60, -87.85),
    "BINGWI NEYAASHI": (49.80, -88.00), "SAND POINT": (49.80, -88.00), "BIINJITIWAABIK ZAAGING": (49.85, -88.30), "ROCKY BAY": (49.85, -88.30),
    "MARTEN FALLS": (51.65, -85.90), "OGOKI": (51.65, -85.90), "EABAMETOONG": (51.55, -88.00), "FORT HOPE": (51.55, -88.00),
    "NESKANTAGA": (52.23, -87.90), "LANSDOWNE HOUSE": (52.23, -87.90), "NIBINAMIK": (52.70, -88.55), "SUMMER BEAVER": (52.70, -88.55),
    "WEBEQUIE": (52.98, -87.37), "KITCHENUHMAYKOOSIB": (53.82, -89.87), "BIG TROUT LAKE": (53.82, -89.87), "WAPEKEKA": (53.80, -89.58),
    "ANGLING LAKE": (53.80, -89.58), "KASABONIKA": (53.53, -88.65), "WUNNUMIN": (52.93, -89.17), "KINGFISHER": (53.02, -89.85),
    "WAWAKAPEWIN": (53.72, -89.35), "SACHIGO": (53.87, -92.20), "BEARSKIN LAKE": (53.89, -90.96), "MUSKRAT DAM": (53.43, -91.75),
    "SANDY LAKE": (53.07, -93.33), "DEER LAKE": (52.62, -94.05), "NORTH SPIRIT LAKE": (52.50, -92.97), "KEEWAYWIN": (52.98, -92.75),
    "POPLAR HILL": (52.10, -94.30), "PIKANGIKUM": (51.82, -93.98), "CAT LAKE": (51.72, -91.83), "SLATE FALLS": (51.13, -91.60),
    "MCDOWELL LAKE": (52.20, -92.75), "FORT SEVERN": (56.00, -87.63), "NORTH CARIBOU LAKE": (52.78, -90.63), "WEAGAMOW": (52.78, -90.63),
    "ROUND LAKE": (52.78, -90.63), "KOOCHECHING": (52.78, -90.63), "WHITEWATER LAKE": (50.90, -89.10), "SAUGEEN NATION": (44.48, -81.33),
    "MATTAWA": (46.32, -78.70), "NIPISSING FIRST NATION": (46.30, -79.60), "WABUN": (48.48, -81.33), "WIKWEMIKONG UNCEDED": (45.80, -81.70),
    "SHEGUIANDAH FIRST NATION": (45.90, -81.90), "WEENUSK FIRST NATION": (54.98, -85.43),
}


def upper(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def norm(s):
    s = upper(s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(THE|OF|INC|LTD|LIMITED|CORP|CORPORATION|SOCIETY|ASSOCIATION|ASSN|FOUNDATION)\b", " ", s)
    s = re.sub(r"\b(NO|NUMBER)\s*\d+\b|#\s*\d+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def place_norm(s):
    """Place-name key: accents stripped, 'St'/'Ste' expanded, punctuation to spaces."""
    s = upper(s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\bSTE\b", "SAINTE", s)
    s = re.sub(r"\bST\b", "SAINT", s)
    return re.sub(r"\s+", " ", s).strip()


def amount(s):
    """'34,129' -> 34129.0; '(265)' -> -265.0; '-' -> 0."""
    s = (s or "").strip().replace(",", "").replace("$", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").strip()
    if s in ("", "-"):
        return 0.0
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return 0.0


def ministry_label(s):
    """'Ministry Of Children, Community And Social Services' -> 'Ministry of Children, Community and Social Services'."""
    s = re.sub(r"\s+", " ", s.strip()).replace(",J", ", J")
    s = re.sub(r"\b(Of|And|For|The|De|Des|Du|La|Le|Et)\b", lambda m: m.group(1).lower(), s)
    return s[0].upper() + s[1:] if s else s


def read_rows():
    """Grant and supplier rows for every year (those outside the windows feed the series only), plus the coverage table."""
    rows = []
    other = Counter()
    coverage = {}
    for fy in COVERAGE_YEARS:
        label = f"FY{fy - 1}-{str(fy)[2:]}"
        path = DL / f"payments-{fy - 1}-{str(fy)[2:]}-en.csv"
        cats = Counter()
        n = Counter()
        window = WINDOWS.get(fy)
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            next(reader)
            for r in reader:
                if len(r) < 5:
                    continue
                v = amount(r[0])
                cat = re.sub(r"\s+", " ", r[2]).strip()
                detail = re.sub(r"\s+", " ", r[3]).strip()
                cats[cat] += v
                n[cat] += 1
                if cat == "Transfer Payments" or (cat == "Statutory Payments" and detail == "Transfer Payments"):
                    kind = "transfer"
                elif cat == "Other Payments":
                    kind = "other"
                else:
                    if window:
                        other[(window, cat)] += v
                    continue
                rows.append({"Recipient": re.sub(r"\s+", " ", r[4]).strip(), "Ministry": ministry_label(r[1]), "Detail": detail,
                             "Kind": kind, "Amount": v, "fye": fy})
        coverage[label] = {"rows": sum(n.values()), "total": round(sum(cats.values())),
                           "by_category": {k: {"total": round(v), "rows": n[k]} for k, v in cats.most_common()}}
    return rows, other, coverage


def main():
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()

    # Name -> postal code sources.
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("ON|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "ON":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[4] == "ON":
                try:
                    pt = (float(r[9]), float(r[10]))
                except ValueError:
                    continue
                for part in r[2].split("/"):
                    places[place_norm(part)].append(pt)
    # Census-subdivision centroids cached by on_prep.py (northern townships and reserves).
    csd_places = {}
    for path in sorted((RAW / "on" / "csd_centroid").glob("*.json")) if (RAW / "on" / "csd_centroid").exists() else []:
        try:
            o = json.load(open(path))
            lon, lat = o["centroid"]["coordinates"]
        except (KeyError, ValueError, TypeError):
            continue
        key = place_norm(re.sub(r"\s*\(.*?\)|\s+\d+[A-Z]?$|\bINDIAN RESERVE\b|\bUNORGANIZED\b.*$", "", o["name"]))
        if key and key not in places:
            csd_places.setdefault(key, (lat, lon))
    place_names = [p for p in places if len(p) >= 5 and p not in AMBIGUOUS]
    place_names += [p for p in list(PLACE_ALIASES) + list(csd_places) if len(p) >= 5 and p not in places and p not in AMBIGUOUS]
    place_names = sorted(set(place_names), key=len, reverse=True)
    place_re = re.compile(r"\b(?:" + "|".join(re.escape(p) for p in place_names) + r")\b")

    loc_cache = {}

    def locate_pc(pc):
        if pc in centroids:
            return index.locate(*centroids[pc])[0]
        return None

    def locate_place(key):
        if key in PLACE_ALIASES:
            return index.locate(*PLACE_ALIASES[key])[0]
        pts = places.get(key)
        if pts:
            return index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))[0]
        if key in csd_places:
            return index.locate(*csd_places[key])[0]
        return None

    def segments(name):
        """'The Corporation Of The Town Of Hearst (O/A: Town Of Hearst)' -> both names; bilingual halves split."""
        inner = [re.sub(r"^O/A:?\s*", "", m).strip() for m in re.findall(r"\(([^)]*)\)", name)]
        base = re.sub(r"\s*\([^)]*\)", " ", name)
        parts = [p.strip() for p in re.split(r"\s*/\s*|_", base) if p.strip()]
        parts += [p for p in inner if p and not re.match(r"^(THE )?(\w+)$", p)]
        return parts or [name]

    def muni_key(name):
        for seg in segments(name):
            key = re.sub(r"\b(INC|LTD|LIMITED)\b.*$", "", place_norm(seg)).strip()
            key = re.sub(r"\bOF(?=[A-Z]{4,})", "OF ", key)
            m = MUNI.match(key)
            if m:
                return m.group(2).strip()
        # A payee that is nothing but a place name ("Toronto", "Chatham-Kent") is the municipality itself.
        for seg in segments(name):
            key = place_norm(seg)
            if (key in places and len(places[key]) >= 20) or key in PLACE_ALIASES:
                return key
        return None

    def nation_key(name):
        for seg in segments(name):
            m = FIRST_NATION.match(place_norm(seg))
            if m:
                return (m.group(1) or m.group(3) or "").strip()
        return None

    def place(name):
        """-> (riding number or None, method)."""
        if name in loc_cache:  # keyed by the spelling as written: the rules below read the raw name
            return loc_cache[name]
        n = norm(name)
        res = (None, "unmatched")
        u = upper(name)
        if not n or "WITHHELD" in n or "CONFIDENTIAL" in n:
            res = (None, "withheld")
        elif UNDER_THRESHOLD.search(u):
            res = (None, "under threshold")
        elif AGGREGATE_INDIVIDUALS.search(u) or (PERSON.match(u) and not NOT_PERSON.search(u)):
            res = (None, "individual")
        elif OUT_OF_PROVINCE.search(u) and not re.search(r"\bONTARIO\b|\bONT\b", u):
            res = (None, "out-of-province")
        elif n in RECIPIENT_POSTAL and locate_pc(RECIPIENT_POSTAL[n]):
            res = (locate_pc(RECIPIENT_POSTAL[n]), "postal code from federal or charity records")
        elif any(norm(seg) in RECIPIENT_PLACES and locate_place(RECIPIENT_PLACES[norm(seg)]) for seg in [name] + segments(name)):
            key = next(norm(seg) for seg in [name] + segments(name) if norm(seg) in RECIPIENT_PLACES and locate_place(RECIPIENT_PLACES[norm(seg)]))
            res = (locate_place(RECIPIENT_PLACES[key]), "place name in recipient (approx.)")
        else:
            for seg in [name] + segments(name):
                key = norm(seg)
                if key in name_pc and locate_pc(name_pc[key]):
                    res = (locate_pc(name_pc[key]), "postal code from federal or charity records")
                    break
            if res[0] is None:
                key = muni_key(name)
                if key:
                    d = locate_place(key)
                    if d:
                        res = (d, "municipality")
            if res[0] is None:
                key = nation_key(name)
                if key:
                    d = locate_place(key) or locate_place(key + " FIRST NATION") or locate_place(re.sub(r"\s+(FIRST NATION|INDIAN BAND|BAND)$", "", key))
                    if d:
                        res = (d, "municipality")
            if res[0] is None and not re.search(r"\bONTARIO$|OF ONTARIO\b|^ONTARIO\b", n):
                # Every place name inside the recipient's name; the biggest place (most GeoNames
                # postal codes) wins.
                pn = place_norm(name)
                hits = [(len(places.get(p, ())) or 50, len(p), p) for p in set(place_re.findall(pn))]
                for _, _, p in sorted(hits, reverse=True):
                    d = locate_place(p)
                    if d:
                        res = (d, "place name in recipient (approx.)")
                        break
        loc_cache[name] = res
        return res

    def spans_districts(key, limit=60):
        """True when a town (20+ postal codes) has over 15% of its postal-code points outside
        its main riding. Villages with a handful of coarse rural centroids never count."""
        pts = places.get(key) or []
        if len(pts) < 20:
            return False
        step = max(1, len(pts) // limit)
        hits = Counter(index.locate(*p)[0] for p in pts[::step])
        hits.pop(None, None)
        return bool(hits) and hits.most_common(1)[0][1] < 0.85 * sum(hits.values())

    multi_division = {}

    def is_supplier(name, detail):
        u = upper(name)
        if HOSPITAL.search(u) and not re.search(r"HOSPITAL ASSOCIATION|HEALTH CARE PRODUCTS|HEALTHCARE PRODUCTS|SUPPL", u):
            return False
        if STRONG_SUPPLIER.search(u):
            return True
        if re.search(r"ASSISTIVE DEVICES|DRUG PROGRAMS", detail or "", re.I) and not re.search(r"HOSPITAL|HEALTH (SCIENCES|NETWORK|CENTRE|SYSTEM)", u):
            return True
        if NONPROFIT.search(u):
            return False
        if NUMBERED.search(norm(name)) or NUMBERED.search(u):
            return True
        if INDUSTRY.search(u):
            return True
        if SUPPLIER_SUFFIX.search(re.sub(r"[^A-Z0-9 ]", " ", u)):
            return True
        return False

    def flag_for(name, kind, detail):
        """Why a placed payment is left out of the adjusted totals, or ""."""
        u = upper(name)
        if PROVINCEWIDE.search(u) and not (HOSPITAL.search(u) and not re.search(r"^ONTARIO HEALTH\b|HOSPITAL ASSOCIATION|HOSPITAL FOUNDATION", u)):
            return "province-wide"
        if ACUTE.search(u) and not NOT_ACUTE.search(u):
            return "province-wide"  # hospitals: regional bodies, see ACUTE
        if REGIONAL.search(u):
            return "other government"
        key = None if nation_key(name) else muni_key(name)
        if key:
            if key in BIG_CITIES or key.replace(" ", "") in BIG_CITIES:
                return "other government"
            if key not in multi_division:
                multi_division[key] = spans_districts(key)
            if multi_division[key]:
                return "other government"
            return ""
        if kind == "other" or is_supplier(name, detail):
            return "supplier"
        return ""

    rows, other_types, coverage = read_rows()
    series_fyes = sorted({r["fye"] for r in rows})  # every fiscal year read, windows or not
    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": [], "series": Counter()} for num in divisions}
    is_formula = formula_matcher("ontario")
    method_counts = Counter()
    excluded = Counter()
    buckets = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    fy_label = {fy: f"FY{fy - 1}-{str(fy)[2:]}" for fy in WINDOWS}
    audit = []  # every row's classification, written to $ON_PLACEMENTS when set (for checking the rules)
    for r in rows:
        v = r["Amount"]
        window = WINDOWS.get(r["fye"])  # None for years outside the windows: placed for the series only
        if v <= 0:
            continue
        program = r["Ministry"]
        num, how = place(r["Recipient"])
        flag = "" if how in ("withheld", "individual", "out-of-province", "under threshold") else flag_for(r["Recipient"], r["Kind"], r["Detail"])
        if window:
            audit.append([window, program, r["Kind"], r["Recipient"], round(v), num or "", how, flag])
        if how in ("withheld", "individual", "out-of-province", "under threshold"):
            if window:
                kind = {"withheld": "withheld", "individual": "individuals", "out-of-province": "out-of-province",
                        "under threshold": "accounts under threshold"}[how]
                excluded[(window, kind)] += v
                buckets[(window, kind)] += v
            continue
        if num is None:
            kind = {"province-wide": "province-wide bodies", "supplier": "suppliers", "other government": "other governments"}.get(flag, "unmatched")
            if window:
                excluded[(window, kind)] += v
                buckets[(window, flag or "unmatched")] += v
                if window == "after" and kind == "unmatched":
                    unmatched[r["Recipient"]] += v
            continue
        r["formula"] = bool(is_formula(f'{program} | {r["Recipient"]}'))  # allocated by a published rule, per data/formula_programs.json
        p = per[num]
        if not flag:
            p["series"][r["fye"]] += v
        if not window:
            continue
        method_counts[(window, how)] += 1
        buckets[(window, flag or "counted")] += v
        p[window]["total"] += v
        p[window]["n"] += 1
        if not flag:
            p[window]["adj"] += v
            p[window]["adj_n"] += 1
            if r["formula"]:
                p[window]["formula"] += v
        else:
            flagged_total[(window, r["Recipient"])] += v
        if window == "after":
            p["progs"][program] += v
            if not flag:
                prog_totals[program][num] += v
            p["grants"].append((v, r, flag, how))

    if os.environ.get("ON_PLACEMENTS"):
        with open(os.environ["ON_PLACEMENTS"], "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["window", "ministry", "kind", "recipient", "amount", "riding", "how", "flag"])
            w.writerows(audit)

    out = {}
    for num, dv in divisions.items():
        p = per[num]
        pop = dv["population"] or 1
        a, b = p["after"], p["before"]
        rec = dict(dv)
        by_recipient = defaultdict(lambda: {"v": 0.0, "n": 0, "progs": Counter(), "flag": "", "how": "", "last": "", "formula": False, "src_v": 0.0, "src": None})
        for v, r, fl, how in p["grants"]:
            g = by_recipient[r["Recipient"]]
            g["v"] += v
            g["n"] += 1
            if v > g["src_v"]:  # the link points at the recipient's largest row
                g["src_v"], g["src"] = v, source_url(r)
            g["progs"][r["Ministry"]] += v
            g["formula"] = g["formula"] or r["formula"]
            g["flag"], g["how"], g["last"] = fl, how, fy_label[r["fye"]]
        top = sorted(by_recipient.items(), key=lambda kv: -kv[1]["v"])[:10]
        rec.update({
            "after_total": round(a["total"]), "after_n": a["n"], "after_adj": round(a["adj"]), "after_adj_n": a["adj_n"],
            "before_total": round(b["total"]), "before_adj": round(b["adj"]),
            "after_formula": round(a["formula"]), "before_formula": round(b["formula"]),
            "pc_after": round(a["adj"] / pop / YEARS, 2), "pc_after_all": round(a["total"] / pop / YEARS, 2),
            "pc_before": round(b["adj"] / pop / YEARS, 2),
            "close": dv["margin_pts"] < CLOSE_MARGIN,
            "gov_won": dv["party_2025"] == GOV_PARTY,
            "top_progs": [[k, round(v)] for k, v in p["progs"].most_common(4)],
            "top_grants": [{"v": round(g["v"]), "who": who[:80], "n": g["n"], "prog": "; ".join(k for k, _ in g["progs"].most_common(2))[:120],
                            "date": g["last"], "flag": g["flag"], "how": g["how"], "formula": g["formula"],
                            **({"src": g["src"]} if g["src"] else {})} for who, g in top],
        })
        rec["change_pct"] = round(100 * (a["adj"] - b["adj"]) / b["adj"], 1) if b["adj"] > 0 else None
        rec["series"] = [round(p["series"][fye]) for fye in series_fyes]
        out[num] = rec
    med = statistics.median(x["pc_after"] for x in out.values())
    for x in out.values():
        x["score"] = round(x["pc_after"] / med, 2) if med else None
        x["group"] = ("Close" if x["close"] else "Safe") + (f" {GOV_PARTY}" if x["gov_won"] else f" {OPP_LABEL}")
    groups = {}
    for g in [f"Close {GOV_PARTY}", f"Close {OPP_LABEL}", f"Safe {GOV_PARTY}", f"Safe {OPP_LABEL}"]:
        xs = [x for x in out.values() if x["group"] == g]
        chg = [x["change_pct"] for x in xs if x["change_pct"] is not None]
        groups[g] = {"ridings": len(xs), "median_pc_after": round(statistics.median(x["pc_after"] for x in xs), 2) if xs else None,
                     "median_pc_before": round(statistics.median(x["pc_before"] for x in xs), 2) if xs else None,
                     "median_change_pct": round(statistics.median(chg), 1) if chg else None,
                     "total_adj_after": round(sum(x["after_adj"] for x in xs))}
    total_after = sum(v for (w, _), v in excluded.items() if w == "after") + sum(x["after_total"] for x in out.values())
    after_fy = next(fy for fy, w in WINDOWS.items() if w == "after")
    first = next(iter(divisions.values()))
    meta = {
        "generated": date.today().isoformat(), "election": ELECTION.isoformat(), "cutoff": CUTOFF.isoformat(),
        "before_start": BEFORE_START.isoformat(), "before_end": BEFORE_END.isoformat(), "years_per_window": YEARS,
        "after_fiscal_year": fy_label[after_fy], "windows": WINDOW_NOTE,
        "straddles_election": False,
        "population_basis": ("2021 census: Statistics Canada's count for the identical 2013-order federal electoral district for 111 ridings; "
                             "2021 census subdivisions summed by centroid for the 13 northern ridings, which are not federal districts; "
                             + first.get("population_basis", "").split(";")[-1].strip()),
        "close_margin": CLOSE_MARGIN, "median_pc_after": med,
        "search_url": SEARCH_URL,
        "series": {"kind": "fiscal year", "labels": [f"{fye - 1}-{str(fye)[2:]}" for fye in series_fyes], "complete": len(series_fyes),
                   "election_index": max([i for i, fye in enumerate(series_fyes) if date(fye, 3, 31) < ELECTION], default=-1)},
        "methods": {f"{w}|{m}": v for (w, m), v in method_counts.items()},
        "excluded_after": {m: round(v) for (w, m), v in excluded.items() if w == "after"},
        "buckets_after": {m: round(v) for (w, m), v in sorted(buckets.items(), key=lambda kv: -kv[1]) if w == "after"},
        "other_payment_types_after": {m: round(v) for (w, m), v in other_types.items() if w == "after"},
        "coverage": coverage,
        "placed_after": round(sum(x["after_total"] for x in out.values())),
        "total_after": round(total_after),
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
