"""Northwest Territories: build the electoral-district table for the 14 November 2023 general
election (postponed from 3 October by the wildfire evacuations): the 19 districts of Schedule A
of the Legislative Assembly and Executive Council Act, unchanged since the 2013 redistribution
(used in 2015, 2019 and 2023).

The NWT has consensus government: every candidate runs as an independent, so party is "IND" for
all 19 and mla_note records what the Assembly made of each member (Premier, minister with
portfolios, Speaker, regular member).

Inputs (data/raw/nt/):
  electoral_districts_2023.geojson  GNWT Centre for Geomatics, Boundaries_LCC map service layer 2
                                    "Electoral District" (attribute ElectoralYear = 2023), queried
                                    as GeoJSON (WGS84) and cached; downloaded here when missing.
                                    This is the service Represent's northwest-territories-
                                    electoral-districts-2013 set was dumped from.
  official_results_2023.json        Elections NWT, Territorial General Election 2023 Official
                                    Results Report (January 2024; the PDF is cached beside it as
                                    2023_official_results.pdf): every candidate's votes, rejected
                                    and declined ballots, registered electors and turnout per
                                    district, plus the electors on each polling community's list.
                                    See the note inside the file for how it was transcribed.
  wiki_List_of_communities_in_the_Northwest_Territories.json
                                    Wikipedia's community list (MediaWiki API wikitext), which
                                    carries Statistics Canada's 2021 census count for every
                                    community; cached, downloaded here when missing.
  Current members and cabinet: gov.nt.ca/en/cabinet (last modified 18 September 2026) and the
  Wikipedia page for the 20th Assembly, read on 26 October 2026, written into ROLES below.

Changes since the election (to 26 October 2026):
  * R.J. Simpson (Hay River North) was chosen Premier and Shane Thompson (Nahendeh) Speaker on
    7 December 2023; the six ministers were chosen the same day.
  * Lesa Semmler (Inuvik Twin Lakes), Minister of Health and Social Services, resigned from
    cabinet and the Assembly on 17 September 2026 (Wikipedia; Elections NWT). Lucy Kuptana took
    Health and Social Services. The seat is vacant: the by-election is set for 24 November 2026
    (writ 26 October 2026). The record keeps the 2023 result and shows the MLA as "Vacant".

Choices made here:
  * num: Elections NWT gives the districts no number, so num is the 1-based position in Elections
    NWT's alphabetical order (the order of the official results report), as a string.
  * Margins and shares use valid votes (the candidates' votes; rejected and declined ballots are
    left out); turnout_pct is Elections NWT's figure (votes cast / registered).
  * Acclamations (Kam Lake, Monfwi, Yellowknife South): no votes, margin_pts 100, result_note.
  * Population: the 2021 census count of each community (Statistics Canada, via Wikipedia's
    community list), summed into districts. Districts made of whole communities get the sum;
    Yellowknife (seven districts plus the Ndilǫ poll of Tu Nedhé-Wiilideh, which the census counts
    inside the city), Hay River (two districts) and Inuvik (two districts) are shared out by each
    district's registered electors in that community at the 2023 election. The result is scaled to
    Statistics Canada's latest NWT estimate (data/population_scale.json) by the ratio of that
    estimate to the census total; population_2021 keeps the unscaled figure.

Outputs: data/nt/divisions.json, divisions_geo.json (tol 0.002, min extent 0.005),
divisions_geo_fine.json (tol 0.0004, min 0.001; districts touching the Yellowknife inset).
"""
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from territories import census_2021_nwt, fetch, make_record, scale_population, wiki_wikitext, write_outputs  # noqa: E402

RAW = ROOT / "data" / "raw" / "nt"
OUT = ROOT / "data" / "nt"
YEAR = 2023
SHAPES_URL = ("https://www.apps.geomatics.gov.nt.ca/arcgis/rest/services/GNWT/Boundaries_LCC/MapServer/2/query"
              "?where=1%3D1&outFields=OBJECTID,ED,EDFrench,ElectoralYear&outSR=4326&f=geojson")
INSETS = [[-114.45, 62.42, -114.3, 62.5]]  # Yellowknife (also in build_map.py)
POPULATION_BASIS = ("2021 census population of the district's communities (Statistics Canada), Yellowknife, Hay River and Inuvik "
                    "shared between their districts by registered electors at the 2023 election, scaled to Statistics Canada's "
                    "latest NWT estimate by the ratio of that estimate to the census total")
# gov.nt.ca/en/cabinet (18 September 2026) and the Assembly; "Regular member" for the rest.
ROLES = {
    "R.J. Simpson": "Cabinet: Premier; Minister of Executive and Indigenous Affairs (chosen 7 December 2023)",
    "Caitlin Cleveland": "Cabinet: Minister of Education, Culture and Employment; Minister of Industry, Tourism and Investment",
    "Lucy Kuptana": "Cabinet: Minister of Health and Social Services (since September 2026, after Lesa Semmler's resignation); "
                    "Minister responsible for Housing NWT and for the Status of Women",
    "Jay MacDonald": "Cabinet: Minister of Environment and Climate Change; Minister of Justice",
    "Vince McKay": "Cabinet: Minister of Municipal and Community Affairs; Minister of Infrastructure; Minister responsible for the "
                   "Workers' Safety and Compensation Commission and the Public Utilities Board",
    "Caroline Wawzonek": "Cabinet: Deputy Premier; Minister of Finance; Minister responsible for Strategic Infrastructure, Energy "
                         "and Supply Chains and for the NWT Power Corporation",
    "Shane Thompson": "Speaker (chosen 7 December 2023)",
}
VACANT = {"Inuvik Twin Lakes": "Vacant: Lesa Semmler, Minister of Health and Social Services since December 2023, resigned on "
                               "17 September 2026; by-election 24 November 2026"}
# Census names (Wikipedia's list) for the polling communities named in the results file.
CENSUS_NAME = {"Hay River Reserve": "Hay River Reserve", "Behchokǫ̀": "Behchokǫ̀", "Whatì": "Whatì", "Gamètì": "Gamèti", "Wekweètì": "Wekweètì",
               "Sambaa K'e": "Sambaa K'e", "Délı̨nę": "Délı̨nę", "Łutselk'e": "Łutselk'e"}


def norm(name):
    return re.sub(r"[^a-z]", "", name.lower().replace("é", "e"))


def load_results():
    src = json.load(open(RAW / "official_results_2023.json"))
    divisions, communities = {}, {}
    for i, d in enumerate(sorted(src["districts"], key=lambda d: d["name"]), start=1):
        num = str(i)
        name = d["name"]
        if "acclaimed" in d:
            cands, turnout = [(None, d["acclaimed"], "IND")], None
        else:
            cands, turnout = [(v, n, "IND") for v, n in d["candidates"]], d["turnout_pct"]
        winner = cands[0][1] if "acclaimed" in d else max(cands)[1]
        if name in VACANT:
            mla, note = "Vacant", VACANT[name]
        else:
            mla, note = winner, ROLES.get(winner, "Regular member")
        divisions[num] = make_record(YEAR, num, name, cands, d["registered"], turnout, mla, "IND", note)
        communities[num] = d["communities"]
    return divisions, communities


def census_population(divisions, communities):
    text = wiki_wikitext("List of communities in the Northwest Territories", RAW / "wiki_List_of_communities_in_the_Northwest_Territories.json")
    census = census_2021_nwt(text)
    by_norm = {norm(k): v for k, v in census.items()}
    # electors per community across districts, to share split communities
    electors_total = defaultdict(int)
    for num, comms in communities.items():
        for c, e in comms.items():
            electors_total[c] += e
    base = {}
    for num, comms in communities.items():
        pop = 0.0
        for c, e in comms.items():
            key = norm(CENSUS_NAME.get(c, c))
            if key not in by_norm:
                raise SystemExit(f"no 2021 census count for {c!r} ({divisions[num]['name']}); census names: {sorted(census)}")
            shared = electors_total[c] > e  # the community has polls in more than one district
            pop += by_norm[key] * (e / electors_total[c] if shared else 1.0)
        base[num] = pop
        divisions[num]["population_2021"] = round(pop)
    return base, sum(census.values())


def load_shapes(divisions):
    path = fetch(SHAPES_URL, RAW / "electoral_districts_2023.geojson")
    by_name = {norm(d["name"]): num for num, d in divisions.items()}
    geoms = {}
    for f in json.load(open(path))["features"]:
        key = norm(f["properties"]["ED"])
        if key not in by_name:
            print("shape with no district:", f["properties"]["ED"], file=sys.stderr)
            continue
        if f["properties"].get("ElectoralYear") != YEAR:
            print("shape year", f["properties"].get("ElectoralYear"), "for", f["properties"]["ED"], file=sys.stderr)
        geoms[by_name[key]] = f["geometry"]
    return geoms


def main():
    divisions, communities = load_results()
    base, census_total = census_population(divisions, communities)
    factor, pop_date, total = scale_population(divisions, "Northwest Territories", base, POPULATION_BASIS)
    geoms = load_shapes(divisions)
    geo, fine = write_outputs(OUT, divisions, geoms, INSETS, 0.002, 0.005)
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    cabinet = sum(d["mla_note"].startswith("Cabinet") for d in divisions.values())
    speaker = sum(d["mla_note"].startswith("Speaker") for d in divisions.values())
    vacant = sum(d["mla"] == "Vacant" for d in divisions.values())
    acclaimed = sum("result_note" in d for d in divisions.values())
    print(f"NWT: {len(divisions)} districts, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in {YEAR} "
          f"({acclaimed} acclaimed), all IND; cabinet {cabinet} (Premier included), speaker {speaker}, "
          f"regular {len(divisions) - cabinet - speaker - vacant}, vacant {vacant}")
    print(f"population: communities' 2021 census {round(total):,} (territory {census_total:,}) scaled by {factor:.4f} to {pop_date}: "
          f"{sum(d['population'] for d in divisions.values()):,}")
    print("geo bytes:", (OUT / "divisions_geo.json").stat().st_size, "fine bytes:", (OUT / "divisions_geo_fine.json").stat().st_size)


if __name__ == "__main__":
    main()
