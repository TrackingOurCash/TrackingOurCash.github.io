"""Postal code -> 2023-order riding, via GeoNames postal-code centroids and
point-in-polygon against the Represent riding boundaries (simple_shape)."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"


def load_centroids():
    """{'K1S5B6': (lat, lon), ...} from GeoNames CA_full.txt."""
    out = {}
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for row in csv.reader(f, delimiter="\t"):
            try:
                out[row[1].replace(" ", "").upper()] = (float(row[9]), float(row[10]))
            except (IndexError, ValueError):
                continue
    return out


class RidingIndex:
    def __init__(self, shapes=None):
        """shapes: iterable of (id, GeoJSON geometry). Defaults to the federal ridings."""
        if shapes is None:
            ids = {o["name"]: o["external_id"] for o in json.load(open(RAW / "fed2023_list.json"))["objects"]}
            shapes = [(ids[o["name"]], o["simple_shape"]) for o in json.load(open(RAW / "fed2023_simple.json"))["objects"]]
        self.polys = []  # (num, bbox, rings)
        for num, g in shapes:
            polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
            for poly in polys:
                xs = [p[0] for p in poly[0]]
                ys = [p[1] for p in poly[0]]
                self.polys.append((num, (min(xs), min(ys), max(xs), max(ys)), poly))

    @staticmethod
    def _in_ring(x, y, ring):
        inside = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i][0], ring[i][1]
            xj, yj = ring[j][0], ring[j][1]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                inside = not inside
            j = i
        return inside

    def locate(self, lat, lon):
        x, y = lon, lat
        for num, (x0, y0, x1, y1), poly in self.polys:
            if x0 <= x <= x1 and y0 <= y <= y1 and self._in_ring(x, y, poly[0]):
                if not any(self._in_ring(x, y, h) for h in poly[1:]):
                    return num, True
        # Not inside any shape (shoreline points, simplification slivers): nearest vertex nearby.
        best, best_d = None, 0.05 ** 2
        for num, (x0, y0, x1, y1), poly in self.polys:
            if x0 - 0.2 <= x <= x1 + 0.2 and y0 - 0.2 <= y <= y1 + 0.2:
                for px, py in poly[0]:
                    d = (px - x) ** 2 + (py - y) ** 2
                    if d < best_d:
                        best, best_d = num, d
        return best, False
