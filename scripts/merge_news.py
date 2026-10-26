"""Merge the news-link results written by the research agents into data/news_links.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
out = {}
for path in sorted((ROOT / "data" / "news").glob("results_*.json")):
    try:
        out.update(json.load(open(path)))
    except json.JSONDecodeError as e:
        print("skipping", path.name, e)
json.dump(out, open(ROOT / "data" / "news_links.json", "w"), ensure_ascii=False, indent=0)
found = sum(1 for v in out.values() if v.get("mainstream") or v.get("independent"))
print(len(out), "grants checked,", found, "with at least one article")
