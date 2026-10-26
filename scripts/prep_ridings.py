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


def load_shapes(ridings):
    shapes = json.load(open(RAW / "fed2023_simple.json"))["objects"]
    ids = {o["name"]: o["external_id"] for o in json.load(open(RAW / "fed2023_list.json"))["objects"]}
    features = []
    for o in shapes:
        num = ids[o["name"]]
        geom = o["simple_shape"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        xs = [p[0] for poly in polys for p in poly[0]]
        ys = [p[1] for poly in polys for p in poly[0]]
        extent = max(max(xs) - min(xs), max(ys) - min(ys))
        tol = max(0.0004, extent / 400)
        min_extent = extent / 200  # drop specks (tiny islands)
        new_polys = []
        for poly in polys:
            ring_x = [p[0] for p in poly[0]]
            ring_y = [p[1] for p in poly[0]]
            if max(max(ring_x) - min(ring_x), max(ring_y) - min(ring_y)) < min_extent:
                continue
            rings = []
            for ring in poly[:1]:  # holes dropped: they're rarely visible at this scale
                # Nunavut's legal boundary runs to the North Pole; cap it just above the
                # northernmost land so the map isn't one giant red wedge.
                ring = [[x, min(y, 83.3)] for x, y in ring]
                s = simplify(ring, tol)
                ring_out = [[round(x, 4), round(y, 4)] for x, y in s]
                # d3-geo wants exterior rings clockwise (negative planar area); the source mixes both.
                area = sum(ring_out[i][0] * ring_out[i + 1][1] - ring_out[i + 1][0] * ring_out[i][1]
                           for i in range(len(ring_out) - 1))
                rings.append(ring_out[::-1] if area > 0 else ring_out)
            new_polys.append(rings)
        features.append({
            "type": "Feature",
            "id": num,
            "properties": {"num": num},
            "geometry": {"type": "MultiPolygon", "coordinates": new_polys},
        })
    return {"type": "FeatureCollection", "features": features}


def main():
    ridings = load_results()
    unmatched = load_mps(ridings)
    geo = load_shapes(ridings)
    json.dump(ridings, open(OUT / "ridings.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "ridings_geo.json", "w"), separators=(",", ":"))
    print(f"{len(ridings)} ridings, {sum(r['mp'] != 'Vacant' for r in ridings.values())} with a current MP")
    print("MP constituencies not matched:", unmatched)
    print("geo bytes:", (OUT / "ridings_geo.json").stat().st_size)


if __name__ == "__main__":
    main()
