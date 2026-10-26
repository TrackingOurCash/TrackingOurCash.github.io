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

NAV = [{"href": "index.html", "label": "Federal ridings"}, {"href": "alberta.html", "label": "Alberta"}]
# The published Claude pages live at fixed links; the website uses relative ones.
ARTIFACT_URLS = {"index.html": "https://claude.ai/artifact/J6Va83R2P7m4HKErD6KXgM", "alberta.html": "https://claude.ai/artifact/HniakFetDdXzVWcveb9zy9"}

COMMON = ["population", "margin_pts", "margin_votes", "after_total", "after_n", "after_adj", "after_adj_n",
          "before_adj", "before_total", "pc_after", "pc_after_all", "pc_before", "change_pct", "score", "close",
          "group", "top_grants"]


def links(items):
    return "; ".join(f'<a href="{u}" target="_blank" rel="noopener">{t}</a>' for t, u in items) + "."


def fmt_money(v):
    return "$" + (f"{v / 1e9:.1f}B" if v >= 1e9 else f"{v / 1e6:.0f}M" if v >= 1e6 else f"{v:,.0f}")


def federal():
    sp = json.load(open(DATA / "riding_spending.json"))
    m = sp["meta"]
    mth = m["methods"]
    placed = sum(v for k, v in mth.items() if k.startswith("after|") and "unmapped" not in k)
    ridings = {}
    for n, r in sp["ridings"].items():
        rec = {k: r[k] for k in COMMON}
        rec.update({"num": n, "name": r["current_name"], "region": r["province"], "party_won": r["party_2025"],
                    "runnerup_party": r["runnerup_party_2025"], "winner": r["winner_2025"], "runnerup": r["runnerup_2025"],
                    "shares": r["shares_2025"], "rep": r["mp"], "rep_party": r["mp_party"], "top_progs": r["top_depts"]})
        ridings[n] = rec
    config = {
        "title": "Where federal grants went after the 2025 election",
        "nav": [dict(x, current=x["href"] == "index.html") for x in NAV],
        "level": "riding", "levelPlural": "ridings", "levelTitle": "Riding", "region": "province", "regionTitle": "Prov.",
        "rep": "MP", "electionYear": "2025",
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
            ]) + f" Data as of {m.get('generated', m['cutoff'])}. Code: the pipeline is open and rebuilds the page daily.",
            f"<b>Where money lands:</b> each award is placed at the recipient's address, not where the money is spent. The dataset's own riding field is rarely filled in, so most of the {placed:,} awards since the election were placed by postal code; recipients with no postal code were matched to their address on other awards, then by city. {mth.get('after|unmapped', 0):,} awards worth {fmt_money(mth.get('after|unmapped $', 0))} are still unplaced.",
            "<b>Left out by default:</b> national non-profits booked at a head office (\"Hockey Canada\"), other governments (provinces, cities spread over several ridings), treaty and specific-claim settlements, and foreign aid routed through Canadian partners. Tick the box to put them back. Companies are kept even when \"Canada\" is in their name.",
            f"<b>Amendments</b> are counted once, at the agreement's latest total value. <b>Reporting lag:</b> departments report quarterly, so the window ends at the last quarter that looks fully reported ({m['cutoff']}).",
            "<b>Party is correlation, not credit:</b> ministers and departments approve grants, not local MPs. A pattern by seat type is a signal worth checking, not proof of intent.",
        ],
    }
    budget = json.load(open(DATA / "budget_by_riding.json")) if (DATA / "budget_by_riding.json").exists() else None
    if budget:
        config["notes"].insert(1, "<b>Budget commitments:</b> the dots and the panel's \"Budget commitments\" list come from reading "
                               + " and ".join(f'<a href="{d["url"]}" target="_blank" rel="noopener">{d["name"]}</a>' for d in budget["documents"])
                               + " for every measure that names a place, then locating that place in a riding. Budgets name few places: most measures are national programs, "
                               "and the money reaches ridings later through departmental grants, which is what the map colours show. "
                               f"Items with no amount are projects the budget names without a dollar figure. {budget['next']}")
    payload = {"config": config, "meta": m, "groups": sp["groups"], "ridings": ridings, "dept": sp["dept_by_riding"], "budget": budget,
               "deptBefore": sp["dept_by_riding_before"], "geo": json.load(open(DATA / "ridings_geo.json")), "land": json.load(open(DATA / "land_geo.json")),
               "geoFine": json.load(open(DATA / "ridings_geo_fine.json")) if (DATA / "ridings_geo_fine.json").exists() else {"features": []}}
    return payload, sp["ridings"]


def alberta():
    sp = json.load(open(DATA / "ab" / "division_spending.json"))
    m = sp["meta"]
    ex = m["excluded_after"]
    ridings = {}
    for n, r in sp["ridings"].items():
        rec = {k: r[k] for k in COMMON}
        rec.update({"num": n, "name": r["name"], "region": "Alberta", "party_won": r["party_2023"], "runnerup_party": r["runnerup_party_2023"],
                    "winner": r["winner_2023"], "runnerup": r["runnerup_2023"], "shares": r["shares_2023"], "rep": r["mla"],
                    "rep_party": r["mla_party"], "top_progs": r["top_progs"]})
        ridings[n] = rec
    land = json.load(open(DATA / "land_geo.json"))
    config = {
        "title": "Where Alberta's grants went after the 2023 election",
        "nav": [dict(x, current=x["href"] == "alberta.html") for x in NAV],
        "level": "division", "levelPlural": "divisions", "levelTitle": "Division", "region": "province", "regionTitle": "Prov.",
        "rep": "MLA", "electionYear": "2023",
        "parties": {"UCP": {"name": "United Conservative", "light": "#1b4c9e", "dark": "#4f80d8"}, "NDP": {"name": "NDP", "light": "#f37021", "dark": "#f68a45"},
                    "AP": {"name": "Alberta Party", "light": "#5a9bd5", "dark": "#7fb3e6"}, "GPA": {"name": "Green", "light": "#3d9b35", "dark": "#5cb954"},
                    "PTP": {"name": "Progressive", "light": "#6a4c93", "dark": "#9b7fc4"}, "IND": {"name": "Independent", "light": "#6f6e69", "dark": "#9a9892"}},
        "legendParties": ["UCP", "NDP", "PTP"],
        "flags": {"province-wide": "province-wide body", "other government": "other government"},
        "filterAll": "All programs", "filterOptions": m["programs"],
        "includeLabel": "Include province-wide bodies (health, post-secondary, school divisions) & big-city governments",
        "groupTitle": "Does money follow close seats?", "groups": ["Close UCP", "Close NDP", "Safe UCP", "Safe NDP"],
        "groupNote": f'"Close" means the 2023 winner led by under {m["close_margin"]} points; "UCP" means the governing United Conservatives won the seat in 2023.',
        "groupParty": {"Close UCP": "UCP", "Safe UCP": "UCP", "Close NDP": "NDP", "Safe NDP": "NDP"},
        "regionOrder": None, "regionGroup": {}, "regionShort": {},
        "beforeLabel": "Same length of time before the election", "topProgsTitle": "Top programs", "topGrantsTitle": "Largest recipients since the election",
        "recordUrl": None, "searchUrl": None, "searchLabel": "",
        "linkNote": "Source: Alberta Treasury Board and Finance grant payments disclosure (open.alberta.ca/dataset/grant-disclosure), which lists every payment by recipient, program and date.",
        "projection": {"parallels": [50, 58], "rotate": [114.5, 0]},
        "insets": [["Calgary", [-114.35, 50.85, -113.85, 51.22]], ["Edmonton", [-113.75, 53.38, -113.25, 53.7]], ["Red Deer", [-113.9, 52.2, -113.7, 52.35]],
                   ["Lethbridge", [-112.95, 49.62, -112.75, 49.75]], ["Fort McMurray", [-111.5, 56.65, -111.3, 56.78]], ["Grande Prairie", [-118.9, 55.12, -118.7, 55.22]]],
        "subtitle": (f"Alberta government grant payments from the 29 May 2023 election to {m['cutoff']}, placed in the 87 electoral divisions and set against the 2023 result. "
                     f"Each division wears its current MLA's party colour; the deeper the colour, the more grant money per resident. "
                     f"\"Before\" is the same length of time ending on election day ({m['before_start']} to {m['before_end']})."),
        "notes": [
            "<b>Sources:</b> " + links([
                ("Alberta grant payments disclosure (Treasury Board and Finance)", "https://open.alberta.ca/dataset/grant-disclosure"),
                ("Elections Alberta 2023 Statement of Vote", "https://www.elections.ab.ca/uploads/2023-Provincial-General-Election-Statement-of-Vote.xlsx"),
                ("Legislative Assembly of Alberta member list", "https://www.assembly.ab.ca/members/members-of-the-legislative-assembly"),
                ("2021 census profiles by electoral division", "https://open.alberta.ca/dataset/330635ba-632a-4ad1-a9f6-b8176216cf07"),
                ("Division boundaries, 2019 map (Represent, Open North)", "https://represent.opennorth.ca/boundary-sets/alberta-electoral-districts-2017/"),
                ("CRA list of charities", "https://open.canada.ca/data/en/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8"),
                ("GeoNames postal codes", "https://download.geonames.org/export/zip/"),
                ("Natural Earth coastlines, lakes and rivers", "https://www.naturalearthdata.com/"),
            ]) + f" Data as of {m.get('generated', m['cutoff'])}.",
            f"<b>Placing payments:</b> Alberta publishes recipient names but no addresses. Each recipient was matched by name to a postal code in the federal grants file or the CRA charity list, to a municipality, or to a place name inside its own name, then located in a division. Of {fmt_money(m['total_after'])} paid since the election, {fmt_money(m['placed_after'])} was placed; {fmt_money(ex.get('individual programs', 0))} went through programs that pay individuals (physician fees, AISH, benefits, awards), {fmt_money(ex.get('individuals', 0))} to recipients who look like individuals, {fmt_money(ex.get('province-wide bodies', 0))} to province-wide bodies with no match, and {fmt_money(ex.get('unmatched', 0))} could not be matched.",
            "<b>Left out by default:</b> province-wide bodies booked at a head office (Alberta Health Services, universities and colleges, school divisions, agencies) and the governments of cities that span several divisions (Calgary, Edmonton and others). Tick the box to put them back.",
            "<b>Boundaries:</b> the 87 divisions used in 2023. Alberta's next election will use a new map that is not final yet.",
            "<b>Party is correlation, not credit:</b> ministers and departments approve grants, not local MLAs. A pattern by seat type is a signal worth checking, not proof of intent.",
        ],
    }
    payload = {"config": config, "meta": m, "groups": sp["groups"], "ridings": ridings, "dept": sp["prog_by_riding"], "deptBefore": {},
               "geo": json.load(open(DATA / "ab" / "divisions_geo.json")), "land": land,
               "geoFine": json.load(open(DATA / "ab" / "divisions_geo_fine.json")) if (DATA / "ab" / "divisions_geo_fine.json").exists() else {"features": []}}
    return payload, sp["ridings"]


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
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")
    fragment = render(payload, ARTIFACT_URLS)
    return fragment if name == "index" else fragment.replace("<title>Riding Spending Map</title>", f"<title>{payload['config']['title']}</title>", 1)


def write_csv(rows, cols, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(rows.values(), key=lambda r: -r["pc_after"]):
            w.writerow([r.get(c) for c in cols])


def main():
    OUTDIR.mkdir(exist_ok=True)
    payload, raw = federal()
    fragment = write_page(payload, "index")
    (OUTDIR / "artifact.html").write_text(fragment)
    write_csv(raw, ["num", "current_name", "province", "population", "mp", "mp_party", "party_2025", "runnerup_party_2025", "margin_votes",
                    "margin_pts", "close", "group", "after_adj", "after_total", "after_n", "before_adj", "before_total", "pc_after",
                    "pc_after_all", "pc_before", "change_pct", "score"], OUTDIR / "riding_spending.csv")
    if (DATA / "ab" / "division_spending.json").exists():
        payload, raw = alberta()
        fragment = write_page(payload, "alberta")
        (OUTDIR / "artifact_alberta.html").write_text(fragment)
        write_csv(raw, ["num", "name", "population", "mla", "mla_party", "party_2023", "runnerup_party_2023", "margin_votes", "margin_pts",
                        "close", "group", "after_adj", "after_total", "after_n", "before_adj", "before_total", "pc_after", "pc_after_all",
                        "pc_before", "change_pct", "score"], OUTDIR / "alberta_spending.csv")


if __name__ == "__main__":
    main()
