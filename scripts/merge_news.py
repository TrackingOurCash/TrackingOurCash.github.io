"""Merge the news-link results written by the research agents into data/news_links.json,
and write data/news/remaining.json with the grants not yet searched (the web-search budget
is about 200 searches per run, so the queue is worked through in batches)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NEWS = ROOT / "data" / "news"


def searched(v):
    if not isinstance(v, dict):
        return False
    if v.get("searched") is False or "not searched" in (v.get("note") or ""):
        return False
    return bool(v.get("query")) or bool(v.get("mainstream") or v.get("independent"))


def main():
    links_path = ROOT / "data" / "news_links.json"
    out = json.load(open(links_path)) if links_path.exists() else {}
    for path in sorted(NEWS.glob("results_*.json")):
        try:
            data = json.load(open(path))
        except json.JSONDecodeError as e:
            print("skipping", path.name, e)
            continue
        for k, v in data.items():
            if searched(v):
                out[k] = {"mainstream": v.get("mainstream"), "independent": v.get("independent"), "query": v.get("query")}
    json.dump(out, open(links_path, "w"), ensure_ascii=False, indent=0)
    queue = json.load(open(ROOT / "data" / "news_queue.json"))
    remaining = [q for q in queue if q["key"] not in out]
    json.dump(remaining, open(NEWS / "remaining.json", "w"), ensure_ascii=False, indent=0)
    ms = sum(1 for v in out.values() if v.get("mainstream"))
    ind = sum(1 for v in out.values() if v.get("independent"))
    print(f"{len(out)} grants searched: {ms} with a mainstream link, {ind} with an independent link; {len(remaining)} remaining")


if __name__ == "__main__":
    main()
