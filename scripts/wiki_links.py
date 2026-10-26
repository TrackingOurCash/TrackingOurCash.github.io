"""Find the Wikipedia article for each riding or division, once, via the Wikipedia search API.

Usage: python3 wiki_links.py <level> <json with name per record> ...
  level is "federal", "alberta", "bc", "saskatchewan", "manitoba", "nb" or "pei"; records are read from
  data/ridings.json (federal) or data/<prov>/divisions.json and the links are cached in
  data/wikipedia_links.json as {level: {num: {"title": ..., "url": ...}}}. Reruns only
  look up ridings that have no link yet.
"""
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "riding-spending map (research; jackson.henry.a@pm.me)"
QUERIES = {
    "federal": "{name} federal electoral district",
    "alberta": "{name} provincial electoral district Alberta",
    "bc": "{name} provincial electoral district British Columbia",
    "saskatchewan": "{name} provincial electoral district Saskatchewan",
    "manitoba": "{name} provincial electoral district Manitoba",
    "nb": "{name} provincial electoral district New Brunswick",
    "pei": "{name} provincial electoral district Prince Edward Island",
    "ontario": "{name} provincial electoral district Ontario",
    "quebec": "{name} provincial electoral district Quebec",
}
SOURCES = {
    "federal": (DATA / "ridings.json", "current_name"),
    "alberta": (DATA / "ab" / "divisions.json", "name"),
    "bc": (DATA / "bc" / "divisions.json", "name"),
    "saskatchewan": (DATA / "sk" / "divisions.json", "name"),
    "manitoba": (DATA / "mb" / "divisions.json", "name"),
    "nb": (DATA / "nb" / "divisions.json", "name"),
    "pei": (DATA / "pe" / "divisions.json", "name"),
    "ontario": (DATA / "on" / "divisions.json", "name"),
    "quebec": (DATA / "qc" / "divisions.json", "name"),
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def search(q):
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "list": "search", "srsearch": q, "srlimit": 5, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return json.load(r)["query"]["search"]


def pick(name, results, level):
    """The first result whose title starts with the riding name and looks like a district article."""
    n = norm(name)
    for res in results:
        t = res["title"]
        tn = norm(t)
        if not (tn.startswith(n) or n.startswith(tn.split(" (")[0])):
            continue
        if level == "federal" and "provincial" in tn:
            continue
        if level != "federal":
            if "federal" in tn:
                continue
            snippet = norm(re.sub(r"<[^>]+>", "", res.get("snippet", "")))
            district_like = any(w in tn for w in ("electoral district", "provincial", "riding")) or \
                any(w in snippet for w in ("electoral district", "constituency", "legislative assembly", "provincial electoral"))
            if not district_like:
                continue  # a bare match may be the town, not the district
        return {"title": t, "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"))}
    return None


def exists(title):
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(
        {"action": "query", "titles": title, "redirects": 1, "format": "json"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        pages = json.load(r)["query"]["pages"]
    page = next(iter(pages.values()))
    return None if "missing" in page else page["title"]


def direct(name, level):
    """Fallback: try the usual title patterns directly."""
    suffixes = ["", " (electoral district)"] if level == "federal" else [" (provincial electoral district)", " (electoral district)", ""]
    for suf in suffixes:
        t = exists(name + suf)
        if t and (level == "federal" or "federal" not in t.lower()):
            return {"title": t, "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(t.replace(" ", "_"))}
    return None


def main():
    levels = sys.argv[1:] or list(SOURCES)
    cache_path = DATA / "wikipedia_links.json"
    cache = json.load(open(cache_path)) if cache_path.exists() else {}
    for level in levels:
        path, key = SOURCES[level]
        if not path.exists():
            continue
        recs = json.load(open(path))
        out = cache.setdefault(level, {})
        missing = [(num, r[key]) for num, r in recs.items() if num not in out]
        for i, (num, name) in enumerate(missing):
            try:
                hit = pick(name, search(QUERIES[level].format(name=name)), level) or direct(name, level)
            except Exception as e:
                print(level, name, "failed:", e, file=sys.stderr)
                continue
            out[num] = hit or {"title": None, "url": "https://en.wikipedia.org/w/index.php?search=" + urllib.parse.quote(name + " electoral district")}
            time.sleep(0.25)
            if i % 25 == 24:
                json.dump(cache, open(cache_path, "w"), ensure_ascii=False, indent=0)
        json.dump(cache, open(cache_path, "w"), ensure_ascii=False, indent=0)
        found = sum(1 for v in out.values() if v.get("title"))
        print(f"{level}: {found} of {len(out)} with an article")


if __name__ == "__main__":
    main()
