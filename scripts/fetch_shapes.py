"""Fetch full-detail boundaries from Represent for ridings that touch a city inset.

Represent's simple_shape is too coarse at city scale, so for the insets we use the
unsimplified shape and simplify it ourselves lightly. Cached under data/raw/shape/
(federal) and data/raw/ab/shape/ (Alberta); reruns fetch only what is missing.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
API = "https://represent.opennorth.ca"

SETS = [
    ("federal-electoral-districts-2023-representation-order", RAW / "fed2023_simple.json", RAW / "fed2023_list.json", RAW / "shape", None),
    ("alberta-electoral-districts-2017", RAW / "ab" / "ab2017_simple.json", RAW / "ab" / "ab2017_list.json", RAW / "ab" / "shape",
     [[-114.35, 50.85, -113.85, 51.22], [-113.75, 53.38, -113.25, 53.7], [-113.9, 52.2, -113.7, 52.35],
      [-112.95, 49.62, -112.75, 49.75], [-111.5, 56.65, -111.3, 56.78], [-118.9, 55.12, -118.7, 55.22]]),
]


def get(url, pause=1.1):
    time.sleep(pause)
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "riding-spending (research)"}), timeout=120) as r:
        return json.load(r)


def bounds(geom):
    polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    return min(xs), min(ys), max(xs), max(ys)


def main():
    from fetch_csd import INSETS
    for set_name, simple_path, list_path, cache, boxes in SETS:
        boxes = boxes or INSETS
        if not simple_path.exists():
            continue
        cache.mkdir(parents=True, exist_ok=True)
        ids = {o["name"]: o["external_id"] for o in json.load(open(list_path))["objects"]}
        wanted = []
        for o in json.load(open(simple_path))["objects"]:
            x0, y0, x1, y1 = bounds(o["simple_shape"])
            if any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in boxes):
                wanted.append(ids[o["name"]])
        for i, num in enumerate(sorted(wanted)):
            out = cache / f"{num}.json"
            if out.exists():
                continue
            try:
                shp = get(f"{API}/boundaries/{set_name}/{num}/shape")
            except Exception as e:
                print(set_name, num, "failed:", e, file=sys.stderr)
                continue
            json.dump(shp, open(out, "w"))
            print(f"{set_name}: {i + 1}/{len(wanted)} {num}", flush=True)
        print(set_name, "done:", len(wanted), "shapes")


if __name__ == "__main__":
    main()
