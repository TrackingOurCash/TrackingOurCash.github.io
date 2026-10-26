"""British Columbia: build the electoral-district table (93 districts, 2023 redistribution).

Joins the 2024 general election results by voting place (winner, runner-up, votes,
margin), 2021 census population by district, and Elections BC's boundaries from the
provincial WFS server. Mirrors ab_prep.py; keys use "2024" where Alberta uses "2023".

Inputs (downloaded into data/raw/bc/; the URLs are in notes/provincial-sources.md):
  eds_2023.geojson             WFS GetFeature, EPSG:4326, fields ED_ABBREVIATION, ED_NAME
  results_by_voting_place.csv  provincial voting results by voting place (2022-2024 events)
  census_2021_ped93_part1.csv  BC Stats census profile, wide: one column per district

Outputs:
  data/bc/divisions.json         one record per district, keyed by ED_ABBREVIATION
  data/bc/divisions_geo.json     simplified GeoJSON (clean_polygons, tol 0.002, min 0.005)
  data/bc/divisions_geo_fine.json  lighter simplification (tol 0.0004) for the city insets:
                                 districts whose bounding box is under 1.2 degrees across
                                 (the coastal and northern districts would add 1.4 MB of
                                 shoreline no inset shows)

Choices made here:
  * The district key ("num") is Elections BC's three-letter ED_ABBREVIATION (e.g. "SRG"),
    not a number: BC has no numbering in the public files.
  * Results: 2024 Provincial General Election rows only (by-elections are dropped), vote
    category "Valid", VOTES_CONSIDERED summed per candidate per district. Voting places
    whose results are combined into another place (COMBINED_INDICATOR = Y) carry 0 votes
    and the receiving place carries the total, so a plain sum is right. No registered-voter
    count is in the file, so there is no turnout_pct.
  * Party codes (AFFILIATION -> short label): "BC NDP" -> NDP, "Conservative Party" -> BCC,
    "BC Green Party" -> GPBC, "Independent" or blank (no affiliation) -> IND,
    "Freedom Party of BC" -> FPBC, "Libertarian" -> LBT, "Communist Party of BC" -> CPBC,
    "Christian Heritage Party of B.C." -> CHP.
  * Current MLAs: the legislature was dissolved for the 24 October 2026 election and no
    member list is published, so mla = the 2024 winner and mla_party = their party, with
    "mla_note" on every record saying so. Replace once results are final (18 Nov 2026).
  * Population: the "Total - Age groups of the population - 100% data" row (Gender = Total)
    of the census profile, matched to districts by normalised name. Unmatched -> 0, printed.
"""
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "bc"
OUT = ROOT / "data" / "bc"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons, polys_of  # noqa: E402

PARTY = {"BC NDP": "NDP", "Conservative Party": "BCC", "BC Green Party": "GPBC", "Independent": "IND", "": "IND",
         "Freedom Party of BC": "FPBC", "Libertarian": "LBT", "Communist Party of BC": "CPBC",
         "Christian Heritage Party of B.C.": "CHP"}
EVENT = "2024 Provincial General Election"
MLA_NOTE = "2024 winner; the October 2026 election results are not final until 18 November 2026"


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def read_text(path):
    raw = open(path, "rb").read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def person(name):
    """'Begg, Garry' -> 'Garry Begg'."""
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name.strip()


def party_of(affiliation):
    a = (affiliation or "").strip()
    if a in PARTY:
        return PARTY[a]
    code = "".join(w[0] for w in re.findall(r"[A-Za-z]+", a) if w.lower() not in ("of", "the", "party"))[:5].upper()
    print("unknown affiliation", repr(a), "->", code, file=sys.stderr)
    return code or "IND"


def load_results():
    votes = defaultdict(lambda: defaultdict(int))  # (num) -> (candidate, affiliation) -> votes
    names = {}
    elected = {}
    for r in csv.DictReader(read_text(RAW / "results_by_voting_place.csv").splitlines()):
        if r["EVENT_NAME"] != EVENT or r["VOTE_CATEGORY"] != "Valid":
            continue
        num = r["ED_ABBREVIATION"].strip()
        names[num] = r["ED_NAME"].strip()
        votes[num][(r["CANDIDATE"].strip(), r["AFFILIATION"].strip())] += int(r["VOTES_CONSIDERED"] or 0)
        if r["ELECTED"] == "Y":
            elected[num] = r["CANDIDATE"].strip()
    divisions = {}
    for num, cands in votes.items():
        results = sorted(({"name": person(c), "party": party_of(a), "votes": v} for (c, a), v in cands.items()),
                         key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        win, second = results[0], results[1]
        if num in elected and person(elected[num]) != win["name"]:
            print(f"{num}: ELECTED flag says {elected[num]} but most votes went to {win['name']}", file=sys.stderr)
        divisions[num] = {
            "num": num,
            "winner_2024": win["name"], "party_2024": win["party"],
            "runnerup_2024": second["name"], "runnerup_party_2024": second["party"],
            "votes_2024": win["votes"], "runnerup_votes_2024": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2024": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "name": names[num],
        }
    return divisions


def load_mlas(divisions):
    """No member list exists while the house is dissolved; the 2024 winner stands in."""
    for d in divisions.values():
        d["mla"] = d["winner_2024"]
        d["mla_party"] = d["party_2024"]
        d["mla_note"] = MLA_NOTE


def load_population(divisions):
    rows = list(csv.reader(read_text(RAW / "census_2021_ped93_part1.csv").splitlines()))
    header = rows[0]
    by_name = {norm(d["name"]): d["num"] for d in divisions.values()}
    total = next(r for r in rows[1:] if r[1].strip() == "Total" and r[2].strip().startswith("Total - Age groups"))
    for col, value in zip(header[4:], total[4:]):
        num = by_name.get(norm(col))
        if num:
            divisions[num]["population"] = int(value.replace(",", "") or 0)
        elif norm(col) != "british columbia":
            print("census column matches no district:", col, file=sys.stderr)
    for d in divisions.values():
        if d.setdefault("population", 0) == 0:
            print("no population for", d["num"], d["name"], file=sys.stderr)


def load_shapes(divisions, tol, min_extent):
    features = []
    for f in json.load(open(RAW / "eds_2023.geojson"))["features"]:
        num = f["properties"]["ED_ABBREVIATION"]
        if num not in divisions:
            print("no district for shape", num, f["properties"]["ED_NAME"], file=sys.stderr)
            continue
        features.append({"type": "Feature", "id": num, "properties": {"num": num},
                         "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(f["geometry"]), tol, min_extent)}})
    features.sort(key=lambda f: f["id"])
    return {"type": "FeatureCollection", "features": features}


def extent(feature):
    pts = [p for poly in feature["geometry"]["coordinates"] for ring in poly for p in ring]
    return max(max(p[0] for p in pts) - min(p[0] for p in pts), max(p[1] for p in pts) - min(p[1] for p in pts))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    divisions = load_results()
    load_mlas(divisions)
    load_population(divisions)
    divisions = dict(sorted(divisions.items()))
    geo = load_shapes(divisions, 0.002, 0.005)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    fine = load_shapes(divisions, 0.0004, 0.001)
    fine["features"] = [f for f in fine["features"] if extent(f) < 1.2]
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    print("fine shapes:", len(fine["features"]))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    print(f"{len(divisions)} districts, {len(geo['features'])} shapes, {close} close in 2024,",
          sum(d["population"] for d in divisions.values()), "people")


if __name__ == "__main__":
    main()
