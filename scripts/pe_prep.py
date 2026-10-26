"""Prince Edward Island: build the electoral-district table (27 districts, 2017 commission
boundaries, used in the 2019 and 3 April 2023 general elections).

PEI publishes no payee list (its Public Accounts Volume II stops at the program level), so
the PEI page shows *federal* grants placed in the provincial districts (pe_spending.py).
This script only prepares the districts: 2023 result, current MLA, population and shapes.

Sources:
  shapes   GeoLinc ArcGIS service Provincial_Electoral_Districts_2017_ELC, layer 0: the 244
           polling divisions with DIST_NO, DISTRICT and electorcou (electors on the list the
           2017 commission worked from). Downloaded as GeoJSON into data/raw/pe/dl/ and
           dissolved into districts here by cancelling the edges two polls share.
  results  data/pe_results.json, curated by hand (Elections PEI and Wikipedia; see
           notes/pe-results-sources.md): every candidate's votes, registered electors and the
           current member of each district, by-elections included.

Defaults chosen here:
  * Population. No census count exists for these districts. Per-person figures use the
    registered electors at the 2023 election (the commission's elector counts when a district
    has none), scaled to Statistics Canada's latest PEI estimate (data/population_scale.json)
    by the ratio of that estimate to the elector total, as the New Brunswick page does.
  * Party codes: PC, LIB, GRN, NDP, IND.
  * Margins and shares use valid votes.

Outputs:
  data/pe/divisions.json           one record per district, keyed by number
  data/pe/divisions_geo.json       simplified GeoJSON (tolerance 0.001, min extent 0.002)
  data/pe/divisions_geo_fine.json  lightly simplified GeoJSON (0.0003) for the city insets
"""
import json
import sys
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "pe"
DL = RAW / "dl"
OUT = ROOT / "data" / "pe"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons  # noqa: E402

POLLS_URL = ("https://geolinc.gov.pe.ca/server/rest/services/Provincial_Electoral_Districts_2017_ELC/MapServer/0/query"
             "?where=DIST_NO%3E0&outFields=DIST_NO,DISTRICT,POLL_NO,POLL_NAME,electorcou&outSR=4326&f=geojson")
INSETS = [[-63.21, 46.22, -63.07, 46.31], [-63.85, 46.38, -63.71, 46.43]]  # Charlottetown, Summerside (also in build_map.py)
POPULATION_BASIS = ("registered electors at the 2023 election (the 2017 commission's count where none is recorded), scaled to "
                    "Statistics Canada's latest PEI estimate by the ratio of that estimate to the elector total")


def fetch_polls():
    DL.mkdir(parents=True, exist_ok=True)
    path = DL / "polls.geojson"
    if not path.exists():
        req = urllib.request.Request(POLLS_URL, headers={"User-Agent": "riding-spending (research)"})
        with urllib.request.urlopen(req, timeout=180) as r:
            path.write_bytes(r.read())
    return json.load(open(path))


def ring_area(ring):
    return abs(sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1))) / 2


def despur(ring):
    """Cut zero-area detours: where a poll's border had an extra vertex its neighbour lacks,
    the long edge and its two halves all survive and the chain runs out and straight back."""
    out, seen = [], {}
    for p in ring:
        if p in seen:
            i = seen[p]
            loop = out[i:] + [p]
            area = sum(loop[k][0] * loop[k + 1][1] - loop[k + 1][0] * loop[k][1] for k in range(len(loop) - 1)) / 2
            if abs(area) < 1e-7:
                for q in out[i + 1:]:
                    seen.pop(q, None)
                del out[i + 1:]
                continue
        seen[p] = len(out)
        out.append(p)
    return out


def despike(ring):
    """Drop spikes: a vertex where the border turns straight back on itself along a path
    under about ten metres wide (the trace of a poll border that nearly, not exactly, matched).
    One pass with a stack, run twice so the join at the ring's start is checked too."""
    def spike(a, b, c):
        ax, ay, cx, cy = a[0] - b[0], a[1] - b[1], c[0] - b[0], c[1] - b[1]
        la, lc = (ax * ax + ay * ay) ** 0.5, (cx * cx + cy * cy) ** 0.5
        if la < 2e-5 or lc < 2e-5:
            return True  # a vertex on top of its neighbour: drop it
        if (ax * cx + ay * cy) / (la * lc) >= -0.99:
            return False
        (sx, sy), (lx, ly), ll = ((cx, cy), (ax, ay), la) if lc < la else ((ax, ay), (cx, cy), lc)
        return abs(sx * ly - sy * lx) / ll < 1e-4
    pts = ring[:-1]
    for _ in range(2):
        if len(pts) < 4:
            return ring
        out = []
        for p in pts:
            out.append(p)
            while len(out) >= 3 and spike(out[-3], out[-2], out[-1]):
                del out[-2]
        pts = out[len(out) // 2:] + out[:len(out) // 2]  # rotate so the old start is mid-ring on the second pass
    return pts + [pts[0]] if len(pts) >= 3 else ring


def dissolve(polys):
    """Union of polygons that share exact borders: every edge two of them share is dropped,
    the rest are chained into rings. polys: GeoJSON polygon coordinate lists."""
    def key(p):
        return (round(p[0], 7), round(p[1], 7))
    count = Counter()
    for poly in polys:
        for ring in poly:
            pts = [key(p) for p in ring]
            for a, b in zip(pts, pts[1:]):
                if a != b:
                    count[frozenset((a, b))] += 1
    adj = defaultdict(set)
    for e, c in count.items():
        if c == 1:
            a, b = tuple(e)
            adj[a].add(b)
            adj[b].add(a)
    rings = []
    while adj:
        start = next(iter(adj))
        ring = [start]
        cur = start
        while True:
            if cur in adj:
                nxt = adj[cur].pop()
                if not adj[cur]:
                    del adj[cur]
                adj[nxt].discard(cur)
                if not adj[nxt]:
                    del adj[nxt]
            else:
                # A T-junction left this vertex with no partner: jump to the nearest loose end.
                cands = [(abs(v[0] - cur[0]) + abs(v[1] - cur[1]), v) for v in adj]
                d, nxt = min(cands) if cands else (9, None)
                if nxt is None or d > 2e-4:
                    break
            ring.append(nxt)
            cur = nxt
            if cur == start:
                break
        if ring[-1] != ring[0]:
            ring.append(ring[0])
        ring = despike(despur(ring))
        area = sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2
        if len(ring) >= 4 and abs(area) > 1e-7:
            rings.append(([list(p) for p in ring], abs(area)))
    # Exterior rings and the holes inside them (PEI's districts have none, but be safe).
    rings.sort(key=lambda r: -r[1])

    def inside(pt, ring):
        x, y = pt
        ok = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi, xj, yj = ring[i][0], ring[i][1], ring[j][0], ring[j][1]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                ok = not ok
            j = i
        return ok
    out = []
    for ring, _ in rings:
        for poly in out:
            if inside(ring[0], poly[0]):
                poly.append(ring)
                break
        else:
            out.append([ring])
    return out


def load_shapes():
    """-> ({num: {'name', 'electors', 'polys'}}, geo, fine)"""
    polls = fetch_polls()["features"]
    by = defaultdict(list)
    info = {}
    for f in polls:
        p = f["properties"]
        num = str(p["DIST_NO"])
        g = f["geometry"]
        by[num].extend(g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]])
        d = info.setdefault(num, {"name": p["DISTRICT"].replace(" - ", "-").strip(), "electors": 0})
        d["electors"] += int(p.get("electorcou") or 0)
    geo = {"type": "FeatureCollection", "features": []}
    fine = {"type": "FeatureCollection", "features": []}
    for num in sorted(by, key=int):
        polys = [p for p in dissolve(by[num]) if ring_area(p[0]) > 1e-6]  # drop specks under about a hectare
        info[num]["parts"] = len(polys)
        geo["features"].append({"type": "Feature", "id": num, "properties": {"num": num},
                                "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys, 0.001, 0.002)}})
        xs = [pt[0] for poly in polys for pt in poly[0]]
        ys = [pt[1] for poly in polys for pt in poly[0]]
        if any(max(xs) > w and min(xs) < e and max(ys) > s and min(ys) < n for w, s, e, n in INSETS):
            fine["features"].append({"type": "Feature", "id": num, "properties": {"num": num},
                                     "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys, 0.0003, 0.0005)}})
    return info, geo, fine


def load_results(info):
    src = json.load(open(ROOT / "data" / "pe_results.json"))
    divisions = {}
    for num, d in src["districts"].items():
        cands = sorted(d["candidates"], key=lambda c: -c["votes"])
        valid = d.get("valid_votes") or sum(c["votes"] for c in cands)
        w, r = cands[0], cands[1]
        shares = Counter()
        for c in cands:
            shares[c["party"]] += c["votes"]
        rec = {
            "num": num, "name": d["name"],
            "winner_2023": w["name"], "party_2023": w["party"], "runnerup_2023": r["name"], "runnerup_party_2023": r["party"],
            "votes_2023": w["votes"], "runnerup_votes_2023": r["votes"],
            "margin_votes": w["votes"] - r["votes"], "margin_pts": round(100 * (w["votes"] - r["votes"]) / valid, 1),
            "shares_2023": {p: round(100 * v / valid, 1) for p, v in shares.most_common()},
            "turnout_pct": d.get("turnout_pct"), "registered_voters_2023": d.get("registered"),
            "mla": d["mla"]["name"], "mla_party": d["mla"]["party"], "mla_note": d["mla"].get("note", ""),
            "electors_commission": info[num]["electors"],
        }
        if rec["name"] != info[num]["name"]:
            print(f"name differs for {num}: results '{rec['name']}', GeoLinc '{info[num]['name']}'", file=sys.stderr)
        divisions[num] = rec
    return divisions


def scale_population(divisions):
    scale = json.load(open(ROOT / "data" / "population_scale.json"))
    estimate = scale["provinces"]["Prince Edward Island"]["estimate"]
    base = {n: (d["registered_voters_2023"] or d["electors_commission"]) for n, d in divisions.items()}
    total = sum(base.values())
    factor = estimate / total
    for n, d in divisions.items():
        d["population"] = round(base[n] * factor)
        d["population_basis"] = POPULATION_BASIS
    return factor, scale["latest_date"], total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    info, geo, fine = load_shapes()
    divisions = load_results(info)
    factor, pop_date, total = scale_population(divisions)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2023"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"{len(divisions)} districts, {len(geo['features'])} shapes ({len(fine['features'])} fine; parts "
          f"{ {n: i['parts'] for n, i in info.items() if i['parts'] > 1} }), {close} close in 2023, seats 2023 {dict(seats)}, now {dict(now)}")
    print(f"population: electors total {total:,}, scaled by {factor:.4f} to {pop_date}: {sum(d['population'] for d in divisions.values()):,}")


if __name__ == "__main__":
    main()
