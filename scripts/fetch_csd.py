"""Fetch municipal (census subdivision) outlines for the city insets from Represent.

For every riding that touches an inset box, ask Represent which census subdivisions
intersect it, then download each subdivision's simplified shape once. Results are
cached under data/raw/csd/ so reruns only fetch what is missing. Represent allows
about 60 requests a minute, so this paces itself.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CACHE = RAW / "csd"
API = "https://represent.opennorth.ca"
FED = "federal-electoral-districts-2023-representation-order"

# The inset boxes used by build_map.py (federal and Alberta pages): [west, south, east, north].
INSETS = [
    [-123.35, 49.0, -122.45, 49.42], [-123.75, 48.35, -123.25, 48.7], [-114.35, 50.85, -113.85, 51.22],
    [-113.75, 53.38, -113.25, 53.7], [-97.4, 49.72, -96.95, 50.0], [-79.85, 43.5, -79.0, 43.95],
    [-80.2, 43.0, -79.0, 43.45], [-80.7, 43.3, -80.2, 43.6], [-81.4, 42.85, -81.1, 43.1],
    [-76.05, 45.2, -75.4, 45.6], [-74.05, 45.38, -73.4, 45.75], [-71.55, 46.68, -71.1, 46.98],
    [-63.85, 44.55, -63.4, 44.85], [-53.0, 47.4, -52.6, 47.65],
    # Alberta-page insets that aren't federal ones.
    [-113.9, 52.2, -113.7, 52.35], [-112.95, 49.62, -112.75, 49.75], [-111.5, 56.65, -111.3, 56.78], [-118.9, 55.12, -118.7, 55.22],
]


def get(url, pause=1.1):
    time.sleep(pause)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "riding-spending (research)"}), timeout=60) as r:
        return json.load(r)


def bounds(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    return min(xs), min(ys), max(xs), max(ys)


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    shapes = json.load(open(RAW / "fed2023_simple.json"))["objects"]
    ids = {o["name"]: o["external_id"] for o in json.load(open(RAW / "fed2023_list.json"))["objects"]}
    touching = set()
    for o in shapes:
        x0, y0, x1, y1 = bounds(o["simple_shape"])
        for w, s, e, n in INSETS:
            if x1 > w and x0 < e and y1 > s and y0 < n:
                touching.add(ids[o["name"]])
    index_path = CACHE / "index.json"
    index = json.load(open(index_path)) if index_path.exists() else {}
    for i, num in enumerate(sorted(touching)):
        if num in index:
            continue
        q = urllib.parse.urlencode({"intersects": f"{FED}/{num}", "limit": 200, "format": "json"})
        try:
            objs = get(f"{API}/boundaries/census-subdivisions/?{q}")["objects"]
        except Exception as e:  # keep going; the next run fills the gap
            print("riding", num, "failed:", e, file=sys.stderr)
            continue
        index[num] = [{"id": o["external_id"], "name": o["name"]} for o in objs]
        json.dump(index, open(index_path, "w"))
        print(f"{i + 1}/{len(touching)} riding {num}: {len(objs)} subdivisions", flush=True)
    wanted = {c["id"]: c["name"] for cs in index.values() for c in cs}
    for j, (cid, name) in enumerate(sorted(wanted.items())):
        out = CACHE / f"{cid}.json"
        if out.exists():
            continue
        try:
            shp = get(f"{API}/boundaries/census-subdivisions/{cid}/simple_shape")
        except Exception as e:
            print("csd", cid, name, "failed:", e, file=sys.stderr)
            continue
        json.dump({"id": cid, "name": name, "shape": shp}, open(out, "w"))
        print(f"{j + 1}/{len(wanted)} {name}", flush=True)
    print("done:", len(wanted), "subdivisions for", len(touching), "ridings")


if __name__ == "__main__":
    main()
