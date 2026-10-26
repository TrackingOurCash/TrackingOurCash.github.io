"""Yukon: build the electoral-district table for the 3 November 2025 general election: the 21
districts of the Electoral District Boundaries Act (S.Y. 2024, c. 14), the 2024 commission's map.

The 2024 Electoral District Boundaries Commission (final report tabled 9 October 2024, Act
assented November 2024) raised the Assembly from 19 to 21 seats: Whistle Bend was split into
Whistle Bend North and Whistle Bend South, Takhini-Kopper King became Takhini, Golden Horn was
merged with Mount Lorne and Marsh Lake, Teslin with the Southern Lakes, and Watson Lake with Ross
River and Faro. Represent's yukon-electoral-districts-2015 set (19 districts) therefore does NOT
apply.

Inputs (data/raw/yt/):
  electoral_districts_2024.geojson  GeoYukon "Yukon Electoral Districts" (Geomatics Yukon, Open
                                    Government Licence - Yukon; "Official Electoral Districts of
                                    the Yukon, dated November 21, 2024, issued under the authority
                                    of the Chief Electoral Officer"), queried as GeoJSON from
                                    mapservices.gov.yk.ca layer 75 and cached; downloaded here
                                    when missing.
  official_results_2025.json        Elections Yukon's official results table (Official Addition of
                                    6 November 2025; Vuntut Gwitchin confirmed by the 12 November
                                    judicial recount), transcribed by hand because electionsyukon.ca
                                    sits behind a Cloudflare check that refuses scripts. Electors,
                                    valid votes and every candidate's votes per district.
  Current MLAs: yukonassembly.ca/mlas (also behind Cloudflare), read on 26 October 2026 and
  written into MLAS below with the 22 November 2025 cabinet (yukon.ca news release "Currie Dixon
  sworn in as the Yukon's 12th Premier"). No by-election, resignation or floor crossing had
  happened by 26 October 2026.

Choices made here:
  * num is Elections Yukon's ED number (1-21, alphabetical).
  * Party codes: YP (Yukon Party), LIB (Yukon Liberal Party), NDP (Yukon New Democratic Party),
    IND. Margins and shares use valid votes; turnout_pct is voters / electors per district
    (Elections Yukon publishes only the territory-wide 53.1%, computed the same way, so the
    per-district figure here uses valid votes and is a touch low).
  * Population: no census or commission count exists per district that can be cited directly
    (the commission's final report is not online), and the Whitehorse area, with four Yukoners in
    five, is cut into 13 districts plus parts of Lake Laberge and Marsh Lake-Mount Lorne-Golden
    Horn, so community populations cannot be summed. Population is therefore the REGISTERED
    ELECTORS at the 2025 election scaled to Statistics Canada's latest Yukon estimate
    (data/population_scale.json) by the ratio of that estimate to the elector total, as the PEI
    and Québec pages do; population_basis says so.

Outputs: data/yt/divisions.json, divisions_geo.json (tol 0.002, min extent 0.005),
divisions_geo_fine.json (tol 0.0004, min 0.001; districts touching the Whitehorse inset).
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from territories import fetch, make_record, scale_population, write_outputs  # noqa: E402

RAW = ROOT / "data" / "raw" / "yt"
OUT = ROOT / "data" / "yt"
YEAR = 2025
SHAPES_URL = ("https://mapservices.gov.yk.ca/arcgis/rest/services/GeoYukon/GY_AdministrativeBoundaries/MapServer/75/query"
              "?where=1%3D1&outFields=*&outSR=4326&f=geojson")
INSETS = [[-135.2, 60.65, -134.9, 60.8]]  # Whitehorse (also in build_map.py)
POPULATION_BASIS = ("registered electors at the 3 November 2025 election (Elections Yukon official results), scaled to "
                    "Statistics Canada's latest Yukon estimate by the ratio of that estimate to the elector total; no census "
                    "count exists for these districts and the Whitehorse area is cut into 15 of them")
# yukonassembly.ca/mlas, 26 October 2026; cabinet from the 22 November 2025 swearing-in.
CABINET = {
    "Currie Dixon": "Premier; Minister of Finance; Minister responsible for the Executive Council Office",
    "Scott Kent": "Minister of Education; Minister responsible for the Yukon Housing Corporation; Government House Leader",
    "Brad Cathers": "Minister of Health and Social Services",
    "Wade Istchenko": "Minister of Environment",
    "Ted Laking": "Minister of Energy, Mines and Resources; Minister responsible for the Yukon Development Corporation and Yukon Energy Corporation",
    "Laura Lang": "Minister of Justice; Minister responsible for the French Language Services Directorate, the Women and Gender Equity Directorate and the Workers' Safety and Compensation Board",
    "Cory Bellmore": "Minister of Community Services; Minister responsible for the Yukon Lottery Commission",
    "Linda Benoit": "Minister of Highways and Public Works",
    "Jen Gehmair": "Minister of Economic Development; Minister of Tourism and Culture; Minister responsible for the Public Service Commission and the Yukon Liquor Corporation",
}
OTHER_ROLES = {"Yvonne Clarke": "Speaker (since 8 December 2025)", "Kate White": "Leader of the Official Opposition",
               "Lane Tredger": "Official Opposition House Leader", "Debra-Leigh Reti": "Leader of the Third Party"}
MLAS = {  # district -> (name, party) as yukonassembly.ca lists them
    "Copperbelt North": ("Currie Dixon", "YP"), "Copperbelt South": ("Scott Kent", "YP"), "Klondike": ("Brent McDonald", "NDP"),
    "Kluane": ("Wade Istchenko", "YP"), "Lake Laberge": ("Brad Cathers", "YP"),
    "Marsh Lake-Mount Lorne-Golden Horn": ("Jen Gehmair", "YP"), "Mayo-Tatchun": ("Cory Bellmore", "YP"),
    "Mountainview": ("Linda Moen", "NDP"), "Porter Creek Centre": ("Ted Laking", "YP"), "Porter Creek North": ("Doris Anderson", "YP"),
    "Porter Creek South": ("Adam Gerle", "YP"), "Riverdale North": ("Carmen Gustafson", "NDP"), "Riverdale South": ("Justin Ziegler", "NDP"),
    "Southern Lakes": ("Tyler Porter", "YP"), "Takhini": ("Kate White", "NDP"), "Vuntut Gwitchin": ("Debra-Leigh Reti", "LIB"),
    "Watson Lake-Ross River-Faro": ("Patti McLeod", "YP"), "Whistle Bend North": ("Yvonne Clarke", "YP"),
    "Whistle Bend South": ("Linda Benoit", "YP"), "Whitehorse Centre": ("Lane Tredger", "NDP"), "Whitehorse West": ("Laura Lang", "YP"),
}
RESULT_NOTES = {"Vuntut Gwitchin": "confirmed unchanged by the 12 November 2025 judicial recount (margin of seven votes)"}


def norm(name):
    return re.sub(r"[^a-z]", "", name.lower())


def load_results():
    src = json.load(open(RAW / "official_results_2025.json"))
    divisions = {}
    for d in src["districts"]:
        name = d["name"]
        mla, party = MLAS[name]
        note = CABINET.get(mla) or OTHER_ROLES.get(mla) or ""
        rec = make_record(YEAR, d["num"], name, [(v, n, p) for v, n, p in d["candidates"]], d["electors"],
                          round(100 * d["valid"] / d["electors"], 1), mla, party, note, valid=d["valid"],
                          result_note=RESULT_NOTES.get(name))
        divisions[d["num"]] = rec
    return divisions


def load_shapes(divisions):
    path = fetch(SHAPES_URL, RAW / "electoral_districts_2024.geojson")
    by_name = {norm(d["name"]): num for num, d in divisions.items()}
    geoms = {}
    for f in json.load(open(path))["features"]:
        key = norm(f["properties"]["ELECTORAL_DISTRICT_NAME"])
        if key not in by_name:
            print("shape with no district:", f["properties"]["ELECTORAL_DISTRICT_NAME"], file=sys.stderr)
            continue
        geoms[by_name[key]] = f["geometry"]
    return geoms


def main():
    divisions = load_results()
    factor, pop_date, total = scale_population(divisions, "Yukon", {n: d[f"registered_voters_{YEAR}"] for n, d in divisions.items()},
                                               POPULATION_BASIS)
    divisions = dict(sorted(divisions.items(), key=lambda kv: int(kv[0])))
    geoms = load_shapes(divisions)
    geo, fine = write_outputs(OUT, divisions, geoms, INSETS, 0.002, 0.005)
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d[f"party_{YEAR}"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"Yukon: {len(divisions)} districts, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in {YEAR}, "
          f"seats {YEAR} {dict(seats)}, sitting {dict(now)}")
    print(f"population: {total:,} registered electors scaled by {factor:.4f} to {pop_date}: {sum(d['population'] for d in divisions.values()):,}")
    print("geo bytes:", (OUT / "divisions_geo.json").stat().st_size, "fine bytes:", (OUT / "divisions_geo_fine.json").stat().st_size)


if __name__ == "__main__":
    main()
