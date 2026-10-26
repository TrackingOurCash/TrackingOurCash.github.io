"""Inline data and shapes into the self-contained HTML pages.

  output/riding_spending_map.html   federal ridings (also output/artifact.html, the bare fragment)
  output/alberta.html               Alberta electoral divisions, when data/ab exists
plus CSV exports of each table.
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUTDIR = ROOT / "output"

NAV = [{"href": "index.html", "label": "Federal ridings"}, {"href": "alberta.html", "label": "Alberta"}, {"href": "bc.html", "label": "British Columbia"},
       {"href": "saskatchewan.html", "label": "Saskatchewan"}, {"href": "manitoba.html", "label": "Manitoba"}, {"href": "nb.html", "label": "New Brunswick"}]
# The published Claude pages live at fixed links; the website uses relative ones.
ARTIFACT_URLS = {"index.html": "https://claude.ai/artifact/J6Va83R2P7m4HKErD6KXgM", "alberta.html": "https://claude.ai/artifact/HniakFetDdXzVWcveb9zy9",
                 "bc.html": "https://claude.ai/artifact/1BU8kCqcxVtwsJpjAnXS7s", "saskatchewan.html": "https://claude.ai/artifact/P8kMKchyth4j5ykhcSXug6",
                 "legislatures.html": "https://claude.ai/artifact/45zE2pwEjXbZ3Wd2Zxib4p", "manitoba.html": "https://claude.ai/artifact/PmTjRxsid59XiGgJgPVmiv",
                 "nb.html": "https://claude.ai/artifact/6srrgUF4eD9A4JLfb9gB4R"}

COMMON = ["population", "margin_pts", "margin_votes", "after_total", "after_n", "after_adj", "after_adj_n",
          "before_adj", "before_total", "pc_after", "pc_after_all", "pc_before", "change_pct", "score", "close",
          "group", "top_grants"]


def links(items):
    return "; ".join(f'<a href="{u}" target="_blank" rel="noopener">{t}</a>' for t, u in items) + "."


def wiki(level):
    path = DATA / "wikipedia_links.json"
    return json.load(open(path)).get(level, {}) if path.exists() else {}


def pop_label():
    path = DATA / "population_scale.json"
    if not path.exists():
        return "2021 census", None
    d = json.load(open(path))
    y, m = d["latest_date"][:7].split("-")
    month = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][int(m) - 1]
    return f"est. {month} {y}", f"{month} {y}"


def fmt_money(v):
    return "$" + (f"{v / 1e9:.1f}B" if v >= 1e9 else f"{v / 1e6:.0f}M" if v >= 1e6 else f"{v:,.0f}")


def federal():
    sp = json.load(open(DATA / "riding_spending.json"))
    m = sp["meta"]
    # News coverage found once per grant by the research step (scripts/merge_news.py); keyed "owner_org|ref_number".
    news = json.load(open(DATA / "news_links.json")) if (DATA / "news_links.json").exists() else {}
    wk = wiki("federal")
    pw = json.load(open(DATA / "poliwave_links.json")) if (DATA / "poliwave_links.json").exists() else {}
    mth = m["methods"]
    placed = sum(v for k, v in mth.items() if k.startswith("after|") and "unmapped" not in k)
    ridings = {}
    for n, r in sp["ridings"].items():
        rec = {k: r[k] for k in COMMON}
        rec["wiki"] = (wk.get(n) or {}).get("url")
        rec["poliwave"] = pw.get(n)
        rec["top_grants"] = [dict(g, news=news.get(f'{g["org"]}|{g["ref"]}')) if f'{g["org"]}|{g["ref"]}' in news else g for g in r["top_grants"]]
        rec.update({"num": n, "name": r["current_name"], "region": r["province"], "party_won": r["party_2025"],
                    "runnerup_party": r["runnerup_party_2025"], "winner": r["winner_2025"], "runnerup": r["runnerup_2025"],
                    "shares": r["shares_2025"], "rep": r["mp"], "rep_party": r["mp_party"], "top_progs": r["top_depts"]})
        ridings[n] = rec
    config = {
        "title": "Where federal grants went after the 2025 election",
        "nav": [dict(x, current=x["href"] == "index.html") for x in NAV],
        "level": "riding", "levelPlural": "ridings", "levelTitle": "Riding", "region": "province", "regionTitle": "Prov.",
        "rep": "MP", "electionYear": "2025", "popLabel": pop_label()[0],
        "spendsUrl": "https://canadaspends.com/en/federal/spending",
        "parties": {"LPC": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"}, "CPC": {"name": "Conservative", "light": "#1b4c9e", "dark": "#4f80d8"},
                    "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"}, "BQ": {"name": "Bloc Québécois", "light": "#1aa7bd", "dark": "#3fc0d4"},
                    "GPC": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"}, "PPC": {"name": "PPC", "light": "#4b2e83", "dark": "#8a6bc8"},
                    "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["LPC", "CPC", "BQ", "NDP", "GPC"],
        "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
        "filterAll": "All departments", "filterOptions": m["departments"],
        "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
        "groupTitle": "Does money follow close seats?", "groups": ["Close Liberal", "Close opposition", "Safe Liberal", "Safe opposition"],
        "groupNote": f'"Close" means the 2025 winner led by under {m["close_margin"]} points; "Liberal" means the Liberals won the seat in 2025.',
        "groupParty": {"Close Liberal": "LPC", "Safe Liberal": "LPC", "Close opposition": None, "Safe opposition": None},
        "regionOrder": ["Territories", "Newfoundland and Labrador", "Prince Edward Island", "Nova Scotia", "New Brunswick", "Quebec", "Ontario",
                        "Manitoba", "Saskatchewan", "Alberta", "British Columbia"],
        "regionGroup": {"Yukon": "Territories", "Northwest Territories": "Territories", "Nunavut": "Territories"},
        "regionShort": {"Territories": "North", "Newfoundland and Labrador": "NL", "Prince Edward Island": "PE", "Nova Scotia": "NS", "New Brunswick": "NB",
                        "Quebec": "QC", "Ontario": "ON", "Manitoba": "MB", "Saskatchewan": "SK", "Alberta": "AB", "British Columbia": "BC"},
        "beforeLabel": "Same dates a year earlier", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest grants since the election",
        "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
        "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
        "linkNote": "Links open the government's own record of each award on open.canada.ca.",
        "projection": {"parallels": [49, 77], "rotate": [96, 0]},
        "insets": [["Vancouver", [-123.35, 49.0, -122.45, 49.42]], ["Victoria", [-123.75, 48.35, -123.25, 48.7]], ["Calgary", [-114.35, 50.85, -113.85, 51.22]],
                   ["Edmonton", [-113.75, 53.38, -113.25, 53.7]], ["Winnipeg", [-97.4, 49.72, -96.95, 50.0]], ["Toronto & GTA", [-79.85, 43.5, -79.0, 43.95]],
                   ["Hamilton–Niagara", [-80.2, 43.0, -79.0, 43.45]], ["Kitchener–Waterloo", [-80.7, 43.3, -80.2, 43.6]], ["London", [-81.4, 42.85, -81.1, 43.1]],
                   ["Ottawa–Gatineau", [-76.05, 45.2, -75.4, 45.6]], ["Montréal", [-74.05, 45.38, -73.4, 45.75]], ["Québec", [-71.55, 46.68, -71.1, 46.98]],
                   ["Halifax", [-63.85, 44.55, -63.4, 44.85]], ["St. John's", [-53.0, 47.4, -52.6, 47.65]]],
        "subtitle": (f"Federal grants and contributions with agreements starting {m['election']} (election day) to {m['cutoff']}, placed in the 343 ridings "
                     f"and set against the 2025 result. Each riding wears its current MP's party colour; the deeper the colour, the more grant money per resident. "
                     f"\"Before\" means the same dates one year earlier."),
        "notes": [
            "<b>Sources:</b> " + links([
                ("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                ("Elections Canada official 2025 results, tables 11 and 12", "https://www.elections.ca/res/rep/off/ovrGE45/home.html"),
                ("House of Commons member list", "https://www.ourcommons.ca/Members/en/search"),
                ("Riding boundaries (Represent, Open North)", "https://represent.opennorth.ca/boundary-sets/federal-electoral-districts-2023-representation-order/"),
                ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                ("Census subdivisions (municipal boundaries, via Represent)", "https://represent.opennorth.ca/boundary-sets/census-subdivisions/"),
                ("Wikipedia (riding articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Canadian_federal_electoral_districts"),
                ("Poliwave riding projections (linked from each panel)", "https://www.poliwave.com/ca/fed/projection/ridings"),
            ]) + f" Data as of {m.get('generated', m['cutoff'])}. Code: the pipeline is open and rebuilds the page daily.",
            f"<b>Where money lands:</b> each award is placed at the recipient's address, not where the money is spent. The dataset's own riding field is rarely filled in, so most of the {placed:,} awards since the election were placed by postal code; recipients with no postal code were matched to their address on other awards, then by city. {mth.get('after|unmapped', 0):,} awards worth {fmt_money(mth.get('after|unmapped $', 0))} are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office (\"Hockey Canada\"), other governments (provinces, cities spread over several ridings), treaty and specific-claim settlements, and foreign aid routed through Canadian partners. Tick the box to put them back. Companies are kept even when \"Canada\" is in their name.",
            f"<b>Amendments</b> are counted once, at the agreement's latest total value. <b>Reporting lag:</b> departments report quarterly, so the window ends at the last quarter that looks fully reported ({m['cutoff']}).",
            f"<b>Population:</b> per-person figures use an estimate for {pop_label()[1]}: each riding's 2021 census count scaled by its province's growth since the census, from Statistics Canada's quarterly estimates (table 17-10-0009-01, the figures behind the population clock). Growth is assumed even within a province, so fast-growing suburbs are still somewhat undercounted.",
            "<b>Party is correlation, not credit:</b> ministers and departments approve grants, not local MPs. A pattern by seat type is a signal worth checking, not proof of intent.",
            "<b>News links:</b> for each riding's largest grant, every grant of $10 million or more, and the top three in close seats, a web search looked for one mainstream outlet (CBC, Global, CTV, Postmedia, Torstar, La Presse and the like) and one independent outlet (Juno, Rebel, Western Standard, The Tyee, National Observer, iPolitics and others) reporting that funding. Links are kept with the data and refreshed only for new grants. \"No coverage found\" means the search found nothing that clearly matched; smaller grants were not searched.",
        ],
    }
    budget = json.load(open(DATA / "budget_by_riding.json")) if (DATA / "budget_by_riding.json").exists() else None
    if budget:
        config["notes"].insert(1, "<b>Budget commitments:</b> the dots and the panel's \"Budget commitments\" list come from reading "
                               + " and ".join(f'<a href="{d["url"]}" target="_blank" rel="noopener">{d["name"]}</a>' for d in budget["documents"])
                               + " for every measure that names a place, then locating that place in a riding. Budgets name few places: most measures are national programs, "
                               "and the money reaches ridings later through departmental grants, which is what the map colours show. "
                               f"Items with no amount are projects the budget names without a dollar figure. {budget['next']}")
    config["legislatureInGrid"] = True  # the federal inset grid has room for it
    payload = {"config": config, "meta": m, "groups": sp["groups"], "ridings": ridings, "dept": sp["dept_by_riding"], "budget": budget,
               "legislature": legislature_for("Canada"),
               "deptBefore": sp["dept_by_riding_before"], "geo": json.load(open(DATA / "ridings_geo.json")), "land": json.load(open(DATA / "land_geo.json")),
               "geoFine": json.load(open(DATA / "ridings_geo_fine.json")) if (DATA / "ridings_geo_fine.json").exists() else {"features": []}}
    return payload, sp["ridings"]


PROVINCES = {
    "alberta": {
        "dir": "ab", "year": "2023", "region": "Alberta", "spendsUrl": "https://canadaspends.com/en/provincial/alberta", "title": "Where Alberta's grants went after the 2023 election",
        "electionLabel": "the 29 May 2023 election", "count": 87, "gov": "UCP",
        "parties": {"UCP": {"name": "United Conservative", "light": "#1b4c9e", "dark": "#4f80d8"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "AP": {"name": "Alberta Party", "light": "#5a9bd5", "dark": "#7fb3e6"}, "GPA": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"},
                    "PTP": {"name": "Progressive", "light": "#6a4c93", "dark": "#9b7fc4"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["UCP", "NDP", "PTP"], "opp": "NDP",
        "groupNote": '"UCP" means the governing United Conservatives won the seat in 2023.',
        "filterAll": "All programs", "topProgsTitle": "Top programs", "beforeLabel": "Same length of time before the election",
        "includeLabel": "Include province-wide bodies (health, post-secondary, school divisions) & big-city governments",
        "projection": {"parallels": [50, 58], "rotate": [114.5, 0]},
        "insets": [["Calgary", [-114.35, 50.85, -113.85, 51.22]], ["Edmonton", [-113.75, 53.38, -113.25, 53.7]], ["Red Deer", [-113.9, 52.2, -113.7, 52.35]],
                   ["Lethbridge", [-112.95, 49.62, -112.75, 49.75]], ["Fort McMurray", [-111.5, 56.65, -111.3, 56.78]], ["Grande Prairie", [-118.9, 55.12, -118.7, 55.22]]],
        "source": "Alberta Treasury Board and Finance grant payments disclosure (open.alberta.ca/dataset/grant-disclosure), which lists every payment by recipient, program and date.",
        "windowNote": "\"Before\" is the same length of time ending on election day",
        "placing": "Alberta publishes recipient names but no addresses. Each recipient was matched by name to a postal code in the federal grants file or the CRA charity list, to a municipality, or to a place name inside its own name, then located in a division.",
        "individualNote": "programs that pay individuals (physician fees, AISH, benefits, awards)",
        "leftOut": "province-wide bodies booked at a head office (Alberta Health Services, universities and colleges, school divisions, agencies) and the governments of cities that span several divisions (Calgary, Edmonton and others)",
        "boundaryNote": "the 87 divisions used in 2023. Alberta's next election will use a new map that is not final yet.",
        "sources": [("Alberta grant payments disclosure (Treasury Board and Finance)", "https://open.alberta.ca/dataset/grant-disclosure"),
                    ("Elections Alberta 2023 Statement of Vote", "https://www.elections.ab.ca/uploads/2023-Provincial-General-Election-Statement-of-Vote.xlsx"),
                    ("Legislative Assembly of Alberta member list", "https://www.assembly.ab.ca/members/members-of-the-legislative-assembly"),
                    ("2021 census profiles by electoral division", "https://open.alberta.ca/dataset/330635ba-632a-4ad1-a9f6-b8176216cf07"),
                    ("Division boundaries, 2019 map (Represent, Open North)", "https://represent.opennorth.ca/boundary-sets/alberta-electoral-districts-2017/"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (division articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Alberta_provincial_electoral_districts")],
    },
    "bc": {
        "dir": "bc", "year": "2024", "region": "British Columbia", "spendsUrl": "https://canadaspends.com/en/provincial/british-columbia", "title": "Where BC's transfers went after the 2024 election",
        "electionLabel": "the 19 October 2024 election", "count": 93, "gov": "NDP",
        "parties": {"NDP": {"name": "BC NDP", "light": "#f37021", "dark": "#f68a45"}, "BCC": {"name": "Conservative", "light": "#1b4c9e", "dark": "#4f80d8"},
                    "GPBC": {"name": "BC Green", "light": "#3d9b35", "dark": "#5cb954"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["NDP", "BCC", "GPBC"], "opp": "BCC",
        "groupNote": '"NDP" means the governing BC NDP won the seat in 2024. BC voted again on 24 October 2026; those results are final on 18 November 2026 and the MLAs shown are the 2024 winners until then.',
        "filterAll": "All ministries", "topProgsTitle": "Top ministries", "beforeLabel": "Fiscal year before the election (to March 2024)",
        "includeLabel": "Include province-wide bodies (health authorities, Crown corporations, universities, school districts) & big-city governments",
        "projection": {"parallels": [49, 55], "rotate": [124, 0]},
        "insets": [["Vancouver", [-123.35, 49.0, -122.45, 49.42]], ["Victoria", [-123.75, 48.35, -123.25, 48.7]], ["Kelowna", [-119.65, 49.75, -119.3, 50.0]],
                   ["Nanaimo", [-124.1, 49.1, -123.85, 49.3]], ["Kamloops", [-120.5, 50.6, -120.2, 50.75]], ["Prince George", [-122.9, 53.85, -122.65, 54.0]]],
        "source": "BC Public Accounts, Consolidated Revenue Fund detailed schedule of government transfers (payees of $25,000 or more, by ministry and fiscal year; no dates or programs are published).",
        "windowNote": "\"After\" is the fiscal year to March 2026, the first full year after the election; \"before\" is the year to March 2024",
        "placing": "BC publishes payee names but no addresses, and only payees of $25,000 or more. Each recipient was matched by name to a postal code in the federal grants file or the CRA charity list, to a municipality or band, or to a place name inside its own name, then located in a district.",
        "individualNote": "programs that pay individuals (medical claims, PharmaCare, income assistance, child care, seniors' supplements)",
        "leftOut": "province-wide bodies booked at a head office (health authorities, BC Housing, BC Hydro, universities, school districts, regional districts) and the governments of cities that span several districts (Vancouver, Surrey, Burnaby and others)",
        "boundaryNote": "the 93 districts of the 2023 redistribution, used in 2024 and again on 24 October 2026.",
        "sources": [("BC Public Accounts: government transfers by payee (BC Data Catalogue)", "https://catalogue.data.gov.bc.ca/dataset/crf-detailed-schedules-of-payments-government-transfers"),
                    ("Elections BC provincial voting results by voting place", "https://catalogue.data.gov.bc.ca/dataset/44914a35-de9a-4830-ac48-870001ef8935"),
                    ("Electoral district boundaries, 2023 redistribution (BC Data Catalogue)", "https://catalogue.data.gov.bc.ca/dataset/provincial-electoral-districts-electoral-boundaries-redistribution-2023"),
                    ("BC Stats 2021 census profiles by electoral district", "https://catalogue.data.gov.bc.ca/dataset/da0326f2-2191-4345-84d3-d14cd6ee76eb"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_British_Columbia_provincial_electoral_districts")],
    },
    "saskatchewan": {
        "dir": "sk", "year": "2024", "region": "Saskatchewan", "title": "Where Saskatchewan's transfers went after the 2024 election",
        "electionLabel": "the 28 October 2024 election", "count": 61, "gov": "SP",
        "parties": {"SP": {"name": "Saskatchewan Party", "light": "#1b7a3e", "dark": "#3fae63"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "SUP": {"name": "Sask United", "light": "#1b4c9e", "dark": "#4f80d8"}, "BPSK": {"name": "Buffalo Party", "light": "#8b5a2b", "dark": "#c0894f"},
                    "SGP": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"}, "PC": {"name": "Progressive Conservative", "light": "#5a9bd5", "dark": "#7fb3e6"},
                    "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["SP", "NDP", "IND"], "opp": "NDP",
        "groupNote": '"SP" means the governing Saskatchewan Party won the seat in 2024.',
        "filterAll": "All programs", "topProgsTitle": "Top programs", "beforeLabel": "Fiscal year before (2023-24)",
        "includeLabel": "Include province-wide bodies (health authority, universities, school divisions, Crown corporations) & Regina and Saskatoon city governments",
        "projection": {"parallels": [49, 60], "rotate": [106, 0]},
        "insets": [["Regina", [-104.75, 50.38, -104.5, 50.52]], ["Saskatoon", [-106.8, 52.05, -106.5, 52.22]], ["Prince Albert", [-105.85, 53.15, -105.65, 53.25]],
                   ["Moose Jaw", [-105.6, 50.36, -105.48, 50.44]]],
        "source": "Saskatchewan Public Accounts, Volume 2 (transfers of $50,000 or more by ministry, program and recipient; a PDF, parsed by this project's own extractor).",
        "windowNote": "The 2025-26 Public Accounts are not published yet, so \"after\" is fiscal 2024-25, which straddles the election (seven months before it, five after), and \"before\" is fiscal 2023-24; the page switches to 2025-26 automatically when that volume appears",
        "placing": "Saskatchewan publishes recipient names but no addresses, and only transfers of $50,000 or more, inside a PDF. The extractor recovered 92% of the dollars in the 2024-25 Volume 2 (the rest is mostly physician payments and transfers under $50,000 that the volume does not itemise). Each recipient was then matched by name to a postal code in the federal grants file or the CRA charity list, to a municipality, or to a place name inside its own name, and located in a constituency.",
        "individualNote": "programs that pay individuals (crop insurance, income assistance, physician services, the drug plan, student aid)",
        "leftOut": "province-wide bodies booked at a head office (the Saskatchewan Health Authority, universities, Sask Polytechnic, school divisions, Crown corporations) and the governments of Regina and Saskatoon, which span several constituencies",
        "boundaryNote": "the 61 constituencies of the 2022 commission, used in 2024. No census population exists for these constituencies, so \"per person\" here means per registered voter at the 2024 election (818,996 in all).",
        "sources": [("Saskatchewan Public Accounts, Volume 2 (2024-25)", "https://www.saskatchewan.ca/-/media/news-release-backgrounders/2025/oct/2024-25-volume-2---5155.pdf"),
                    ("Elections Saskatchewan 2024 poll-by-poll results", "https://cdn.elections.sk.ca/upload/2024-GE-POLL-BY-POLL-RESULTS-v1.0.csv"),
                    ("Elections Saskatchewan constituency boundaries (2022 commission)", "https://www.elections.sk.ca/candidates-political-parties/maps/"),
                    ("Legislative Assembly of Saskatchewan member list", "https://www.legassembly.sk.ca/mlas/mla-contact-information/"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (constituency articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Saskatchewan_provincial_electoral_districts")],
    },
    "manitoba": {
        "dir": "mb", "year": "2023", "region": "Manitoba", "title": "Where Manitoba's payments went after the 2023 election",
        "electionLabel": "the 3 October 2023 election", "count": 57, "gov": "NDP",
        "parties": {"NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"}, "PC": {"name": "Progressive Conservative", "light": "#1b4c9e", "dark": "#4f80d8"},
                    "LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"}, "GPM": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"},
                    "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["NDP", "PC", "LIB"], "opp": "PC",
        "groupNote": '"NDP" means the governing New Democrats won the seat in 2023.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "beforeLabel": "Last full year before the election (2022-23)",
        "includeLabel": "Include province-wide bodies (health authorities, Hydro, universities, school divisions) & the Winnipeg and Brandon city governments",
        "projection": {"parallels": [50, 58], "rotate": [97.5, 0]},
        "insets": [["Winnipeg", [-97.4, 49.72, -96.95, 50.0]], ["Brandon", [-100.05, 49.78, -99.85, 49.9]]],
        "source": "Manitoba Public Accounts, \"Vendor Payments over $50,000\" (payees of $50,000 or more by department and fiscal year; grants and purchases are mixed; the town is printed for payees outside Winnipeg).",
        "windowNote": "\"After\" is fiscal 2025-26, the latest year published; \"before\" is fiscal 2022-23, the last full year before the election",
        "placing": "Manitoba prints the payee's town for everyone outside Winnipeg, so those payees are placed by their town. Winnipeg payees were matched by name to a postal code in the federal grants file or the CRA charity list, then located in a division. Public debt charges are left out altogether, and obvious suppliers of goods and services (contractors, consultants, software, pharmacies) are flagged and excluded from the default view because the list mixes them with grants.",
        "individualNote": "pensions, tax credits and programs that pay individuals (income assistance, child-care providers, physicians)",
        "leftOut": "province-wide bodies booked at a head office (the regional health authorities, Shared Health, Manitoba Hydro, universities, school divisions, child and family services authorities), the governments of Winnipeg and Brandon, and suppliers of goods and services",
        "boundaryNote": "the 57 divisions of the 2018 commission, used in 2019 and 2023. Their populations come from the 2016 census (the commission's figures), scaled to Statistics Canada's July 2026 estimate for Manitoba.",
        "sources": [("Manitoba Public Accounts: vendor payments over $50,000", "https://www.gov.mb.ca/government/finances/annualreports-publicaccounts.html"),
                    ("Elections Manitoba 2023 results", "https://www.electionsmanitoba.ca/en/Results/PreviousElections/2023"),
                    ("Legislative Assembly of Manitoba member list", "https://www.gov.mb.ca/legislature/members/mla_list_constituency.html"),
                    ("2018 Electoral Divisions Boundaries Commission report (populations)", "https://www.boundariescommission.mb.ca/wp-content/uploads/edbc-final-report-2018-en.pdf"),
                    ("Division boundaries (Represent, Open North)", "https://represent.opennorth.ca/boundary-sets/manitoba-electoral-districts-2018/"),
                    ("Canadian Geographical Names Database (towns)", "https://natural-resources.canada.ca/maps-tools-publications/maps/geographical-names-canada"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (division articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Manitoba_provincial_electoral_districts")],
    },
    "nb": {
        "dir": "nb", "year": "2024", "region": "New Brunswick", "title": "Where New Brunswick's payments went around the 2024 election",
        "electionLabel": "the 21 October 2024 election", "count": 49, "gov": "LIB",
        "parties": {"LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"}, "PC": {"name": "Progressive Conservative", "light": "#1b4c9e", "dark": "#4f80d8"},
                    "GRN": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "PANB": {"name": "People's Alliance", "light": "#6a4c93", "dark": "#9b7fc4"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["LIB", "PC", "GRN"], "opp": "PC",
        "groupNote": '"LIB" means the governing Liberals won the seat in 2024.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "beforeLabel": "Fiscal year before the election (2023-24)",
        "includeLabel": "Include province-wide bodies (Horizon and Vitalité, NB Power, universities, school districts) & multi-district city governments",
        "projection": {"parallels": [45, 48], "rotate": [66.5, 0]},
        "insets": [["Moncton", [-64.9, 46.03, -64.65, 46.17]], ["Saint John", [-66.2, 45.2, -65.95, 45.35]], ["Fredericton", [-66.75, 45.88, -66.55, 46.0]]],
        "source": "New Brunswick Public Accounts, \"Supplier and Grant Payments by Department\" (open data; payees of $25,000 or more; grants and purchases share one list).",
        "windowNote": "The year to March 2026 is published in December, so \"after\" is fiscal 2024-25, which straddles the election (seven months before it, five after), and \"before\" is fiscal 2023-24; the page switches to 2025-26 automatically when it appears",
        "placing": "New Brunswick publishes payee names only. Each was matched by name to a postal code in the federal grants file or the CRA charity list, to a municipality or First Nation, or to a place name inside its own name, then located in a district. Obvious suppliers of goods and services are flagged and excluded from the default view because the list mixes them with grants.",
        "individualNote": "payments to individuals",
        "leftOut": "province-wide bodies booked at a head office (the Horizon and Vitalité health networks, NB Power, universities, school districts, regional service commissions), the governments of cities that span several districts, suppliers of goods and services, and payments to bodies outside the province",
        "boundaryNote": "the 49 districts of the 2023 commission, used in 2024. No census population exists for them, so \"per person\" here means per elector as estimated by the boundary commission, scaled to Statistics Canada's July 2026 estimate for New Brunswick.",
        "sources": [("New Brunswick Public Accounts: supplier and grant payments by department (open data)", "https://gnb.socrata.com/stories/s/kntu-qzem"),
                    ("Elections New Brunswick 2024 results", "https://www.electionsnb.ca/content/enb/en/resources/publications/election-results.html"),
                    ("Legislative Assembly of New Brunswick member list", "https://www.legnb.ca/en/members/current"),
                    ("Electoral Boundaries and Representation Commission report (electors)", "https://www2.gnb.ca/content/gnb/en/corporate/promo/boundaries-representation-commission.html"),
                    ("District boundaries (Represent, Open North)", "https://represent.opennorth.ca/boundary-sets/new-brunswick-electoral-districts-2024/"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_New_Brunswick_provincial_electoral_districts")],
    },
}


LEVEL = {"alberta": ("division", "divisions"), "bc": ("district", "districts"), "saskatchewan": ("constituency", "constituencies"),
         "manitoba": ("division", "divisions"), "nb": ("district", "districts")}


def provincial(key):
    P = PROVINCES[key]
    y = P["year"]
    sp = json.load(open(DATA / P["dir"] / "division_spending.json"))
    m = sp["meta"]
    ex = m["excluded_after"]
    wk = wiki(key)
    ridings = {}
    for n, r in sp["ridings"].items():
        rec = {k: r[k] for k in COMMON}
        rec["wiki"] = (wk.get(n) or {}).get("url")
        rec.update({"num": n, "name": r["name"], "region": P["region"], "party_won": r[f"party_{y}"], "runnerup_party": r[f"runnerup_party_{y}"],
                    "winner": r[f"winner_{y}"], "runnerup": r[f"runnerup_{y}"], "shares": r[f"shares_{y}"], "rep": r["mla"],
                    "rep_party": r["mla_party"], "top_progs": r["top_progs"]})
        ridings[n] = rec
    land = json.load(open(DATA / "land_geo.json"))
    gov, opp = P["gov"], P["opp"]
    config = {
        "title": P["title"],
        "nav": [dict(x, current=x["href"] == f"{key}.html") for x in NAV],
        "level": LEVEL[key][0], "levelPlural": LEVEL[key][1], "levelTitle": LEVEL[key][0].capitalize(), "region": "province", "regionTitle": "Prov.",
        "rep": "MLA", "electionYear": y, "spendsUrl": P.get("spendsUrl"), "popLabel": "registered voters, 2024" if key == "saskatchewan" else ("electors, est. " + pop_label()[1]) if key == "nb" else pop_label()[0],
        "parties": P["parties"], "legendParties": P["legendParties"],
        "flags": {"province-wide": "province-wide body", "other government": "other government", "supplier": "supplier, not a grant", "winnipeg (approx.)": "Winnipeg, location approx."},
        "filterAll": P["filterAll"], "filterOptions": m["programs"],
        "includeLabel": P["includeLabel"],
        "groupTitle": "Does money follow close seats?", "groups": [f"Close {gov}", f"Close {opp}", f"Safe {gov}", f"Safe {opp}"],
        "groupNote": f'"Close" means the {y} winner led by under {m["close_margin"]} points; ' + P["groupNote"],
        "groupParty": {f"Close {gov}": gov, f"Safe {gov}": gov, f"Close {opp}": opp, f"Safe {opp}": opp},
        "regionOrder": None, "regionGroup": {}, "regionShort": {},
        "beforeLabel": P["beforeLabel"], "topProgsTitle": P["topProgsTitle"], "topGrantsTitle": "Largest recipients since the election",
        "recordUrl": None, "searchUrl": None, "searchLabel": "",
        "linkNote": "Source: " + P["source"],
        "projection": P["projection"], "insets": P["insets"],
        "subtitle": (f"{P['region']} government payments from {P['electionLabel']} to {m['cutoff']}, placed in the {P['count']} electoral "
                     f"{LEVEL[key][1]} and set against the {y} result. Each one wears its current MLA's party colour; "
                     f"the deeper the colour, the more money per resident. {P['windowNote']} ({m['before_start']} to {m['before_end']})."),
        "notes": [
            "<b>Sources:</b> " + links(P["sources"]) + f" Data as of {m.get('generated', m['cutoff'])}.",
            f"<b>Placing payments:</b> {P['placing']} Of {fmt_money(m['total_after'])} paid in the \"after\" window, {fmt_money(m['placed_after'])} was placed; "
            f"{fmt_money(ex.get('individual programs', 0))} went through {P['individualNote']}, {fmt_money(ex.get('individuals', 0))} to recipients who look like individuals, "
            f"{fmt_money(ex.get('province-wide bodies', 0))} to province-wide bodies with no match, "
            + (f"{fmt_money(ex.get('suppliers', 0))} to suppliers of goods and services, " if ex.get('suppliers') else "")
            + (f"{fmt_money(ex.get('out-of-province', 0))} to bodies outside the province, " if ex.get('out-of-province') else "")
            + f"and {fmt_money(ex.get('unmatched', 0))} could not be matched.",
            f"<b>Left out by default:</b> {P['leftOut']}. Tick the box to put them back.",
            f"<b>Boundaries:</b> {P['boundaryNote']}",
            ("<b>Population:</b> no census count exists for these constituencies, so per-person figures are per registered voter at the 2024 election." if key == "saskatchewan" else
             f"<b>Population:</b> no census count exists for these districts, so per-person figures use the boundary commission's estimated electors per district, scaled to Statistics Canada's {pop_label()[1]} estimate for New Brunswick." if key == "nb" else
             f"<b>Population:</b> per-person figures use an estimate for {pop_label()[1]}: the boundary commission's 2016 census count for each division, scaled by Manitoba's growth since then from Statistics Canada's quarterly estimates (table 17-10-0009-01). Growth is assumed even within the province." if key == "manitoba" else
             f"<b>Population:</b> per-person figures use an estimate for {pop_label()[1]}: each {LEVEL[key][0]}'s 2021 census count scaled by {P['region']}'s growth since the census, from Statistics Canada's quarterly estimates (table 17-10-0009-01). Growth is assumed even within the province."),
            "<b>Party is correlation, not credit:</b> ministers and departments approve grants, not local MLAs. A pattern by seat type is a signal worth checking, not proof of intent.",
        ],
    }
    fine = DATA / P["dir"] / "divisions_geo_fine.json"
    config["legislatureInGrid"] = False  # provinces: below the city insets
    payload = {"config": config, "meta": m, "groups": sp["groups"], "ridings": ridings, "dept": sp["prog_by_riding"], "deptBefore": {},
               "legislature": legislature_for(P["region"]),
               "geo": json.load(open(DATA / P["dir"] / "divisions_geo.json")), "land": land,
               "geoFine": json.load(open(fine)) if fine.exists() else {"features": []}}
    return payload, sp["ridings"], y


def render(payload, nav_urls=None):
    tpl = (ROOT / "scripts" / "map_template.html").read_text()
    if nav_urls:
        payload = dict(payload, config=dict(payload["config"], nav=[dict(n, href=nav_urls.get(n["href"], n["href"])) for n in payload["config"]["nav"]]))
    return tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def write_page(payload, name):
    html = render(payload)
    if name != "index":
        html = html.replace("<title>Riding Spending Map</title>", f"<title>{payload['config']['title']}</title>", 1)
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + html.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1) + "</body>\n</html>\n")
    out = OUTDIR / (("riding_spending_map" if name == "index" else name) + ".html")
    out.write_text(full)
    if name == "index":
        (OUTDIR / "index.html").write_text(full)  # the nav links point here, on the website and when opened locally
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")
    fragment = render(payload, ARTIFACT_URLS)
    return fragment if name == "index" else fragment.replace("<title>Riding Spending Map</title>", f"<title>{payload['config']['title']}</title>", 1)


def write_csv(rows, cols, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(rows.values(), key=lambda r: -r["pc_after"]):
            w.writerow([r.get(c) for c in cols])


def legislatures():
    """The legislatures-at-a-glance page from data/legislatures.json."""
    src = DATA / "legislatures.json"
    if not src.exists():
        return
    d = json.load(open(src))
    tpl = (ROOT / "scripts" / "legislatures_template.html").read_text()

    def page(nav_urls):
        nav = [dict(n, href=(nav_urls or {}).get(n["href"], n["href"]), current=n["href"] == "legislatures.html") for n in NAV]
        payload = dict(d, config={"nav": nav})
        return tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))

    html = page(None)
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + html.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1) + "</body>\n</html>\n")
    (OUTDIR / "legislatures.html").write_text(full)
    (OUTDIR / "artifact_legislatures.html").write_text(page(ARTIFACT_URLS))
    print(OUTDIR / "legislatures.html", f"{len(full) / 1e6:.2f} MB")


def legislature_for(name):
    """The jurisdiction's record from data/legislatures.json (standings, leaders, dates, budget), or None."""
    src = DATA / "legislatures.json"
    if not src.exists():
        return None
    d = json.load(open(src))
    for j in d["jurisdictions"]:
        if j["name"] == name:
            return dict(j, as_of=d["as_of"], population_date=d["population_date"])
    return None


def main():
    OUTDIR.mkdir(exist_ok=True)
    payload, raw = federal()
    fragment = write_page(payload, "index")
    (OUTDIR / "artifact.html").write_text(fragment)
    write_csv(raw, ["num", "current_name", "province", "population", "mp", "mp_party", "party_2025", "runnerup_party_2025", "margin_votes",
                    "margin_pts", "close", "group", "after_adj", "after_total", "after_n", "before_adj", "before_total", "pc_after",
                    "pc_after_all", "pc_before", "change_pct", "score"], OUTDIR / "riding_spending.csv")
    for key in PROVINCES:
        P = PROVINCES[key]
        if not (DATA / P["dir"] / "division_spending.json").exists():
            continue
        payload, raw, y = provincial(key)
        fragment = write_page(payload, key)
        (OUTDIR / f"artifact_{key}.html").write_text(fragment)
        write_csv(raw, ["num", "name", "population", "mla", "mla_party", f"party_{y}", f"runnerup_party_{y}", "margin_votes", "margin_pts",
                        "close", "group", "after_adj", "after_total", "after_n", "before_adj", "before_total", "pc_after", "pc_after_all",
                        "pc_before", "change_pct", "score"], OUTDIR / f"{key}_spending.csv")


if __name__ == "__main__":
    main()
