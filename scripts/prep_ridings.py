"""Build the riding table (343 ridings, 2023 Representation Order).

Joins Elections Canada 2025 results (winner, runner-up, margin, 2021 population),
the current House of Commons member list, and simplified boundary shapes.

Outputs:
  data/ridings.json        one record per riding
  data/ridings_geo.json    simplified GeoJSON keyed by riding number
"""
import csv
import json
import re
import unicodedata
from pathlib import Path

from fetch_csd import INSETS

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data"

PARTY_SHORT = {
    "Liberal": "LPC",
    "Conservative": "CPC",
    "NDP-New Democratic Party": "NDP",
    "New Democratic Party": "NDP",
    "NDP": "NDP",
    "Bloc Québécois": "BQ",
    "Green Party": "GPC",
    "Independent": "IND",
    "People's Party - PPC": "PPC",
}


def norm(name):
    """Normalize a riding name so EC, House of Commons and Represent spellings match."""
    s = re.sub(r"[–—\-'’]", " ", name)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def party_of(candidate_field):
    """'Paul Connors Liberal/Libéral' -> 'LPC'."""
    eng = candidate_field.split("/")[0]
    for full, short in sorted(PARTY_SHORT.items(), key=lambda kv: -len(kv[0])):
        if eng.endswith(" " + full):
            return short
    for full, short in PARTY_SHORT.items():
        if full in eng:
            return short
    return "OTH"


def load_results():
    ridings = {}
    with open(RAW / "ec2025_table11.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if not row or not row[2].strip().isdigit():
                continue
            num = row[2].strip()
            ridings[num] = {
                "num": num,
                "name": row[1].split("/")[0].strip(),
                "province": row[0].split("/")[0].strip(),
                "population": int(row[3]),
                "electors": int(row[4]),
                "turnout_pct": float(row[11] or 0),
            }
    cands = {}
    with open(RAW / "ec2025_table12.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.reader(f):
            if len(row) < 8 or not row[2].strip().isdigit():
                continue
            cands.setdefault(row[2].strip(), []).append(
                {"name": row[3], "party": party_of(row[3]), "votes": int(row[6]), "pct": float(row[7])}
            )
    for num, cs in cands.items():
        cs.sort(key=lambda c: -c["votes"])
        r = ridings[num]
        win, second = cs[0], cs[1]
        r["winner_2025"] = re.sub(r"\s+(Liberal|Conservative|NDP.*|Bloc.*|Green.*|Independent|People.*)$", "",
                                  win["name"].split("/")[0]).strip().rstrip("* ").strip()
        r["party_2025"] = win["party"]
        r["runnerup_2025"] = re.sub(r"\s+(Liberal|Conservative|NDP.*|Bloc.*|Green.*|Independent|People.*)$", "",
                                    second["name"].split("/")[0]).strip().rstrip("* ").strip()
        r["runnerup_party_2025"] = second["party"]
        r["votes_2025"] = win["votes"]
        r["runnerup_votes_2025"] = second["votes"]
        r["margin_votes"] = win["votes"] - second["votes"]
        r["margin_pts"] = round(win["pct"] - second["pct"], 1)
        r["shares_2025"] = {c["party"]: c["pct"] for c in cs[:4]}
    return ridings


# Ridings renamed after the 2025 election (House of Commons name -> EC riding number).
RENAMED = {
    "North York": "35120",
    "York—South Simcoe": "35069",
    "Vallée-du-Haut-Saint-Laurent": "24007",
    "The Eastern Peninsulas": "10007",
    "Coast of Bays—Central—Notre Dame": "10003",
    "Saskatoon East": "47010",
    "New Brunswick Southwest": "13009",
    "Rimouski-Neigette—Mitis—Matapédia—Les Basques": "24062",
    "Halifax West—Peggy's Cove": "12007",
    "Cariboo—Prince George—Omineca": "59004",
    "Saint-Augustin—Portneuf—Jacques-Cartier": "24058",
    "Argenteuil—Papineau—Des Collines": "24005",
    "Richmond—Arthabaska—des-Sources": "24061",
    "Cape Spear—Mount Pearl—Paradise": "10002",
    "Longueuil—Charles-LeMoyne—Greenfield Park": "24041",
    "Jonquière—Hébertville—Pays-des-Bleuets": "24030",
}


def load_mps(ridings):
    by_name = {norm(r["name"]): r for r in ridings.values()}
    # Represent carries the current official names (some ridings were renamed in 2024).
    for o in json.load(open(RAW / "fed2023_list.json"))["objects"]:
        by_name.setdefault(norm(o["name"]), ridings[o["external_id"]])
    unmatched = []
    with open(RAW / "mps.csv", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            r = by_name.get(norm(row["Constituency"])) or ridings.get(RENAMED.get(row["Constituency"], ""))
            if not r:
                unmatched.append(row["Constituency"])
                continue
            party = row["Political Affiliation"]
            r["mp"] = f'{row["First Name"]} {row["Last Name"]}'.strip()
            r["mp_party"] = PARTY_SHORT.get(party, party)
            r["current_name"] = row["Constituency"]
    for r in ridings.values():
        r.setdefault("mp", "Vacant")
        r.setdefault("mp_party", "")
        r.setdefault("current_name", r["name"].replace("--", "—"))
    return unmatched


def simplify(points, tol):
    """Douglas-Peucker on a ring of [lon, lat]."""
    if len(points) < 5:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        den = (dx * dx + dy * dy) ** 0.5
        best, idx = 0.0, None
        for i in range(a + 1, b):
            px, py = points[i]
            # A closed ring starts and ends on the same point, so the first segment has no
            # length; measure distance from that point instead of from the line.
            d = abs(dy * px - dx * py + bx * ay - by * ax) / den if den > 1e-9 else ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
            if d > best:
                best, idx = d, i
        if idx is not None and best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    out = [p for p, k in zip(points, keep) if k]
    return out if len(out) >= 4 else points[:1] + points[1:-1][:2] + points[-1:]


def densify(ring, step=0.2):
    """Insert points along long straight edges (the 60th parallel, the 141st meridian) so
    d3's great-circle rendering follows the lon/lat line both neighbours were drawn with."""
    out = [ring[0]]
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        n = int(max(abs(x1 - x0), abs(y1 - y0)) / step)
        for i in range(1, n + 1):
            out.append([x0 + (x1 - x0) * i / (n + 1), y0 + (y1 - y0) * i / (n + 1)])
        out.append([x1, y1])
    return out


def clean_polygons(polys, tol, min_extent, cap_lat=None):
    """Simplify a list of GeoJSON polygons (each a list of rings) with one tolerance,
    drop specks, and wind exterior rings clockwise for d3-geo (holes the other way)."""
    new_polys = []
    for poly in polys:
        rings = []
        for i, ring in enumerate(poly):
            if cap_lat is not None:
                ring = [[x, min(y, cap_lat)] for x, y in ring]
            ring_x = [p[0] for p in ring]
            ring_y = [p[1] for p in ring]
            if max(max(ring_x) - min(ring_x), max(ring_y) - min(ring_y)) < min_extent:
                if i == 0:
                    break
                continue
            s = densify(simplify(ring, tol))
            ring_out = [[round(x, 4), round(y, 4)] for x, y in s]
            if len(ring_out) < 4:
                continue
            area = sum(ring_out[j][0] * ring_out[j + 1][1] - ring_out[j + 1][0] * ring_out[j][1]
                       for j in range(len(ring_out) - 1))
            clockwise = area < 0
            if (i == 0) != clockwise:
                ring_out = ring_out[::-1]
            rings.append(ring_out)
        if rings:
            new_polys.append(rings)
    return new_polys


def polys_of(geom):
    return geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]


def load_shapes(ridings):
    shapes = json.load(open(RAW / "fed2023_simple.json"))["objects"]
    ids = {o["name"]: o["external_id"] for o in json.load(open(RAW / "fed2023_list.json"))["objects"]}
    features = []
    for o in shapes:
        num = ids[o["name"]]
        # One tolerance for every riding, so shared borders simplify the same way on both sides.
        # Nunavut's legal boundary runs to the North Pole; cap it just above the northernmost land.
        new_polys = clean_polygons(polys_of(o["simple_shape"]), 0.003, 0.01, cap_lat=83.3)
        features.append({"type": "Feature", "id": num, "properties": {"num": num},
                         "geometry": {"type": "MultiPolygon", "coordinates": new_polys}})
    return {"type": "FeatureCollection", "features": features}


def load_fine_shapes(cache, ids_by_num, tol=0.0004):
    """Full-detail shapes (fetch_shapes.py) for the ridings that touch a city inset,
    lightly simplified. Returns a FeatureCollection; empty when nothing is cached."""
    features = []
    if cache.exists():
        for path in sorted(cache.glob("*.json")):
            num = path.stem
            if num not in ids_by_num:
                continue
            geom = json.load(open(path))
            features.append({"type": "Feature", "id": num, "properties": {"num": num},
                             "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, 0.001)}})
    return {"type": "FeatureCollection", "features": features}


def load_land():
    """Natural Earth 10m coastlines: Canada (the clip for the riding layer), neighbouring
    land for context, and the big lakes to paint back over the ridings."""
    countries = json.load(open(RAW / "ne" / "ne_10m_admin_0_countries.geojson"))["features"]
    lakes = json.load(open(RAW / "ne" / "ne_10m_lakes.geojson"))["features"]
    out = {"type": "FeatureCollection", "features": []}
    for f in countries:
        name = f["properties"].get("ADMIN")
        if name == "Canada":
            out["features"].append({"type": "Feature", "properties": {"kind": "canada"},
                                    "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(f["geometry"]), 0.004, 0.02)}})
        elif name in ("United States of America", "Greenland", "Saint Pierre and Miquelon"):
            # Keep only the parts near Canada.
            polys = [p for p in polys_of(f["geometry"]) if max(pt[1] for pt in p[0]) > 40 and min(pt[0] for pt in p[0]) < -45 and max(pt[0] for pt in p[0]) > -170]
            out["features"].append({"type": "Feature", "properties": {"kind": "other"},
                                    "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys, 0.01, 0.05)}})
    def in_inset(geom):
        coords = geom["coordinates"]
        if geom["type"] == "MultiPolygon":
            pts = [pt for poly in coords for pt in poly[0]]
        elif geom["type"] == "Polygon":
            pts = coords[0]
        elif geom["type"] == "MultiLineString":
            pts = [pt for line in coords for pt in line]
        else:
            pts = coords
        if not pts:
            return False
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        return any(x1 > w and x0 < e and y1 > so and y0 < n for w, so, e, n in INSETS)

    for f in lakes:
        p = f["properties"]
        polys = polys_of(f["geometry"])
        if p.get("scalerank", 9) <= 2 and max(pt[1] for pt in polys[0][0]) > 41 and min(pt[0] for pt in polys[0][0]) < -52:
            out["features"].append({"type": "Feature", "properties": {"kind": "lake", "name": p.get("name")},
                                    "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys, 0.004, 0.02)}})
        elif in_inset(f["geometry"]):
            # Smaller lakes only matter inside the city insets.
            out["features"].append({"type": "Feature", "properties": {"kind": "lake_small", "name": p.get("name")},
                                    "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys, 0.001, 0.002)}})
    rivers = json.load(open(RAW / "ne" / "ne_10m_rivers_lake_centerlines.geojson"))["features"]
    for f in rivers:
        g = f["geometry"]
        if g["type"] not in ("LineString", "MultiLineString") or not in_inset(g):
            continue
        lines = g["coordinates"] if g["type"] == "MultiLineString" else [g["coordinates"]]
        lines = [[[round(x, 4), round(y, 4)] for x, y in simplify(line, 0.001)] for line in lines if len(line) > 1]
        out["features"].append({"type": "Feature", "properties": {"kind": "river", "name": f["properties"].get("name")},
                                "geometry": {"type": "MultiLineString", "coordinates": lines}})
    # Municipal outlines (census subdivisions) fetched by fetch_csd.py, when present.
    for path in sorted((RAW / "csd").glob("*.json")) if (RAW / "csd").exists() else []:
        if path.name == "index.json":
            continue
        c = json.load(open(path))
        if not in_inset(c["shape"]):
            continue  # the riding touched an inset box but this municipality is far outside it
        out["features"].append({"type": "Feature", "properties": {"kind": "muni", "name": c["name"]},
                                "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(c["shape"]), 0.0015, 0.003)}})
    return out


def scale_population(records, province_of):
    """Replace the 2021 census count with an estimate for today: the census count scaled by
    the province's growth since 2021 (data/population_scale.json from population.py).
    The census figure is kept as population_2021."""
    path = OUT / "population_scale.json"
    if not path.exists():
        return None
    scale = json.load(open(path))
    for r in records.values():
        f = scale["provinces"].get(province_of(r), {}).get("factor", 1.0)
        r["population_2021"] = r["population"]
        r["population"] = round(r["population"] * f)
    return scale["latest_date"]


def main():
    ridings = load_results()
    pop_date = scale_population(ridings, lambda r: r["province"])
    unmatched = load_mps(ridings)
    geo = load_shapes(ridings)
    fine = load_fine_shapes(RAW / "shape", ridings)
    land = load_land()
    json.dump(ridings, open(OUT / "ridings.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "ridings_geo.json", "w"), separators=(",", ":"))
    json.dump(land, open(OUT / "land_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "ridings_geo_fine.json", "w"), separators=(",", ":"))
    print(f"{len(ridings)} ridings, {sum(r['mp'] != 'Vacant' for r in ridings.values())} with a current MP; population scaled to {pop_date}")
    print("MP constituencies not matched:", unmatched)
    print("geo bytes:", (OUT / "ridings_geo.json").stat().st_size, "land bytes:", (OUT / "land_geo.json").stat().st_size,
          "fine shapes:", len(fine["features"]), (OUT / "ridings_geo_fine.json").stat().st_size)


if __name__ == "__main__":
    main()
