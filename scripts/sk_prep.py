"""Saskatchewan: build the constituency table (61 constituencies, 2022 commission
boundaries, used in the 28 October 2024 general election).

Joins the 2024 poll-by-poll results (winner, runner-up, votes, margin, shares), the
current MLA list, a population figure, and the Elections Saskatchewan KML boundaries.

Sources (downloaded into data/raw/sk/dl/ when missing):
  results   https://cdn.elections.sk.ca/upload/2024-GE-POLL-BY-POLL-RESULTS-v1.0.csv
  MLAs      https://www.legassembly.sk.ca/umbraco/api/mlacontactinformation/GetCsv/1095
  shapes    https://cdn.elections.sk.ca/maps-ge30/ESK_KML_Shape_Files_Mar2024.zip
            (KML/ConstituencyGE30th.kmz inside it)

Defaults chosen here, for want of better data:
  * Population. No census profile exists for the 2022 constituencies, and the 2022
    commission's voting-age table is an image in its PDF, so "population" is the
    number of registered voters at the 2024 election (sum of the poll-level
    "Registered Voters" column). Every record says so in "population_basis". That
    is close to the voting-age basis the commission itself used, and it is what the
    per-capita figures divide by.
  * MLA party. The Assembly's CSV gives the caucus, not the party: Government
    Caucus -> SP, Opposition Caucus -> NDP, Independent -> IND. When the sitting
    MLA is the 2024 winner and the caucus mapping disagrees with the party they
    were elected under, the caucus (current standing) wins and a note is printed.
  * Constituency names are the Assembly's mixed-case spelling; results and shapes
    are matched to them by constituency number, with a normalised-name fallback.

Outputs:
  data/sk/divisions.json           one record per constituency, keyed by number
  data/sk/divisions_geo.json       simplified GeoJSON (tolerance 0.002, min extent 0.005)
  data/sk/divisions_geo_fine.json  lightly simplified GeoJSON for city insets
"""
import csv
import json
import re
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "sk"
DL = RAW / "dl"
OUT = ROOT / "data" / "sk"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons  # noqa: E402

SOURCES = {
    "results_2024.csv": "https://cdn.elections.sk.ca/upload/2024-GE-POLL-BY-POLL-RESULTS-v1.0.csv",
    "mlas.csv": "https://www.legassembly.sk.ca/umbraco/api/mlacontactinformation/GetCsv/1095",
    "boundaries.zip": "https://cdn.elections.sk.ca/maps-ge30/ESK_KML_Shape_Files_Mar2024.zip",
}
# Ballot party codes in the results file -> short labels used on the map.
PARTY = {"SP": "SP", "NDP": "NDP", "SUP": "SUP", "BPSK": "BPSK", "SGP": "SGP", "PC": "PC", "SPP": "SPP", "IND": "IND"}
CAUCUS = {"Government Caucus": "SP", "Opposition Caucus": "NDP", "Independent": "IND"}
POPULATION_BASIS = "registered voters, 2024 general election (Elections Saskatchewan poll-by-poll file)"


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


def fetch_all():
    DL.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = DL / name
        if path.exists() and path.stat().st_size > 0:
            continue
        print("downloading", url, file=sys.stderr)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (riding-spending; python-urllib)"})
        with urllib.request.urlopen(req, timeout=120) as r, open(path, "wb") as f:
            f.write(r.read())


def person(name):
    """'Laliberte, Leroy' -> 'Leroy Laliberte'."""
    name = (name or "").strip()
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def to_int(s):
    s = (s or "").replace(",", "").strip()
    return int(float(s)) if s else 0


def load_results():
    rows = list(csv.DictReader(read_text(DL / "results_2024.csv").splitlines()))
    parties = [c for c in rows[0] if c + " Candidate" in rows[0]]
    votes = defaultdict(Counter)
    cands = defaultdict(dict)
    registered = Counter()
    rejected = Counter()
    names = {}
    for r in rows:
        num = str(int(r["Constituency Number"]))
        names[num] = r["Constituency"].strip()
        registered[num] += to_int(r["Registered Voters"])
        rejected[num] += to_int(r["Rejected"])
        for p in parties:
            votes[num][p] += to_int(r[p])
            if r.get(p + " Candidate", "").strip():
                cands[num][p] = person(r[p + " Candidate"])
    divisions = {}
    for num in sorted(votes, key=int):
        results = sorted(({"name": cands[num].get(p, ""), "party": PARTY.get(p, p), "votes": v}
                          for p, v in votes[num].items() if p in cands[num] or v), key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        win, second = results[0], results[1]
        divisions[num] = {
            "num": num,
            "winner_2024": win["name"], "party_2024": win["party"],
            "runnerup_2024": second["name"], "runnerup_party_2024": second["party"],
            "votes_2024": win["votes"], "runnerup_votes_2024": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2024": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "turnout_pct": round(100 * (valid + rejected[num]) / registered[num], 1) if registered[num] else 0,
            "name": names[num].title().replace("'S", "'s"),
            "population": registered[num],
            "population_basis": POPULATION_BASIS,
        }
    return divisions


def load_mlas(divisions):
    by_name = {norm(d["name"]): d for d in divisions.values()}
    for r in csv.DictReader(read_text(DL / "mlas.csv").splitlines()):
        d = by_name.get(norm(r["Constituency"]))
        if not d:
            print("no constituency for MLA row", r["Constituency"], file=sys.stderr)
            continue
        d["name"] = r["Constituency"].strip()
        d["mla"] = re.sub(r"^(Hon\.|Honourable)\s+", "", r["Name"].strip())
        caucus = r["Party"].strip()
        party = CAUCUS.get(caucus, caucus)
        if norm(d["mla"]) == norm(d["winner_2024"]) and party != d["party_2024"]:
            print(f"note: {d['name']}: {d['mla']} won as {d['party_2024']} in 2024, now sits as {caucus} -> {party}",
                  file=sys.stderr)
        elif norm(d["mla"]) != norm(d["winner_2024"]):
            print(f"note: {d['name']}: sitting MLA {d['mla']} is not the 2024 winner {d['winner_2024']}", file=sys.stderr)
        d["mla_party"] = party
    for d in divisions.values():
        d.setdefault("mla", "Vacant")
        d.setdefault("mla_party", "")


def kml_polygons():
    """-> {constituency number: (name, [polygon, ...])}, each polygon a list of rings of [lon, lat]."""
    with zipfile.ZipFile(DL / "boundaries.zip") as z:
        kmz = z.read("KML/ConstituencyGE30th.kmz")
    tmp = DL / "ConstituencyGE30th.kmz"
    tmp.write_bytes(kmz)
    with zipfile.ZipFile(tmp) as z:
        kml = next(n for n in z.namelist() if n.lower().endswith(".kml"))
        root = ET.fromstring(z.read(kml))
    ns = root.tag.split("}")[0] + "}"
    out = {}
    for pm in root.iter(ns + "Placemark"):
        name = (pm.findtext(ns + "name") or "").strip()
        desc = pm.findtext(ns + "description") or ""
        m = re.search(r"Constitu_1</td>\s*<td>(\d+)</td>", desc)
        num = str(int(m.group(1))) if m else None
        polys = []
        for poly in pm.iter(ns + "Polygon"):
            rings = []
            outer = poly.find(f"{ns}outerBoundaryIs/{ns}LinearRing/{ns}coordinates")
            inners = poly.findall(f"{ns}innerBoundaryIs/{ns}LinearRing/{ns}coordinates")
            for el in [outer] + inners:
                if el is None or not el.text:
                    continue
                ring = []
                for triple in el.text.split():
                    parts = triple.split(",")
                    ring.append([float(parts[0]), float(parts[1])])
                if len(ring) >= 4:
                    rings.append(ring)
            if rings:
                polys.append(rings)
        out[num or name] = (name, polys)
    return out


def load_shapes(divisions):
    by_name = {norm(d["name"]): d["num"] for d in divisions.values()}
    coarse, fine = [], []
    for key, (name, polys) in kml_polygons().items():
        num = key if key in divisions else by_name.get(norm(name))
        if not num:
            print("no constituency for shape", name, file=sys.stderr)
            continue
        for features, tol, min_extent in ((coarse, 0.002, 0.005), (fine, 0.0004, 0.001)):
            features.append({"type": "Feature", "id": num, "properties": {"num": num},
                             "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys, tol, min_extent)}})
    key = lambda f: int(f["id"])
    return ({"type": "FeatureCollection", "features": sorted(coarse, key=key)},
            {"type": "FeatureCollection", "features": sorted(fine, key=key)})


def main():
    fetch_all()
    OUT.mkdir(parents=True, exist_ok=True)
    divisions = load_results()
    load_mlas(divisions)
    geo, fine = load_shapes(divisions)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2024"] for d in divisions.values())
    print(f"{len(divisions)} constituencies, {len(geo['features'])} shapes ({len(fine['features'])} fine), "
          f"{close} close in 2024, seats {dict(seats)}, population basis: {POPULATION_BASIS},",
          sum(d["population"] for d in divisions.values()), "registered voters")


if __name__ == "__main__":
    main()
