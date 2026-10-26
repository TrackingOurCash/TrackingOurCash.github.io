"""Nova Scotia: aggregate provincial payments by electoral district.

Reads the Public Accounts "Volume 3 - Supplement to the Public Accounts" PDFs in
data/raw/ns/dl/pa-supplementary-<fye>.pdf (one per fiscal year ending 31 March <fye>;
published by the Department of Finance and Treasury Board at
https://notices.novascotia.ca/files/public-accounts/<fye>/pa-supplementary-<fye>.pdf, a host
that refuses connections from here, so new volumes are looked for on the Internet Archive)
and data/ns/divisions.json (from ns_prep.py). Writes data/ns/division_spending.json with
the same shape as the New Brunswick file.

The volume lists, department by department, four sections: "Salaries" (employees paid
$25,000 or more, then "Salaries Under $25,000" as one line, external secondments), "Travel"
(employees with $3,500 or more), "Grants and Contributions" (every payee of $5,000 or more,
then "Accounts Under $5,000" as one line) and "Other" (goods and services: every supplier
paid $5,000 or more). Each section ends with its printed total, each department with
"Total, Department of ...". There is no address, no program and no date. So:
  * Only the "Grants and Contributions" and "Other" sections are used. Salaries, travel
    and secondments are dropped (their dollars are in meta.dropped_sections_after).
  * Department stands in for the program (top_progs, programs, prog_by_riding,
    top_grants.prog are department names; for the "Public Service" chapter the agency
    named in its block, e.g. "Communications Nova Scotia"), and top_grants.date is the
    fiscal-year label "FY2024-25".
  * "Other" rows are purchases: they are placed and flagged "supplier" (or "province-wide",
    "other government", "intra-government" when the payee is one of those), so they show in
    pc_after_all and the top recipients but never in the adjusted figures. Only "Grants and
    Contributions" rows can be counted.
  * Lines that are not payees (Accounts Under $5,000, Accounts Payable Adjustments,
    Chargeables to Other Departments, amortization, "DCS ICM Client Payments", the
    refundable tax credits, Restructuring Costs, student grants and loan forgiveness,
    teachers' pension refunds, Disaster Relief, ...) count under
    excluded_after["program aggregates (no payee)"].
  * Windows are whole fiscal years. The election was 26 November 2024. The FY2025-26
    volume is published around the end of the following calendar year and did not exist
    on 26 October 2026, so "after" is FY2024-25 (1 April 2024 to 31 March 2025), which
    STRADDLES the election: eight months of it fall before the vote, four after. The
    "before" window is FY2023-24. years_per_window = 1.0. The script looks for
    data/raw/ns/dl/pa-supplementary-2026.pdf, asks the Internet Archive for a copy of the
    official URL when it is missing, and when the file exists switches to after = FY2025-26,
    before = FY2023-24 (FY2024-25 then skipped as the straddling year). FY2022-23 is read
    for the series only. Each year's adjusted dollars go into a per-district time series
    (ridings[num].series, aligned to meta.series.labels).
    meta: election 2024-11-26, cutoff = end of the after year, before_start/before_end =
    the before year.
  * Every volume's rows are written to data/raw/ns/payees_<fy>.csv (department, section,
    payee, amount, page) for inspection, with data/raw/ns/payees_<fy>_check.json recording
    how the parsed rows compare with the printed section and department totals. The CSV
    is the cache: delete it to re-read the PDF.

Each payment is placed by the recipient's name, in this order (as nb_spending.py does):
  1. the same name in the federal grants file, data/name_postal.json ("NS|name" keys);
  2. the CRA list of registered charities with Province NS (name -> postal code), then the
     province's directories of long-term care facilities and licensed child care
     (data.novascotia.ca; name -> coordinates, fetched once into data/raw/ns/dl/);
  3. a municipality ("Town of X", "Municipality of the County/District of X", "Region of
     Queens Municipality", "Halifax Regional Municipality", "Village of X") -> the GeoNames
     centroid of its seat (MUNI_SEATS), or a First Nation ("X First Nation", "X Band")
     -> FIRST_NATIONS (hand-set coordinates of the band office);
  4. RECIPIENT_PLACES, a short hand-set table for the largest adult residential and
     rehabilitation centres whose names carry no place (Kings Regional Rehabilitation
     Centre -> Waterville, Quest -> Lower Sackville, Sunset -> Pugwash, ...);
  5. a place name inside the recipient's name ("Yarmouth Heights Seniors Residence");
     when several match, the place with the most GeoNames postal codes wins. Halifax,
     Dartmouth, Sydney, Bedford and Sackville each span several districts, so a bare
     "Halifax" in a name never places a payee (about $8 M a year stays unmatched for it).
Postal codes and place names come from GeoNames CA_full.txt (province NS; "St"/"Ste"
expanded, accents stripped) and are located by point-in-polygon on the 2026 boundaries in
data/ns/divisions_geo.json. GeoNames names that are also surnames, counties or ordinary
words (Kings, Queens, Victoria, Windsor, Valley, Cape Breton, ...) are never place hits.

Classification (decided before placing; each bucket's dollars are in meta.buckets_after):
  * "individuals": payees written "Surname, Given"; never placed.
  * "out-of-province": other governments and bodies outside Nova Scotia (Receiver General,
    New Brunswick Minister of Finance, Régie de l'assurance maladie du Québec, University
    of Prince Edward Island, Memorial University, ...); never placed.
  * "intra-government": the province paying itself ("Department of ...", Public Service
    Commission, Communications Nova Scotia, Purchasing Card, Telephone Network); never
    placed.
  * "province-wide": Nova Scotia Health, the IWK, Emergency Medical Care / EHS, the
    universities and NSCC, the regional centres for education and the CSAP, Housing Nova
    Scotia / the Provincial Housing Agency, the Crown corporations and agencies (Build /
    Develop / Invest Nova Scotia, Events East, Research Nova Scotia, Perennia, Efficiency
    One, NS Liquor, Art Gallery, Nova Scotia Lands, Municipal Finance Corporation, ...),
    Mi'kmaw Kina'matnewey and the tribal councils, the unions and professional bodies,
    bodies named "... of Nova Scotia" / "Nova Scotia ...", "Province of", "Government of".
    Placed when a location is known (so they show in the district's top recipients,
    flagged) and excluded from the adjusted totals; when they cannot be placed they count
    under excluded_after["province-wide bodies"].
  * "other government": Halifax and Cape Breton regional municipalities, the regional,
    county and district municipalities that span several districts (Kings, Colchester,
    Pictou, Cumberland, Annapolis, Inverness, Lunenburg, East and West Hants); placed at
    the seat and flagged. Towns and the county/district municipalities inside one district
    (Argyle, Barrington, Clare, Chester, Richmond, Victoria, Guysborough, St. Mary's, ...)
    count.
  * "supplier": every "Other" row, and in "Grants and Contributions" obvious suppliers of
    goods and services (Ltd/Inc/Corp with an industry word, hotels, numbered companies,
    pharmacies, fuel, construction, consulting, software, equipment, law firms, banks)
    unless a care or community word (home, manor, villa, care, residence, daycare, society,
    association, co-op, church, club, school, First Nation, ...) is present; a strong
    supplier word (construction, paving, truck, leasing, equipment, hotel, insurance, bank,
    in trust, holdings, pharmacy) wins over the care word.
  * everything else (non-profits, towns, First Nations, nursing homes, child-care
    operators, libraries, farms and small businesses paid by Agriculture or Tourism)
    counts in the adjusted totals.

Groups: "Close PC", "Close opposition", "Safe PC", "Safe opposition"; gov_won means the
Progressive Conservatives (who won government in 2024) won the seat; close means a margin
under 10 points. Chéticamp-Margarees-Pleasant Bay is grouped by its 2026 by-election result.

Checking the rules: NS_PLACEMENTS=/path/to/file.tsv python3 scripts/ns_spending.py also
writes every row's window, department, section, recipient, amount, district, method, flag.
"""
import csv
import json
import os
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
DL = RAW / "ns" / "dl"
OUT = ROOT / "data" / "ns"
sys.path.insert(0, str(ROOT / "scripts"))
import sk_pdf  # noqa: E402
from geo import RidingIndex, load_centroids  # noqa: E402
from build_spending import formula_matcher, recipient_table  # noqa: E402

ELECTION = date(2024, 11, 26)
BEFORE_START, BEFORE_END = date(2023, 4, 1), date(2024, 3, 31)
YEARS = 1.0
CLOSE_MARGIN = 10.0
GOV_PARTY = "PC"
OPP_LABEL = "opposition"
OFFICIAL_URL = "https://notices.novascotia.ca/files/public-accounts/{fye}/pa-supplementary-{fye}.pdf"
WINDOW_NOTE = {
    2025: "after = FY2024-25 (1 April 2024 to 31 March 2025, which straddles the 26 November 2024 election: eight months before "
          "the vote, four after; the FY2025-26 volume was not yet published); before = FY2023-24 (1 April 2023 to 31 March 2024), "
          "the last full fiscal year before the election; annual data, no payment dates",
    2026: "after = FY2025-26 (1 April 2025 to 31 March 2026), the first full fiscal year after the 26 November 2024 election; "
          "before = FY2023-24 (1 April 2023 to 31 March 2024), the last full fiscal year before it; FY2024-25 straddles the "
          "election and is skipped; annual data, no payment dates",
}
# Internet Archive copies of the volumes (the official host refuses connections from here);
# top_grants.src links these, opened at the page the payee's line was parsed from. FY2022-23
# (pa-supplementary-2023.pdf) has no archived copy, so its rows link the official URL.
ARCHIVE_TIMESTAMPS = {2024: "20260413123039", 2025: "20260416080444"}
SOURCE_URLS = {fye: f"https://web.archive.org/web/{ts}/{OFFICIAL_URL.format(fye=fye)}" for fye, ts in ARCHIVE_TIMESTAMPS.items()}
SEARCH_URL = "https://duckduckgo.com/?q={q}+Nova+Scotia+grant"  # {q}: the recipient, URL-encoded by the page
USED_SECTIONS = {"Grants and Contributions", "Other"}
# Whole chapters that hold no payees.
AGGREGATE_DEPTS = re.compile(r"^(Refundable Tax Credits|Restructuring Costs|Pension Valuation Adjustment|Finance and Treasury Board-Debt Servicing Costs|"
                             r"Government Contributions to Benefit Plans)$")
AGGREGATE = re.compile(
    r"^(Accounts (Under|Payable)|Salaries Under|Amortization|Bad Debt|Chargeables|Net TCA|Purchasing Card|Telephone Network|Fringe Benefits|"
    r"Total\b|Restructuring Costs|Refund |Disaster Relief|Property Tax Rebate|Interest Relief|Loan Forgiveness|Canada Study Grant|Nova Scotia Student Grant|"
    r"Education Programs$|Other Educational Grants|Rehabilitation Training Allowance|Pension Valuation|Debt Servicing|Interest on |"
    r"Provincial Share|Grants in Lieu|Capital Grants$|Operating Grants$|Special Grants$|Miscellaneous|Sundry|Write-?offs?$|Recoveries$|"
    r"Prior Year|Valuation Allowance|Provision for|Unallocated)|"
    r"(Client Payments|Tax Credits?|Tax Rebates?|Rebate Program|Pensions|Benefit Payments|Income Assistance|Assistance Payments|Allowances|"
    r"Grant Program|Tax Benefit|Benefit|Supplement|Bursar(y|ies)|Scholarships?|Rebates?|Subsid(y|ies)|Refunds?)$",
    re.I)
# "Surname, Given" (one to three words each side, no corporate word): a person.
PERSON = re.compile(r"^[A-Z'\-]+( [A-Z'\-]+){0,2}, [A-Z'\-.]+( [A-Z'\-.]+){0,3}$")
NOT_PERSON = re.compile(r"\b(INC|LTD|LTEE|LLP|LLC|LP|LIMITED|CORP|CO|DIVISION|PLAN|OFFICE|SERVICES?|GROUP|TRUST|PARTNERS|CONSULTANTS?|CONSULTING|"
                        r"ASSOCIATES|CANADA|NS|NOVA SCOTIA|CENTRE|CENTER|FARMS?|HOLDINGS|ENTERPRISES|AGENCY|CLINIC|"
                        r"PHARMACY|FOUNDATION|DEPARTMENT|HOSPITALS?|UNIVERSITY|CITY|TOWN|VILLAGE|DR|MD|DDS|DVM)\b")
OUT_OF_PROVINCE = re.compile(
    r"RECEIVER GENERAL|CANADA REVENUE|GOVERNMENT OF (CANADA|ALBERTA|YUKON|ONTARIO|QUEBEC|NEW BRUNSWICK|MANITOBA|SASKATCHEWAN|BRITISH COLUMBIA|"
    r"PRINCE EDWARD|NEWFOUNDLAND|NUNAVUT|NORTHWEST)|MINISTER OF FINANCE|MINISTRY OF|MINISTERE DE|MINISTÈRE DE|\bHER MAJESTY|HIS MAJESTY|"
    r"NEW BRUNSWICK|QUEBEC|ONTARIO|PRINCE EDWARD ISLAND|NEWFOUNDLAND|ALBERTA|BRITISH COLUMBIA|MANITOBA|SASKATCHEWAN|YUKON|NUNAVUT|"
    r"\bMAINE\b|MEMORIAL UNIVERSITY|UNIVERSITY OF NEW BRUNSWICK|UNIVERSITE DE MONCTON|UNIVERSITÉ DE MONCTON|UNIVERSITY OF PRINCE|MCGILL|"
    r"UNIVERSITY OF TORONTO|UNIVERSITY OF OTTAWA|MICHENER INSTITUTE|\bUHN\b|\bPEI\b|\bP\.E\.I\b|\bNB\b|\bNL\b|"
    r"DESTINATION CANADA|CANADIAN TOURISM COMMISSION|TREASURER OF|STATE OF|COUNCIL OF ATLANTIC PREMIERS|COUNCIL OF (THE )?FEDERATION|"
    r"CANADIAN BLOOD SERVICES|CANADA HEALTH INFOWAY|CANADIAN INSTITUTE FOR HEALTH|INTERNATIONAL REGISTRATION PLAN|"
    r"CANADIAN AGENCY FOR DRUGS|CANADIAN COUNCIL OF|CANADIAN INTERGOVERNMENTAL|CANADA MORTGAGE|CANADIAN NUCLEAR|COUNCIL OF MINISTERS OF EDUCATION|"
    r"CITY OF (MONCTON|SAINT JOHN|FREDERICTON|CHARLOTTETOWN|ST\.? JOHN'S|OTTAWA|TORONTO|MONTREAL)|FORUM OF LABOUR|"
    r"ATLANTIC (LOTTERY|VETERINARY)|HOSPITALS? - |CANADIAN FOOD INSPECTION|FISHERIES AND OCEANS CANADA|PARKS CANADA|"
    r"ENVIRONMENT (AND CLIMATE CHANGE )?CANADA|HEALTH CANADA|SERVICE CANADA|STATISTICS CANADA|NATURAL RESOURCES CANADA|"
    r"EMPLOYMENT AND SOCIAL DEVELOPMENT CANADA|IMMIGRATION, REFUGEES|PUBLIC SERVICES AND PROCUREMENT|CANADIAN HERITAGE|"
    r"TRANSPORT CANADA|INFRASTRUCTURE CANADA|INDIGENOUS SERVICES CANADA|CROWN-INDIGENOUS|VETERANS AFFAIRS|CANADIAN COAST GUARD|"
    r"ROYAL CANADIAN MOUNTED POLICE|\bRCMP\b|DEPARTMENT OF NATIONAL DEFENCE|NATIONAL RESEARCH COUNCIL|CANADA COUNCIL|"
    r"COMMUNITY HOUSING TRANSFORMATION CENTRE|CANADIAN HOUSING|CANADIAN MEDICAL ASSOCIATION|CANADIAN CANCER SOCIETY$|CANADIAN PAEDIATRIC",
    re.I)
INTRA_GOV = re.compile(
    r"^DEPARTMENT OF |^DEPT OF |^PUBLIC SERVICE COMMISSION$|^COMMUNICATIONS NOVA SCOTIA|^PURCHASING CARD|^TELEPHONE NETWORK|"
    r"^NOVA SCOTIA DEPARTMENT|^EXECUTIVE COUNCIL OFFICE|^OFFICE OF THE (SPEAKER|AUDITOR|OMBUDSMAN)|^TREASURY BOARD|"
    r"^MINISTER OF (FINANCE|JUSTICE)|^PROVINCE OF NOVA SCOTIA$|^GOVERNMENT OF NOVA SCOTIA$|^NOVA SCOTIA PROVINCIAL GOVERNMENT$|"
    r"^OFFICE OF (ADDICTIONS|EQUITY|HEALTHCARE|L'NU|SERVICE EFFICIENCY|THE INFORMATION|IMMIGRATION|REGULATORY|PRIORITIES|THE PREMIER)|"
    r"^INTERGOVERNMENTAL AFFAIRS|^SERVICE NOVA SCOTIA|^PUBLIC PROSECUTION SERVICE|^ELECTIONS NOVA SCOTIA|^HUMAN RIGHTS COMMISSION|"
    r"^NOVA SCOTIA (UTILITY AND REVIEW BOARD|SECURITIES COMMISSION|POLICE COMPLAINTS)|^PROVINCIAL (TREASURY|COURT)|^NS DEPT",
    re.I)
PROVINCEWIDE = re.compile(
    r"NOVA SCOTIA HEALTH|\bNSHA\b|\bNSH\b|IZAAK WALTON KILLAM|\bIWK\b|EMERGENCY MEDICAL CARE|EMERGENCY HEALTH SERVICES|\bEHS\b|\bEMC\b|"
    r"MEDAVIE|LIFEFLIGHT|CANADIAN BLOOD|DOCTORS NOVA SCOTIA|NOVA SCOTIA MEDICAL|COLLEGE OF (PHYSICIANS|NURSES|PHARMACISTS|REGISTERED|"
    r"LICENSED|PARAMEDICS|DENTAL|OPTOMETRISTS|PHYSIOTHERAPISTS|OCCUPATIONAL|PSYCHOLOGISTS|SOCIAL WORKERS|EARLY|CHIROPRACTORS)|"
    r"DALHOUSIE|SAINT MARY'?S UNIVERSITY|ST\.? FRANCIS XAVIER|ST FX|STFX|ACADIA UNIVERSITY|CAPE BRETON UNIVERSITY|MOUNT SAINT VINCENT|"
    r"UNIVERSITY OF KING'?S|UNIVERSITE SAINTE-?ANNE|UNIVERSITÉ SAINTE-?ANNE|NSCAD|NOVA SCOTIA COLLEGE OF ART|ATLANTIC SCHOOL OF THEOLOGY|"
    r"NOVA SCOTIA COMMUNITY COLLEGE|\bNSCC\b|UNIVERSITY|UNIVERSITE|UNIVERSITÉ|MARITIME PROVINCES HIGHER EDUCATION|COLLEGE$|COLLEGE OF|"
    r"REGIONAL CENTRE FOR EDUCATION|CENTRE FOR EDUCATION|CONSEIL SCOLAIRE ACADIEN|\bCSAP\b|SCHOOL BOARD|ATLANTIC PROVINCES SPECIAL EDUCATION|"
    r"\bAPSEA\b|MI'?KMAW KINA'?MATNEWEY|\bMK\b|NOVA SCOTIA TEACHERS|TEACHERS UNION|TEACHERS' UNION|\bNSGEU\b|\bNSNU\b|NURSES'? UNION|"
    r"\bCUPE\b|\bIUOE\b|\bNSUPE\b|UNION OF NOVA SCOTIA|\bUNSM\b|NOVA SCOTIA FEDERATION OF MUNICIPALITIES|ASSOCIATION OF MUNICIPAL|"
    r"HOUSING NOVA SCOTIA|NOVA SCOTIA PROVINCIAL HOUSING|PROVINCIAL HOUSING AGENCY|HOUSING AUTHORITY|NOVA SCOTIA HOUSING|"
    r"BUILD NOVA SCOTIA|DEVELOP NOVA SCOTIA|INVEST NOVA SCOTIA|NOVA SCOTIA BUSINESS INC|\bNSBI\b|INNOVACORP|EVENTS EAST|"
    r"RESEARCH NOVA SCOTIA|PERENNIA|EFFICIENCY ?ONE|EFFICIENCY NOVA SCOTIA|NOVA SCOTIA LIQUOR|\bNSLC\b|ART GALLERY OF NOVA SCOTIA|"
    r"NOVA SCOTIA LANDS|NOVA SCOTIA MUNICIPAL FINANCE|MUNICIPAL FINANCE CORP|CROP AND LIVESTOCK INSURANCE|NOVA SCOTIA FARM LOAN|"
    r"FISHERIES AND AQUACULTURE LOAN|NOVA SCOTIA PENSION|PENSION SERVICES|PUBLIC SERVICE SUPERANNUATION|TEACHERS' PENSION|"
    r"WORKERS'? COMPENSATION BOARD|\bWCB\b|NOVA SCOTIA LEGAL AID|LEGAL AID|NOVA SCOTIA BARRISTERS|TOURISM NOVA SCOTIA|"
    r"NOVA SCOTIA GAMING|ATLANTIC LOTTERY|HALIFAX.DARTMOUTH BRIDGE|HALIFAX HARBOUR BRIDGES|NOVA SCOTIA POWER|NS POWER|EMERA|VON CANADA|VICTORIAN ORDER|"
    r"CANADIAN RED CROSS|UNITED WAY|CENTRAIDE|NOVA SCOTIA WORKS|SPECIAL OLYMPICS NOVA SCOTIA|SPORT NOVA SCOTIA|RECREATION NOVA SCOTIA|"
    r"NOVA SCOTIA (ASSOCIATION|FEDERATION|SOCIETY|COUNCIL|FOUNDATION|COMMISSION|NETWORK|COALITION|ALLIANCE|INSTITUTE|UNION|TRUST|"
    r"ADVISORY|ARTS|APPRENTICESHIP|BOXING|CRIME STOPPERS|FISHERIES|FORESTRY|CATTLE|EGG|PORK|CHICKEN|TURKEY|FRUIT|APPLE|BLUEBERRY|"
    r"CRANBERRY|MINK|SHEEP|HONEY|MAPLE|CHRISTMAS TREE|LANDSCAPE|WOODLOT|SALMON|SEAFOOD|LOBSTER|AQUACULTURE|TRAILS|SNOWMOBILE|"
    r"OFF HIGHWAY|HOCKEY|SOCCER|BASEBALL|CURLING|GYMNASTICS|LACROSSE|RUGBY|SAILING|SKI|SWIMMING|TENNIS|TRACK|VOLLEYBALL|"
    r"EQUESTRIAN|GOLF|BASKETBALL|FOOTBALL|SCHOOL ATHLETIC|MUSIC|CHORAL|CRAFTS|DESIGNER|BOOK|WRITERS|FILM|TALENT|MUSEUM|"
    r"LIBRARY|LIBRARIES|ARCHIVES|HISTORICAL|GENEALOGY|LEAGUE|SENIORS|ABORIGINAL|NATIVE|MI'?KMAQ|MI'?KMAW|AFRICAN|BLACK|ACADIAN|"
    r"ACADIEN|GAELIC|MULTICULTURAL|IMMIGRANT|FRANCOPHONE|HEALTH|NURSES|PHARMAC|DENTAL|HOME CARE|HOME SUPPORT|CONTINUING CARE|"
    r"NURSING HOMES|LONG TERM CARE|EARLY CHILDHOOD|CHILD CARE|CHILDCARE|FAMILY RESOURCE|TRANSITION HOUSE|STATUS OF WOMEN|"
    r"LEGION|FIREFIGHTERS|GROUND SEARCH|SEARCH AND RESCUE|AMATEUR|CADET|SCOUTS|GUIDES|4-H|HORTICULTUR|AGRICULTUR|FARMERS|"
    r"YOUNG FARMERS|ORGANIC|ENVIRONMENT|NATURE|WILDLIFE|SALMON|TRAILS|LUNG|HEART|CANCER|KIDNEY|DIABETES|AUTISM|BRAIN INJURY|"
    r"SCHIZOPHRENIA|ALZHEIMER|EPILEPSY|MS SOCIETY|DISABILIT|DEAF|BLIND|LEARNING DISAB|LITERACY|READING|DOWN SYNDROME|"
    r"EARLY INTERVENTION|SPEECH|HEARING|VISION|COMMUNITY LINKS|COMMUNITY TRANSPORT|HOUSING|TENANTS|LANDLORD|HOME BUILDERS|"
    r"CONSTRUCTION ASSOC|ROAD BUILDERS|TRUCKING|TOURISM|HOTEL ASSOC|RESTAURANT ASSOC|CHAMBER|BUSINESS|CO-?OPERATIVE COUNCIL|"
    r"CREDIT UNION|VOLUNTARY|VOLUNTEER|NON-?PROFIT|COMMUNITY|SOCIAL WORKERS|PSYCHOLOG|MENTAL HEALTH|ADDICTION|RECOVERY|"
    r"PUBLIC INTEREST|LAW REFORM|HUMAN RIGHTS|CIVIL LIBERTIES|VICTIM|RESTORATIVE|CRIMINAL|POLICE|CHIEFS OF POLICE|"
    r"PUBLIC HEALTH|MEDICAL|PARAMEDIC|PHYSIO|OCCUPATIONAL|DIETITIAN|MIDWI|DOULA|DOCTORS|PHYSICIAN|RURAL HEALTH|"
    r"SENIORS|ELDER|VETERANS|WOMEN|MEN'S|YOUTH|CHILDREN|FAMILY|PARENT|FOSTER|ADOPT|PREGNANCY|LGBT|RAINBOW|PRIDE|"
    r"INTERNATIONAL|GLOBAL|WORLD)|"
    r"\bNS (ASSOCIATION|FEDERATION|SOCIETY|COUNCIL|FOUNDATION|COMMISSION|NETWORK|COALITION|ALLIANCE|INSTITUTE|UNION|TRUST|ASSN|HEALTH|"
    r"NURSES|SENIORS|TEACHERS|MUNICIPAL)|"
    r"^NOVA SCOTIA [A-Z'&,\- ]+ (ASSOC|ASSOCIATION|SOCIETY|FEDERATION|COUNCIL|FOUNDATION|NETWORK|ALLIANCE|COALITION|INSTITUTE|UNION|BOARD|"
    r"COMMISSION|AGENCY|AUTHORITY|CORPORATION|CORP|INC|LTD|LIMITED|TRUST|LEAGUE|GUILD|PARTNERSHIP|COOPERATIVE|CO-OPERATIVE|CO-OP)$|"
    r"(ASSOCIATION|FEDERATION|FÉDÉRATION|SOCIETY|SOCIETE|SOCIÉTÉ|COUNCIL|CONSEIL|FOUNDATION|FONDATION|INSTITUTE|INSTITUT|NETWORK|RESEAU|RÉSEAU|"
    r"COALITION|ALLIANCE|ASSEMBLY|CHAMBER|BOARD|OFFICE|COMMISSION|CORPORATION|LEAGUE|CONFERENCE|UNION|TRUST|AUTHORITY|AGENCY|CENTRE|CENTER|"
    r"PARTNERSHIP|ASSOC|BUREAU|COLLEGE|GUILD|CHAPTER|ORDER|SYNOD|DIOCESE) "
    r"(OF|FOR|DU|DE|DES|POUR|IN) .*(NOVA SCOTIA|NOUVELLE-ECOSSE|NOUVELLE-ÉCOSSE|NOUVELLE ECOSSE|\bN\.?S\.?\b)|"
    r"(NOVA SCOTIA|NOUVELLE-ECOSSE|NOUVELLE-ÉCOSSE|NOUVELLE ECOSSE)$|"
    r"FEDERATION ACADIENNE DE LA NOUVELLE|FÉDÉRATION ACADIENNE DE LA NOUVELLE|CONSEIL COMMUNAUTAIRE|"
    r"UNION OF NOVA SCOTIA MI'?KMAQ|UNION OF NOVA SCOTIA INDIANS|CONFEDERACY OF MAINLAND|\bCMM\b|\bKMKNO\b|KWILMU'?KW|"
    r"MI'?KMAW (NATIVE FRIENDSHIP|FAMILY|LEGAL|ECONOMIC|RIGHTS|CIRCLE|NATURAL|CHILD)|MI'?KMAQ (RIGHTS|NATIVE|CHILD|FAMILY|GRAND)|NATIVE COUNCIL|"
    r"ATLANTIC (CANADA|PROVINCES|POLICY|SALMON|BALLET|CANCER|REGION|FIRST NATIONS)|SALMON FEDERATION|CROWN CORPORATION|"
    r"COMMISSIONAIRES|SKILLS CANADA|JUNIOR ACHIEVEMENT|\bPROVINCE OF\b|\bGOVERNMENT OF\b|\bMINISTER OF\b|"
    r"ENGAGE NOVA SCOTIA|SCREEN NOVA SCOTIA|MUSIC NOVA SCOTIA|SAFETY SERVICES NOVA SCOTIA|DIVERT NS|DIVERT NOVA SCOTIA|"
    r"NOVA SCOTIA NATURE TRUST|NATURE CONSERVANCY|DUCKS UNLIMITED|CLEAN FOUNDATION|ECOLOGY ACTION|NOVA SCOTIA ONSITE|"
    r"NOVA SCOTIA LANDS|NSCAD|CYBER ?NB|CYBERSECURITY|OCEAN SUPERCLUSTER|CENTRE FOR OCEAN|COVE\b|VOLTA\b|MITACS|MARINE RENEWABLES|"
    r"NET ZERO ATLANTIC|OFFSHORE ENERGY|HALIFAX PARTNERSHIP|INNOVATE|ARDEN PROFESSIONAL|902 MANUP",
    re.I)
MUNI = re.compile(r"^(?:THE )?(?:MUNICIPALITY OF (?:THE )?(?:COUNTY|DISTRICT) OF|MUNICIPALITY OF|REGION OF|TOWN OF|VILLAGE OF|CITY OF|"
                  r"VILLAGE COMMISSION OF|REGIONAL MUNICIPALITY OF|COUNTY OF|DISTRICT OF) (.+?)(?: MUNICIPALITY| COUNTY| DISTRICT)?(?: FOR .*|$)")
MUNI_SUFFIX = re.compile(r"^(.+?) (REGIONAL MUNICIPALITY|MUNICIPALITY|VILLAGE COMMISSION|COUNTY MUNICIPALITY|DISTRICT MUNICIPALITY)$")
FIRST_NATION = re.compile(r"^(.+?) (FIRST NATIONS?|INDIAN BAND|BAND COUNCIL|BAND|MI KMAQ NATION|MI KMAW NATION|NATION)(?:S| S)?\b")
# Municipalities whose territory spans several districts: always "other government".
MULTI_DISTRICT_MUNIS = {"HALIFAX", "CAPE BRETON", "KINGS", "COLCHESTER", "PICTOU", "CUMBERLAND", "ANNAPOLIS", "INVERNESS",
                        "LUNENBURG", "EAST HANTS", "WEST HANTS", "QUEENS", "ANTIGONISH", "YARMOUTH", "DIGBY", "SHELBURNE"}
# Municipality (normalised name without the "Town of"/"County of" wrapper) -> seat, as a GeoNames place key
# or (lat, lon). County and district municipalities share a name with their town; the town is
# in the same district as the seat except where listed in MUNI_SEATS.
MUNI_SEATS = {
    "HALIFAX": (44.648, -63.586), "HALIFAX REGIONAL": (44.648, -63.586), "CAPE BRETON": (46.137, -60.194),
    "CAPE BRETON REGIONAL": (46.137, -60.194), "QUEENS": (44.038, -64.717), "REGION OF QUEENS": (44.038, -64.717),
    "WEST HANTS": (44.990, -64.137), "WEST HANTS REGIONAL": (44.990, -64.137), "EAST HANTS": (44.973, -63.512),
    "ANNAPOLIS": (44.742, -65.515), "ANTIGONISH": (45.619, -61.998), "COLCHESTER": (45.365, -63.287), "CUMBERLAND": (45.818, -64.218),
    "INVERNESS": (46.012, -61.527), "KINGS": (45.077, -64.502), "PICTOU": (45.678, -62.709), "RICHMOND": (45.515, -61.014),
    "VICTORIA": (46.102, -60.752), "ARGYLE": (43.858, -65.967), "BARRINGTON": (43.558, -65.615), "CHESTER": (44.541, -64.240),
    "CLARE": (44.384, -66.080), "DIGBY": (44.622, -65.760), "GUYSBOROUGH": (45.388, -61.498), "LUNENBURG": (44.377, -64.519),
    "SHELBURNE": (43.763, -65.323), "ST MARYS": (45.141, -61.986), "SAINT MARYS": (45.141, -61.986), "YARMOUTH": (43.837, -66.117),
    "AMHERST": (45.818, -64.218), "ANNAPOLIS ROYAL": (44.742, -65.515), "BERWICK": (45.047, -64.736), "BRIDGEWATER": (44.378, -64.519),
    "CLARKS HARBOUR": (43.432, -65.638), "CLARK S HARBOUR": (43.432, -65.638), "KENTVILLE": (45.077, -64.496), "LOCKEPORT": (43.698, -65.112),
    "MAHONE BAY": (44.449, -64.381), "MIDDLETON": (44.941, -65.071), "MULGRAVE": (45.612, -61.390), "NEW GLASGOW": (45.592, -62.645),
    "OXFORD": (45.731, -63.869), "PORT HAWKESBURY": (45.616, -61.352), "STELLARTON": (45.561, -62.660), "STEWIACKE": (45.141, -63.351),
    "TRENTON": (45.617, -62.634), "TRURO": (45.365, -63.287), "WESTVILLE": (45.566, -62.709), "WOLFVILLE": (45.091, -64.364),
    "WINDSOR": (44.990, -64.137), "HANTSPORT": (45.063, -64.169), "PARRSBORO": (45.405, -64.329), "SPRINGHILL": (45.651, -64.057),
    "BRIDGETOWN": (44.845, -65.300), "CANSO": (45.336, -60.994), "LIVERPOOL": (44.038, -64.717), "SHERBROOKE": (45.141, -61.986),
    "BADDECK": (46.102, -60.752), "ARICHAT": (45.515, -61.014), "PORT HOOD": (46.012, -61.527), "TUSKET": (43.858, -65.967),
    "ELMSDALE": (44.973, -63.512),
}
# Band office coordinates (lat, lon); keys are normalised names and common spellings.
FIRST_NATIONS = {
    "ACADIA": (43.838, -66.117), "ANNAPOLIS VALLEY": (45.072, -64.612), "CAMBRIDGE": (45.072, -64.612), "BEAR RIVER": (44.574, -65.650),
    "ESKASONI": (45.937, -60.606), "GLOOSCAP": (45.062, -64.170), "HORTON": (45.062, -64.170), "MEMBERTOU": (46.127, -60.170),
    "MILLBROOK": (45.342, -63.279), "PAQTNKEK": (45.633, -61.700), "PAQ TNKEK": (45.633, -61.700), "AFTON": (45.633, -61.700),
    "PICTOU LANDING": (45.670, -62.680), "POTLOTEK": (45.720, -60.950), "CHAPEL ISLAND": (45.720, -60.950),
    "SIPEKNE KATIK": (45.100, -63.420), "SIPEKNEKATIK": (45.100, -63.420), "INDIAN BROOK": (45.100, -63.420), "SHUBENACADIE": (45.100, -63.420),
    "WAGMATCOOK": (46.080, -60.980), "WE KOQMA Q": (45.980, -61.100), "WEKOQMAQ": (45.980, -61.100), "WAYCOBAH": (45.980, -61.100),
    "WHYCOCOMAGH": (45.980, -61.100),
}
SUPPLIER_SUFFIX = re.compile(r"\b(LTD|LTEE|LIMITED|LIMITEE|CORP|CORPORATION|LLC|LLP|LP|L P|ULC|PBC|CO|COMPANY|COMPAGNIE|GMBH|PLC|SA|AG)\b")
INC = re.compile(r"\bINC\b|\bINCORPORATED\b")
NUMBERED = re.compile(r"^\d{5,8} (NS|N S|NOVA SCOTIA|CANADA|ONTARIO|QUEBEC|NEW BRUNSWICK|NB)\b")
INDUSTRY = re.compile(
    r"\b(?:CONSTRUCTION|PAVING|CONTRACT(ING|OR|ORS)|CONSULT(ING|ANT|ANTS)|ENGINEER|ARCHITECT|SOFTWARE|TECHNOLOG|SYSTEMS|SOLUTIONS|"
    r"PHARMA|GLAXO|PFIZER|MERCK|NOVARTIS|SANOFI|ASTRAZENECA|JANSSEN|ABBVIE|BAYER|ROCHE|TELECOM|BELL CANADA|BELL ALIANT|ROGERS|TELUS|"
    r"XPLOR|EASTLINK|ENERG(Y|IES)|FUEL|PETROL|OIL\b|PROPANE|GAS\b|IRVING|ESSO|SHELL|ULTRAMAR|WILSON FUEL|EQUIPMENT|SUPPL(Y|IES)|"
    r"SALES|RENTAL|MANUFACTUR|FABRICATION|TRUCK|AUTO\b|AUTOMOTIVE|MOTORS|\bGMC\b|FORD\b|CHEVROLET|TOYOTA|HONDA|NISSAN|HYUNDAI|KIA\b|"
    r"ELECTRIC|PLUMBING|HEATING|EXCAVAT|ASPHALT|LUMBER|MACHIN|HOLDINGS|ENTERPRISES|VENTURES|REALTY|PROPERTIES|DEVELOPMENTS|INVESTMENTS|"
    r"TRADING|INDUSTR|LOGISTIC|TRANSPORT|TRUCKING|MECHANICAL|STEEL|CONCRETE|ROOFING|WELDING|TOWING|TIRE\b|TIRES|INSURANCE|BANK|"
    r"CREDIT UNION|LAW\b|LEGAL\b|BARRISTER|IN TRUST|PRINTING|SECURITY|STAFFING|PERSONNEL|FLEXTRACK|IBM\b|MICROSOFT|ORACLE|DELL\b|XEROX|"
    r"CANON\b|SIEMENS|HONEYWELL|JOHNSON CONTROLS|KONE\b|OTIS\b|SCHINDLER|MEDICAL SUPPL|DIAGNOSTIC|LABORATOR|CLEANING|JANITORIAL|"
    r"LANDSCAP|SNOW|FORESTRY|SAWMILL|PULP|PAPER\b|MINING|MINES\b|QUARR|GRAVEL|SAND\b|AGGREGATE|BUILDERS|BUILDING SUPPL|HARDWARE|"
    r"HOME HARDWARE|CANADIAN TIRE|KENT BUILDING|COSTCO|WALMART|SOBEYS|LOBLAW|SUPERSTORE|STAPLES|OFFICE DEPOT|GRAND & TOY|AMAZON|UBER|"
    r"AIR CANADA|PORTER|VIA RAIL|HOTEL|MOTEL|\bINN\b|HILTON|MARRIOTT|WESTIN|HOLIDAY INN|DOUBLETREE|BEST WESTERN|COMFORT INN|HAMPTON INN|"
    r"RESTAURANT|PIZZ|CATERING|FOOD SERVICE|CAFETERIA|VENDING|AVIATION|AIRCRAFT|HELICOPT|MARINE\b|SHIPYARD|DREDG|FENCING|SIGNS?\b|"
    r"GLASS|WINDOWS|DOORS|FLOOR|PAINT|CARPET|FURNITURE|APPLIANCE|RADIO|BROADCAST|MEDIA|PUBLISH|ADVERTIS|MARKETING|COMMUNICATIONS? (INC|LTD)|"
    r"DESIGN INC|STUDIO|PRODUCTIONS|SURVEY|GEOMATIC|ENVIRONMENTAL (INC|LTD|SERVICES)|WASTE|RECYCL|DISPOSAL|SEPTIC|WATER TREATMENT|"
    r"FILTRATION|UNIFORM|APPAREL|SPORTS? EXCELLENCE|SOURCE FOR SPORTS|GROUP\b|LEASING|STEWART MCKELVEY|COX & PALMER|MCINNES COOPER|"
    r"BOYNECLARKE|PATTERSON LAW|SOLICITOR|LAW OFFICE|LAW FIRM|VIRTUAL CARE|TELEHEALTH|MANULIFE|SUN LIFE|CANADA LIFE|GREAT-WEST|BLUE CROSS|"
    r"DESJARDINS|ROYAL BANK|SCOTIABANK|\bBMO\b|\bTD\b|\bCIBC\b|NATIONAL BANK|APPLE CANADA|GOOGLE|META PLATFORMS|FACEBOOK|ADOBE|SAP\b|"
    r"CGI\b|DELOITTE|KPMG|ERNST & YOUNG|\bEY\b|PRICEWATERHOUSE|\bPWC\b|GRANT THORNTON|MNP\b|ACCENTURE|GARTNER|ESRI|DAVIS PIER|"
    r"PUBLIC RELATIONS|ASSOCIATES INC|& ASSOCIATES|PARTNERS\b|MANAGEMENT (INC|LTD)|CAPITAL INC|CAPITAL LTD|FINANCIAL|LEASE\b|"
    r"RENT-?ALL|HOME DEPOT|RONA\b|LOWE'S|IKEA|BEST BUY|TRANSPORT LTD|TRANSPORT INC|FREIGHT|COURIER|PUROLATOR|FEDEX|\bUPS\b|CANADA POST|"
    r"TIMBER|FOREST PRODUCTS|WOODLANDS|PHARMACY|PHARMACIES|DRUG MART|LAWTONS|SHOPPERS|GUARDIAN|PHARMASAVE|PHARMACHOICE|MEDICINE SHOPPE|"
    r"DRUGS\b|DENTAL CLINIC|VETERINAR|OPTICAL|CLINIC INC|CLINIC LTD|PHYSIOTHERAPY INC|CHIROPRACT|HEARING (AID|CENTRE)|"
    r"SHANNEX|GEM HEALTH|NORTHWOOD INC|GREEN SHIELD|PARAMED|BAYSHORE|CLOSING THE GAP|WE CARE HEALTH|\bLTD\b|\bLTEE\b|\bLIMITED\b|\bLIMITEE\b|\bCORP\b|\bLLC\b|\bLLP\b|\bULC\b)",
    re.I)
NONPROFIT = re.compile(
    r"\b(?:HOME\b|HOMES\b|VILLA|MANOR|MANOIR|FOYER|RESIDENCE|RÉSIDENCE|RESIDENCES|\bCARE\b|SOINS|CHILD ?CARE|DAYCARE|DAY CARE|GARDERIE|"
    r"NURSING|HOUSING|HABITATION|LOGEMENT|CO-?OP\b|COOPERATIVE|COOPÉRATIVE|ASSOCIATION|SOCIETY|SOCIETE|SOCIÉTÉ|ASSOC\b|"
    r"FOUNDATION|FONDATION|\bCLUB\b|CHURCH|EGLISE|ÉGLISE|PARISH|PAROISSE|DIOCESE|FESTIVAL|MUSEUM|MUSEE|MUSÉE|THEATRE|THÉÂTRE|"
    r"THEATER|GALLERY|GALERIE|SYMPHONY|ORCHESTR|CHORAL|CHOIR|CHORALE|BALLET|DANCE|DANSE|ARTS?\b|SCHOOL|ECOLE|ÉCOLE|ACADEMY|"
    r"ACADEMIE|ACADÉMIE|MONTESSORI|PRESCHOOL|PRESCOLAIRE|KINDER|LEARNING|APPRENTISSAGE|LITERACY|COMMUNITY|"
    r"COMMUNAUTAIRE|COMMUNAUTE|COMMUNAUTÉ|CENTRE\b|CENTER\b|COUNCIL|CONSEIL|COMMITTEE|COMITE|COMITÉ|HOUSE\b|MAISON|TRANSITION|"
    r"SHELTER|REFUGE|FAMILY|FAMILLE|FAMILIAL|YOUTH|JEUNESSE|JEUNES|SENIORS?|AINES|AÎNÉS|AGE D'OR|LIBRARY|BIBLIOTH|FOOD BANK|"
    r"SOUP KITCHEN|HOSPICE|PALLIATI|WELLNESS|MENTAL HEALTH|ADDICTION|RECOVERY|CRISIS|SUPPORT|SOUTIEN|ENTRAIDE|VOLUNTEER|BENEVOL|BÉNÉVOL|"
    r"CHARIT|LEGION|LIONS|KINSMEN|KIWANIS|ROTARY|KNIGHTS OF COLUMBUS|SALVATION ARMY|YMCA|YWCA|BOYS (AND|&) GIRLS|BIG BROTHERS|"
    r"SCOUTS|GUIDES|CADETS|4-H|FAIR\b|EXHIBITION|EXPOSITION|AGRICULTURAL SOCIETY|HISTORICAL|HERITAGE|PATRIMOINE|MULTICULTURAL|"
    r"IMMIGRANT|NEWCOMER|REFUGEE|FIRST NATION|PREMIERE NATION|PREMIÈRE NATION|TRIBAL|MI'?K?MA|L'?NU\b|INDIGENOUS|ABORIGINAL|FRIENDSHIP|"
    r"WOMEN|FEMMES|MEN'?S|PREGNANCY|DISABILIT|HANDICAP|ABILITY|ABILITIES|AUTISM|AUTISME|DEAF|BLIND|SPECIAL CARE|SPECIAL NEEDS|"
    r"GROUP HOME|RESIDENTIAL|INCLUSION|L'ARCHE|EMPLOYMENT|EMPLOI|ENTERPRISE CENTRE|CBDC|COMMUNITY BUSINESS DEVELOPMENT|CHAMBER OF COMMERCE|"
    r"BOARD OF TRADE|DOWNTOWN|BUSINESS IMPROVEMENT|TOURISM ASSOC|PARK\b|PARC\b|TRAIL|SENTIER|ARENA|RINK|POOL|RECREATION|LOISIRS|"
    r"SPORTS? (CLUB|ASSOC|COUNCIL|CENTRE)|HOCKEY|SOCCER|CURLING|SKI\b|GOLF|SAILING|ROWING|SWIM|GYMNAST|FIGURE SKAT|SPEED SKAT|BASEBALL|"
    r"SOFTBALL|BASKETBALL|VOLLEYBALL|RUGBY|LACROSSE|JUDO|KARATE|BOXING|ATHLETI|TRACK AND FIELD|SPECIAL OLYMPICS|OLYMPI|PARALYMPI|"
    r"GAMES\b|JEUX\b|CAMP\b|CAMPS\b|BIBLE|GOSPEL|MINISTR|MISSION\b|CATHEDRAL|ABBEY|MONASTERY|CONVENT|SISTERS|CHRISTIAN|CATHOLIC|BAPTIST|"
    r"ANGLICAN|UNITED CHURCH|PENTECOST|WESLEYAN|ADVENTIST|MOSQUE|ISLAMIC|MUSLIM|JEWISH|SYNAGOGUE|TEMPLE|SIKH|HINDU|BUDDHIST|"
    r"HOSPITAL FOUNDATION|HEALTH FOUNDATION|AUXILIARY|RED CROSS|CANCER|DIABETES|HEART AND STROKE|LUNG|KIDNEY|ALZHEIMER|PARKINSON|"
    r"ARTHRITIS|MS SOCIETY|EPILEPS|CEREBRAL|DOWN SYNDROME|CHILDREN'?S|ENFANTS|ENFANCE|PETITE ENFANCE|BABIES|KIDS|PETITS|TOTS|TOUT-PETITS|"
    r"AMIS\b|FRIENDS|BUDDIES|RAINBOW|SUNSHINE|SMILING|HAPPY|LITTLE|PETIT|TINY|TEDDY|BEAR|BUMBLE|BUSY|CREATIVE|DISCOVERY|IMAGIN|WONDER|"
    r"GIGGLE|PLAY(?:SCHOOL|GROUP|HOUSE|TIME)?\b|NURSERY|CRECHE|HEADSTART|HEAD START|EARLY (LEARNING|CHILDHOOD|YEARS)|AFTER ?SCHOOL|"
    r"TRANSITION HOUSE|SAFE HOUSE|OUTREACH|DROP-IN|HALFWAY|JOHN HOWARD|ELIZABETH FRY|SEXUAL|ASSAULT|VIOLENCE|ABUSE|RESTORATIVE|"
    r"LEGAL CLINIC|ADVOCACY|CITIZENS|RESIDENTS|RATEPAYERS|FIRE DEPARTMENT|FIRE DEPT|FIRE HALL|VOLUNTEER FIRE|FIREMEN|SEARCH AND RESCUE|"
    r"GROUND SEARCH|WATERSHED|CONSERVATION|NATURALIST|NATURE|ENVIRONMENTAL (ASSOC|COUNCIL|NETWORK|TRUST)|ESTUARY|RIVER (ASSOC|KEEPER|WATCH)|"
    r"SALMON (ASSOC|PROTECTIVE)|WILDLIFE|ANGLERS|HUNTERS|ROD AND GUN|FISH AND GAME|HARBOUR AUTHORITY|AIRPORT|FARMERS'? MARKET|MARCHE|"
    r"CARNIVAL|PARADE|CELEBRATION|FETE|JAZZ|BLUES|FOLK|MUSIC|FILM|CINEMA|WRITERS|POETS|BOOK|CRAFTS?\b|ARTISAN|POTTERY|QUILT|WEAVERS|"
    r"GENEALOG|ARCHIVES|HISTORY|VETERANS|SNOWMOBILE|ATV\b|QUAD\b|TRAILS\b|CYCLING|RUNNING|MARATHON|TRIATHLON|HORSE|EQUESTR|RIDING\b|"
    r"THERAPEUTIC|THERAPY|SPEECH|LANGUAGE|FRANCOPHONE|ACADIEN|ACADIENNE|ACADIAN|GAELIC|AFRICAN|BLACK\b|IMMERSION|FRENCH|FRANCAIS|"
    r"TUTOR|MENTOR|LEADERSHIP|SKILLS\b|NUMERACY|ADULT LEARN|APPRENTIS|CONSERVATORY|CEMETERY|MEMORIAL|COMMEMORAT|LIGHTHOUSE|WHARF|"
    r"MARINA|YACHT|BOAT CLUB|CANOE|KAYAK|SURF|ANIMAL|SPCA|HUMANE|RESCUE|SANCTUARY|ZOO\b|AQUARIUM|BOTANIC|GARDEN|ARBORETUM|"
    r"PARTNERSHIP INC|NETWORK|RESEAU|COALITION|ALLIANCE|COLLECTIVE|COMMONS|COOP\b|CO OP\b|NON-?PROFIT|NON PROFIT|CHARITABLE|BENEVOLENT|"
    r"RELIEF|AID\b|HELP\b|HOPE\b|HARVEST|SHARE\b|CARING|COMPASSION|DIGNITY|INDEPENDENT LIVING|SELF-HELP|PEER|CLUBHOUSE|OPEN DOOR|"
    r"WELCOME|SETTLEMENT|NEW CANADIAN|SMALL OPTIONS|OPTIONS\b|ADULT SERVICE|WORK ACTIVITY|WORKSHOP|SHELTERED|VOCATIONAL|REHAB|"
    r"ENHANCED CARE|CONTINUING CARE|LONG TERM CARE|LONG-TERM CARE|SENIORS'? RESIDENCE|RETIREMENT|LODGE|HAVEN|GARDENS|ESTATES|COURT\b|"
    r"PLACE\b|LEGION|BAND\b|NATION\b|REGIONAL ENTERPRISE|\bREN\b|LIBRARY|LIBRARIES|MUSEUM|SCIENCE CENTRE|DISCOVERY CENTRE|"
    r"INTERPRETIVE|VISITOR|TOURISM|DEVELOPMENT ASSOC|DEVELOPMENT AGENCY|WATERFRONT|HARBOURFRONT|MAIN STREET|TOWN OF|VILLAGE OF|"
    r"MUNICIPALITY|COUNTY OF|DISTRICT OF|REGION OF|UNIVERSITY|COLLEGE|INSTITUTE|RESEARCH)",
    re.I)
# Words that make a supplier even when a care or community word is also present.
STRONG_SUPPLIER = re.compile(
    r"\b(?:CONSTRUCTION|PAVING|ASPHALT|CONTRACTING|CONTRACTORS|TRUCK|LEASING|EQUIPMENT|ENGINEERING|ARCHITECT|IN TRUST|BARRISTER|SOLICITOR|"
    r"INSURANCE|BANK\b|HOTEL|MOTEL|INN\b|HILTON|MARRIOTT|WESTIN|HOLIDAY INN|DOUBLETREE|BEST WESTERN|COMFORT INN|HAMPTON INN|HOLDINGS|"
    r"REALTY|PROPERTIES|DEVELOPMENTS|PHARMA\b|PHARMACY|PHARMACIES|DRUG MART|LAWTONS|SHOPPERS|PHARMASAVE|PHARMACHOICE|TELECOM|OIL\b|FUEL|"
    r"PETROL|ENERGY|LUMBER|HARDWARE|MANUFACTUR|SALES|RENTALS?\b|TOWING|TIRES?\b|AUTO BODY|MOTORS|LOGISTICS|TIMBER|FOREST PRODUCTS|PULP|"
    r"SAWMILL|STEEL|CONCRETE|WELDING|EXCAVAT|PLUMBING|ELECTRICAL|ROOFING|HOMES (INC|LTD)|LAW OFFICE|LAW FIRM|STEWART MCKELVEY|COX & PALMER|"
    r"MCINNES COOPER|BOYNECLARKE|MANAGEMENT (INC|LTD|LIMITED)|LIMITED PARTNERSHIP|CONSULTING|CONSULTANTS|SOFTWARE|TECHNOLOGIES|"
    r"BAYSHORE|PARAMED|CBI HOME HEALTH|CBI HEALTH|GREEN SHIELD|CLOSING THE GAP|WE CARE HEALTH|KIDS & COMPANY|HARDING MEDICAL|\bPBC\b|"
    r"SYSTEMS INC|SOLUTIONS INC|STAFFING|SECURITY|CLEANING|JANITORIAL|CATERING|FOOD SERVICES|MEDICAL SUPPL|LABORATOR|DIAGNOSTIC)",
    re.I)
# GeoNames place names that are also surnames, counties, regions or ordinary words: never a place
# hit on their own (only applies to the "place name inside the recipient" step).
AMBIGUOUS = {"KINGS", "QUEENS", "VICTORIA", "RICHMOND", "CUMBERLAND", "COLCHESTER", "HANTS", "CAPE BRETON", "ANNAPOLIS VALLEY",
             "WINDSOR", "VALLEY", "CENTRAL", "MIDDLE", "UPPER", "LOWER", "WEST", "EAST", "NORTH", "SOUTH", "HARBOUR", "ISLAND",
             "RIVER", "LAKE", "BROOK", "BAY", "HEAD", "POINT", "CROSSING", "JUNCTION", "STATION", "SETTLEMENT", "LANDING", "CENTRE",
             "CENTER", "CORNER", "ROAD", "HILL", "MOUNTAIN", "GRANDE", "GRAND", "FOREST", "SPRINGFIELD", "CAMBRIDGE", "MILFORD",
             "STANLEY", "CLYDE", "DOUGLAS", "LINCOLN", "SCOTCH", "ENGLISH", "FRENCH", "SCOTT", "WILSON", "MARTIN", "MORRISON", "GRAHAM",
             "MURRAY", "WALLACE", "ROSS", "ALLEN", "BAKER", "TAYLOR", "STEWART", "ARMSTRONG", "ANDERSON", "MCKAY", "MACKAY", "MACKENZIE",
             "MCKENZIE", "CAMPBELL", "MCDONALD", "MACDONALD", "FRASER", "HARRIS", "ELLIS", "WILLIAMS", "YOUNG", "JOHNSON", "SMITH",
             "HALIFAX", "DARTMOUTH", "SYDNEY", "BEDFORD", "SACKVILLE", "FUNDY",
             "ACADIA", "ACADIE", "EVANGELINE", "SAINT MARYS", "SAINT MARY S", "SAINT ANNE", "SAINTE ANNE", "SAINT JOSEPH", "SAINT PAUL",
             "SAINT PETER", "SAINT PETERS", "SAINT ANDREWS", "SAINT MARGARET", "SAINT MARGARETS", "MARGARETS", "NORTHUMBERLAND",
             "ATLANTIC", "MARITIME", "HIGHLAND", "HIGHLANDS", "MEADOWS", "GARDENS", "WOODLANDS", "OAKLAND", "GREENFIELD", "GREENWOOD",
             "WESTFIELD", "RIVERSIDE", "LAKESIDE", "BAYVIEW", "HILLSIDE", "FAIRVIEW", "PLEASANT", "ORCHARD", "PORTAGE", "DOMINION",
             "RESERVE", "FLORENCE", "ALBERT", "BIRCH", "MAPLE", "CEDAR", "PINE", "SPRUCE", "OAK", "ELM", "WILLOW", "ROSE", "LILY",
             "SUNNYSIDE", "SUMMERVILLE", "SPRINGVILLE", "ECONOMY", "ENFIELD", "LANTZ", "DEBERT", "HILDEN", "VALLEY", "CHANCE",
             "HOPEWELL", "UNION", "HARMONY", "LIBERTY", "PARADISE", "PROSPECT", "PRESTON", "ARCADIA", "BROOKLYN", "AYLESFORD",
             "COLDBROOK", "CLEMENTSPORT", "KINGSTON", "HAMPTON", "LAWRENCETOWN", "LONDONDERRY", "DURHAM", "BRISTOL", "DEVON",
             "CORNWALL", "ESSEX", "SOMERSET", "NEWPORT", "SALEM", "BELMONT", "BEAVER", "SHEET", "SPRING", "FALL", "RIVER", "MIRA",
             "SOUTHAMPTON", "WESTCHESTER", "MELFORD"}
# Recipients with no place in their name whose location is known (adult residential and
# rehabilitation centres funded by Social Development; approximate: the facility's community).
RECIPIENT_PLACES = {
    "Kings Regional Rehabilitation Centre": (45.054, -64.657),  # Waterville
    "Quest-A Society for Adult Support and Rehabilitation": (44.776, -63.679),  # Lower Sackville
    "Sunset Residential and Rehabilitation Services Inc": (45.853, -63.664),  # Pugwash
    "Gables Lodge": (45.818, -64.218),  # Amherst
    "Lunenburg County Home Support Services Society": (44.378, -64.519),  # Bridgewater
    "Harbourview Haven Nursing Home": (44.377, -64.309),  # Lunenburg
    "Colchester Residential Services Society": (45.365, -63.287),  # Truro
}
# Generic words dropped when matching a payee to the facility directories by core name
# ("Celtic Court Continuing Care Residence-Shannex" -> "CELTIC COURT" -> directory "Celtic Court").
FACILITY_GENERIC = re.compile(r"\b(THE|CONTINUING|CARE|RESIDENCE|RESIDENCES|CENTRE|CENTER|NURSING|HOME|HOMES|ENHANCED|LONG|TERM|LODGE|MANOR|"
                              r"VILLA|FOR|SPECIAL|SENIORS|RETIREMENT|CAMPUS|COMMUNITY|FACILITY|LTD|INC|SHANNEX|GEM|ROSECREST|NORTHWOOD|"
                              r"HEALTH|SERVICES|PROGRAM|DAYCARE|DAY|CHILD|CHILDCARE|CHILDREN|CHILDRENS|S|EARLY|LEARNING|EDUCATION|PRESCHOOL|"
                              r"ACADEMY|SCHOOL|SOCIETY|ASSOCIATION|ASSOC|AND|OF|AT|IN|BAY)\b")


def upper(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().upper()


def norm(s):
    s = upper(s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(THE|OF|INC|LTD|LIMITED|CORP|CORPORATION|SOCIETY|ASSOCIATION|ASSN|ASSOC|FOUNDATION)\b", " ", s)
    s = re.sub(r"\b(NO|NUMBER)\s*\d+\b|#\s*\d+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def place_norm(s):
    """Place-name key: accents stripped, 'St'/'Ste' expanded, punctuation to spaces."""
    s = upper(s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\bSTE\b", "SAINTE", s)
    s = re.sub(r"\bST\b", "SAINT", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ the PDFs

AMOUNT = re.compile(r"^\(?\$?[\d,]+\.\d{2}\)?$")
ROW = re.compile(r"^(.*?)\s*(?:\.{2,}\s*)?(\(?\$?[\d,]+\.\d{2}\)?)$")
SECTION = re.compile(r"^(Salaries|Travel|Grants and Contributions|Other|External Secondments|[A-Z][A-Za-z' ]+):$")
GUTTER = 425.0  # x of the gap between the two columns (names start at 90 and 435)


def amount(s):
    s = s.strip().replace("$", "").replace(",", "")
    neg = s.startswith("(")
    v = float(s.strip("()"))
    return -v if neg else v


def title_case(s):
    small = {"of", "the", "and", "for", "to", "de", "la", "du", "des"}
    words = []
    for i, w in enumerate(s.lower().split()):
        words.append(w if (w in small and i) else re.sub(r"(^|['\-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w))
    return " ".join(words).replace("Nova Scotia", "Nova Scotia").replace("L'nu", "L'nu")


def page_lines(items):
    """-> [text] for one page: the left column's lines top to bottom, then the right column's.
    A page is two-column when some text (not an amount) starts right of the gutter; on a
    one-column page (the end of a department, amounts far right) every line stays whole.
    An amount that sits on a baseline of its own just above a dot-leader row with no amount
    (a layout glitch on a few pages) is handed to that row."""
    texty_all = [it for it in items if it[3].strip()]
    two_col = any(it[1] >= GUTTER and not AMOUNT.match(it[3].strip()) and re.search(r"[A-Za-z]", it[3]) for it in texty_all)
    cols = {0: [], 1: []}
    for line in sk_pdf._group_lines(items):
        line.sort(key=lambda it: it[1])
        texty = [it for it in line if it[3].strip()]
        if not texty:
            continue
        parts = ((0, [it for it in texty if it[1] < GUTTER]), (1, [it for it in texty if it[1] >= GUTTER])) if two_col else ((0, texty),)
        for c, part in parts:
            if part:
                cols[c].append(sk_pdf.items_to_lines(part)[0])
    out = []
    for lines in (cols[0], cols[1]):
        k = 0
        while k < len(lines):
            t = lines[k].strip()
            if AMOUNT.match(t) and k + 1 < len(lines) and re.search(r"\.{2,}\s*$", lines[k + 1]):
                out.append(lines[k + 1].strip() + " " + t)
                k += 2
                continue
            out.append(t)
            k += 1
    return out


def parse_volume(path):
    """-> rows [(department, section, payee, amount, page)], check {...} from one Volume 3 PDF."""
    data = open(path, "rb").read()
    rows, sections, dept_totals = [], [], []
    dept = section = None
    pending, heading = [], []
    running = 0.0
    for pno, content in enumerate(sk_pdf.page_contents(data), 1):
        items = sk_pdf.stream_text_items(content)
        if not items:
            continue
        top = max(it[0] for it in items)
        head = sk_pdf.items_to_lines([it for it in items if abs(it[0] - top) < 2])
        chapter = head[0].strip() if head else ""
        body = [it for it in items if abs(it[0] - top) >= 2]
        if chapter.startswith("Department of "):
            dept = chapter[14:]
        elif chapter and chapter != "Public Service" and not re.fullmatch(r"\d+", chapter):
            dept = chapter
        for text in page_lines(body):
            text = text.strip()
            if not text or re.fullmatch(r"\d{1,3}", text) or text == chapter:
                continue
            if re.fullmatch(r"[A-Z][A-Z0-9'&,\-/ ]+", text) and not AMOUNT.match(text) and ".." not in text and len(text) > 3:
                heading.append(text)  # a Public Service agency heading (may wrap)
                continue
            if heading:
                dept = title_case(" ".join(heading))
                heading = []
            m = SECTION.match(text)
            if m:
                section = m.group(1)
                pending, running = [], 0.0
                continue
            if AMOUNT.match(text):
                sections.append((dept, section, round(running, 2), amount(text), pno))
                pending, running = [], 0.0
                continue
            m = ROW.match(text)
            if m and (".." in text or m.group(1)):
                name = re.sub(r"\s*\.{2,}\s*$", "", " ".join(pending + [m.group(1)])).strip()
                pending = []
                v = amount(m.group(2))
                if name.startswith("Total, "):
                    dept_totals.append((dept, name[7:].rstrip(" ."), v, pno))
                elif name.startswith("Total"):
                    continue
                else:
                    rows.append((dept, section, name, v, pno))
                    running += v
            else:
                pending.append(text)
    checked = [s for s in sections if s[1] in USED_SECTIONS]
    ok = [s for s in checked if abs(s[2] - s[3]) <= 1]
    check = {
        "rows": len(rows), "departments": sorted({r[0] for r in rows if r[0]}),
        "section_totals_checked": len(checked), "section_totals_matched": len(ok),
        "mismatched": [[d, s, parsed, printed, p] for d, s, parsed, printed, p in checked if abs(parsed - printed) > 1],
        "sections": [[d, s, parsed, printed, p] for d, s, parsed, printed, p in checked],
        "used_sections_parsed": round(sum(r[3] for r in rows if r[1] in USED_SECTIONS)),
        "used_sections_printed": round(sum(s[3] for s in checked)),
        "all_sections_parsed": round(sum(r[3] for r in rows)),
        "department_totals_printed": round(sum(t[2] for t in dept_totals)),
        "department_totals_n": len(dept_totals),
    }
    return rows, check


def load_volume(fye):
    """Rows of one fiscal year, from the CSV cache or the PDF."""
    csv_path = RAW / "ns" / f"payees_{fye - 1}-{str(fye)[2:]}.csv"
    check_path = RAW / "ns" / f"payees_{fye - 1}-{str(fye)[2:]}_check.json"
    if not csv_path.exists():
        rows, check = parse_volume(DL / f"pa-supplementary-{fye}.pdf")
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["department", "section", "payee", "amount", "page"])
            w.writerows(rows)
        json.dump(check, open(check_path, "w"), indent=1, ensure_ascii=False)
        print(f"FY{fye - 1}-{str(fye)[2:]}: {check['rows']} rows; {check['section_totals_matched']}/{check['section_totals_checked']} "
              f"grant and supplier section totals match; parsed {check['used_sections_parsed']:,} vs printed {check['used_sections_printed']:,}",
              file=sys.stderr)
    rows = []
    with open(csv_path, newline="") as f:
        for r in csv.DictReader(f):
            rows.append({"Recipient": r["payee"], "Dept": r["department"], "Section": r["section"], "Amount": float(r["amount"]), "fye": fye,
                         "Page": int(r.get("page") or 0)})
    check = json.load(open(check_path)) if check_path.exists() else {}
    return rows, check


def source_url(r):
    """The Volume 3 PDF of the row's year, opened at the page the row was parsed from."""
    url = SOURCE_URLS.get(r["fye"]) or OFFICIAL_URL.format(fye=r["fye"])
    return f'{url}#page={r["Page"]}' if r.get("Page") else url


def look_for_next_volume(fye=2026):
    """Try the official URL (refuses connections from here) and the Internet Archive for the
    next volume; keep it in data/raw/ns/dl/ when found."""
    path = DL / f"pa-supplementary-{fye}.pdf"
    if path.exists():
        return True
    url = OFFICIAL_URL.format(fye=fye)
    for candidate in (url, None):
        try:
            if candidate is None:
                api = f"http://archive.org/wayback/available?url={url.split('://', 1)[1]}"
                with urllib.request.urlopen(api, timeout=20) as r:
                    snap = json.load(r).get("archived_snapshots", {}).get("closest")
                if not snap or not snap.get("available"):
                    continue
                candidate = snap["url"]
            req = urllib.request.Request(candidate, headers={"User-Agent": "Mozilla/5.0 riding-spending (research)"})
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
            if blob[:5] == b"%PDF-":
                path.write_bytes(blob)
                SOURCE_URLS[fye] = candidate
                print("fetched", path.name, "from", candidate, file=sys.stderr)
                return True
        except Exception as e:  # noqa: BLE001
            print(f"no FY{fye - 1}-{str(fye)[2:]} volume via {candidate or 'Internet Archive'}: {e}", file=sys.stderr)
    return False


FACILITY_FILES = {
    "ltc_facilities.csv": "https://data.novascotia.ca/api/views/x76a-axw2/rows.csv?accessType=DOWNLOAD",
    "child_care_directory.csv": "https://data.novascotia.ca/api/views/3j9v-yimg/rows.csv?accessType=DOWNLOAD",
}


def load_facilities():
    """{normalised facility name: (lat, lon)} from the province's long-term care and child care
    directories (data.novascotia.ca x76a-axw2 and 3j9v-yimg), fetched once into data/raw/ns/dl/."""
    out = {}
    for name, url in FACILITY_FILES.items():
        path = DL / name
        if not path.exists():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 riding-spending (research)"})
                with urllib.request.urlopen(req, timeout=120) as r:
                    path.write_bytes(r.read())
            except Exception as e:  # noqa: BLE001
                print("facility directory fetch failed:", name, e, file=sys.stderr)
                continue
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                fac = r.get("Facility Name") or r.get("FACILITY_NAME") or ""
                pt = None
                if r.get("X Coordinate") and r.get("Y  Coordinate"):
                    pt = (float(r["Y  Coordinate"]), float(r["X Coordinate"]))
                else:
                    m = re.search(r"POINT \(([-\d.]+) ([-\d.]+)\)", r.get("georeference") or "")
                    if m:
                        pt = (float(m.group(2)), float(m.group(1)))
                if fac and pt:
                    out.setdefault(norm(fac), pt)
                    core = facility_core(fac)
                    if core:
                        out.setdefault("core:" + core, pt)
    return out


def facility_core(name):
    """'The Mira Nursing Home' -> 'MIRA'; 'Celtic Court Continuing Care Residence-Shannex' -> 'CELTIC COURT'.
    Empty when what is left is too short to be safe."""
    core = re.sub(r"\s+", " ", FACILITY_GENERIC.sub(" ", norm(name))).strip()
    return core if len(core) >= 4 else ""


def windows():
    """Fiscal year ending -> window, plus the cutoff date, from the files that exist."""
    if look_for_next_volume(2026):
        return {2026: "after", 2024: "before"}, date(2026, 3, 31), WINDOW_NOTE[2026]
    return {2025: "after", 2024: "before"}, date(2025, 3, 31), WINDOW_NOTE[2025]


def main():
    WINDOWS, CUTOFF, window_note = windows()
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()

    # Name -> postal code sources.
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("NS|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "NS":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    facilities = load_facilities()
    recipient_places = {norm(k): v for k, v in RECIPIENT_PLACES.items()}
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[4] == "NS":
                try:
                    pt = (float(r[9]), float(r[10]))
                except ValueError:
                    continue
                for part in r[2].split("/"):
                    places[place_norm(part)].append(pt)
    place_names = sorted((p for p in places if len(p) >= 6 and p not in AMBIGUOUS), key=len, reverse=True)

    loc_cache = {}

    def locate_pc(pc):
        if pc in centroids:
            return index.locate(*centroids[pc])[0]
        return None

    def locate_latlon(pt):
        return index.locate(*pt)[0]

    def locate_place(key):
        pts = places.get(key)
        if not pts:
            return None
        return locate_latlon((sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)))

    def segments(name):
        base = re.sub(r"\s*\([^)]*\)", " ", name)
        parts = [p.strip() for p in re.split(r"\s*/\s*|_", base) if p.strip()]
        return parts or [name]

    def muni_key(name):
        for seg in segments(name):
            s = re.sub(r"\b(INC|LTD)\b.*$", "", place_norm(seg)).strip()
            m = MUNI.match(s)
            if m:
                return m.group(1).strip()
            m = MUNI_SUFFIX.match(s)
            if m:
                return m.group(1)
        return None

    def nation_key(name):
        for seg in segments(name):
            m = FIRST_NATION.match(place_norm(seg))
            if m:
                return m.group(1).strip()
        return None

    def place(name):
        """-> (district number or None, method)."""
        if name in loc_cache:
            return loc_cache[name]
        n = norm(name)
        res = (None, "unmatched")
        u = upper(name)
        if not n or "WITHHELD" in n or "CONFIDENTIAL" in n:
            res = (None, "withheld")
        elif PERSON.match(u) and not NOT_PERSON.search(u):
            res = (None, "individual")
        elif INTRA_GOV.search(u):
            res = (None, "intra-government")
        elif OUT_OF_PROVINCE.search(u) and not re.search(r"NOVA SCOTIA|NOUVELLE.ECOSSE|\bNS\b|HALIFAX|DARTMOUTH|SYDNEY", u):
            res = (None, "out-of-province")
        else:
            for seg in [name] + segments(name):
                key = norm(seg)
                if key in name_pc and locate_pc(name_pc[key]):
                    res = (locate_pc(name_pc[key]), "postal code from federal or charity records")
                    break
            if res[0] is None:
                for seg in [name] + segments(name):
                    key = norm(seg)
                    core = facility_core(seg)
                    pt = facilities.get(key) or (facilities.get("core:" + core) if core else None)
                    if pt and locate_latlon(pt):
                        res = (locate_latlon(pt), "address from facility directory")
                        break
            if res[0] is None and norm(name) in recipient_places:
                d = locate_latlon(recipient_places[norm(name)])
                if d:
                    res = (d, "place name in recipient (approx.)")
            if res[0] is None:
                key = muni_key(name)
                if key:
                    d = locate_latlon(MUNI_SEATS[key]) if key in MUNI_SEATS else locate_place(key)
                    if d:
                        res = (d, "municipality")
            if res[0] is None:
                key = nation_key(name)
                if key:
                    pt = FIRST_NATIONS.get(key) or FIRST_NATIONS.get(key.replace(" FIRST", ""))
                    d = locate_latlon(pt) if pt else locate_place(key)
                    if d:
                        res = (d, "municipality")
            if res[0] is None and not re.search(r"\bNOVA SCOTIA\b|\bNOUVELLE ECOSSE\b", n):
                pn = f" {place_norm(name)} "
                hits = [(len(places.get(p, ())), len(p), p) for p in place_names if f" {p} " in pn]
                hits += [(50, len(p), p) for p in FIRST_NATIONS if len(p) >= 6 and f" {p} " in pn]
                for _, _, p in sorted(hits, reverse=True):
                    d = locate_latlon(FIRST_NATIONS[p]) if p in FIRST_NATIONS and p not in places else locate_place(p)
                    if d:
                        res = (d, "place name in recipient (approx.)")
                        break
        loc_cache[name] = res
        return res

    def is_supplier(name):
        u = upper(name)
        if STRONG_SUPPLIER.search(u):
            return True
        if NONPROFIT.search(u):
            return False
        if NUMBERED.match(norm(name)) and len(norm(name).split()) <= 4:
            return True
        if INDUSTRY.search(u):
            return True
        if SUPPLIER_SUFFIX.search(re.sub(r"[^A-Z0-9 ]", " ", u)):
            return True
        if INC.search(u):
            return True
        return False

    def flag_for(name, section):
        """Why a placed payment is left out of the adjusted totals, or ""."""
        u = upper(name)
        if PROVINCEWIDE.search(u) and not muni_key(name):
            return "province-wide"
        key = None if nation_key(name) else muni_key(name)
        if key:
            return "other government" if key in MULTI_DISTRICT_MUNIS or key.endswith(" REGIONAL") else ""
        if section == "Other" or is_supplier(name):
            return "supplier"
        return ""

    rows, checks, dropped = [], {}, Counter()
    for path in sorted(DL.glob("pa-supplementary-*.pdf")):
        fye = int(re.search(r"(\d{4})", path.name).group(1))
        vol_rows, check = load_volume(fye)
        checks[f"FY{fye - 1}-{str(fye)[2:]}"] = check
        for r in vol_rows:
            if r["Section"] not in USED_SECTIONS:
                if WINDOWS.get(fye):
                    dropped[(WINDOWS[fye], r["Section"] or "(none)")] += r["Amount"]
                continue
            rows.append(r)
    series_fyes = sorted({r["fye"] for r in rows})
    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": [], "series": Counter()} for num in divisions}
    is_formula = formula_matcher("ns")
    method_counts = Counter()
    excluded = Counter()
    buckets = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    fy_label = {fy: f"FY{fy - 1}-{str(fy)[2:]}" for fy in WINDOWS}
    audit = []
    for r in rows:
        v = r["Amount"]
        window = WINDOWS.get(r["fye"])
        if v <= 0:
            continue
        program = r["Dept"]
        if AGGREGATE_DEPTS.match(program or "") or AGGREGATE.search(r["Recipient"]):
            if window:
                excluded[(window, "program aggregates (no payee)")] += v
                buckets[(window, "program aggregates")] += v
                audit.append([window, program, r["Section"], r["Recipient"], round(v), "", "aggregate", ""])
            continue
        num, how = place(r["Recipient"])
        if window:
            audit.append([window, program, r["Section"], r["Recipient"], round(v), num or "", how,
                          "" if how in ("withheld", "individual", "out-of-province", "intra-government") else flag_for(r["Recipient"], r["Section"])])
        if how in ("withheld", "individual", "out-of-province", "intra-government"):
            if window:
                kind = "individuals" if how == "individual" else how
                excluded[(window, kind)] += v
                buckets[(window, kind)] += v
            continue
        flag = flag_for(r["Recipient"], r["Section"])
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

    if os.environ.get("NS_PLACEMENTS"):
        with open(os.environ["NS_PLACEMENTS"], "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["window", "department", "section", "recipient", "amount", "district", "how", "flag"])
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
            g["progs"][r["Dept"]] += v
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
            "gov_won": dv["party_2024"] == GOV_PARTY,
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
    meta = {
        "generated": date.today().isoformat(), "election": ELECTION.isoformat(), "cutoff": CUTOFF.isoformat(),
        "before_start": BEFORE_START.isoformat(), "before_end": BEFORE_END.isoformat(), "years_per_window": YEARS,
        "after_fiscal_year": fy_label[after_fy], "windows": window_note,
        "straddles_election": after_fy == 2025,
        "sections": "Grants and Contributions (counted when placeable and not flagged) and Other (goods and services, always flagged supplier); "
                    "Salaries, Travel and External Secondments dropped",
        "population_basis": next(iter(divisions.values())).get("population_basis", ""),
        "close_margin": CLOSE_MARGIN, "median_pc_after": med,
        "search_url": SEARCH_URL,
        "series": {"kind": "fiscal year", "labels": [f"{fye - 1}-{str(fye)[2:]}" for fye in series_fyes], "complete": len(series_fyes),
                   "election_index": max([i for i, fye in enumerate(series_fyes) if date(fye, 3, 31) < ELECTION], default=-1)},
        "methods": {f"{w}|{m}": v for (w, m), v in method_counts.items()},
        "excluded_after": {m: round(v) for (w, m), v in excluded.items() if w == "after"},
        "buckets_after": {m: round(v) for (w, m), v in sorted(buckets.items(), key=lambda kv: -kv[1]) if w == "after"},
        "dropped_sections_after": {m: round(v) for (w, m), v in dropped.items() if w == "after"},
        "placed_after": round(sum(x["after_total"] for x in out.values())),
        "total_after": round(total_after),
        "pdf_check": {fy: {k: v for k, v in c.items() if k not in ("departments", "sections")} for fy, c in checks.items()},
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
