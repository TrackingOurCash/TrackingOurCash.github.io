"""Last gate before the site is published: run.sh calls it after build_map.py.

Fails (exit 1, so the workflow does not deploy and the live site stays as it was) when a page
is missing, has no data in it, or has shrunk to under 60% of the page now live on the website
(LIVE_URL, set by the workflow; skipped when the live site can't be reached).
Writes output/status.json either way: build time, data windows, every warning run.sh logged
(sources that were down, layers that fell back to their last good copy) and page sizes.
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"
DATA = ROOT / "data"
PAGES = ["index.html", "budget.html", "byelections.html", "bc.html", "alberta.html", "saskatchewan.html", "manitoba.html", "ontario.html", "quebec.html",
         "nb.html", "pei.html", "ns.html", "nl.html", "yukon.html", "nwt.html", "nunavut.html", "international.html", "sources.html"]


def live_size(base, page):
    try:
        with urllib.request.urlopen(f"{base.rstrip('/')}/{page}", timeout=30) as r:
            return len(r.read())
    except Exception:  # noqa: BLE001
        return None


def main():
    problems, sizes = [], {}
    base = os.environ.get("LIVE_URL")
    for p in PAGES:
        f = OUT / p
        if not f.exists():
            problems.append(f"{p} was not built")
            continue
        html = f.read_text(errors="replace")
        sizes[p] = len(html.encode())
        if "/*__DATA__*/null" in html:
            problems.append(f"{p} has no data in it")
        if p != "sources.html" and sizes[p] < 300_000:
            problems.append(f"{p} is only {sizes[p]:,} bytes")
        if base:
            live = live_size(base, p)
            if live and sizes[p] < 0.6 * live:
                problems.append(f"{p} shrank from {live:,} to {sizes[p]:,} bytes against the live site")
    warnings = [w for w in (DATA / "build_warnings.txt").read_text().splitlines() if w.strip()] if (DATA / "build_warnings.txt").exists() else []
    meta = {}
    if (DATA / "riding_spending.json").exists():
        m = json.load(open(DATA / "riding_spending.json"))["meta"]
        meta = {"federal_data_generated": m.get("generated"), "election": m.get("election"), "federal_window_end": m.get("cutoff")}
    status = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta, "ok": not problems, "problems": problems,
              "warnings": warnings, "pages": sizes}
    OUT.mkdir(exist_ok=True)
    json.dump(status, open(OUT / "status.json", "w"), indent=1)
    for w in warnings:
        print("warning:", w)
    if problems:
        print("site check FAILED: " + "; ".join(problems))
        sys.exit(1)
    print(f"site check ok: {len(sizes)} pages, {len(warnings)} warnings")


if __name__ == "__main__":
    main()
