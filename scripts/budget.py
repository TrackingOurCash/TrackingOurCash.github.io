"""Tie place-named federal budget items to ridings.

Reads data/budget_items.json (hand-curated from the budget documents; each item names
the places the budget text names) and writes data/budget_by_riding.json:
  {"documents": [...], "next": "...", "by_riding": {num: [item, ...]}, "unplaced": [...]}

A place is located by its GeoNames entry (city + province) and point-in-polygon on the
riding boundaries. A city that spans several ridings (Toronto, Edmonton) attaches the
item to every riding its postal codes fall in, marked city-wide, since the budget text
names the city rather than a site.
"""
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from geo import RidingIndex

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
DATA = ROOT / "data"


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def main():
    index = RidingIndex()
    places = defaultdict(list)
    with open(RAW / "geonames" / "CA_full.txt", encoding="utf-8", newline="") as f:
        for r in csv.reader(f, delimiter="\t"):
            try:
                places[(norm(r[2]), r[4])].append((float(r[9]), float(r[10])))
            except (IndexError, ValueError):
                continue

    def ridings_for(place):
        name, _, prov = place.rpartition(",")
        pts = places.get((norm(name), prov.strip()))
        if not pts:
            return None
        step = max(1, len(pts) // 80)
        hits = Counter(index.locate(*p)[0] for p in pts[::step])
        hits.pop(None, None)
        total = sum(hits.values())
        # Ridings holding at least a tenth of the city's postal codes count as "in the city".
        return [n for n, c in hits.most_common() if c >= 0.1 * total] or list(hits)[:1]

    src = json.load(open(DATA / "budget_items.json"))
    by_riding = defaultdict(list)
    unplaced = []
    for i, item in enumerate(src["items"]):
        placed = False
        for place in item["places"]:
            nums = ridings_for(place)
            if not nums:
                continue
            placed = True
            for n in nums:
                if any(r["id"] == i for r in by_riding[n]):
                    continue  # two named places in the same riding: list the item once
                by_riding[n].append(dict(item, id=i, place=place, city_wide=len(nums) > 1))
        if not placed:
            unplaced.append(item)
    out = {"documents": src["documents"], "next": src["next"], "by_riding": dict(by_riding), "unplaced": unplaced}
    json.dump(out, open(DATA / "budget_by_riding.json", "w"), ensure_ascii=False)
    print(f"{len(src['items'])} items, {len(by_riding)} ridings touched, {len(unplaced)} unplaced:",
          [u["places"] for u in unplaced])


if __name__ == "__main__":
    main()
