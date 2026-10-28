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

NAV = [{"href": "index.html", "label": "Federal ridings"}, {"href": "bc.html", "label": "British Columbia"}, {"href": "alberta.html", "label": "Alberta"},
       {"href": "saskatchewan.html", "label": "Saskatchewan"}, {"href": "manitoba.html", "label": "Manitoba"}, {"href": "ontario.html", "label": "Ontario"},
       {"href": "quebec.html", "label": "Quebec"}, {"href": "nb.html", "label": "New Brunswick"}, {"href": "pei.html", "label": "PEI"}, {"href": "ns.html", "label": "Nova Scotia"}, {"href": "nl.html", "label": "Newfoundland"},
       {"href": "yukon.html", "label": "Yukon"}, {"href": "nwt.html", "label": "NWT"}, {"href": "nunavut.html", "label": "Nunavut"},
       {"href": "international.html", "label": "International"}]
# The published Claude pages live at fixed links; the website uses relative ones.
ARTIFACT_URLS = {"index.html": "https://claude.ai/artifact/J6Va83R2P7m4HKErD6KXgM", "alberta.html": "https://claude.ai/artifact/HniakFetDdXzVWcveb9zy9",
                 "bc.html": "https://claude.ai/artifact/1BU8kCqcxVtwsJpjAnXS7s", "saskatchewan.html": "https://claude.ai/artifact/P8kMKchyth4j5ykhcSXug6",
                 "legislatures.html": "https://claude.ai/artifact/45zE2pwEjXbZ3Wd2Zxib4p", "manitoba.html": "https://claude.ai/artifact/PmTjRxsid59XiGgJgPVmiv",
                 "nb.html": "https://claude.ai/artifact/6srrgUF4eD9A4JLfb9gB4R", "pei.html": "https://claude.ai/artifact/X4239bKZYyxRcX8ozVVZHQ",
                 "ontario.html": "https://claude.ai/artifact/JXkiRVQspJBViHHJ2MDcYL", "quebec.html": "https://claude.ai/artifact/YCvZDpg18q9rNjVfrG1nGz",
                 "ns.html": "https://claude.ai/artifact/KZKpkXpFKx5vSGPxYMrDPX", "nl.html": "https://claude.ai/artifact/9bRA1fMpskDcP2EzTcYjT1",
                 "yukon.html": "https://claude.ai/artifact/TfZdzP8WmqHWxpADNAJQjS", "nwt.html": "https://claude.ai/artifact/EHbnP8UrR4CvzXmWrNDpc1", "nunavut.html": "https://claude.ai/artifact/8QyhH7xKkzNy3vzTws8c81",
                 "sources.html": "https://claude.ai/artifact/SUrRaa5Q3jGQ19N657K9nG", "international.html": "https://claude.ai/artifact/FQKbVmqvTbXkT6dL7SezeK"}

COMMON = ["population", "margin_pts", "margin_votes", "after_total", "after_n", "after_adj", "after_adj_n",
          "before_adj", "before_total", "pc_after", "pc_after_all", "pc_before", "change_pct", "score", "close",
          "group", "top_grants", "series", "after_formula", "before_formula", "latest_grants", "latest_date"]


def links(items):
    return "; ".join(f'<a href="{u}" target="_blank" rel="noopener">{t}</a>' for t, u in items) + "."


def wiki(level):
    path = DATA / "wikipedia_links.json"
    return json.load(open(path)).get(level, {}) if path.exists() else {}


def ministers(level):
    """Cabinet ministers by riding key for one government (data/ministers.json, curated), or {}."""
    path = DATA / "ministers.json"
    if not path.exists():
        return {}, None
    lv = json.load(open(path))["levels"].get(level) or {}
    return lv.get("ministers", {}), lv


def pop_label():
    path = DATA / "population_scale.json"
    if not path.exists():
        return "2021 census", None
    d = json.load(open(path))
    y, m = d["latest_date"][:7].split("-")
    month = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][int(m) - 1]
    return f"est. {month} {y}", f"{month} {y}"


def land_for(insets):
    """The land file with the inset-only layers (municipal outlines, small lakes, rivers) cut to this
    page's inset boxes, so a page does not carry every other page's city outlines."""
    land = json.load(open(DATA / "land_geo.json"))
    boxes = [b for _, b in insets]

    def near(geom):
        coords = geom["coordinates"]
        pts = [pt for poly in coords for pt in poly[0]] if geom["type"] == "MultiPolygon" else [pt for line in coords for pt in line]
        if not pts:
            return False
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        if max(x1 - x0, y1 - y0) > 3:
            return False  # a vast rural subdivision whose box happens to cover a city
        return any(x1 > w and x0 < e and y1 > so and y0 < n for w, so, e, n in boxes)
    land["features"] = [f for f in land["features"] if f["properties"]["kind"] not in ("muni", "lake_small", "river", "urban") or near(f["geometry"])]
    return land


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
    mins, minfo = ministers("federal")
    ridings = {}
    for n, r in sp["ridings"].items():
        rec = {k: r.get(k) for k in COMMON}
        rec["wiki"] = (wk.get(n) or {}).get("url")
        rec["poliwave"] = pw.get(n)
        rec["minister"] = mins.get(n)
        rec["top_grants"] = [dict(g, news=news.get(f'{g["org"]}|{g["ref"]}')) if f'{g["org"]}|{g["ref"]}' in news else g for g in r["top_grants"]]
        rec.update({"num": n, "name": r["current_name"], "region": r["province"], "party_won": r["party_2025"],
                    "runnerup_party": r["runnerup_party_2025"], "winner": r["winner_2025"], "runnerup": r["runnerup_2025"],
                    "shares": r["shares_2025"], "rep": r["mp"], "rep_party": r["mp_party"], "top_progs": r["top_depts"]})
        ridings[n] = rec
    config = {
        "title": "Where federal grants went after the 2025 election",
        "nav": [dict(x, current=x["href"] == "index.html") for x in NAV],
        "ministers": minfo and {"head": minfo.get("head"), "source": minfo.get("source"), "note": minfo.get("note"), "as_of": json.load(open(DATA / "ministers.json"))["as_of"], "govParty": "LPC"},
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
    # Formula vs discretionary split (data/formula_programs.json), when the pipeline has computed it.
    fp = json.load(open(DATA / "formula_programs.json")) if (DATA / "formula_programs.json").exists() else None
    if fp and any("after_formula" in r for r in sp["ridings"].values()):
        config["formula"] = {"by": fp["levels"]["federal"]["by"], "note": fp["note"], "examples": [e["why"] for e in fp["levels"]["federal"]["formula"][:6]], "as_of": fp["as_of"]}
        fshare = sum(r.get("after_formula", 0) for r in sp["ridings"].values()) / max(1, sum(r["after_adj"] for r in sp["ridings"].values()))
        config["notes"].append("<b>Formula vs discretionary:</b> " + fp["note"] + f" The classification (by program) is a curated list kept with the data; tick \"discretionary only\" above the map to drop the formula money. Only {fshare:.0%} of the adjusted dollars in the window are formula money, because the big formula streams (First Nations core funding and the like) start on 1 April each year, four weeks before election day, and so fall outside both windows.")
    # Federal contracts (scripts/contracts.py): the same windows, placed by the vendor's postal area.
    cpath = DATA / "contracts_by_riding.json"
    if cpath.exists():
        ct = json.load(open(cpath))
        cm = ct["meta"]
        config["contracts"] = {"source": cm["source"], "generated": cm["generated"], "large_threshold": cm["large_threshold"], "total_after": cm["total_after_$"], "placed_after": cm["placed_after_$"],
                               "foreign_after": cm["foreign_after_$"], "unmapped_after": cm["unmapped_after_$"], "top_vendors": cm["top_vendors"], "large_after": cm["large_after"], "departments": cm["departments"]}
        config["notes"].append(f"<b>Contracts:</b> the \"Contracts\" switch above the map swaps in federal procurement from the <a href=\"https://open.canada.ca/data/en/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b\" target=\"_blank\" rel=\"noopener\">proactive publication of contracts over $10,000</a>, "
                               f"same windows as the grants: {fmt_money(cm['total_after_$'])} awarded since the election, {fmt_money(cm['placed_after_$'])} placed. The file gives only the vendor's postal area (the first three characters), so each contract is split across the ridings that area covers in proportion to its addresses, "
                               f"and the money sits where the vendor bills from, not where the work happens: Ottawa-area ridings and the downtown Toronto and Montréal areas where IBM, Bell and the consultancies book national contracts read high. Contracts of {fmt_money(cm['large_threshold'])} or more (multi-year ships, aircraft, software) are flagged, left out of the adjusted figures and listed in the Megacontracts card with their riding; foreign vendors ({fmt_money(cm['foreign_after_$'])}) are not placed. Amendments count once, at the contract's latest total, dated by the original award.")
        contracts_payload = {"ridings": ct["ridings"], "dept": ct["dept_by_riding"], "large": cm.get("large", []), "series": cm.get("series")}
        config["filterOptions"] = sorted(set(config["filterOptions"]) | set(cm["departments"]))  # the department menu serves both layers
    else:
        contracts_payload = None
    config["search"] = True  # type-ahead search box beside the department menu (MPs, ridings, departments, recipients, grants, contracts, dates)
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
               "deptBefore": sp["dept_by_riding_before"], "recipients": sp.get("recipients", []), "contracts": contracts_payload, "geo": json.load(open(DATA / "ridings_geo.json")), "land": land_for(config["insets"]),
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
    "ns": {
        "dir": "ns", "year": "2024", "region": "Nova Scotia", "title": "Where Nova Scotia's grants went around the 2024 election",
        "electionLabel": "the 26 November 2024 election", "count": 56, "gov": "PC",
        "parties": {"PC": {"name": "Progressive Conservative", "light": "#1b4c9e", "dark": "#4f80d8"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"}, "GRN": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"},
                    "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["PC", "NDP", "LIB"], "opp": "opposition",
        "groupNote": '"PC" means the governing Progressive Conservatives won the seat in 2024; "opposition" covers the NDP, Liberals and the independent. Chéticamp-Margarees-Pleasant Bay, created in 2026, is grouped by its June 2026 by-election.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "beforeLabel": "Fiscal year before the election (2023-24)",
        "includeLabel": "Include province-wide bodies (Nova Scotia Health, IWK, universities, NSCC, regional centres for education) & multi-district municipalities",
        "projection": {"parallels": [44, 47], "rotate": [63, 0]},
        "insets": [["Halifax", [-63.85, 44.55, -63.4, 44.85]], ["Sydney", [-60.3, 46.05, -60.1, 46.2]], ["Truro", [-63.35, 45.33, -63.2, 45.4]]],
        "source": "Nova Scotia Public Accounts, Volume 3 (Supplement to the Public Accounts): every grant and contribution and every supplier of $5,000 or more, listed by department with no address, program or date; read from the Internet Archive's copies because the province's notices site refuses connections.",
        "windowNote": "The 2025-26 volume is published late in the following year, so \"after\" is fiscal 2024-25, which straddles the election (eight months before it, four after), and \"before\" is fiscal 2023-24; the page switches to 2025-26 automatically when that volume appears",
        "placing": "Nova Scotia publishes payee names only. Each was matched by name to a postal code in the federal grants file or the CRA charity list, to the province's long-term care and child care directories, to a municipality or First Nation, or to a place name inside its own name, then located in a district. The volume's \"Other\" section (goods and services) is flagged as suppliers and left out of the default view, as are obvious suppliers among the grants.",
        "individualNote": "payments to individuals",
        "leftOut": "province-wide bodies booked at a head office (Nova Scotia Health, the IWK, universities and NSCC, regional centres for education, VON, Crown corporations), the regional, county and district municipalities that span several districts, suppliers of goods and services, the province paying its own departments, tax credits and other program totals with no named payee, and bodies outside the province",
        "boundaryNote": "the 56 districts in force since April 2026 (the 55 of the 2019 commission used in 2024, plus Chéticamp-Margarees-Pleasant Bay, carved out of Inverness and filled at a June 2026 by-election; Inverness keeps its 2024 result). No census population exists for them, so \"per person\" here means per elector on the 2024 final list, scaled to Statistics Canada's July 2026 estimate for Nova Scotia.",
        "sources": [("Nova Scotia Public Accounts, Volume 3 - Supplement to the Public Accounts (Internet Archive copy)", "https://web.archive.org/web/2026/https://notices.novascotia.ca/files/public-accounts/2025/pa-supplementary-2025.pdf"),
                    ("Elections Nova Scotia 2024 poll-by-poll results", "https://electionsnovascotia.ca/files/GeneralElection_42nd/42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx"),
                    ("Elections Nova Scotia (by-election reports, district boundaries 2026)", "https://electionsnovascotia.ca/"),
                    ("Nova Scotia House of Assembly member list", "https://nslegislature.ca/members/profiles"),
                    ("Long-term care and child care directories (Nova Scotia open data)", "https://data.novascotia.ca/"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Census subdivisions (municipal boundaries, via Represent)", "https://represent.opennorth.ca/boundary-sets/census-subdivisions/"),
                    ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Nova_Scotia_provincial_electoral_districts")],
    },
    "nl": {
            "dir": "nl", "year": "2025", "region": "Newfoundland and Labrador",  # canadaspends.com has no NL page
            "title": "Where federal grants land in Newfoundland and Labrador's provincial districts",
            "electionLabel": "the 14 October 2025 provincial election", "count": 40, "gov": "PC",
            "parties": {"PC": {"name": "Progressive Conservative", "light": "#1b4c9e", "dark": "#4f80d8"}, "LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"},
                        "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
            "legendParties": ["PC", "LIB", "NDP", "IND"], "opp": "opposition",
            "groupNote": '"PC" means the governing Progressive Conservatives won the seat in 2025; "opposition" covers the Liberals, the NDP and the two independents (Eddie Joyce and Paul Lane, the Speaker). The money is federal, so the question here is whether Ottawa\'s grants land more heavily in the province\'s close provincial seats.',
            "filterAll": "All departments", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest federal grants since the 2025 federal election",
            "beforeLabel": "Same dates a year earlier",
            "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
            "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
            "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
            "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
            "linkNote": "Links open the government's own record of each award on open.canada.ca.",
            "popLabel": "electors, est. {pop_date}",
            "projection": {"parallels": [47, 55], "rotate": [60, 0]},
            "insets": [["St. John's", [-53.0, 47.4, -52.6, 47.65]], ["Corner Brook", [-58.0, 48.9, -57.85, 48.98]]],
            "source": "the federal Proactive Disclosure of grants and contributions (open.canada.ca), the same awards as the federal page, placed in Newfoundland and Labrador's provincial districts.",
            "subtitle": ("Federal grants and contributions with agreements starting {election} (the federal election) to {cutoff}, placed in Newfoundland and Labrador's 40 provincial districts "
                         "and set against the 14 October 2025 provincial result. Each district wears its current MHA's party colour; the deeper the colour, the more federal grant money "
                         "per resident. \"Before\" means the same dates one year earlier. The province publishes no list of its own payees, so provincial payments cannot be shown."),
            "notes": [
                "<b>Why federal money:</b> Newfoundland and Labrador's Public Accounts (the Report on the Program Expenditures and Revenues of the Consolidated Revenue Fund) stop at the "
                "program level and the province publishes no payee or grant-recipient list, so provincial payments cannot be placed in a district. This page therefore shows the federal "
                "grants that land in each district: the same awards as the federal page, cut along provincial lines.",
                "<b>Where money lands:</b> each award is placed at the recipient's address, not where the money is spent, by postal code; recipients with no postal code were "
                "matched to their address on other awards, then by postal area or city (marked approximate). {unmapped_n} awards worth {unmapped_money} since the federal election are still unplaced.",
                "<b>Left out by default:</b> national non-profits booked at a head office, other governments (the Province itself, the City of St. John's and the other towns that span several districts, "
                "the Nunatsiavut Government), treaty settlements and foreign aid. Tick the box to put them back.",
                "<b>Boundaries:</b> the 40 districts of the 2015 Electoral Districts Boundaries Commission, used in 2015, 2019, 2021 and 2025, from Elections NL's map service "
                "(the open-data \"Provincial Electoral Districts (2015)\" layer). Results are the official addition of 17 October 2025, with the 21 November 2025 judicial recount in "
                "Topsail – Paradise (Paul Dinn, PC, by 106 votes). Keith Russell (Lake Melville) was elected PC and has sat as an independent since 14 September 2026.",
                "<b>Population:</b> no census count exists for these districts (the 2015 commission worked from the 2011 census), so per-person figures use the registered electors at the "
                "2025 election, scaled to Statistics Canada's {pop_date} estimate for the province.",
                "<b>Party is correlation, not credit:</b> federal ministers and departments approve these grants, not MHAs. A pattern by provincial seat type is a signal worth checking, not proof of intent.",
            ],
            "boundaryNote": ("the 40 districts of the 2015 Electoral Districts Boundaries Commission, used in 2015, 2019, 2021 and 2025, from Elections NL's map service (the open-data "
                             "\"Provincial Electoral Districts (2015)\" layer). Results are the official addition of 17 October 2025, with the judicial recount of 21 November 2025 in "
                             "Topsail – Paradise (Paul Dinn, PC, by 106 votes). Keith Russell (Lake Melville) was elected PC and has sat as an independent since 14 September 2026."),
            "sources": [("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                        ("Newfoundland and Labrador Public Accounts (program level only)", "https://www.gov.nl.ca/exec/tbs/home/publications/public-accounts/"),
                        ("Elections NL, official results of the 2025 general election (release of 20 October 2025)", "https://www.gov.nl.ca/releases/2025/elections/1020n02/"),
                        ("Elections NL, Topsail – Paradise judicial recount (21 November 2025)", "https://www.gov.nl.ca/releases/2025/elections/1121n06/"),
                        ("Elections NL, 2025 general election report under s. 164 (electors, ballots cast, rejected)", "https://www.elections.gov.nl.ca/files/October-14-2025-Preliminary-Election-Report-1.pdf"),
                        ("Elections NL, 2025 results dashboard and district map service", "https://www.elections.gov.nl.ca/2025-general-election-official-results/"),
                        ("District boundaries, 2015 commission (Provincial Electoral Districts (2015), opendata.gov.nl.ca)", "https://opendata.gov.nl.ca/public/opendata/page/?page-id=datasetdetails&id=361"),
                        ("2015 Electoral Districts Boundaries Commission final report (2011 populations)", "https://www.nledbc.ca/reports"),
                        ("House of Assembly of Newfoundland and Labrador member list", "https://www.assembly.nl.ca/Members/members.aspx"),
                        ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                        ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                        ("Census subdivisions (municipal boundaries, via Represent)", "https://represent.opennorth.ca/boundary-sets/census-subdivisions/"),
                        ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Newfoundland_and_Labrador_provincial_electoral_districts")],
        },
    "yukon": {
        "dir": "yt", "year": "2025", "region": "Yukon", "title": "Where federal grants land in Yukon's electoral districts",
        "electionLabel": "the 3 November 2025 territorial election", "count": 21, "gov": "YP",
        "parties": {"YP": {"name": "Yukon Party", "light": "#1b4c9e", "dark": "#4f80d8"}, "LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"},
                    "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["YP", "NDP", "LIB"], "opp": "opposition",
        "groupNote": '"YP" means the governing Yukon Party won the seat in 2025; "opposition" covers the NDP (official opposition) and the lone Liberal. The money is federal, so the question is whether Ottawa\'s grants land more heavily in the territory\'s close seats.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest federal grants since the 2025 federal election",
        "beforeLabel": "Same dates a year earlier", "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
        "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
        "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
        "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
        "linkNote": "Links open the government's own record of each award on open.canada.ca.",
        "popLabel": "electors, est. {pop_date}",
        "projection": {"parallels": [60, 69], "rotate": [135, 0]},
        "insets": [["Whitehorse", [-135.2, 60.65, -134.9, 60.8]]],
        "source": "the federal Proactive Disclosure of grants and contributions (open.canada.ca), the same awards as the federal page, placed in Yukon's 21 electoral districts.",
        "subtitle": ("Federal grants and contributions with agreements starting {election} (the federal election) to {cutoff}, placed in Yukon's 21 electoral districts "
                     "and set against the 3 November 2025 territorial result. Each district wears its current MLA's party colour; the deeper the colour, the more federal grant money "
                     "per resident. \"Before\" means the same dates one year earlier. Yukon publishes no list of its own payees, so territorial payments cannot be shown."),
        "notes": [
            "<b>Why federal money:</b> Yukon's Public Accounts stop at the program level (Schedules 1 to 11) and the territory publishes no payee list, so this page shows the federal grants that land in each district: the same awards as the federal page.",
            "<b>Where money lands:</b> each award is placed at the recipient's address by postal code; recipients with no postal code were matched to their address on other awards, then by postal area or city (marked approximate). {unmapped_n} awards worth {unmapped_money} since the federal election are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office, other governments (the Yukon government itself, the City of Whitehorse, First Nations governments where flagged), treaty settlements and foreign aid. Tick the box to put them back.",
            "<b>Boundaries:</b> the 21 districts of the Electoral District Boundaries Act (2024), first used on 3 November 2025 (two new Whistle Bend seats; Golden Horn, Teslin, Ross River and Faro merged into neighbours), from GeoYukon's official electoral-district layer.",
            "<b>Population:</b> no census count exists for these districts and Whitehorse is cut into 15 of them, so per-person figures use the registered electors at the 2025 election, scaled to Statistics Canada's {pop_date} estimate for Yukon.",
            "<b>Party is correlation, not credit:</b> federal ministers and departments approve these grants, not MLAs. A pattern by seat type is a signal worth checking, not proof of intent.",
        ],
        "sources": [("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                    ("Yukon Public Accounts 2024-25 (program-level schedules only)", "https://open.yukon.ca/data/2024-25-public-accounts"),
                    ("Elections Yukon 2025 general election official results", "https://electionsyukon.ca/en/2025-general-election-official-results"),
                    ("Yukon Legislative Assembly member list", "https://yukonassembly.ca/mlas"),
                    ("Electoral district boundaries (GeoYukon, Electoral District Boundaries Act 2024)", "https://open.yukon.ca/data/yukon-electoral-districts"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Yukon_territorial_electoral_districts")],
    },
    "nwt": {
        "dir": "nt", "year": "2023", "region": "Northwest Territories", "title": "Where federal grants land in the Northwest Territories' electoral districts",
        "electionLabel": "the 14 November 2023 territorial election", "count": 19, "gov": "cabinet",
        "parties": {"IND": {"name": "Independent (consensus government)", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["IND"], "opp": "regular members",
        "groupNote": 'The NWT has consensus government: every MLA is an independent, so the groups are cabinet (the Premier and six ministers, dashed outlines on the map) against the regular members. The money is federal.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest federal grants since the 2025 federal election",
        "beforeLabel": "Same dates a year earlier", "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
        "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
        "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
        "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
        "linkNote": "Links open the government's own record of each award on open.canada.ca.",
        "popLabel": "residents, est. {pop_date}",
        "projection": {"parallels": [60, 70], "rotate": [115, 0]},
        "insets": [["Yellowknife", [-114.45, 62.42, -114.3, 62.5]]],
        "source": "the federal Proactive Disclosure of grants and contributions (open.canada.ca), placed in the NWT's 19 electoral districts.",
        "subtitle": ("Federal grants and contributions with agreements starting {election} (the federal election) to {cutoff}, placed in the Northwest Territories' 19 electoral districts "
                     "and set against the 14 November 2023 territorial result. The NWT has no parties; cabinet members' districts carry a dashed outline. \"Before\" means the same dates one year earlier. "
                     "The territory's own payee reporting covers one department, so territorial payments are not shown."),
        "notes": [
            "<b>Why federal money:</b> the GNWT itemises recipients only in Industry, Tourism and Investment's annual Grants and Contributions Results Report; the Public Accounts stop at the program level. This page shows the federal grants that land in each district.",
            "<b>Where money lands:</b> each award is placed at the recipient's address by postal code; recipients with no postal code were matched to their address on other awards, then by postal area or city (marked approximate). {unmapped_n} awards worth {unmapped_money} since the federal election are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office, other governments (the GNWT itself, the City of Yellowknife, Indigenous governments where flagged), treaty settlements and foreign aid. Tick the box to put them back.",
            "<b>Boundaries:</b> the 19 districts of the 2013 redistribution, used in 2015, 2019 and 2023, from the GNWT Centre for Geomatics.",
            "<b>Population:</b> the 2021 census count of each district's communities (Yellowknife, Hay River and Inuvik shared between their districts by registered electors), scaled to Statistics Canada's {pop_date} estimate.",
            "<b>Since the election:</b> Inuvik Twin Lakes has been vacant since Lesa Semmler resigned in September 2026; the by-election is on 24 November 2026.",
        ],
        "sources": [("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                    ("Elections NWT 2023 official results report", "https://www.electionsnwt.ca/en/official-voting-results-historical"),
                    ("GNWT Premier and Cabinet", "https://www.gov.nt.ca/en/cabinet"),
                    ("Legislative Assembly of the Northwest Territories members", "https://www.ntlegislativeassembly.ca/meet-members/all"),
                    ("Electoral district boundaries (GNWT Centre for Geomatics)", "https://www.apps.geomatics.gov.nt.ca/arcgis/rest/services/GNWT/Boundaries_LCC/MapServer/2"),
                    ("ITI Grants and Contributions Results Report 2023-24", "https://www.iti.gov.nt.ca/en/files/2024-grants-and-contributions-report"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Northwest_Territories_territorial_electoral_districts")],
    },
    "nunavut": {
        "dir": "nu", "year": "2025", "region": "Nunavut", "title": "Where federal grants land in Nunavut's constituencies",
        "electionLabel": "the 27 October 2025 territorial election", "count": 22, "gov": "cabinet",
        "parties": {"IND": {"name": "Independent (consensus government)", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["IND"], "opp": "regular members",
        "groupNote": 'Nunavut has consensus government: every MLA is an independent, so the groups are cabinet (the Premier and eight ministers chosen by the Assembly on 18 November 2025, dashed outlines on the map) against the regular members. The money is federal.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest federal grants since the 2025 federal election",
        "beforeLabel": "Same dates a year earlier", "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
        "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
        "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
        "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
        "linkNote": "Links open the government's own record of each award on open.canada.ca.",
        "popLabel": "residents, est. {pop_date}",
        "projection": {"parallels": [60, 80], "rotate": [85, 0]},
        "insets": [["Iqaluit", [-68.6, 63.72, -68.45, 63.78]]],
        "source": "the federal Proactive Disclosure of grants and contributions (open.canada.ca), placed in Nunavut's 22 constituencies.",
        "subtitle": ("Federal grants and contributions with agreements starting {election} (the federal election) to {cutoff}, placed in Nunavut's 22 constituencies "
                     "and set against the 27 October 2025 territorial result. Nunavut has no parties; cabinet members' constituencies carry a dashed outline. \"Before\" means the same dates one year earlier. "
                     "Nunavut's Grants and Contributions Report names only municipalities and territorial corporations, so territorial payments are not shown."),
        "notes": [
            "<b>Why federal money:</b> the Government of Nunavut's annual Grants and Contributions Report gives totals by department, recipient category and municipality, not named recipients, and the Public Accounts stop at the program level. This page shows the federal grants that land in each constituency.",
            "<b>Where money lands:</b> each award is placed at the recipient's address by postal code; recipients with no postal code were matched to their address on other awards, then by postal area or city (marked approximate). {unmapped_n} awards worth {unmapped_money} since the federal election are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office, other governments (the Government of Nunavut itself, the City of Iqaluit, Inuit organizations where flagged), treaty settlements and foreign aid. Tick the box to put them back.",
            "<b>Boundaries:</b> the 22 constituencies of the 2024 amendment to the Nunavut Elections Act (from the 2023 Electoral Boundaries Commission), first used on 27 October 2025, from Elections Nunavut's GIS file; the legal boundary runs to the North Pole and is cut off at 83.3°N here.",
            "<b>Population:</b> the 2021 census count of each constituency's communities (Iqaluit, Arviat, Rankin Inlet and Igloolik shared between their constituencies by electors), scaled to Statistics Canada's {pop_date} estimate.",
            "<b>Since the election:</b> Aggu tied 105 to 105 and was decided by a new election on 15 December 2025 (Edward Attagutaluk); Hudson Bay changed hands at the 28 September 2026 by-election (Jason Iqaluq).",
        ],
        "sources": [("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                    ("Elections Nunavut 2025 general election results", "https://www.elections.nu.ca/en/2025-territorial-general-elections"),
                    ("Legislative Assembly of Nunavut members", "https://assembly.nu.ca/members/mla"),
                    ("Government of Nunavut cabinet portfolios (20 November 2025)", "https://www.gov.nu.ca/en/newsroom/premier-main-announces-cabinet-portfolios-2025-11-20"),
                    ("Constituency boundaries (Elections Nunavut GIS shape file)", "https://www.elections.nu.ca/en/documents"),
                    ("Government of Nunavut Grants and Contributions Report 2024-25", "https://www.gov.nu.ca/sites/default/files/documents/2025-11/2024-25_Grants_and_Contributions_Report.pdf"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Wikipedia (constituency articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Nunavut_territorial_electoral_districts")],
    },
    # PEI publishes no payee list, so its page shows the federal grants that land in each provincial district (pe_spending.py).
    "pei": {
        "dir": "pe", "year": "2023", "region": "Prince Edward Island",  # canadaspends.com has no PEI page yet
        "title": "Where federal grants land in PEI's provincial districts",
        "electionLabel": "the 3 April 2023 provincial election", "count": 27, "gov": "PC",
        "parties": {"PC": {"name": "Progressive Conservative", "light": "#1b4c9e", "dark": "#4f80d8"}, "LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"},
                    "GRN": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "ISL": {"name": "Island Party", "light": "#8b5a2b", "dark": "#c0894f"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["PC", "LIB", "GRN"], "opp": "opposition",
        "groupNote": '"PC" means the governing Progressive Conservatives won the seat in 2023; "opposition" covers the Liberals, Greens and independents. The money is federal, so the question here is whether Ottawa\'s grants land more heavily in the Island\'s close provincial seats.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest federal grants since the 2025 federal election",
        "beforeLabel": "Same dates a year earlier",
        "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
        "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
        "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
        "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
        "linkNote": "Links open the government's own record of each award on open.canada.ca.",
        "popLabel": "electors, est. {pop_date}",
        "projection": {"parallels": [46, 47], "rotate": [63.2, 0]},
        "insets": [["Charlottetown", [-63.21, 46.22, -63.07, 46.31]], ["Summerside", [-63.85, 46.38, -63.71, 46.43]]],
        "source": "the federal Proactive Disclosure of grants and contributions (open.canada.ca), the same awards as the federal page, placed in PEI's provincial districts.",
        "subtitle": ("Federal grants and contributions with agreements starting {election} (the federal election) to {cutoff}, placed in PEI's 27 provincial districts "
                     "and set against the 3 April 2023 provincial result. Each district wears its current MLA's party colour; the deeper the colour, the more federal grant money "
                     "per resident. \"Before\" means the same dates one year earlier. PEI publishes no list of its own payees, so provincial payments cannot be shown."),
        "notes": [
            "<b>Why federal money:</b> PEI's Public Accounts Volume II itemises spending by department and program only (\"Operating Grant\", \"Pharmacare\", \"Miscellaneous\") and "
            "the province publishes no payee list, so provincial payments cannot be placed in a district. This page therefore shows the federal grants that land in each "
            "district: the same awards as the federal page, cut along provincial lines.",
            "<b>Where money lands:</b> each award is placed at the recipient's address, not where the money is spent, by postal code; recipients with no postal code were "
            "matched to their address on other awards, then by postal area or city (marked approximate). {unmapped_n} awards worth {unmapped_money} since the federal election are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office, other governments (the Province of PEI itself, Charlottetown and Summerside, which span several districts), "
            "treaty settlements and foreign aid. Tick the box to put them back.",
            "<b>Boundaries:</b> the 27 districts of the 2017 commission, used in 2019 and 2023, from the province's GeoLinc map service (polling divisions, merged here).",
            "<b>Population:</b> no census count exists for these districts, so per-person figures use the registered electors at the 2023 election, scaled to Statistics Canada's "
            "{pop_date} estimate for PEI.",
            "<b>Party is correlation, not credit:</b> federal ministers and departments approve these grants, not MLAs. A pattern by provincial seat type is a signal worth checking, not proof of intent.",
        ],
        "sources": [("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                    ("PEI Public Accounts (Volume II stops at the program level)", "https://www.princeedwardisland.ca/en/topic/public-accounts"),
                    ("Elections PEI 2023 general election results", "https://www.electionspei.ca/"),
                    ("Legislative Assembly of Prince Edward Island member list", "https://www.assembly.pe.ca/members"),
                    ("District boundaries, 2017 commission (GeoLinc map service)", "https://geolinc.gov.pe.ca/server/rest/services/Provincial_Electoral_Districts_2017_ELC/MapServer/0"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Census subdivisions (municipal boundaries, via Represent)", "https://represent.opennorth.ca/boundary-sets/census-subdivisions/"),
                    ("Wikipedia (district articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Prince_Edward_Island_provincial_electoral_districts")],
    },
    "ontario": {
        "dir": "on", "year": "2025", "region": "Ontario", "spendsUrl": "https://canadaspends.com/en/provincial/ontario", "title": "Where Ontario's payments went after the 2025 election",
        "electionLabel": "the 27 February 2025 election", "count": 124, "gov": "PC",
        "parties": {"PC": {"name": "Progressive Conservative", "light": "#1b4c9e", "dark": "#4f80d8"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "LIB": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"}, "GRN": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"},
                    "NBP": {"name": "New Blue", "light": "#5a9bd5", "dark": "#7fb3e6"}, "OP": {"name": "Ontario Party", "light": "#6a4c93", "dark": "#9b7fc4"},
                    "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["PC", "NDP", "LIB", "GRN"], "opp": "opposition",
        "groupNote": '"PC" means the governing Progressive Conservatives won the seat in 2025; "opposition" covers the NDP, Liberals, Greens and independents.',
        "filterAll": "All ministries", "topProgsTitle": "Top ministries", "beforeLabel": "Last full fiscal year before the election (2023-24)",
        "includeLabel": "Include hospitals and province-wide bodies (Ontario Health, Metrolinx, the IESO, school boards, universities) & multi-riding city and regional governments",
        "flags": {"province-wide": "hospital or province-wide body", "other government": "other government", "supplier": "supplier, not a grant"},
        "projection": {"parallels": [43, 50], "rotate": [84, 0]},
        "insets": [["Toronto & GTA", [-79.85, 43.5, -79.0, 43.95]], ["Hamilton–Niagara", [-80.2, 43.0, -79.0, 43.45]], ["Kitchener–Waterloo", [-80.7, 43.3, -80.2, 43.6]],
                   ["London", [-81.4, 42.85, -81.1, 43.1]], ["Ottawa", [-76.05, 45.2, -75.4, 45.6]], ["Windsor", [-83.15, 42.22, -82.85, 42.38]]],
        "source": "Ontario Public Accounts, Detailed Schedule of Payments (data.ontario.ca; transfer-payment recipients of $120,000 or more and suppliers of $50,000 or more, by ministry and fiscal year; no addresses, programs or dates).",
        "windowNote": "\"After\" is fiscal 2025-26 (April 2025 to March 2026), the first full year after the election; \"before\" is fiscal 2023-24, the last full year before it; 2024-25 straddles the vote and is skipped",
        "placing": "Ontario publishes payee names only. Each was matched by name to a postal code in the federal grants file or the CRA charity list, to a municipality or First Nation, or to a place name inside its own name, then located in a riding. Hospitals are placed where they stand but flagged like the other provinces' health authorities, since a teaching hospital's operating grant serves a whole region; tick the box to see them. The schedule's supplier list (goods and services) is flagged and excluded from the default view.",
        "individualNote": "programs that pay individuals (OHIP physician billings, the Ontario Drug Benefit, student loans, assistive devices, GAINS) and accounts below the reporting thresholds",
        "leftOut": "hospitals and province-wide bodies booked at a head office (Ontario Health, Metrolinx, the IESO and OPG, Infrastructure Ontario, school boards, universities and colleges, Legal Aid, Agricorp), the governments of Toronto, Ottawa and other cities and regions that span several ridings, suppliers of goods and services, and payments to bodies outside the province",
        "boundaryNote": "the 124 ridings used in 2018, 2022 and 2025. 111 are the 2013 federal districts, whose 2021 census counts are used; the 13 northern ridings are not, so their counts are 2021 census subdivisions summed inside each riding (Greater Sudbury and Thunder Bay split between their two ridings). Ontario repealed its fixed election date in November 2025; the legislature expires in March 2030.",
        "sources": [("Ontario Public Accounts: Detailed Schedule of Payments (data.ontario.ca)", "https://data.ontario.ca/dataset/56c9a95f-c7b6-40ee-a4b8-d2343e51c83d"),
                    ("Elections Ontario 2025 official results", "https://results.elections.on.ca/en/publications"),
                    ("Legislative Assembly of Ontario member list", "https://www.ola.org/en/members/current"),
                    ("Statistics Canada 2021 census counts, federal electoral districts (2013 order)", "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810001001"),
                    ("Statistics Canada 2021 census counts, census subdivisions", "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201"),
                    ("Riding boundaries, Representation Act 2015 (Represent, Open North)", "https://represent.opennorth.ca/boundary-sets/ontario-electoral-districts-representation-act-2015/"),
                    ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Census subdivisions (municipal boundaries, via Represent)", "https://represent.opennorth.ca/boundary-sets/census-subdivisions/"),
                    ("Wikipedia (riding articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Ontario_provincial_electoral_districts")],
    },
    # Quebec publishes transfers by beneficiary category only, so its page also shows federal grants (fed_prov_spending.py qc).
    "quebec": {
        "dir": "qc", "year": "2026", "region": "Quebec",  # canadaspends.com has no Quebec page
        "title": "Where federal grants land in Quebec's provincial ridings",
        "electionLabel": "the 5 October 2026 provincial election", "count": 127, "gov": "PQ",
        "parties": {"PQ": {"name": "Parti Québécois", "light": "#1b4c9e", "dark": "#4f80d8"}, "PLQ": {"name": "Liberal", "light": "#d71920", "dark": "#ea3a40"},
                    "PCQ": {"name": "Conservative", "light": "#6a4c93", "dark": "#9b7fc4"}, "QS": {"name": "Québec solidaire", "light": "#f37021", "dark": "#f68a45"},
                    "CAQ": {"name": "Coalition Avenir Québec", "light": "#1aa7bd", "dark": "#3fc0d4"}, "PVQ": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"},
                    "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["PQ", "PLQ", "PCQ", "QS"], "opp": "opposition",
        "groupNote": '"PQ" means the governing Parti Québécois won the seat in 2026; "opposition" covers the Liberals, Conservatives and Québec solidaire. The money is federal, so the question here is whether Ottawa\'s grants land more heavily in Quebec\'s close provincial seats.',
        "filterAll": "All departments", "topProgsTitle": "Top departments", "topGrantsTitle": "Largest federal grants since the 2025 federal election",
        "beforeLabel": "Same dates a year earlier",
        "includeLabel": "Include national HQs, other governments, settlements & foreign aid",
        "flags": {"national": "national HQ", "government": "other government", "settlement": "treaty settlement", "international": "foreign aid"},
        "recordUrl": "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent",
        "searchUrl": "https://search.open.canada.ca/grants/?search_text={q}", "searchLabel": "all awards to this recipient",
        "linkNote": "Links open the government's own record of each award on open.canada.ca.",
        "popLabel": "electors, est. {pop_date}",
        "projection": {"parallels": [46, 50], "rotate": [71.5, 0]},
        "insets": [["Montréal", [-74.05, 45.38, -73.4, 45.75]], ["Québec", [-71.55, 46.68, -71.1, 46.98]], ["Gatineau", [-75.95, 45.4, -75.6, 45.55]],
                   ["Sherbrooke", [-72.0, 45.33, -71.8, 45.45]], ["Trois-Rivières", [-72.7, 46.3, -72.5, 46.42]], ["Saguenay", [-71.3, 48.35, -70.95, 48.5]]],
        "source": "the federal Proactive Disclosure of grants and contributions (open.canada.ca), the same awards as the federal page, placed in Quebec's provincial ridings.",
        "subtitle": ("Federal grants and contributions with agreements starting {election} (the federal election) to {cutoff}, placed in Quebec's 127 provincial ridings "
                     "and set against the 5 October 2026 provincial result. Each riding wears its current MNA's party colour; the deeper the colour, the more federal grant money "
                     "per resident. \"Before\" means the same dates one year earlier. Quebec publishes no list of its own payees, so provincial payments cannot be shown."),
        "notes": [
            "<b>Why federal money:</b> Quebec's Comptes publics (Volume 2) report transfer spending by portfolio and by seven categories of beneficiary (municipalities, non-profits, "
            "health and education institutions, private firms, government bodies, individuals), never by named recipient, and no payee list exists. This page therefore shows "
            "the federal grants that land in each riding: the same awards as the federal page, cut along the 2026 provincial lines.",
            "<b>Where money lands:</b> each award is placed at the recipient's address, not where the money is spent, by postal code; recipients with no postal code were "
            "matched to their address on other awards, then by postal area or city (marked approximate). {unmapped_n} awards worth {unmapped_money} since the federal election are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office, other governments (the Gouvernement du Québec itself is the big one, plus the cities that span several ridings), "
            "treaty settlements and foreign aid. Tick the box to put them back.",
            "<b>Boundaries:</b> the 127 ridings of the 2026 electoral map (the Commission de la représentation électorale's delimitation, amended by the June 2026 law that kept 127 seats), "
            "first used on 5 October 2026. Champlain's result is under judicial recount; Vachon's is the post-recount count (3 votes).",
            "<b>Population:</b> no census count exists for these ridings, so per-person figures use the registered electors at the 2026 election, scaled to Statistics Canada's "
            "{pop_date} estimate for Quebec.",
            "<b>Party is correlation, not credit:</b> federal ministers and departments approve these grants, not MNAs. A pattern by provincial seat type is a signal worth checking, not proof of intent.",
        ],
        "sources": [("Proactive Disclosure – Grants and Contributions (Treasury Board, open.canada.ca)", "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"),
                    ("Comptes publics du Québec, Volume 2 (transfers by beneficiary category only)", "https://www.donneesquebec.ca/recherche/dataset/comptes-publics-du-gouvernement-volume-2"),
                    ("Élections Québec, 2026 general election results", "https://www.electionsquebec.qc.ca/resultats-et-statistiques/resultats-elections-generales-provinciales-en-direct/"),
                    ("Élections Québec open data: 2026 riding boundaries and list", "https://www.dgeq.org/donnees.html"),
                    ("Élections Québec, revision of the electoral map", "https://www.electionsquebec.qc.ca/cartes-electorales/revision-de-la-carte-electorale-du-quebec/"),
                    ("Assemblée nationale du Québec member list", "https://www.assnat.qc.ca/fr/deputes/index.html"),
                    ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                    ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
                    ("Census subdivisions (municipal boundaries, via Represent)", "https://represent.opennorth.ca/boundary-sets/census-subdivisions/"),
                    ("Wikipedia (riding articles, linked from each panel)", "https://en.wikipedia.org/wiki/List_of_Quebec_provincial_electoral_districts")],
    },
}


LEVEL = {"alberta": ("division", "divisions"), "bc": ("district", "districts"), "saskatchewan": ("constituency", "constituencies"),
         "manitoba": ("division", "divisions"), "nb": ("district", "districts"), "pei": ("district", "districts"),
         "ontario": ("riding", "ridings"), "quebec": ("riding", "ridings"), "ns": ("district", "districts"), "nl": ("district", "districts"),
         "yukon": ("district", "districts"), "nwt": ("district", "districts"), "nunavut": ("constituency", "constituencies")}


def provincial(key):
    P = PROVINCES[key]
    y = P["year"]
    sp = json.load(open(DATA / P["dir"] / "division_spending.json"))
    m = sp["meta"]
    ex = m["excluded_after"]
    wk = wiki(key)
    news = json.load(open(DATA / "news_links.json")) if P.get("recordUrl") and (DATA / "news_links.json").exists() else {}
    pnews = json.load(open(DATA / "news_links_prov.json")) if (DATA / "news_links_prov.json").exists() else {}
    mins, minfo = ministers({"yukon": "yt", "nwt": "nt", "nunavut": "nu"}.get(key, key))
    ridings = {}
    for n, r in sp["ridings"].items():
        rec = {k: r.get(k) for k in COMMON}
        rec["wiki"] = (wk.get(n) or {}).get("url")
        rec["minister"] = mins.get(n)
        if not rec.get("latest_grants"):
            rec["latest_grants"] = r["top_grants"]
            rec["latest_date"] = m.get("after_fiscal_year") or m.get("after_year") or (r["top_grants"][0]["date"] if r["top_grants"] else None)
        if news:  # federal awards carry open.canada.ca keys, so the federal page's news links apply
            rec["top_grants"] = [dict(g, news=news[f'{g["org"]}|{g["ref"]}']) if f'{g.get("org")}|{g.get("ref")}' in news else g for g in r["top_grants"]]
        elif pnews:  # provincial coverage is keyed by recipient name
            rec["top_grants"] = [dict(g, news=pnews[f'{key}|{g["who"]}']) if f'{key}|{g["who"]}' in pnews else g for g in r["top_grants"]]
        rec.update({"num": n, "name": r["name"], "region": P["region"], "party_won": r[f"party_{y}"], "runnerup_party": r[f"runnerup_party_{y}"],
                    "winner": r[f"winner_{y}"], "runnerup": r[f"runnerup_{y}"], "shares": r[f"shares_{y}"], "rep": r["mla"],
                    "rep_party": r["mla_party"], "top_progs": r["top_progs"]})
        ridings[n] = rec
    land = land_for(P["insets"])
    gov, opp = P["gov"], P["opp"]
    rep = {"quebec": "MNA", "ontario": "MPP", "nl": "MHA"}.get(key, "MLA")
    mins_level = {"yukon": "yt", "nwt": "nt", "nunavut": "nu"}.get(key, key)
    config = {
        "title": P["title"],
        "nav": [dict(x, current=x["href"] == f"{key}.html") for x in NAV],
        "ministers": minfo and {"head": minfo.get("head"), "source": minfo.get("source"), "note": minfo.get("note"), "as_of": json.load(open(DATA / "ministers.json"))["as_of"], "govParty": P["gov"] if P["gov"] in P["parties"] else "IND"},
        "level": LEVEL[key][0], "levelPlural": LEVEL[key][1], "levelTitle": LEVEL[key][0].capitalize(), "region": "province", "regionTitle": "Prov.",
        "rep": rep, "electionYear": y, "spendsUrl": P.get("spendsUrl"),
        "popLabel": P["popLabel"].format(pop_date=pop_label()[1]) if P.get("popLabel") else "registered voters, 2024" if key == "saskatchewan" else ("electors, est. " + pop_label()[1]) if key in ("nb", "ns") else pop_label()[0],
        "parties": P["parties"], "legendParties": P["legendParties"],
        "flags": P.get("flags") or {"province-wide": "province-wide body", "other government": "other government", "supplier": "supplier, not a grant", "winnipeg (approx.)": "Winnipeg, location approx."},
        "filterAll": P["filterAll"], "filterOptions": m["programs"],
        "includeLabel": P["includeLabel"],
        "groupTitle": "Does money follow close seats?", "groups": [f"Close {gov}", f"Close {opp}", f"Safe {gov}", f"Safe {opp}"],
        "groupNote": f'"Close" means the {y} winner led by under {m["close_margin"]} points; ' + P["groupNote"],
        "groupParty": {f"Close {gov}": gov if gov in P["parties"] else None, f"Safe {gov}": gov if gov in P["parties"] else None, f"Close {opp}": opp if opp in P["parties"] else None, f"Safe {opp}": opp if opp in P["parties"] else None},
        "regionOrder": None, "regionGroup": {}, "regionShort": {},
        "beforeLabel": P["beforeLabel"], "topProgsTitle": P["topProgsTitle"], "topGrantsTitle": P.get("topGrantsTitle", "Largest recipients since the election"),
        "recordUrl": P.get("recordUrl"), "searchUrl": P.get("searchUrl") or m.get("search_url"), "searchLabel": P.get("searchLabel") or ("search the web for this recipient" if m.get("search_url") else ""),
        "linkNote": P.get("linkNote") or ("Recipient names open the source record where the province publishes one (a page of the Public Accounts volume, or the open-data table); " if any("src" in g for r in sp["ridings"].values() for g in r["top_grants"]) else "") + "Source: " + P["source"],
        "projection": P["projection"], "insets": P["insets"],
        "subtitle": P["subtitle"].format(**m) if P.get("subtitle") else
                    (f"{P['region']} government payments from {P['electionLabel']} to {m['cutoff']}, placed in the {P['count']} electoral "
                     f"{LEVEL[key][1]} and set against the {y} result. Each one wears its current {rep}'s party colour; "
                     f"the deeper the colour, the more money per resident. {P['windowNote']} ({m['before_start']} to {m['before_end']})."),
        "notes": ["<b>Sources:</b> " + links(P["sources"]) + f" Data as of {m.get('generated', m['cutoff'])}."] +
                 [n.format(pop_date=pop_label()[1], unmapped_n=m["methods"].get("after|unmapped", 0), unmapped_money=fmt_money(ex.get("unmatched", 0))) for n in P["notes"]]
                 if P.get("notes") else [
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
             f"<b>Population:</b> no census count exists for these districts, so per-person figures use the electors on the 2024 final list, scaled to Statistics Canada's {pop_label()[1]} estimate for Nova Scotia." if key == "ns" else
             f"<b>Population:</b> per-person figures use an estimate for {pop_label()[1]}: the boundary commission's 2016 census count for each division, scaled by Manitoba's growth since then from Statistics Canada's quarterly estimates (table 17-10-0009-01). Growth is assumed even within the province." if key == "manitoba" else
             f"<b>Population:</b> per-person figures use an estimate for {pop_label()[1]}: each riding's 2021 census count (the federal district's for 111 ridings, census subdivisions summed for the 13 northern ones) scaled by Ontario's growth since the census, from Statistics Canada's quarterly estimates (table 17-10-0009-01). Growth is assumed even within the province." if key == "ontario" else
             f"<b>Population:</b> per-person figures use an estimate for {pop_label()[1]}: each {LEVEL[key][0]}'s 2021 census count scaled by {P['region']}'s growth since the census, from Statistics Canada's quarterly estimates (table 17-10-0009-01). Growth is assumed even within the province."),
            f"<b>Party is correlation, not credit:</b> ministers and departments approve grants, not local {rep}s. A pattern by seat type is a signal worth checking, not proof of intent.",
        ],
    }
    fp = json.load(open(DATA / "formula_programs.json")) if (DATA / "formula_programs.json").exists() else None
    flevel = {"pei": "federal", "quebec": "federal", "nl": "federal", "yukon": "federal", "nwt": "federal", "nunavut": "federal"}.get(key, key)
    if fp and flevel in fp["levels"] and any("after_formula" in r for r in sp["ridings"].values()):
        lv = fp["levels"][flevel]
        config["formula"] = {"by": lv["by"], "note": fp["note"], "examples": [e["why"] for e in lv["formula"][:6]], "as_of": fp["as_of"]}
        config["notes"].append("<b>Formula vs discretionary:</b> " + fp["note"] + (" Here the split is by program." if lv["by"] == "program" else " This government's statements name no programs, so the split is by class of recipient: municipalities, First Nations, school and child-care operators, care homes and the like count as formula money.") + " Tick \"discretionary only\" above the map to drop the formula money.")
    fine = DATA / P["dir"] / "divisions_geo_fine.json"
    config["legislatureInGrid"] = False  # provinces: below the city insets
    config["search"] = True  # the same type-ahead search as the federal page: MLAs, districts, ministries, recipients, payments, dates
    config["findItem"] = "Grant" if P.get("recordUrl") or "grants" in P["title"] else "Payment"
    payload = {"config": config, "meta": m, "groups": sp["groups"], "ridings": ridings, "dept": sp["prog_by_riding"], "deptBefore": {}, "recipients": sp.get("recipients", []),
               "legislature": legislature_for(P["region"]),
               "geo": json.load(open(DATA / P["dir"] / "divisions_geo.json")), "land": land,
               "geoFine": json.load(open(fine)) if fine.exists() else {"features": []}}
    return payload, sp["ridings"], y


def render(payload, nav_urls=None):
    tpl = (ROOT / "scripts" / "map_template.html").read_text()
    cfg = dict(payload["config"], sourcesHref=(nav_urls or {}).get("sources.html", "sources.html"))
    if nav_urls:
        cfg["nav"] = [dict(n, href=nav_urls.get(n["href"], n["href"])) for n in cfg["nav"]]
    payload = dict(payload, config=cfg)
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
    """The jurisdiction's record from data/legislatures.json (standings, leaders, dates, budget), with
    every government's budget figures for comparison bars and the five-year history when present."""
    src = DATA / "legislatures.json"
    if not src.exists():
        return None
    d = json.load(open(src))
    hist_path = DATA / "fiscal_history.json"
    hist = json.load(open(hist_path))["jurisdictions"] if hist_path.exists() else {}
    compare = [{"name": j["name"], "budget": j["budget"], "population": j["population"]} for j in d["jurisdictions"] if j.get("budget") and j.get("population")]
    eq_path = DATA / "equalization.json"
    eq = json.load(open(eq_path)) if eq_path.exists() else None
    for j in d["jurisdictions"]:
        if j["name"] == name:
            equal = None
            if eq:
                if name == "Canada":
                    equal = {"year": eq["year"], "total": eq["total_millions"], "prev_year": eq["previous"]["year"], "prev_total": eq["previous"]["total_millions"],
                             "recipients": {k: v for k, v in eq["provinces"].items() if v}, "source": eq["source"]}
                elif name in eq["provinces"]:
                    equal = {"year": eq["year"], "amount": eq["provinces"][name], "prev_year": eq["previous"]["year"], "prev_amount": eq["previous"]["provinces"].get(name),
                             "cht": (eq.get("cht_millions") or {}).get(name), "cst": (eq.get("cst_millions") or {}).get(name), "source": eq["source"]}
            return dict(j, as_of=d["as_of"], population_date=d["population_date"], compare=compare, history=hist.get(name), equalization=equal)
    return None


def world():
    """The international page: federal money abroad by country (scripts/intl_*.py) on a world map."""
    sp_path, geo_path = DATA / "intl" / "intl_spending.json", DATA / "intl" / "world_geo.json"
    if not (sp_path.exists() and geo_path.exists()):
        print("international page skipped: run scripts/intl_prep.py and scripts/intl_spending.py first")
        return
    sp, geo = json.load(open(sp_path)), json.load(open(geo_path))
    m = dict(sp["meta"])
    m["gii_n"] = sum(1 for k in sp["countries"].values() if k.get("gii") is not None)
    src = m.get("sources", {})
    def src_link(key, fallback):
        x = src.get(key) or {}
        return f'<a href="{x.get("url")}" target="_blank" rel="noopener">{x.get("label") or fallback}</a>' if x.get("url") else (x.get("label") or fallback)
    kw = m.get("keywords", {})
    notes = [
        f"<b>Sources:</b> {src_link('grants', 'Proactive disclosure of grants and contributions')}; {src_link('contracts', 'Proactive publication of contracts over $10,000')}; "
        f"{src_link('iati', 'Global Affairs Canada IATI activity files')}; {src_link('gii', 'UNDP Gender Inequality Index')}. The three spending sources overlap (Global Affairs grants appear both in the disclosure and in IATI), so the page switches between them instead of adding them up.",
        f"<b>Fiscal years</b> run 1 April to 31 March ({', '.join(m.get('fys', []))}). "
        + "".join(f"FY {fy} is still being reported (records to {d}). " for fy, d in (m.get("fy_through") or {}).items())
        + "Contracts are dated by the original award (an amendment does not move them), grants by the agreement start, IATI aid by the disbursements paid in the year.",
        "<b>Where the money is placed:</b> contracts by the vendor's country, grants and contributions by the recipient's address (a United Nations agency in New York or Geneva counts there, wherever the program runs), IATI aid by the project's recipient countries. Canada itself is shaded neutral.",
        "<b>Gender Inequality Index (UNDP):</b> 0 means women and men fare equally on reproductive health, empowerment and labour-market measures; higher means less equal. It shades the map, and the flags card plots flagged dollars against it so readers can see where gender-focused money goes. Grey countries have no score.",
    ] + [f"<b>Caveat:</b> {n}" for n in m.get("notes", [])]
    config = {
        "title": "Canada's money abroad",
        "subtitle": ("Federal contracts, grants and contributions paid to vendors and recipients outside Canada, and Global Affairs Canada's aid "
                     "as reported to IATI, by fiscal year. Countries are shaded by the UN Gender Inequality Index (deeper means less equal for women) "
                     "and the bubbles show the dollars; switch to colour by spending for a continent-by-continent view."),
        "nav": [dict(x, current=x["href"] == "international.html") for x in NAV],
        "notes": notes,
    }
    payload = {"config": config, "meta": m, "countries": sp["countries"], "records": sp.get("records", []), "geo": geo}
    base = (ROOT / "scripts" / "map_template.html").read_text()
    head = base[:base.index("</style>") + len("</style>")].replace("<title>Riding Spending Map</title>", f"<title>{config['title']}</title>", 1)
    tpl = head + "\n" + (ROOT / "scripts" / "world_template.html").read_text()
    def html_for(nav_urls=None):
        cfg = dict(config, sourcesHref=(nav_urls or {}).get("sources.html", "sources.html"))
        if nav_urls:
            cfg["nav"] = [dict(n, href=nav_urls.get(n["href"], n["href"])) for n in config["nav"]]
        pl = dict(payload, config=cfg)
        return tpl.replace("/*__DATA__*/null", json.dumps(pl, ensure_ascii=False, separators=(",", ":")))
    html = html_for()
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + html.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1) + "</body>\n</html>\n")
    out = OUTDIR / "international.html"
    out.write_text(full)
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")
    (OUTDIR / "artifact_international.html").write_text(html_for(ARTIFACT_URLS))
    return config


def sources(pages):
    """sources.html: every source behind every page (scripts/sources_page.py)."""
    import sources_page
    base = (ROOT / "scripts" / "map_template.html").read_text()
    head = base[:base.index("</style>") + len("</style>")].replace("<title>Riding Spending Map</title>", "<title>Sources</title>", 1)
    nav = [n for n in NAV]
    body, n = sources_page.build(pages, nav, head)
    full = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            + body.replace('<div class="wrap">', '</head>\n<body>\n<div class="wrap">', 1) + "</body>\n</html>\n")
    (OUTDIR / "sources.html").write_text(full)
    (OUTDIR / "artifact_sources.html").write_text(sources_page.build(pages, nav, head, ARTIFACT_URLS)[0])
    print(OUTDIR / "sources.html", f"{n} distinct source addresses")


def main():
    OUTDIR.mkdir(exist_ok=True)
    payload, raw = federal()
    label = {n["href"]: n["label"] for n in NAV}
    src_pages = [("index.html", label["index.html"], payload["config"]["notes"] + [payload["config"].get("linkNote") or ""])]
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
        src_pages.append((f"{key}.html", label.get(f"{key}.html", key), payload["config"]["notes"] + [payload["config"].get("linkNote") or ""]))
        fragment = write_page(payload, key)
        (OUTDIR / f"artifact_{key}.html").write_text(fragment)
        write_csv(raw, ["num", "name", "population", "mla", "mla_party", f"party_{y}", f"runnerup_party_{y}", "margin_votes", "margin_pts",
                        "close", "group", "after_adj", "after_total", "after_n", "before_adj", "before_total", "pc_after", "pc_after_all",
                        "pc_before", "change_pct", "score"], OUTDIR / f"{key}_spending.csv")
    wc = world()
    if wc:
        src_pages.append(("international.html", "International", wc["notes"]))
    order = {n["href"]: i for i, n in enumerate(NAV)}
    sources(sorted(src_pages, key=lambda p: order.get(p[0], 99)))


if __name__ == "__main__":
    main()
