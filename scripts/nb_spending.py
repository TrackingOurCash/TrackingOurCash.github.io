"""New Brunswick: aggregate provincial payments by electoral district.

Reads data/raw/nb/payments-fy*.csv (Socrata "Supplier and Grant Payments by Department":
every payee receiving more than $25,000 from a department in a fiscal year; columns
Department, Supplier Name, Payment, Payment Type; HST excluded) and data/nb/divisions.json
(from nb_prep.py). Writes data/nb/division_spending.json with the same shape as the BC
file.

The CSV gives department, name, amount and payment type only: no address, no program,
no date, and grants are not separated from purchases. So:
  * Department stands in for the program: the program labels (top_progs, programs,
    prog_by_riding, top_grants.prog) are department names (English half of the bilingual
    label), and top_grants.date is the fiscal-year label "FY2024-25".
  * Payment Type: only "Payments & Grants" rows are used. "Loan Disbursements",
    "Purchase Cards" and "Other Payments" (together about 6% of FY2025 dollars) are
    dropped and their totals recorded in meta.other_payment_types_after.
  * Windows are whole fiscal years. The election was 21 October 2024. The FY2026 dataset
    (year to 31 March 2026) is published in December 2026 and did not exist on 25 October
    2026 (the Socrata catalogue's latest is "2025 - Supplier and Grant Payments", posted
    15 December 2025), so "after" is FY2025 (1 April 2024 to 31 March 2025), which
    STRADDLES the election: about six and a half months of it fall before the vote. The
    "before" window is FY2024 (1 April 2023 to 31 March 2024). years_per_window = 1.0.
    If a payments-fy2026.csv is dropped into data/raw/nb/ the script switches on its own
    to after = FY2026, before = FY2024 (FY2025 then skipped as the straddling year) and
    the meta dates follow. FY2021-FY2023 are downloaded for reference but not counted in
    the windows. Every payments-fy*.csv present is read, and each year's adjusted dollars
    go into a per-district time series (ridings[num].series, aligned to
    meta.series.labels), placed and flagged exactly as the windows are.
    meta: election 2024-10-21, cutoff = end of the after year, before_start/before_end =
    the before year.

Each payment is placed by the recipient's name, in this order (as bc_spending.py does):
  1. the same name in the federal grants file, data/name_postal.json ("NB|name" keys);
  2. the CRA list of registered charities with Province NB (name -> postal code);
  3. a municipality name ("City of X", "Town of X", "Village of X", "Ville de X",
     "Municipalité (régionale) de X", "Communauté rurale de X", "Rural Community of X",
     "X Rural Community", "Municipality of X", or just "X" when the whole payee name is a
     place with 20+ postal codes, as Transportation writes "Edmundston") or a First
     Nation ("X First Nation", "Première nation X") -> GeoNames centroid of that place, or
     PLACE_ALIASES (hand-set coordinates, approximate: the main settlement) for the 2023
     amalgamated municipalities and First Nations that GeoNames does not list (Tantramar,
     Hautes-Terres, Champdoré, Belle-Baie, Fundy Albert, Strait Shores, Heron Bay,
     Sitansisk, Neqotkuk, ...);
  4. a place name inside the recipient's name ("Villa Providence Shédiac inc"); when
     several match, the place with the most GeoNames postal codes wins ("Foyer
     Saint-Thomas Vallée de Memramcook" -> Memramcook, not the hamlet of Saint-Thomas).
Postal codes and place names come from GeoNames CA_full.txt (province NB; bilingual
names like "Grand-Sault/Grand Falls" are indexed under both halves, "St"/"Ste" are
expanded to "Saint"/"Sainte", accents stripped) and are located by point-in-polygon on
the 2024 boundaries in data/nb/divisions_geo.json. GeoNames names that are also surnames
or ordinary words (Douglas, Lincoln, Stanley, Forest, Central, ...) are never place hits.

Classification (decided before placing; each bucket's dollars are in meta.buckets_after):
  * "individuals": payees written "Surname, Given" (foster parents, care providers,
    landlords, students); never placed, counted under excluded_after["individuals"].
  * "out-of-province": other governments and bodies outside New Brunswick (Receiver
    General for Canada, Minister of Finance - Nova Scotia, Régie de l'assurance maladie
    du Québec, "Hospitals - Ontario", Memorial University, Maine DOT, ...); never placed.
  * "province-wide": the Horizon and Vitalité health networks, EM/ANB and Medavie
    (ambulance and extra-mural), NB Power, Service New Brunswick, Vestcor and the pension
    plans, WorkSafeNB, Legal Aid, universities and colleges, school districts, NB Housing,
    the Regional Service Commissions, Crown corporations and agencies, tribal councils,
    bodies named "... of New Brunswick" / "du Nouveau-Brunswick" / "New Brunswick ..."
    (associations, federations, foundations). Placed when a location is known (so they
    show in the district's top recipients, flagged) and excluded from the adjusted totals;
    when they cannot be placed they count under excluded_after["province-wide bodies"].
  * "other government": the cities of Moncton, Saint John and Fredericton (always) and any
    other municipality whose postal codes fall materially (over 15%) outside one district
    (Dieppe, Miramichi, Riverview, Edmundston, ...). Placed and flagged.
  * "supplier": obvious suppliers of goods and services: names ending in Ltd, Ltée,
    Limited, Corp, LLC, LLP or LP; names with an industry word (construction, paving,
    contracting, consulting, engineering, architects, software, technologies, pharma,
    telecom, energy, fuel, equipment, supply, sales, rentals, manufacturing, trucking,
    auto, electrical, plumbing, asphalt, holdings, enterprises, law firms, insurance,
    banks); bare numbered companies ("724007 NB Ltd"); and any Inc/Ltd paid by
    Transportation and Infrastructure, General Government or Finance. A care or
    community word (villa, manor, foyer, résidence, home, care, soins, daycare, garderie,
    housing, co-op, association, society, club, church, festival, museum, school, ...)
    overrides the Ltd/industry/department tests, because New Brunswick's nursing homes,
    special-care homes, daycares and community groups are incorporated as "Inc"/"Ltée";
    but a strong supplier word (construction, paving, truck, leasing, equipment, hotel,
    insurance, bank, in trust, holdings, "Homes Inc", ...) or an incorporated payee of
    Transportation and Infrastructure is a supplier whatever else the name says. The same
    recipient can be a supplier under one department and not another ("Greater
    Fredericton Knowledge Park Inc": Transportation vs Post-Secondary).
    Suppliers are placed when they can be and flagged "supplier" (so pc_after_all keeps
    them and pc_after leaves them out); unplaced ones count under
    excluded_after["suppliers"].
  * everything else (non-profits, municipalities, First Nations, nursing homes, daycares,
    farms, small businesses paid by Agriculture or Tourism) counts in the adjusted totals.

Groups: "Close LIB", "Close PC", "Safe LIB", "Safe PC"; gov_won means the Liberals (who
won government in 2024) won the seat; close means a margin under 10 points. Tantramar and
Fredericton Lincoln (Green) fall in the "PC" (not government) groups.

Checking the rules: NB_PLACEMENTS=/path/to/file.tsv python3 scripts/nb_spending.py also
writes every row's window, department, recipient, amount, district, method and flag.

Result on 25 October 2026 (FY2025 as "after", $8.54 B of Payments & Grants): 56% of the
dollars placed in a district (most of it the two health networks and the universities,
flagged province-wide), 10% counted in the adjusted per-elector figures, 7% unmatched
(home-care agencies and firms with no place in their name), 16% suppliers, 13%
province-wide bodies that could not be placed, 7% out of province, 0.7% individuals.
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

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "nb"
sys.path.insert(0, str(ROOT / "scripts"))
from geo import RidingIndex, load_centroids  # noqa: E402
from build_spending import recipient_table  # noqa: E402

ELECTION = date(2024, 10, 21)
BEFORE_START, BEFORE_END = date(2023, 4, 1), date(2024, 3, 31)
YEARS = 1.0
CLOSE_MARGIN = 10.0
GOV_PARTY = "LIB"
OPP_LABEL = "PC"
WINDOW_NOTE = {
    2025: "after = FY2025 (1 April 2024 to 31 March 2025, which straddles the 21 October 2024 election: FY2026 is not published until December 2026); "
          "before = FY2024 (1 April 2023 to 31 March 2024), the last full fiscal year before the election; annual data, no payment dates",
    2026: "after = FY2026 (1 April 2025 to 31 March 2026), the first full fiscal year after the 21 October 2024 election; "
          "before = FY2024 (1 April 2023 to 31 March 2024), the last full fiscal year before it; FY2025 straddles the election and is skipped; annual data, no payment dates",
}

# "Surname, Given" (one to three words each side, no corporate word): a person.
PERSON = re.compile(r"^[A-Z'\-]+( [A-Z'\-]+){0,2}, [A-Z'\-.]+( [A-Z'\-.]+){0,3}$")
NOT_PERSON = re.compile(r"\b(INC|LTD|LTEE|LLP|LLC|LP|LIMITED|CORP|CO|DIVISION|PLAN|OFFICE|SERVICES?|GROUP|TRUST|PARTNERS|CONSULTANTS?|CONSULTING|"
                        r"ASSOCIATES|CANADA|NB|NEW BRUNSWICK|CENTRE|CENTER|FARMS?|HOLDINGS|ENTERPRISES|AGENCY|CLINIC|"
                        r"PHARMACY|PHARMACIE|FOUNDATION|DEPARTMENT|EXCHEQUER|HOSPITALS?|UNIVERSITY|CITY|TOWN|VILLAGE)\b")
OUT_OF_PROVINCE = re.compile(
    r"RECEIVER GENERAL|CANADA REVENUE|GOVERNMENT OF (CANADA|ALBERTA|YUKON|ONTARIO|QUEBEC|NOVA SCOTIA|MANITOBA|SASKATCHEWAN|BRITISH COLUMBIA|"
    r"PRINCE EDWARD|NEWFOUNDLAND|NUNAVUT|NORTHWEST)|MINISTER OF FINANCE - |MINISTRY OF|MINISTERE DE|HOSPITALS - |"
    r"NOVA SCOTIA|QUEBEC|ONTARIO|PRINCE EDWARD ISLAND|NEWFOUNDLAND|ALBERTA|BRITISH COLUMBIA|MANITOBA|SASKATCHEWAN|YUKON|"
    r"\bMAINE\b|MEMORIAL UNIVERSITY|DALHOUSIE UNIVERSITY|UNIVERSITY OF PRINCE|LISTUGUJ|GESGAPEGIAG|\bPEI\b|\bP\.E\.I\b|"
    r"DESTINATION CANADA|CANADIAN TOURISM COMMISSION|TREASURER OF|STATE OF|COUNCIL OF ATLANTIC|ATLANTIC PROVINCES|"
    r"CANADIAN BLOOD SERVICES|CANADA HEALTH INFOWAY|CANADIAN INSTITUTE FOR HEALTH|INTERNATIONAL REGISTRATION PLAN",
    re.I)
PROVINCEWIDE = re.compile(
    r"^HORIZON\b|HORIZON HEALTH|VITALIT|EM/ANB|EM-ANB|AMBULANCE NEW BRUNSWICK|AMBULANCE NB|EXTRA-?MURAL|MEDAVIE|NEW BRUNSWICK MEDICAL SOCIETY|"
    r"SERVICE NEW BRUNSWICK|SERVICE NOUVEAU-BRUNSWICK|\bSNB\b|NB POWER|ENERGIE NB|ÉNERGIE NB|VESTCOR|PENSION PLAN|REGIME DE RETRAITE|"
    r"RÉGIME DE RETRAITE|WORKSAFE|TRAVAIL SECURITAIRE|TRAVAIL SÉCURITAIRE|LEGAL AID|AIDE JURIDIQUE|FOREST PROTECTION LIMITED|"
    r"KINGS LANDING|OPPORTUNITIES NEW BRUNSWICK|OPPORTUNITES N|OPPORTUNITÉS N|REGIONAL DEVELOPMENT CORPORATION|"
    r"SOCIETE DE DEVELOPPEMENT REGIONAL|NB LIQUOR|ALCOOL NB|CANNABIS NB|INVEST NB|RESEARCH NB|RECHERCHE NB|"
    r"NEW BRUNSWICK INNOVATION|NEW BRUNSWICK HEALTH RESEARCH|TOURISM NEW BRUNSWICK|NB HIGHWAY|HIGHWAY CORPORATION|"
    r"INTERNAL SERVICES AGENCY|NB LOTTERIES|LOTTERIES AND GAMING|EFFICIENCY NB|NB MUSEUM|NEW BRUNSWICK MUSEUM|MUSEE DU NOUVEAU|"
    r"NBCC|CCNB|COLLEGE COMMUNAUTAIRE|COLLÈGE COMMUNAUTAIRE|NEW BRUNSWICK COMMUNITY COLLEGE|UNIVERSITY|UNIVERSITE|UNIVERSITÉ|"
    r"COLLEGE OF|COLLEGE$|COLLÈGE|POLYTECHNIC|CRAFT COLLEGE|"
    r"SCHOOL DISTRICT|DISTRICT SCOLAIRE|ANGLOPHONE (NORTH|SOUTH|EAST|WEST)|FRANCOPHONE (NORD|SUD)|BOARD OF EDUCATION|"
    r"REGIONAL SERVICE COMMISSION|SERVICE COMMISSION|COMMISSION DE SERVICES R|COMMISSION DES SERVICES R|COMMISSION DE SERIVES|"
    r"NEW BRUNSWICK HOUSING|NB HOUSING|HABITATION NB|HOUSING CORPORATION$|"
    r"TRIBAL COUNCIL|FIRST NATIONS (EDUCATION|HEALTH|CHIEFS)|MI'?GMAWE'?L TPLU'?TAQNN|WOLASTOQEY NATION|"
    r"\bPROVINCE OF\b|\bGOVERNMENT OF\b|\bMINISTER OF\b|DEPARTMENT OF|MINISTRY OF|MINISTERE|MINISTÈRE|"
    r"TEACHERS.? FEDERATION|FEDERATION DES ENSEIGNANT|FÉDÉRATION DES ENSEIGNANT|\bCUPE\b|\bSCFP\b|NURSES UNION|"
    r"UNION OF (THE )?MUNICIPALITIES|UNION DES MUNICIPALITES|CITIES OF NEW BRUNSWICK|ASSOCIATION FRANCOPHONE DES MUNICIPALITES|"
    r"NEW BRUNSWICK (ASSOCIATION|FEDERATION|FÉDÉRATION|SOCIETY|COUNCIL|FOUNDATION|COMMISSION|NETWORK|COALITION|ALLIANCE|INSTITUTE|UNION|TRUST|"
    r"ABORIGINAL|ABORIGINAL PEOPLES|MULTICULTURAL|SENIORS|SPORTS|MEDICAL|PHARMAC|DENTAL|NURSES|LUNG|HEART|CANCER|CRIME|ROAD BUILDERS|"
    r"LIBRARIES|LIBRARY|ARTS BOARD|HISTORICAL|GENEALOGICAL|FOREST|WOODLOT|CATTLE|POTATO|SOIL|APPLE|MAPLE|BLUEBERRY|FISH|CHICKEN|"
    r"EGG|MILK|PORK|SHEEP|AGRICULTURAL|TRAILS|SNOWMOBILE|ATV|HOCKEY|SOCCER|BASEBALL|SPECIAL OLYMPICS|FARMERS)|"
    r"\bNB (ASSOCIATION|FEDERATION|SOCIETY|COUNCIL|FOUNDATION|COMMISSION|NETWORK|COALITION|ALLIANCE|INSTITUTE|UNION|TRUST|MEDICAL|ASSN)|"
    r"(ASSOCIATION|FEDERATION|FÉDÉRATION|SOCIETY|SOCIETE|SOCIÉTÉ|COUNCIL|CONSEIL|FOUNDATION|FONDATION|INSTITUTE|INSTITUT|NETWORK|RESEAU|RÉSEAU|"
    r"COALITION|ALLIANCE|ASSEMBLY|CHAMBER|BOARD|OFFICE|COMMISSION|CORPORATION|LEAGUE|CONFERENCE|UNION|TRUST|AUTHORITY|AGENCY|CENTRE|CENTER) "
    r"(OF|FOR|DU|DE|DES|POUR) .*(NEW BRUNSWICK|NOUVEAU-BRUNSWICK|NOUVEAU BRUNSWICK|\bN\.?-?B\.?\b)|"
    r"(NEW BRUNSWICK|NOUVEAU-BRUNSWICK|NOUVEAU BRUNSWICK)$|"
    r"ACADIENNE DU NOUVEAU|ACADIEN DU NOUVEAU|SOCIETE DE L'ACADIE|SOCIÉTÉ DE L'ACADIE|SOCIETE NATIONALE DE L'ACADIE|"
    r"UNITED WAY|CENTRAIDE|CANADIAN MENTAL HEALTH ASSOCIATION OF NEW BRUNSWICK|CANADIAN RED CROSS|CROIX-ROUGE|"
    r"ATLANTIC (CANADA|PROVINCES|LOTTERY|BALLET|SALMON)|SALMON FEDERATION|CROWN CORPORATION|SOCIETE DE GESTION|"
    r"COMMISSIONAIRES|APPRENTICESHIP|SKILLS CANADA|JUNIOR ACHIEVEMENT|SPECIAL OLYMPICS NEW",
    re.I)
MUNI = re.compile(r"^(?:CORPORATION OF )?(?:THE )?(CITY|TOWN|VILLAGE|RURAL COMMUNITY|REGIONAL MUNICIPALITY|RURAL DISTRICT|MUNICIPALITY|"
                  r"VILLE|MUNICIPALITE REGIONALE|MUNICIPALITE|COMMUNAUTE RURALE|DISTRICT RURAL|COMMUNAUTE|COMMUNITY) "
                  r"(?:OF |DE |DES |DU |D |LA |LE |LES )?(.+?)(?: FOR | POUR |$)")
MUNI_SUFFIX = re.compile(r"^(.+?) (RURAL COMMUNITY|REGIONAL MUNICIPALITY|RURAL DISTRICT|MUNICIPALITY|COMMUNAUTE RURALE|MUNICIPALITE REGIONALE|DISTRICT RURAL)$")
FIRST_NATION = re.compile(r"^(.+?) (FIRST NATION|INDIAN BAND|BAND COUNCIL|BAND|NATION)(?:'S| S)?\b|^PREMIERE NATION (?:DE |DES |DU |D )?(.+?)$")
# Spread over several districts whatever the postal codes say.
BIG_CITIES = {"MONCTON", "SAINT JOHN", "FREDERICTON"}
SUPPLIER_SUFFIX = re.compile(r"\b(LTD|LTEE|LIMITED|LIMITEE|CORP|CORPORATION|LLC|LLP|LP|L P|CO|COMPANY|COMPAGNIE|GMBH|PLC|SA|AG)\b")
INC = re.compile(r"\bINC\b|\bINCORPORATED\b|\bINCORPOREE\b")
NUMBERED = re.compile(r"^\d{5,8} (NB|N B|CANADA|ONTARIO|QUEBEC|NOVA SCOTIA)\b")
INDUSTRY = re.compile(
    r"\b(?:CONSTRUCTION|PAVING|PAVAGE|CONTRACT(ING|OR|ORS)|CONSULT(ING|ANT|ANTS)|ENGINEER|INGENIEUR|ARCHITECT|SOFTWARE|LOGICIEL|"
    r"TECHNOLOG|SYSTEMS|SOLUTIONS|PHARMA|GLAXO|PFIZER|MERCK|NOVARTIS|SANOFI|ASTRAZENECA|JOHNSON INCORPORATED|TELECOM|BELL CANADA|"
    r"BELL ALIANT|ROGERS|TELUS|XPLOR|EASTLINK|ENERG(Y|IE|IES)|FUEL|PETROL|OIL\b|PROPANE|GAS\b|IRVING|ESSO|SHELL|ULTRAMAR|"
    r"EQUIPMENT|EQUIPEMENT|SUPPL(Y|IES)|SALES|RENTAL|LOCATION D|MANUFACTUR|FABRICATION|TRUCK|CAMION|AUTO\b|AUTOMOBILE|MOTORS|"
    r"\bGMC\b|FORD\b|CHEVROLET|TOYOTA|HONDA|NISSAN|HYUNDAI|KIA\b|ELECTRIC|ELECTRIQUE|PLUMBING|PLOMBERIE|HEATING|CHAUFFAGE|"
    r"EXCAVAT|ASPHALT|LUMBER|BOIS\b|MACHIN|HOLDINGS|ENTERPRISES|ENTREPRISES|VENTURES|REALTY|PROPERTIES|DEVELOPMENTS|INVESTMENTS|"
    r"TRADING|INDUSTR|LOGISTIC|TRANSPORT|TRUCKING|MECHANICAL|STEEL|CONCRETE|BETON|ROOFING|TOITURE|WELDING|SOUDURE|TOWING|REMORQUAGE|"
    r"TIRE\b|TIRES|PNEUS|INSURANCE|ASSURANCE|BANK|BANQUE|CREDIT UNION|CAISSE POPULAIRE|LAW\b|AVOCAT|LEGAL\b|BARRISTER|IN TRUST|"
    r"EN FIDUCIE|PRINTING|IMPRIMERIE|SECURITY|SECURITE|STAFFING|PERSONNEL|FLEXTRACK|IBM\b|MICROSOFT|ORACLE|DELL\b|XEROX|"
    r"CANON\b|SIEMENS|HONEYWELL|JOHNSON CONTROLS|KONE\b|OTIS\b|SCHINDLER|MEDICAL SUPPL|DIAGNOSTIC|LABORATOR|CLEANING|JANITORIAL|"
    r"NETTOYAGE|LANDSCAP|PAYSAG|SNOW|DENEIGEMENT|FORESTRY|FORESTERIE|SAWMILL|SCIERIE|PULP|PAPER\b|MINING|MINES\b|QUARR|"
    r"CARRIERE|GRAVEL|GRAVIER|SAND\b|AGGREGATE|BUILDERS|BUILDING SUPPL|HARDWARE|QUINCAILLERIE|HOME HARDWARE|CANADIAN TIRE|"
    r"KENT BUILDING|COSTCO|WALMART|SOBEYS|LOBLAW|SUPERSTORE|STAPLES|OFFICE DEPOT|GRAND & TOY|AMAZON|UBER|AIR CANADA|PORTER|"
    r"VIA RAIL|HOTEL|MOTEL|\bINN\b|AUBERGE|RESTAURANT|PIZZ|CATERING|TRAITEUR|FOOD SERVICE|CAFETERIA|VENDING|"
    r"AVIATION|AIRCRAFT|HELICOPT|MARINE\b|SHIPYARD|DREDG|FENCING|CLOTURE|SIGNS?\b|ENSEIGNES|GLASS|VITRE|WINDOWS|FENETRES|"
    r"DOORS|PORTES|FLOOR|PLANCHER|PAINT|PEINTURE|CARPET|TAPIS|FURNITURE|MEUBLES|APPLIANCE|RADIO|BROADCAST|MEDIA|PUBLISH|"
    r"ADVERTIS|PUBLICIT|MARKETING|COMMUNICATIONS? INC|DESIGN INC|STUDIO|PRODUCTIONS|SURVEY|ARPENT|GEOMATIC|ENVIRONMENTAL (INC|LTD|SERVICES)|"
    r"WASTE|DECHETS|RECYCL|DISPOSAL|SEPTIC|WATER TREATMENT|FILTRATION|UNIFORM|APPAREL|VETEMENT|SPORTS? EXCELLENCE|SOURCE FOR SPORTS|"
    r"GROUP\b|GROUPE\b|LEASING|CREDIT-?BAIL|STEWART MCKELVEY|COX & PALMER|MCINNES COOPER|LAWSON CREAMER|BARRISTER|SOLICITOR|LAW OFFICE|"
    r"LAW FIRM|NOTAIRE|EVISIT|VIRTUAL CARE|TELEHEALTH|MANULIFE|SUN LIFE|CANADA LIFE|GREAT-WEST|BLUE CROSS|MEDAVIE|DESJARDINS|"
    r"ROYAL BANK|SCOTIABANK|\bBMO\b|\bTD\b|\bCIBC\b|NATIONAL BANK|APPLE CANADA|GOOGLE|META PLATFORMS|FACEBOOK|ADOBE|SAP\b|"
    r"CGI\b|DELOITTE|KPMG|ERNST & YOUNG|\bEY\b|PRICEWATERHOUSE|\bPWC\b|GRANT THORNTON|MNP\b|ACCENTURE|GARTNER|ESRI|"
    r"PUBLIC RELATIONS|RELATIONS PUBLIQUES|ASSOCIATES INC|ASSOCIES INC|& ASSOCIATES|ET ASSOCIES|PARTNERS\b|PARTENAIRES\b|"
    r"MANAGEMENT INC|MANAGEMENT LTD|GESTION\b|INVESTISSEMENT|CAPITAL INC|CAPITAL LTD|FINANCIAL|FINANCIERE|FINANCIÈRE|LEASE\b|"
    r"RENT-?ALL|HOME DEPOT|RONA\b|LOWE'S|IKEA|BEST BUY|TRANSPORT LTD|TRANSPORT INC|TRANSPORT LTEE|FREIGHT|COURIER|PUROLATOR|"
    r"FEDEX|\bUPS\b|CANADA POST|POSTES CANADA|TIMBER|FOREST PRODUCTS|PRODUITS FORESTIERS|PULP|SAWMILL|SCIERIE|WOODLANDS|"
    r"\bLTD\b|\bLTEE\b|\bLIMITED\b|\bLIMITEE\b|\bCORP\b|\bLLC\b|\bLLP\b)",
    re.I)
NONPROFIT = re.compile(
    r"\b(?:HOME\b|HOMES\b|VILLA|MANOR|MANOIR|FOYER|RESIDENCE|RÉSIDENCE|RESIDENCES|\bCARE\b|SOINS|CHILD ?CARE|DAYCARE|DAY CARE|GARDERIE|"
    r"NURSING|INFIRMI|HOUSING|HABITATION|LOGEMENT|CO-?OP\b|COOPERATIVE|COOPÉRATIVE|COOPERATIVE|ASSOCIATION|SOCIETY|SOCIETE|SOCIÉTÉ|"
    r"FOUNDATION|FONDATION|\bCLUB\b|CHURCH|EGLISE|ÉGLISE|PARISH|PAROISSE|DIOCESE|FESTIVAL|MUSEUM|MUSEE|MUSÉE|THEATRE|THÉÂTRE|"
    r"THEATER|GALLERY|GALERIE|SYMPHONY|ORCHESTR|CHORAL|CHOIR|CHORALE|BALLET|DANCE|DANSE|ARTS?\b|SCHOOL|ECOLE|ÉCOLE|ACADEMY|"
    r"ACADEMIE|ACADÉMIE|MONTESSORI|PRESCHOOL|PRESCOLAIRE|KINDER|LEARNING|APPRENTISSAGE|LITERACY|ALPHABETISATION|COMMUNITY|"
    r"COMMUNAUTAIRE|COMMUNAUTE|COMMUNAUTÉ|CENTRE\b|CENTER\b|COUNCIL|CONSEIL|COMMITTEE|COMITE|COMITÉ|HOUSE\b|MAISON|TRANSITION|"
    r"SHELTER|REFUGE|FAMILY|FAMILLE|FAMILIAL|YOUTH|JEUNESSE|JEUNES|SENIORS?|AINES|AÎNÉS|AGE D'OR|LIBRARY|BIBLIOTH|FOOD BANK|"
    r"BANQUE ALIMENTAIRE|SOUP KITCHEN|HOSPICE|PALLIATI|WELLNESS|MIEUX-ETRE|MIEUX-ÊTRE|MENTAL HEALTH|SANTE MENTALE|ADDICTION|"
    r"RECOVERY|RETABLISSEMENT|CRISIS|CRISE|SUPPORT|SOUTIEN|ENTRAIDE|VOLUNTEER|BENEVOL|BÉNÉVOL|CHARIT|LEGION|LIONS|KINSMEN|KIWANIS|"
    r"ROTARY|KNIGHTS OF COLUMBUS|CHEVALIERS DE COLOMB|SALVATION ARMY|ARMEE DU SALUT|YMCA|YWCA|BOYS AND GIRLS|BIG BROTHERS|"
    r"SCOUTS|GUIDES|CADETS|4-H|FAIR\b|EXHIBITION|EXPOSITION|AGRICULTURAL SOCIETY|HISTORICAL|HERITAGE|PATRIMOINE|MULTICULTURAL|"
    r"IMMIGRANT|NEWCOMER|REFUGEE|FIRST NATION|PREMIERE NATION|PREMIÈRE NATION|TRIBAL|MI'?K?GMA|WOLASTOQ|MALISEET|MALECITE|"
    r"INDIGENOUS|AUTOCHTONE|ABORIGINAL|FRIENDSHIP|AMITIE|AMITIÉ|WOMEN|FEMMES|MEN'?S|HOMMES|PREGNANCY|GROSSESSE|DISABILIT|HANDICAP|"
    r"ABILITY|ABILITIES|AUTISM|AUTISME|DEAF|SOURD|BLIND|AVEUGLE|SPECIAL CARE|SPECIAL NEEDS|GROUP HOME|RESIDENTIAL|INCLUSION|"
    r"L'ARCHE|EMPLOYMENT|EMPLOI|ENTERPRISE CENTRE|CBDC|COMMUNITY BUSINESS DEVELOPMENT|CHAMBER OF COMMERCE|CHAMBRE DE COMMERCE|"
    r"DOWNTOWN|CENTRE-VILLE|BUSINESS IMPROVEMENT|TOURISM ASSOC|TOURISME|PARK\b|PARC\b|TRAIL|SENTIER|ARENA|ARÉNA|RINK|POOL|"
    r"PISCINE|RECREATION|LOISIRS|SPORTS? (CLUB|ASSOC|COUNCIL|CENTRE)|HOCKEY|SOCCER|CURLING|SKI\b|GOLF|SAILING|ROWING|SWIM|"
    r"GYMNAST|FIGURE SKAT|SPEED SKAT|BASEBALL|SOFTBALL|BASKETBALL|VOLLEYBALL|RUGBY|LACROSSE|JUDO|KARATE|BOXING|ATHLETI|"
    r"TRACK AND FIELD|SPECIAL OLYMPICS|OLYMPI|PARALYMPI|GAMES\b|JEUX\b|CAMP\b|CAMPS\b|BIBLE|GOSPEL|MINISTR|MISSION\b|"
    r"CATHEDRAL|CATHEDRALE|ABBEY|MONASTERY|CONVENT|COUVENT|SISTERS|SOEURS|RELIGIEUSES|CHRISTIAN|CHRETIEN|CHRÉTIEN|CATHOLIC|"
    r"CATHOLIQUE|BAPTIST|ANGLICAN|UNITED CHURCH|PENTECOST|WESLEYAN|ADVENTIST|MOSQUE|ISLAMIC|JEWISH|SYNAGOGUE|TEMPLE|SIKH|HINDU|"
    r"BUDDHIST|HOSPITAL FOUNDATION|HEALTH FOUNDATION|FONDATION DE L'HOPITAL|AUXILIARY|RED CROSS|CANCER|DIABETES|DIABETE|"
    r"HEART AND STROKE|LUNG|KIDNEY|ALZHEIMER|PARKINSON|ARTHRITIS|MS SOCIETY|SCLEROSE|EPILEPS|CEREBRAL|DOWN SYNDROME|"
    r"CHILDREN'?S|ENFANTS|ENFANCE|PETITE ENFANCE|BABIES|BEBE|BÉBÉ|KIDS|PETITS|TOTS|TOUT-PETITS|AMIS\b|FRIENDS|BUDDIES|"
    r"RAINBOW|SUNSHINE|SMILING|HAPPY|LITTLE|PETIT|TINY|TEDDY|BEAR|BUMBLE|BUSY|CREATIVE|DISCOVERY|IMAGIN|WONDER|GIGGLE|PLAY(?:SCHOOL|GROUP|HOUSE|TIME)?\b|"
    r"JARDIN D'ENFANT|NURSERY|CRECHE|CRÈCHE|HEADSTART|HEAD START|EARLY (LEARNING|CHILDHOOD|YEARS)|AFTER ?SCHOOL|"
    r"TRANSITION HOUSE|SAFE HOUSE|OUTREACH|DROP-IN|HALFWAY|JOHN HOWARD|ELIZABETH FRY|SEXUAL|ASSAULT|VIOLENCE|ABUSE|"
    r"PEACEKEEP|JUSTICE INITIATIVE|RESTORATIVE|LEGAL CLINIC|ADVOCACY|CITIZENS|RESIDENTS|RATEPAYERS|FIRE DEPARTMENT|FIRE DEPT|"
    r"VOLUNTEER FIRE|POMPIERS|SEARCH AND RESCUE|RECHERCHE ET SAUVETAGE|GROUND SEARCH|AMBULANCE SERVICE INC|WATERSHED|"
    r"BASSIN VERSANT|CONSERVATION|NATURALIST|NATURE|ENVIRONNEMENT|ENVIRONMENTAL (ASSOC|COUNCIL|NETWORK|TRUST)|ESTUARY|ESTUAIRE|"
    r"RIVER (ASSOC|KEEPER|WATCH)|SALMON (ASSOC|PROTECTIVE)|WILDLIFE|FAUNE|ANGLERS|HUNTERS|ROD AND GUN|FISH AND GAME|"
    r"HARBOUR AUTHORITY|ADMINISTRATION PORTUAIRE|AIRPORT|AEROPORT|AÉROPORT|FARMERS'? MARKET|MARCHE|MARCHÉ|FESTIVAL|CARNAVAL|"
    r"CARNIVAL|PARADE|CELEBRATION|FETE|FÊTE|JAZZ|BLUES|FOLK|MUSIC|MUSIQUE|FILM|CINEMA|CINÉMA|WRITERS|ECRIVAINS|POETS|BOOK|LIVRE|"
    r"CRAFTS?\b|ARTISAN|POTTERY|QUILT|WEAVERS|GENEALOG|ARCHIVES|HISTORY|HISTOIRE|VETERANS|ANCIENS COMBATTANTS|SNOWMOBILE|"
    r"MOTONEIGE|ATV\b|VTT\b|QUAD\b|TRAILS\b|CYCLING|VELO|VÉLO|RUNNING|MARATHON|TRIATHLON|HORSE|EQUESTR|ÉQUESTR|RIDING\b|"
    r"THERAPEUTIC|THERAPY|THÉRAPIE|THERAPIE|SPEECH|LANGUAGE|LANGUE|FRANCOPHONE|ACADIEN|ACADIENNE|ANGLOPHONE|BILINGU|"
    r"IMMERSION|FRENCH|FRANCAIS|FRANÇAIS|ENGLISH|ANGLAIS|LANGUAGE SCHOOL|TUTOR|TUTORAT|MENTOR|LEADERSHIP|SKILLS\b|COMPETENCES|"
    r"LITERACY|NUMERACY|ADULT LEARN|APPRENTIS|APPRENTI-SAGE|COLLEGE OF PIPING|CONSERVATORY|CONSERVATOIRE|UNIVERSITE DU TROISIEME|"
    r"CEMETERY|CIMETIERE|CIMETIÈRE|MEMORIAL|COMMEMORAT|LIGHTHOUSE|PHARE|WHARF|QUAI|MARINA|YACHT|BOAT CLUB|CANOE|KAYAK|"
    r"SURF|ANIMAL|SPCA|HUMANE|REFUGE|RESCUE|SAUVETAGE|SANCTUARY|SHELTER|ZOO\b|AQUARIUM|BOTANIC|GARDEN|JARDIN|ARBORETUM|"
    r"KINGSBRAE|MACTAQUAC|"
    r"PARTNERSHIP INC|PARTENARIAT|NETWORK|RESEAU|RÉSEAU|COALITION|ALLIANCE|COLLECTIVE|COLLECTIF|COMMONS|COOP\b|CO OP\b|"
    r"NON-?PROFIT|NON PROFIT|SANS BUT LUCRATIF|OSBL|OBNL|CHARITABLE|BENEVOLENT|RELIEF|AID\b|AIDE\b|HELP\b|HOPE\b|ESPOIR|"
    r"HARVEST|MOISSON|SHARE\b|PARTAGE|CARING|COMPASSION|DIGNITY|DIGNITE|DIGNITÉ|INDEPENDENT LIVING|VIE AUTONOME|"
    r"SELF-HELP|PEER|PAIRS|CLUBHOUSE|OPEN SKY|OPEN DOOR|PORTE OUVERTE|WELCOME|ACCUEIL|SETTLEMENT|ETABLISSEMENT|"
    r"MULTICULTUR|NEW CANADIAN|NOUVEAUX ARRIVANTS)",
    re.I)
# Words that make a supplier even when a care or community word is also present
# ("Trius Truck Centre", "Hyatt Place Moncton / Downtown", "Maple Leaf Homes Inc").
STRONG_SUPPLIER = re.compile(
    r"\b(?:CONSTRUCTION|PAVING|PAVAGE|ASPHALT|CONTRACTING|CONTRACTORS|TRUCK|CAMION|LEASING|EQUIPMENT|EQUIPEMENT|ENGINEERING|"
    r"INGENIERIE|ARCHITECT|IN TRUST|EN FIDUCIE|BARRISTER|SOLICITOR|INSURANCE|ASSURANCES?\b|BANK\b|BANQUE|HOTEL|MOTEL|INN\b|"
    r"AUBERGE|HOLDINGS|REALTY|PROPERTIES|DEVELOPMENTS|PHARMA|TELECOM|OIL\b|FUEL|PETROL|ENERGY|ENERGIE|LUMBER|HARDWARE|"
    r"MANUFACTUR|SALES|RENTALS?\b|TOWING|TIRES?\b|AUTO BODY|MOTORS|LOGISTICS|TIMBER|FOREST PRODUCTS|PRODUITS FORESTIERS|PULP|"
    r"SAWMILL|SCIERIE|STEEL|CONCRETE|BETON|WELDING|EXCAVAT|PLUMBING|PLOMBERIE|ELECTRICAL|ELECTRIQUE|ROOFING|TOITURE|HOMES (INC|LTD)|"
    r"LAW OFFICE|LAW FIRM|STEWART MCKELVEY|COX & PALMER|MCINNES COOPER|MANAGEMENT (INC|LTD|LIMITED)|LIMITED PARTNERSHIP)",
    re.I)
SUPPLIER_DEPTS = {"Transportation and Infrastructure", "General Government", "Finance and Treasury Board",
                  "Service of the Public Debt", "Executive Council Office", "Legislative Assembly"}
# GeoNames place names that are also surnames, ordinary words, counties or regions: never a
# place hit. (Only applies to the "place name inside the recipient" step.)
AMBIGUOUS = {"BURTON", "DOUGLAS", "LINCOLN", "CLAIR", "ALMA", "BATH", "NORTON", "FOREST", "SPRINGFIELD", "RICHMOND", "KINGSTON",
             "WINDSOR", "CENTRAL", "DURHAM", "CAMBRIDGE", "NEWTON", "STANLEY", "BRISTOL", "DRUMMOND", "GORDON", "HAMILTON",
             "GLENWOOD", "RIVERSIDE", "SUMMIT", "PLEASANT", "CANAAN", "BELLEVUE", "FAIRFIELD", "FAIRVIEW", "MOUNTAIN", "VALLEY",
             "MIDLAND", "HILLSIDE", "BAYVIEW", "PARKER", "MORRISON", "WILSON", "HARVEY", "ALBERT", "VICTORIA", "QUEENS", "KINGS",
             "CHARLOTTE", "SUNBURY", "CARLETON", "WESTMORLAND", "GLOUCESTER", "NORTHUMBERLAND", "LAKESIDE", "LAKEVIEW",
             "LAKEVILLE", "WOODLANDS", "OAKLAND", "HIGHLAND", "HIGHLANDS", "MEADOWS", "GREENFIELD", "GREENWOOD", "WESTFIELD",
             "EASTWOOD", "WESTWOOD", "NORTHFIELD", "BEAVER", "MAPLE GROVE", "MAPLE RIDGE", "ORCHARD", "GARDENS", "PORTAGE",
             "CROSSING", "JUNCTION", "HARBOUR", "ISLAND", "SETTLEMENT", "STATION", "LANDING", "CENTRE", "CENTER", "DUFFERIN",
             "COLLINS", "WALKER", "ARMSTRONG", "ANDERSON", "WATSON", "JOHNSON", "JOHNSTON", "CAMPBELL", "MCKENZIE", "MACKENZIE",
             "GRAHAM", "WRIGHT", "MURRAY", "ALLEN", "SCOTT", "YOUNG", "HOWARD", "WALLACE", "MARTIN", "RUSSELL", "MILLER", "CLARK",
             "BAKER", "TAYLOR", "HAYES", "HOLMES", "HOWE", "LEONARD", "LORNE", "ACADIA", "ACADIE", "FUNDY", "EVANGELINE",
             "SAINT MARYS", "SAINT ANNE", "SAINTE ANNE", "SAINT JOSEPH", "SAINT MARTIN", "SAINT PIERRE", "SAINT JEAN",
             "SAINT MARY S", "SAINT PAUL", "SAINT LOUIS", "SAINT CHARLES", "SAINT ANTOINE", "SAINT ANDRE", "SAINT JACQUES",
             "SAINT FRANCOIS", "SAINT JOHN"}
# (lat, lon) for the 2023 amalgamated municipalities and First Nations GeoNames has no entry
# for; keys are normalised names. Approximate: the main settlement of each.
PLACE_ALIASES = {
    "TANTRAMAR": (45.897, -64.368), "HAUTES TERRES": (47.603, -65.050), "CHAMPDORE": (46.370, -64.751),
    "BEAUSOLEIL": (46.330, -64.600), "CAP ACADIE": (46.219, -64.283), "BELLE BAIE": (47.700, -65.713),
    "THREE RIVERS": (45.722, -65.512), "ARCADIA": (46.120, -65.280), "BUTTERNUT VALLEY": (45.843, -65.393),
    "MAPLE HILLS": (45.985, -65.335), "FUNDY ST MARTINS": (45.356, -65.530), "FUNDY SAINT MARTINS": (45.356, -65.530),
    "GRAND LAKE": (46.000, -66.097), "HANWELL": (45.896, -66.777), "NACKAWIC MILLVILLE": (45.994, -67.240),
    "NACKAWIC": (45.994, -67.240), "FUNDY ALBERT": (45.750, -64.730), "STRAIT SHORES": (46.050, -64.080),
    "FIVE RIVERS": (45.935, -65.170), "VALLEY WATERS": (45.633, -65.700), "LAKELAND RIDGES": (45.860, -67.300),
    "CARLETON NORTH": (46.440, -67.620), "EASTERN CHARLOTTE": (45.130, -66.830), "HERON BAY": (48.060, -66.370),
    "BAIE DES HERONS": (48.060, -66.370), "BOIS JOLI": (47.780, -65.720), "NOUVELLE ARCADIE": (46.735, -65.430),
    "ILE DE LAMEQUE": (47.790, -64.650), "HAUT MADAWASKA": (47.260, -68.600), "VALLEE DES RIVIERES": (47.163, -67.925),
    "SUNBURY YORK SOUTH": (45.670, -66.610), "SOUTHWEST MIRAMICHI BAY DU VIN": (46.735, -65.830),
    "NASHWAAK": (46.290, -66.740), "TRACADIE": (47.514, -64.913), "TRACADIE SHEILA": (47.514, -64.913),
    "CAMPOBELLO ISLAND": (44.880, -66.950), "CAMPOBELLO": (44.880, -66.950), "BEAUBASSIN EST": (46.200, -64.390),
    "BEAUBASSIN EAST": (46.200, -64.390), "UPPER MIRAMICHI": (46.460, -66.420), "SAINT ANDREWS": (45.084, -67.057),
    "SAINT STEPHEN": (45.194, -67.280), "SAINT GEORGE": (45.128, -66.829), "GRAND BAY WESTFIELD": (45.336, -66.217),
    "RIVIERE VERTE": (47.320, -68.150), "SAINT LEONARD": (47.163, -67.925), "SAINT ISIDORE": (47.603, -65.050),
    "KEDGWICK": (47.645, -67.343), "SAINT QUENTIN": (47.513, -67.392), "SAINT JOHN": (45.273, -66.063),
    # First Nations (band office locations).
    "ST MARY S": (45.973, -66.633), "SAINT MARY S": (45.973, -66.633), "SITANSISK": (45.973, -66.633),
    "METEPENAGIAG": (46.930, -65.800), "RED BANK": (46.930, -65.800), "MADAWASKA MALISEET": (47.370, -68.350),
    "MADAWASKA": (47.370, -68.350), "OROMOCTO": (45.848, -66.479), "WOODSTOCK": (46.152, -67.601),
    "ESGENOOPETITJ": (47.210, -65.100), "BURNT CHURCH": (47.210, -65.100), "EEL RIVER BAR": (48.050, -66.420),
    "UGPI GANJIG": (48.050, -66.420), "TOBIQUE": (46.790, -67.720), "NEQOTKUK": (46.790, -67.720),
    "KINGSCLEAR": (45.880, -66.900), "BILIJK": (45.880, -66.900), "ELSIPOGTOG": (46.520, -64.950),
    "BIG COVE": (46.520, -64.950), "PABINEAU": (47.550, -65.650), "OINPEGITJOIG": (47.550, -65.650),
    "FORT FOLLY": (45.900, -64.520), "AMLAMGOG": (45.900, -64.520), "EEL GROUND": (47.030, -65.600),
    "NATOAGANEG": (47.030, -65.600), "INDIAN ISLAND": (46.600, -64.780), "L NUI MENIKUK": (46.600, -64.780),
    "BOUCTOUCHE": (46.470, -64.740), "BUCTOUCHE": (46.470, -64.740), "TJIPOGTOTJG": (46.470, -64.740),
    "WELAMUKOTUK": (45.848, -66.479),
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
    return -float(s) if neg else float(s)


def windows():
    """Fiscal year ending -> window, plus the cutoff date, from the files that exist."""
    if (RAW / "nb" / "payments-fy2026.csv").exists():
        return {2026: "after", 2024: "before"}, date(2026, 3, 31), WINDOW_NOTE[2026]
    return {2025: "after", 2024: "before"}, date(2025, 3, 31), WINDOW_NOTE[2025]


def read_rows(wanted):
    """Every payments-fy*.csv present (years outside the windows feed the series only)."""
    rows = []
    other = Counter()
    for path in sorted((RAW / "nb").glob("payments-fy*.csv")):
        fy = int(re.search(r"fy(\d{4})", path.name).group(1))
        window = wanted.get(fy)
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f)
            next(reader)  # bilingual header
            for r in reader:
                if len(r) < 4 or not r[1].strip():
                    continue
                dept = r[0].split(" / ")[0].strip()
                ptype = r[3].split(" / ")[0].strip()
                v = amount(r[2])
                if ptype != "Payments & Grants":
                    if window:
                        other[(window, ptype or "(blank)")] += v
                    continue
                rows.append({"Recipient": r[1].strip(), "Dept": dept, "Amount": v, "fye": fy})
    return rows, other


def main():
    WINDOWS, CUTOFF, window_note = windows()
    divisions = json.load(open(OUT / "divisions.json"))
    geo = json.load(open(OUT / "divisions_geo.json"))
    index = RidingIndex([(f["id"], f["geometry"]) for f in geo["features"]])
    centroids = load_centroids()

    # Name -> postal code sources.
    name_pc = {k[3:]: v for k, v in json.load(open(ROOT / "data" / "name_postal.json")).items() if k.startswith("NB|")}
    with open(RAW / "cra" / "ident_2024.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["Province"] == "NB":
                for nm in (r["Legal Name"], r["Account Name"]):
                    name_pc.setdefault(norm(nm), r["Postal Code"].replace(" ", "").upper())
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            if r[4] == "NB":
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

    def locate_place(key):
        if key in PLACE_ALIASES:
            return index.locate(*PLACE_ALIASES[key])[0]
        pts = places.get(key)
        if not pts:
            return None
        return index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))[0]

    def segments(name):
        """Bilingual 'Ville de Dieppe/City of Dieppe' -> both halves; brackets dropped."""
        base = re.sub(r"\s*\([^)]*\)", " ", name)
        parts = [p.strip() for p in re.split(r"\s*/\s*|_", base) if p.strip()]
        return parts or [name]

    def muni_key(name):
        for seg in segments(name):
            m = MUNI.match(place_norm(seg))
            if m:
                key = re.sub(r"\b(INC|LTD|LTEE)\b.*$", "", m.group(2)).strip()
                if key:
                    return key
            m = MUNI_SUFFIX.match(re.sub(r"\b(INC|LTD|LTEE)\b.*$", "", place_norm(seg)).strip())
            if m:
                return m.group(1)
        # A payee that is nothing but a place name ("Edmundston", "Grand-Sault / Grand Falls")
        # is the municipality itself.
        for seg in segments(name):
            key = place_norm(seg)
            if key in places and len(places[key]) >= 20 or key in PLACE_ALIASES:
                return key
        return None

    def nation_key(name):
        for seg in segments(name):
            m = FIRST_NATION.match(place_norm(seg))
            if m:
                return (m.group(1) or m.group(3)).strip()
        return None

    def place(name):
        """-> (district slug or None, method)."""
        if name in loc_cache:  # keyed by the spelling as written: the rules below read the raw name
            return loc_cache[name]
        n = norm(name)
        res = (None, "unmatched")
        u = upper(name)
        if not n or "WITHHELD" in n or "CONFIDENTIAL" in n:
            res = (None, "withheld")
        elif PERSON.match(u) and not NOT_PERSON.search(u):
            res = (None, "individual")
        elif OUT_OF_PROVINCE.search(u) and not re.search(r"NEW BRUNSWICK|NOUVEAU.BRUNSWICK|\bNB\b", u):
            res = (None, "out-of-province")
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
                    d = locate_place(key) or locate_place(key + " FIRST NATION")
                    if d:
                        res = (d, "municipality")
            if res[0] is None and not re.search(r"\bNEW BRUNSWICK\b|\bNOUVEAU BRUNSWICK\b", n):
                # Every place name inside the recipient's name; the biggest place (most GeoNames
                # postal codes) wins, so "Foyer Saint-Thomas Vallée de Memramcook" goes to
                # Memramcook, not to the hamlet of Saint-Thomas.
                pn = f" {place_norm(name)} "
                hits = [(len(places.get(p, ())) or 50, len(p), p) for p in place_names if f" {p} " in pn]
                hits += [(50, len(p), p) for p in PLACE_ALIASES if len(p) >= 6 and p not in places and f" {p} " in pn]
                for _, _, p in sorted(hits, reverse=True):
                    d = locate_place(p)
                    if d:
                        res = (d, "place name in recipient (approx.)")
                        break
        loc_cache[name] = res
        return res

    def spans_districts(key, limit=60):
        """True when a town (20+ postal codes) has over 15% of its postal-code points outside
        its main district. Villages with a handful of coarse rural centroids never count."""
        pts = places.get(key) or []
        if len(pts) < 20:
            return False
        step = max(1, len(pts) // limit)
        hits = Counter(index.locate(*p)[0] for p in pts[::step])
        hits.pop(None, None)
        return bool(hits) and hits.most_common(1)[0][1] < 0.85 * sum(hits.values())

    multi_division = {}

    def is_supplier(name, dept):
        u = upper(name)
        if STRONG_SUPPLIER.search(u):
            return True
        if dept == "Transportation and Infrastructure" and (INC.search(u) or SUPPLIER_SUFFIX.search(re.sub(r"[^A-Z0-9 ]", " ", u))) \
                and not re.search(r"HOUSING|COMMISSION|FIRST NATION|NATION\b|RURAL COMMUNITY|MUNICIPALIT|VILLAGE|TOWN OF|CITY OF|VILLE DE", u):
            return True
        if NONPROFIT.search(u):
            return False
        if NUMBERED.match(norm(name)) and len(norm(name).split()) <= 4:
            return True
        if INDUSTRY.search(u):
            return True
        if SUPPLIER_SUFFIX.search(re.sub(r"[^A-Z0-9 ]", " ", u)):
            return True
        if INC.search(u) and dept in SUPPLIER_DEPTS:
            return True
        return False

    def flag_for(name, dept):
        """Why a placed payment is left out of the adjusted totals, or ""."""
        u = upper(name)
        if PROVINCEWIDE.search(u):
            return "province-wide"
        key = None if nation_key(name) else muni_key(name)
        if key:
            if key in BIG_CITIES:
                return "other government"
            if key not in multi_division:
                multi_division[key] = spans_districts(key)
            if multi_division[key]:
                return "other government"
            return ""
        if is_supplier(name, dept):
            return "supplier"
        return ""

    rows, other_types = read_rows(WINDOWS)
    series_fyes = sorted({r["fye"] for r in rows})  # every fiscal year read, windows or not
    per = {num: {"after": Counter(), "before": Counter(), "progs": Counter(), "grants": [], "series": Counter()} for num in divisions}
    method_counts = Counter()
    excluded = Counter()
    buckets = Counter()
    flagged_total = Counter()
    unmatched = Counter()
    prog_totals = defaultdict(lambda: defaultdict(float))
    fy_label = {fy: f"FY{fy - 1}-{str(fy)[2:]}" for fy in WINDOWS}
    audit = []  # every row's classification, written to $NB_PLACEMENTS when set (for checking the rules)
    for r in rows:
        v = r["Amount"]
        window = WINDOWS.get(r["fye"])  # None for years outside the windows: placed for the series only
        if v <= 0:
            continue
        program = r["Dept"]
        num, how = place(r["Recipient"])
        if window:
            audit.append([window, r["Dept"], r["Recipient"], round(v), num or "", how,
                          "" if how in ("withheld", "individual", "out-of-province") else flag_for(r["Recipient"], program)])
        if how in ("withheld", "individual", "out-of-province"):
            if window:
                kind = "individuals" if how == "individual" else how
                excluded[(window, kind)] += v
                buckets[(window, kind)] += v
            continue
        flag = flag_for(r["Recipient"], program)
        if num is None:
            kind = {"province-wide": "province-wide bodies", "supplier": "suppliers", "other government": "other governments"}.get(flag, "unmatched")
            if window:
                excluded[(window, kind)] += v
                buckets[(window, flag or "unmatched")] += v
                if window == "after" and kind == "unmatched":
                    unmatched[r["Recipient"]] += v
            continue
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
        else:
            flagged_total[(window, r["Recipient"])] += v
        if window == "after":
            p["progs"][program] += v
            if not flag:
                prog_totals[program][num] += v
            p["grants"].append((v, r, flag, how))

    if os.environ.get("NB_PLACEMENTS"):
        with open(os.environ["NB_PLACEMENTS"], "w", newline="") as f:
            w = csv.writer(f, delimiter="\t")
            w.writerow(["window", "department", "recipient", "amount", "district", "how", "flag"])
            w.writerows(audit)

    out = {}
    for num, dv in divisions.items():
        p = per[num]
        pop = dv["population"] or 1
        a, b = p["after"], p["before"]
        rec = dict(dv)
        by_recipient = defaultdict(lambda: {"v": 0.0, "n": 0, "progs": Counter(), "flag": "", "how": "", "last": ""})
        for v, r, fl, how in p["grants"]:
            g = by_recipient[r["Recipient"]]
            g["v"] += v
            g["n"] += 1
            g["progs"][r["Dept"]] += v
            g["flag"], g["how"], g["last"] = fl, how, fy_label[r["fye"]]
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
        "population_basis": next(iter(divisions.values())).get("population_basis", ""),
        "close_margin": CLOSE_MARGIN, "median_pc_after": med,
        "series": {"kind": "fiscal year", "labels": [f"{fye - 1}-{str(fye)[2:]}" for fye in series_fyes], "complete": len(series_fyes),
                   "election_index": max([i for i, fye in enumerate(series_fyes) if date(fye, 3, 31) < ELECTION], default=-1)},
        "methods": {f"{w}|{m}": v for (w, m), v in method_counts.items()},
        "excluded_after": {m: round(v) for (w, m), v in excluded.items() if w == "after"},
        "buckets_after": {m: round(v) for (w, m), v in sorted(buckets.items(), key=lambda kv: -kv[1]) if w == "after"},
        "other_payment_types_after": {m: round(v) for (w, m), v in other_types.items() if w == "after"},
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
