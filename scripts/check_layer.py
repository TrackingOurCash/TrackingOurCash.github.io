"""Sanity check for a provincial layer after a rebuild: data/<dir>/division_spending.json must
exist, parse, and carry some money in the after-election window, and divisions_geo.json must
have shapes. run.sh restores the committed copy of the layer when this fails, so a source that
is unreachable on build day (an archive 429, a moved PDF) cannot publish an empty map."""
import json
import sys
from pathlib import Path


def after_total(node):
    if isinstance(node, dict):
        return sum((v if isinstance(v, (int, float)) and k == "after_total" else after_total(v)) for k, v in node.items())
    if isinstance(node, list):
        return sum(after_total(x) for x in node)
    return 0


def main():
    d = Path(sys.argv[1])
    try:
        total = after_total(json.load(open(d / "division_spending.json")))
        shapes = len(json.load(open(d / "divisions_geo.json")).get("features", []))
    except Exception as e:  # noqa: BLE001
        sys.exit(f"{d}: unreadable ({e})")
    if total <= 0 or shapes == 0:
        sys.exit(f"{d}: after_total {total:,.0f}, {shapes} shapes; rejecting")
    print(f"{d}: ok, ${total:,.0f} after the election across {shapes} shapes")


if __name__ == "__main__":
    main()
