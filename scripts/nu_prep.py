"""Nunavut: build the constituency table for the 27 October 2025 general election: the 22
constituencies of the Nunavut Elections Act as amended by Bill 48, An Act Respecting the
Constituencies of Nunavut (assented 31 May 2024, in force on the dissolution of the 6th Assembly),
which implemented part of the Nunavut Electoral Boundaries Commission Report 2023. The names are
the same 22 as in 2021; the authoritative boundaries are the Chief Electoral Officer's "Official
Digital Version of Nunavut's Constituencies Maps 2024".

Nunavut has consensus government: every candidate runs as an independent, so party is "IND" for
all 22 and mla_note records what the Assembly made of each member (Premier, minister with
portfolios, Speaker, regular member).

Inputs (data/raw/nu/):
  EN_FUTURE_NU_Constituencies.zip / shp/   Elections Nunavut, "Maps of Constituencies - GIS shape
                                    file" (elections.nu.ca/en/documents), the 2024 constituencies
                                    ("FUTURE" when it was posted in 2024), NAD83 CSRS degrees, with
                                    English, French, Inuktitut and Inuinnaqtun names; downloaded and
                                    unzipped here when missing.
  results/823.html ... 844.html     Elections Nunavut's official results page for each constituency
                                    of the 2025 general election (elections.nu.ca/en/elections/
                                    results/2498/data/<id>): every candidate's votes, rejected
                                    ballots, electors on the list (and per community for multi-
                                    community constituencies), turnout; downloaded when missing.
  results/aggu_new_election_823.html  the 15 December 2025 Aggu new election (results/2823/data/823).
  results/hudson_bay_byelection_831.html  the 28 September 2026 Hudson Bay by-election (results/2906/data/831).
  wiki_List_of_municipalities_in_Nunavut.json  Wikipedia's municipality list (MediaWiki API wikitext)
                                    with Statistics Canada's 2021 census count per community.
  Current members and cabinet: assembly.nu.ca/members/mla and the 20 November 2025 Government of
  Nunavut release "Premier Main announces cabinet portfolios", read on 26 October 2026 (ROLES below).

Changes since the election (to 26 October 2026):
  * Aggu tied (Joanna Quassa 105, Erasmus Ivvalu 105, confirmed by the judicial recount), so under
    s. 149(2) of the Act a new election was held on 15 December 2025: Edward Attagutaluk won (86
    of 190 votes, six candidates). The record shows the tie as the 2025 result (winner "Tie",
    margin 0) and Attagutaluk as the sitting MLA.
  * Hudson Bay: Daniel Qavvik (acclaimed in 2025) resigned on 1 June 2026; Jason Iqaluq won the
    by-election of 28 September 2026 (168 of 228 votes, 469 on the list).
  * The 7th Assembly chose John Main (Arviat North-Whale Cove) Premier and David Joanasie (South
    Baffin) Speaker on 18 November 2025; the eight ministers were chosen the same day and got
    their portfolios on 20 November 2025.

Choices made here:
  * num: Elections Nunavut gives the constituencies no number, so num is the 1-based position in
    Elections Nunavut's alphabetical order, as a string.
  * Margins and shares use valid votes; turnout_pct is Elections Nunavut's figure.
  * Acclamations (Hudson Bay, South Baffin): no votes, margin_pts 100, result_note; Elections
    Nunavut publishes no elector count for them, so registered_voters_2025 is null.
  * Population: the 2021 census count of each community (Statistics Canada, via Wikipedia's
    municipality list; the Act's constituencies are whole communities plus the land around them)
    summed into constituencies. Iqaluit (four), Arviat (two), Rankin Inlet (two) and Igloolik
    (two) are shared out by each constituency's electors on the list in that community at the
    2025 election. The result is scaled to Statistics Canada's latest Nunavut estimate
    (data/population_scale.json) by the ratio of that estimate to the census total;
    population_2021 keeps the unscaled figure.

Outputs: data/nu/divisions.json, divisions_geo.json (tol 0.01, min extent 0.02, latitude capped
at 83.3 as prep_ridings does), divisions_geo_fine.json (tol 0.0004, min 0.001; the four Iqaluit
constituencies, which touch the Iqaluit inset).
"""
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from territories import census_2021_nunavut, fetch, make_record, read_shapefile, scale_population, strip_html, wiki_wikitext, write_outputs  # noqa: E402

RAW = ROOT / "data" / "raw" / "nu"
OUT = ROOT / "data" / "nu"
YEAR = 2025
SITE = "https://www.elections.nu.ca"
SHP_URL = f"{SITE}/sites/default/files/documents/EN_FUTURE_NU_Constituencies.zip"
RESULT_IDS = range(823, 845)  # the 22 constituencies, alphabetical, of election 2498
INSETS = [[-68.6, 63.72, -68.45, 63.78]]  # Iqaluit (also in build_map.py)
POPULATION_BASIS = ("2021 census population of the constituency's communities (Statistics Canada), Iqaluit, Arviat, Rankin Inlet "
                    "and Igloolik shared between their constituencies by electors on the list at the 2025 election, scaled to "
                    "Statistics Canada's latest Nunavut estimate by the ratio of that estimate to the census total")
COMMUNITIES = {  # elections.nu.ca/en/constituency-map
    "Aggu": ["Igloolik"], "Aivilik": ["Naujaat", "Coral Harbour"], "Amittuq": ["Igloolik", "Sanirajak"],
    "Arviat North-Whale Cove": ["Arviat", "Whale Cove"], "Arviat South": ["Arviat"], "Baker Lake": ["Baker Lake"],
    "Cambridge Bay": ["Cambridge Bay"], "Gjoa Haven": ["Gjoa Haven"], "Hudson Bay": ["Sanikiluaq"],
    "Iqaluit-Manirajak": ["Iqaluit"], "Iqaluit-Niaqunnguu": ["Iqaluit"], "Iqaluit-Sinaa": ["Iqaluit"], "Iqaluit-Tasiluk": ["Iqaluit"],
    "Kugluktuk": ["Kugluktuk"], "Netsilik": ["Taloyoak", "Kugaaruk"], "Pangnirtung": ["Pangnirtung"],
    "Quttiktuq": ["Arctic Bay", "Grise Fiord", "Resolute Bay"], "Rankin Inlet North-Chesterfield Inlet": ["Rankin Inlet", "Chesterfield Inlet"],
    "Rankin Inlet South": ["Rankin Inlet"], "South Baffin": ["Kinngait", "Kimmirut"], "Tununiq": ["Pond Inlet"],
    "Uqqummiut": ["Clyde River", "Qikiqtarjuaq"],
}
CENSUS_NAME = {"Resolute Bay": "Resolute"}
# assembly.nu.ca/members/mla and the 20 November 2025 portfolio release; "Regular member" for the rest.
ROLES = {
    "John Main": "Cabinet: Premier; Minister of Executive and Intergovernmental Affairs; Minister of Finance (chosen 18 November 2025)",
    "George Hickes": "Cabinet: Deputy Premier; Minister of Justice; Minister of Transportation and Infrastructure Nunavut",
    "David Akeeagok": "Cabinet: Government House Leader; Minister of Education; Minister responsible for Nunavut Arctic College",
    "Janet Pitsiulaaq Brewster": "Cabinet: Minister of Health",
    "Gwen Healey Akearok": "Cabinet: Minister of Family Services; Minister responsible for the Qulliq Energy Corporation",
    "Brian Koonoo": "Cabinet: Minister of Environment; Minister of Culture and Heritage",
    "Cecile Nelvana Lyall": "Cabinet: Minister responsible for the Nunavut Housing Corporation",
    "Craig Simailak": "Cabinet: Minister of Community Services",
    "Annie Tattuinee": "Cabinet: Minister of Human Resources",
    "David Joanasie": "Speaker (chosen 18 November 2025)",
}
SITTING = {  # constituencies whose member is not the 2025 general-election winner
    "Aggu": ("Edward Attagutaluk", "Regular member; won the 15 December 2025 new election held after the 27 October 2025 vote tied "
                                   "(Joanna Quassa and Erasmus Ivvalu, 105 votes each)"),
    "Hudson Bay": ("Jason Iqaluq", "Regular member; won the 28 September 2026 by-election after Daniel Qavvik (acclaimed in 2025) "
                                   "resigned on 1 June 2026"),
}


def norm(name):
    return re.sub(r"[^a-z]", "", name.lower())


def fetch_results():
    for i in RESULT_IDS:
        fetch(f"{SITE}/en/elections/results/2498/data/{i}", RAW / "results" / f"{i}.html")
    fetch(f"{SITE}/en/elections/results/2823/data/823", RAW / "results" / "aggu_new_election_823.html")
    fetch(f"{SITE}/en/elections/results/2906/data/831", RAW / "results" / "hudson_bay_byelection_831.html")


def parse_results_page(path):
    """-> dict(name, acclaimed | candidates [(votes, name)], rejected, votes_cast, electors, turnout_pct, electors_by_community)"""
    t = strip_html(open(path, encoding="utf-8").read())
    t = t[t.find("Home Territorial Elections"):t.find("Contact 41 Sivulliq")]
    t = re.sub(r"\b2025 Territorial General Election\b|Home Territorial Elections|Aggu New Election Results|By-election Hudson Bay", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    m = re.match(r"(.+?) Acclaimed (.+)$", t)
    if m and "Total Votes" not in t:
        return {"name": m.group(1).strip(), "acclaimed": m.group(2).strip()}
    m = re.match(r"(?P<name>.+?) (?:Elected (?P<elected>.+?) Total Votes: \d+|.*?Tie vote.*?December 15, 2025) (?P<cast>\d+) Total Votes "
                 r"Voter Turnout: (?P<turnout>[\d.]+)% Total voters on list: (?P<electors>\d+)(?P<rest>.*)$", t)
    if not m:
        raise SystemExit(f"cannot parse {path}: {t[:300]}")
    rest = m.group("rest")
    by_comm = {c: int(n) for c, n in re.findall(r"Total voters for ([A-Za-z' ]+?): (\d+)", rest)}
    table = rest[rest.find("Total Votes", rest.find("Poll by poll")) + len("Total Votes"):]
    cands, rejected = [], 0
    for cm in re.finditer(r"([A-Za-z' .\-]+?) ((?:\d+ )+)(?=[A-Z]|$)", table):
        name, nums = cm.group(1).strip(), cm.group(2).split()
        total = int(nums[-1])
        if name == "Rejected Ballots":
            rejected = total
        elif name == "Total Votes":
            break
        else:
            cands.append((total, name))
    return {"name": m.group("name").strip(), "candidates": cands, "rejected": rejected, "votes_cast": int(m.group("cast")),
            "electors": int(m.group("electors")), "turnout_pct": float(m.group("turnout")), "electors_by_community": by_comm}


def load_results():
    fetch_results()
    pages = [parse_results_page(RAW / "results" / f"{i}.html") for i in RESULT_IDS]
    pages.sort(key=lambda p: p["name"])
    by_election = parse_results_page(RAW / "results" / "hudson_bay_byelection_831.html")
    assert by_election["candidates"][0][1] == "Jason Iqaluq", by_election
    divisions, electors_in = {}, {}
    for i, p in enumerate(pages, start=1):
        num, name = str(i), p["name"]
        if name not in COMMUNITIES:
            raise SystemExit(f"unexpected constituency {name!r}")
        if "acclaimed" in p:
            cands, electors, turnout, note = [(None, p["acclaimed"], "IND")], None, None, None
        else:
            cands = [(v, n, "IND") for v, n in p["candidates"]]
            electors, turnout, note = p["electors"], p["turnout_pct"], None
            if cands[0][0] == cands[1][0] == max(c[0] for c in cands):
                note = "tie; a new election under s. 149(2) of the Nunavut Elections Act was held on 15 December 2025"
        winner = cands[0][1] if "acclaimed" in p else max(cands)[1]
        mla, role = SITTING.get(name, (winner, ROLES.get(winner, "Regular member")))
        rec = make_record(YEAR, num, name, cands, electors, turnout, mla, "IND", role, result_note=note)
        if note and note.startswith("tie"):
            rec[f"winner_{YEAR}"] = "Tie"
        divisions[num] = rec
        comms = COMMUNITIES[name]
        if len(comms) == 1:
            electors_in[num] = {comms[0]: electors or 0}
        else:
            missing = set(comms) - set(p.get("electors_by_community", {}))
            if missing and "acclaimed" not in p:
                raise SystemExit(f"{name}: no elector count for {missing}")
            electors_in[num] = {c: p.get("electors_by_community", {}).get(c, 0) for c in comms}
    return divisions, electors_in


def census_population(divisions, electors_in):
    text = wiki_wikitext("List of municipalities in Nunavut", RAW / "wiki_List_of_municipalities_in_Nunavut.json")
    census = census_2021_nunavut(text)
    by_norm = {norm(k): v for k, v in census.items()}
    districts_of = defaultdict(list)
    for num, comms in electors_in.items():
        for c in comms:
            districts_of[c].append(num)
    base = {}
    for num, comms in electors_in.items():
        pop = 0.0
        for c, e in comms.items():
            key = norm(CENSUS_NAME.get(c, c))
            if key not in by_norm:
                raise SystemExit(f"no 2021 census count for {c!r}; census names: {sorted(census)}")
            others = districts_of[c]
            if len(others) == 1:
                pop += by_norm[key]
            else:
                total_e = sum(electors_in[o][c] for o in others)
                pop += by_norm[key] * e / total_e
        base[num] = pop
        divisions[num]["population_2021"] = round(pop)
    return base, sum(census.values())


def load_shapes(divisions):
    zip_path = fetch(SHP_URL, RAW / "EN_FUTURE_NU_Constituencies.zip")
    shp_dir = RAW / "shp"
    shp = shp_dir / "EN_FUTURE_NU_Constituencies.shp"
    if not shp.exists():
        shp_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(shp_dir)
    by_name = {norm(d["name"]): num for num, d in divisions.items()}
    geoms = {}
    for attrs, geom in read_shapefile(shp):
        key = norm(attrs["Name_E"])
        if key not in by_name:
            print("shape with no constituency:", attrs["Name_E"], file=sys.stderr)
            continue
        geoms[by_name[key]] = geom
    return geoms


def main():
    divisions, electors_in = load_results()
    base, census_total = census_population(divisions, electors_in)
    factor, pop_date, total = scale_population(divisions, "Nunavut", base, POPULATION_BASIS)
    geoms = load_shapes(divisions)
    geo, fine = write_outputs(OUT, divisions, geoms, INSETS, 0.01, 0.02, cap_lat=83.3)
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    cabinet = sum(d["mla_note"].startswith("Cabinet") for d in divisions.values())
    speaker = sum(d["mla_note"].startswith("Speaker") for d in divisions.values())
    acclaimed = sum(d.get("result_note") == "acclaimed" for d in divisions.values())
    print(f"Nunavut: {len(divisions)} constituencies, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in {YEAR} "
          f"({acclaimed} acclaimed, Aggu tied), all IND; cabinet {cabinet} (Premier included), speaker {speaker}, regular {len(divisions) - cabinet - speaker}")
    print(f"population: communities' 2021 census {round(total):,} (territory {census_total:,}) scaled by {factor:.4f} to {pop_date}: "
          f"{sum(d['population'] for d in divisions.values()):,}")
    print("geo bytes:", (OUT / "divisions_geo.json").stat().st_size, "fine bytes:", (OUT / "divisions_geo_fine.json").stat().st_size)


if __name__ == "__main__":
    main()
