"""Manitoba: build the electoral-division table (57 divisions, 2018 commission
boundaries, used in the 2019 and 3 October 2023 general elections).

Joins the 2023 results (winner, runner-up, votes, margin, shares), the current MLA
list, the 2018 commission's per-division population, and Represent's boundaries.

Sources (downloaded into data/raw/mb/dl/ when missing):
  results    https://www.electionsmanitoba.ca/downloads/43GE%20Summary%20of%20Votes%20Received.xlsx
             (every candidate, party and vote count; the runner-up comes from here)
             https://www.electionsmanitoba.ca/downloads/Summary_of_Results_GE2023.xlsx
             (one row per division: member elected, registered voters, plurality; used
             as a cross-check)
  MLAs       https://www.gov.mb.ca/legislature/members/mla_list_constituency.html
             (constituency | name | party; by-elections since 2023 are reflected)
  population https://www.boundariescommission.mb.ca/wp-content/uploads/edbc-final-report-2018-en.pdf
             (Appendix C tables, 2016 census population of each final division)
  shapes     Represent boundary set manitoba-electoral-districts-2018 (simple_shape
             for the province; full /shape, fetched one per 1.1 s and cached in
             data/raw/mb/shape/, for divisions touching the Winnipeg or Brandon inset)

Defaults chosen here:
  * Division numbers. Neither Elections Manitoba's files nor Represent carry a
    division number, so "num" is the position (1-57) in the alphabetical list of
    English names, which is the order Elections Manitoba publishes.
  * Names are the Legislative Assembly's spelling ("St. Boniface", "La Vérendrye");
    the bilingual results names ("Brandon East/Brandon-Est") are cut at the slash.
  * Party codes: NDP, PC, LIB (ballot code MLP, Manitoba Liberal Party), GPM (Green),
    IND; minor parties keep their ballot code (KP, CPC-M, MP). The Assembly lists
    Cindy Lamoureux as "IND LIB"; that is recorded as LIB.
  * Population is the 2018 commission's 2016-census count for each division (the only
    per-division census figure for these boundaries). It is scaled to today by the
    ratio of Statistics Canada's latest Manitoba estimate (data/population_scale.json,
    1,517,379 at 1 July 2026) to the commission total, so per-capita figures are on
    the same footing as the other provinces; the raw count is kept as population_2016
    and "population_basis" says so. No population_2021 is written because there is
    no 2021 census figure for these divisions.
  * Margins and shares use valid votes (declined and rejected ballots excluded).

Outputs:
  data/mb/divisions.json           one record per division, keyed by number
  data/mb/divisions_geo.json       simplified GeoJSON (tolerance 0.002, min extent 0.005)
  data/mb/divisions_geo_fine.json  lightly simplified GeoJSON (0.0004) for the insets
"""
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "mb"
DL = RAW / "dl"
SHAPES = RAW / "shape"
OUT = ROOT / "data" / "mb"
sys.path.insert(0, str(ROOT / "scripts"))
from ab_prep import xlsx_sheets  # noqa: E402
from prep_ridings import clean_polygons, polys_of  # noqa: E402
from sk_pdf import pdf_pages  # noqa: E402

API = "https://represent.opennorth.ca"
BOUNDARY_SET = "manitoba-electoral-districts-2018"
SOURCES = {
    "mb2018_list.json": f"{API}/boundaries/{BOUNDARY_SET}/?limit=100",
    "mb2018_simple.json": f"{API}/boundaries/{BOUNDARY_SET}/simple_shape?limit=100",
    "43GE_Summary_of_Votes_Received.xlsx": "https://www.electionsmanitoba.ca/downloads/43GE%20Summary%20of%20Votes%20Received.xlsx",
    "Summary_of_Results_GE2023.xlsx": "https://www.electionsmanitoba.ca/downloads/Summary_of_Results_GE2023.xlsx",
    "mla_list_constituency.html": "https://www.gov.mb.ca/legislature/members/mla_list_constituency.html",
    "edbc-final-report-2018-en.pdf": "https://www.boundariescommission.mb.ca/wp-content/uploads/edbc-final-report-2018-en.pdf",
}
# Winnipeg and Brandon inset boxes [west, south, east, north]: divisions touching them get full shapes.
INSETS = [[-97.4, 49.72, -96.95, 50.0], [-100.05, 49.78, -99.85, 49.9]]
PARTY = {"NDP": "NDP", "PC": "PC", "MLP": "LIB", "LIB": "LIB", "GPM": "GPM", "IND": "IND", "IND LIB": "LIB",
         "KP": "KP", "CPC-M": "CPC-M", "MP": "MP"}
POPULATION_BASIS = ("2016 census (boundary commission), scaled to Statistics Canada's latest Manitoba estimate "
                    "by the ratio of that estimate to the commission total")
UA = {"User-Agent": "Mozilla/5.0 (riding-spending; python-urllib)"}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def get(url, path, pause=1.0):
    if path.exists() and path.stat().st_size > 0:
        return
    print("downloading", url, file=sys.stderr)
    time.sleep(pause)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())


def fetch_all():
    DL.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        get(url, DL / name)


def person(name):
    """'KENNEDY, Hon. Nellie' -> 'Nellie Kennedy'."""
    name = re.sub(r"\s+", " ", (name or "").replace("\n", " ")).strip()
    name = re.sub(r"\b(Hon|Honourable)\.?\s+", "", name)
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip().title() if last.strip().isupper() else last.strip()}"
    return name


def is_num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


def english(name):
    return name.split("/")[0].strip()


def load_results():
    """One record per division from the candidate-level workbook."""
    divisions = {}
    cur = None
    for _, rows in xlsx_sheets(DL / "43GE_Summary_of_Votes_Received.xlsx"):
        for r in rows:
            if r.get("A") and r.get("C") and is_num(r.get("D")):
                cur = {"name": english(r["A"]), "cands": [], "registered": 0, "cast": 0}
                divisions[cur["name"]] = cur
            if cur is None:
                continue
            if r.get("C") and r.get("B") and is_num(r.get("D")) and r["B"] not in ("Declined", "Rejected"):
                party = r["C"].strip()
                cur["cands"].append({"name": person(r["B"]), "party": PARTY.get(party, party),
                                     "votes": int(float(r.get("D") or 0))})
            elif is_num(r.get("G")) and not r.get("B"):
                cur["registered"] = int(float(r["G"]))
                cur["cast"] = int(float(r.get("F") or 0))
    # Cross-check with the one-row-per-division summary.
    summary = {}
    for _, rows in xlsx_sheets(DL / "Summary_of_Results_GE2023.xlsx"):
        for r in rows:
            if r.get("B") and r.get("C") and is_num(r.get("D")):
                summary[english(r["A"])] = (person(r["B"]), PARTY.get(r["C"].strip(), r["C"].strip()), int(float(r["D"])))
    out = {}
    for i, name in enumerate(sorted(divisions, key=norm), 1):
        d = divisions[name]
        results = sorted(d["cands"], key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        win, second = results[0], results[1]
        num = str(i)
        if name in summary and (norm(summary[name][0]) != norm(win["name"]) or summary[name][1] != win["party"]):
            print(f"warning: {name}: summary says {summary[name][:2]}, candidate file says {win['name']} {win['party']}", file=sys.stderr)
        out[num] = {
            "num": num,
            "winner_2023": win["name"], "party_2023": win["party"],
            "runnerup_2023": second["name"], "runnerup_party_2023": second["party"],
            "votes_2023": win["votes"], "runnerup_votes_2023": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2023": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "turnout_pct": round(100 * d["cast"] / d["registered"], 1) if d["registered"] else 0,
            "registered_voters_2023": d["registered"],
            "name": name,
        }
    if len(out) != 57:
        print(f"warning: {len(out)} divisions parsed, expected 57", file=sys.stderr)
    return out


def load_mlas(divisions):
    by_name = {norm(d["name"]): d for d in divisions.values()}
    text = open(DL / "mla_list_constituency.html", encoding="utf-8", errors="replace").read()
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) != 3 or cells[0] == "Constituency":
            continue
        d = by_name.get(norm(cells[0]))
        if not d:
            print("no division for MLA row", cells, file=sys.stderr)
            continue
        d["name"] = re.sub(r"\s+", " ", cells[0])
        d["mla"] = person(cells[1])
        party = re.sub(r"\s+", " ", cells[2]).strip()
        d["mla_party"] = PARTY.get(party, party)
        if norm(d["mla"]) != norm(d["winner_2023"]):
            print(f"note: {d['name']}: sitting MLA {d['mla']} ({d['mla_party']}) is not the 2023 winner {d['winner_2023']}", file=sys.stderr)
        elif d["mla_party"] != d["party_2023"]:
            print(f"note: {d['name']}: {d['mla']} won as {d['party_2023']}, now sits as {d['mla_party']}", file=sys.stderr)
    for d in divisions.values():
        d.setdefault("mla", "Vacant")
        d.setdefault("mla_party", "")


def load_population(divisions):
    """2016 census counts from the commission report's Appendix C (final divisions)."""
    rows = {}
    active = False
    for page in pdf_pages(DL / "edbc-final-report-2018-en.pdf"):
        for line in page:
            if line.startswith("Table") and "Final (2018)" in line:
                active = True
                continue
            if not active:
                continue
            if line.startswith("* Source"):
                active = False
                continue
            # The PDF encodes the "fi" and "fl" ligatures as control characters.
            line = line.replace("\x1e", "fi").replace("\x1f", "fl")
            m = re.match(r"^(.+?)\**\s+([\d,]+)\s+-?[\d.]+\s*%$", line)
            if m:
                rows[m.group(1).strip()] = int(m.group(2).replace(",", ""))
    lookup = {norm(k): v for k, v in rows.items()}
    found = 0
    for d in divisions.values():
        n = norm(d["name"])
        pop = lookup.get(n)
        if pop:
            d["population_2016"] = pop
            found += 1
        else:
            print("no commission population for", d["name"], file=sys.stderr)
            d["population_2016"] = 0
    return found


def scale_population(divisions):
    scale = json.load(open(ROOT / "data" / "population_scale.json"))
    estimate = scale["provinces"]["Manitoba"]["estimate"]
    total = sum(d["population_2016"] for d in divisions.values())
    factor = estimate / total if total else 1.0
    for d in divisions.values():
        d["population"] = round(d["population_2016"] * factor)
        d["population_basis"] = POPULATION_BASIS
    return factor, scale["latest_date"], total


def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def load_shapes(divisions):
    by_name = {norm(d["name"]): d["num"] for d in divisions.values()}
    slugs = {o["name"]: o["url"] for o in json.load(open(DL / "mb2018_list.json"))["objects"]}
    coarse, fine = [], []
    SHAPES.mkdir(parents=True, exist_ok=True)
    for o in json.load(open(DL / "mb2018_simple.json"))["objects"]:
        num = by_name.get(norm(o["name"]))
        if not num:
            print("no division for shape", o["name"], file=sys.stderr)
            continue
        coarse.append({"type": "Feature", "id": num, "properties": {"num": num},
                       "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(o["simple_shape"]), 0.002, 0.005)}})
        x0, y0, x1, y1 = bounds(o["simple_shape"])
        if not any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in INSETS):
            continue
        cache = SHAPES / (slugs[o["name"]].rstrip("/").split("/")[-1] + ".json")
        try:
            get(f"{API}{slugs[o['name']]}shape", cache, pause=1.1)
            geom = json.load(open(cache))
        except Exception as e:  # noqa: BLE001
            print("fine shape failed for", o["name"], e, file=sys.stderr)
            continue
        fine.append({"type": "Feature", "id": num, "properties": {"num": num},
                     "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), 0.0004, 0.001)}})
    key = lambda f: int(f["id"])
    return ({"type": "FeatureCollection", "features": sorted(coarse, key=key)},
            {"type": "FeatureCollection", "features": sorted(fine, key=key)})


def main():
    fetch_all()
    OUT.mkdir(parents=True, exist_ok=True)
    divisions = load_results()
    load_mlas(divisions)
    found = load_population(divisions)
    factor, pop_date, total = scale_population(divisions)
    geo, fine = load_shapes(divisions)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2023"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"{len(divisions)} divisions, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in 2023, "
          f"seats 2023 {dict(seats)}, now {dict(now)}")
    print(f"population: commission 2016 figures for {found} divisions, total {total:,}, scaled by {factor:.4f} to {pop_date}: "
          f"{sum(d['population'] for d in divisions.values()):,}")


if __name__ == "__main__":
    main()
