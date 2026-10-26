"""Newfoundland and Labrador: build the electoral-district table for the 14 October 2025
general election: the 40 districts of the 2015 Electoral Districts Boundaries Commission
(used in 2015, 2019, 2021 and 2025).

NL publishes no payee list (the Public Accounts stop at the program level), so the NL page
shows *federal* grants placed in the provincial districts (fed_prov_spending.py, as PEI and
Québec). This script only prepares the districts: 2025 result, current MHA, population and
shapes.

Inputs (data/raw/nl/, downloaded here when missing; never re-downloaded):
  official_results_release.html  Office of the Chief Electoral Officer news release of
                                 20 October 2025, "Official Results of the 2025 Provincial
                                 General Election": every candidate's votes after the
                                 official addition of 17 October 2025, by numbered district
                                 (the official district numbers 1-40 are the ones used
                                 everywhere here).
  2025-General-Election-Report.pdf  Elections NL's official report (20 MB): per district a
                                 "Summary of Polling Divisions" page with the total number
                                 of registered electors and an "Official Results" table
                                 whose TOTAL row has rejected ballots and total votes cast.
                                 Its text is extracted with a small stdlib PDF reader
                                 (FlateDecode streams, Tm/TJ operators) and the per-district
                                 figures are cached in report2025_totals.json, since the
                                 extraction takes minutes.
  votes_by_candidate.json        Elections NL's results dashboard layer
                                 (2025_NL_Provincial_Election_Votes_by_Candidate_view), used
                                 only to cross-check the release.
  members-index.js               the House of Assembly's member list (the data file behind
                                 https://www.assembly.nl.ca/Members/members.aspx: name,
                                 district, party), by-elections and caucus changes included.
  nledbc_Appendix1.pdf           the 2015 commission's final report, Appendix 1 "Summary of
                                 final proposal": 2011-census population per district.
  districts_2015.geojson         the 40 district polygons from Elections NL's
                                 2025_Provincial_Electoral_Districts_view feature service
                                 (the same 2015 map as the open-data shapefile
                                 "Provincial Electoral Districts (2015)",
                                 opendata.gov.nl.ca file-id 3323), WGS84, 6 decimals.

Choices made here:
  * Results: the official release (votes per candidate, valid votes only). Margins and
    shares are over the district's valid votes (the sum of the candidates' votes);
    turnout_pct is total votes cast (valid + rejected, from the official report's TOTAL
    row) over the registered electors in the district (the report's "Total Number of
    Registered Electors in District", which is the revised list; Elections NL's own
    turnout figures use it). Candidate names are "Given Surname" as on the ballot.
  * Party codes: PC, LIB, NDP, IND (the release lists independents with no affiliation;
    Elections NL calls them "Non-Affiliated").
  * Current MHAs: the Assembly's list, matched by district name; the party is the caucus
    the member sits in today, so a member who left a caucus gets a note (Keith Russell,
    Lake Melville, elected PC, independent since 14 September 2026). Paul Lane
    (Mount Pearl - Southlands, independent) is Speaker.
  * Population: no census count exists for these districts (the commission worked from
    the 2011 census, 15 years old now), so "population" is the REGISTERED ELECTORS of each
    district at the 14 October 2025 election, scaled as pe_prep.scale_population does:
    multiplied by the ratio of Statistics Canada's latest NL estimate
    (data/population_scale.json) to the elector total, so the 40 figures sum to the
    province's population and per-capita figures sit on the same footing as the other
    provinces'. Within the province they are per elector. The commission's 2011 population
    is kept as population_2011_commission for reference (four districts were renamed by
    the House when the map was enacted: the commission's Gros Morne, Portugal Cove - Bell
    Island, St. George's - Grand Lake and Trinity - Bay de Verde became Humber - Gros Morne,
    Conception Bay East - Bell Island, St. George's - Humber and Carbonear - Trinity - Bay
    de Verde).
  * Names: Elections NL's official spelling from the release ("Baie Verte – Green Bay",
    en dash between the parts; "Grand Falls-Windsor – Buchans"); the Assembly and the
    map layer write plain hyphens, so matching is on a normalised key.

Outputs:
  data/nl/divisions.json          one record per district, keyed by district number,
                                  PEI schema with the year 2025 in the key names
  data/nl/divisions_geo.json      simplified GeoJSON (clean_polygons, tol 0.002, min 0.005)
  data/nl/divisions_geo_fine.json lighter simplification (tol 0.0004, min 0.001) of the
                                  full shapes for the districts touching a city inset
                                  (St. John's, Corner Brook)
"""
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
import zlib
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "nl"
OUT = ROOT / "data" / "nl"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons, polys_of  # noqa: E402

ARCGIS = "https://services8.arcgis.com/aCyQID5qQcyrJMm2/arcgis/rest/services"
SOURCES = {
    "official_results_release.html": "https://www.gov.nl.ca/releases/2025/elections/1020n02/",
    "2025-General-Election-Report.pdf": "https://www.elections.gov.nl.ca/files/2025-General-Election-Report.pdf",
    "votes_by_candidate.json": f"{ARCGIS}/2025_NL_Provincial_Election_Votes_by_Candidate_view/FeatureServer/0/query?where=1%3D1&outFields=*&f=json",
    "members-index.js": "https://www.assembly.nl.ca/js/members-index.js",
    "nledbc_Appendix1.pdf": "https://www.nledbc.ca/final/Appendix1.pdf",
    "districts_2015.geojson": (f"{ARCGIS}/2025_Provincial_Electoral_Districts_view/FeatureServer/0/query"
                               "?where=1%3D1&outFields=id,dist_name&outSR=4326&geometryPrecision=6&f=geojson"),
}
# St. John's, Corner Brook: [west, south, east, north] (also in build_map.py).
INSETS = [[-53.0, 47.4, -52.6, 47.65], [-58.0, 48.9, -57.85, 48.98]]
PARTY = {"Liberal Party": "LIB", "Progressive Conservative Party": "PC", "New Democratic Party": "NDP",
         "Non-Affiliated": "IND", "": "IND"}
CAUCUS = {"Progressive Conservative": "PC", "Liberal": "LIB", "New Democrat": "NDP", "Independent/Non-Affiliated": "IND",
          "Independent": "IND"}
# The House renamed four districts when it enacted the commission's map (same boundaries).
COMMISSION_RENAMED = {"gros morne": "humber gros morne", "portugal cove bell island": "conception bay east bell island",
                      "st george s grand lake": "st george s humber", "trinity bay de verde": "carbonear trinity bay de verde"}
POPULATION_BASIS = ("registered electors at the 14 October 2025 election (Elections NL official report), scaled to "
                    "Statistics Canada's latest NL estimate by the ratio of that estimate to the elector total; "
                    "the 2015 boundary commission's counts are 2011-census based and no census population exists for these districts")
# Hand-written notes (Wikipedia, 2025 Newfoundland and Labrador general election; CBC and VOCM
# of 14 September 2026 for the caucus change), keyed by district number.
RESULT_NOTES = {
    "36": "judicial recount granted 14 November 2025 and concluded 21 November 2025, reaffirming the result (Paul Dinn, PC, by 102 votes)",
    "23": "a judicial recount was requested and refused on 14 November 2025 (Mark Butt, PC, by 18 votes)",
    "28": "a judicial recount was requested and refused on 14 November 2025 (Jeff Dwyer, PC, by 64 votes)",
}
MLA_NOTES = {
    "22": "Elected as PC; left the PC caucus on 14 September 2026, at the start of the Churchill Falls debate, to sit as an independent.",
    "25": "Speaker of the House of Assembly since 3 November 2025; elected and sits as an independent.",
}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 riding-spending"}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def get(url, path, pause=1.0):
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url, file=sys.stderr)
    time.sleep(pause)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=600) as r, open(path, "wb") as f:
        f.write(r.read())


def fetch_all():
    for name, url in SOURCES.items():
        get(url, RAW / name)


def person(name):
    """'O\\'DRISCOLL, Loyola' -> 'Loyola O\\'Driscoll'; 'MCKENNA, Jim' -> 'Jim McKenna'."""
    name = re.sub(r"\s+", " ", html.unescape(name).replace("\xa0", " ").replace("’", "'")).strip()
    if "," not in name:
        return name
    last, first = (s.strip() for s in name.split(",", 1))
    last = re.sub(r"(^|[\s\-'])([a-z])", lambda m: m.group(1) + m.group(2).upper(), last.lower())
    last = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), last)
    return f"{first} {last}"


def load_release():
    """{num: {'name', 'candidates': [{'name', 'party', 'votes'}]}} from the official release."""
    text = open(RAW / "official_results_release.html", encoding="utf-8", errors="replace").read()
    body = text[text.find("ELECTORAL DISTRICT NAME"):]
    out, cur = {}, None
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if not cells:
            continue
        if len(cells) == 5:
            num = cells[0]
            if not num.isdigit():
                continue
            cur = out[num] = {"name": cells[1].replace("’", "'"), "candidates": []}
            cells = cells[2:]
        if cur is None or len(cells) != 3:
            continue
        cand, party, votes = cells
        if party not in PARTY:
            print("unknown affiliation", repr(party), "in", cur["name"], file=sys.stderr)
        cur["candidates"].append({"name": person(cand), "party": PARTY.get(party, party), "votes": int(votes.replace(",", ""))})
    if len(out) != 40:
        print(f"warning: {len(out)} districts in the release, expected 40", file=sys.stderr)
    return out


def pdf_lines(path):
    """Text lines of a PDF, page by page: FlateDecode content streams, text grouped by the
    Tm y coordinate and ordered by x (enough for the tables Elections NL and the commission
    publish; the numbers are checked against known totals below)."""
    data = open(path, "rb").read()
    pages = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            s = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        if b"BT" not in s or b"Tm" not in s:
            continue
        rows, x, y = {}, 0.0, 0.0
        for mm in re.finditer(rb"1 0 0 1 ([\d.\-]+) ([\d.\-]+) Tm|\[(.*?)\]\s*TJ|\((.*?)\)\s*Tj", s, re.S):
            if mm.group(1):
                x, y = float(mm.group(1)), float(mm.group(2))
                continue
            raw = mm.group(3) if mm.group(3) is not None else b"(" + mm.group(4) + b")"
            txt = ""
            for p, k in re.findall(rb"\(((?:\\.|[^\\)])*)\)|(-?\d+\.?\d*)", raw):
                if p:
                    txt += re.sub(rb"\\(.)", rb"\1", p).decode("latin-1")
                elif k and float(k) < -200:
                    txt += " "
            rows.setdefault(round(y), []).append((x, txt))
            x += 1e-3
        pages.append([" ".join(t for _, t in sorted(rows[yy])) for yy in sorted(rows, reverse=True)])
    return pages


def report_totals(release):
    """{num: {'electors', 'rejected', 'cast'}} from the official report, cached."""
    cache = RAW / "report2025_totals.json"
    if cache.exists():
        return json.load(open(cache))
    by_name = {norm(d["name"]): num for num, d in release.items()}
    electors, totals = {}, {}
    for page in pdf_lines(RAW / "2025-General-Election-Report.pdf"):
        text = re.sub(r"\s+", " ", " ".join(page))
        m = re.search(r"ELECTORAL DISTRICT OF (.+?): SUMMARY OF POLLING DIVISIONS.*?Registered Electors in District: ([\d, ]+)", text)
        if m:
            num = by_name.get(norm(m.group(1)))
            if num:
                electors.setdefault(num, int(re.sub(r"\D", "", m.group(2))))
        m = re.search(r"ELECTORAL DISTRICT OF (.+?): OFFICIAL RESULTS", text)
        t = re.search(r"TOTAL((?: [\d ]+)+)", text)
        if m and t:
            num = by_name.get(norm(m.group(1)))
            if num and num not in totals:
                totals[num] = re.sub(r"\D", "", t.group(1))
    out = {}
    for num, d in release.items():
        votes = [c["votes"] for c in d["candidates"]]  # the report's columns are alphabetical, like the release
        valid = sum(votes)
        digits = totals.get(num, "")
        prefix = "".join(str(v) for v in votes)
        rec = {"electors": electors.get(num)}
        if not digits.startswith(prefix):
            print(f"warning: report TOTAL row for {d['name']} does not match the release: {digits} vs {prefix}", file=sys.stderr)
        else:
            rest = digits[len(prefix):]
            found = [r for r in range(0, 2000) if rest.startswith(f"{r}{valid + r}")]
            if len(found) > 1 and rec["electors"]:
                found = [r for r in found if rest.startswith(f"{r}{valid + r}{rec['electors']}")] or found[:1]
            if found:
                rec["rejected"], rec["cast"] = found[0], valid + found[0]
            else:
                print(f"warning: cannot read rejected ballots for {d['name']}: {rest}", file=sys.stderr)
        out[num] = rec
    json.dump(out, open(cache, "w"), indent=1)
    return out


def cross_check(release):
    """The dashboard layer must agree with the release, candidate by candidate."""
    data = json.load(open(RAW / "votes_by_candidate.json"))
    dash = {}
    for f in data["features"]:
        a = f["attributes"]
        dash.setdefault(str(a["districtid"]), {})[norm(a["candidatename"]).split()[0]] = a["votes"]
    bad = 0
    for num, d in release.items():
        for c in d["candidates"]:
            surname = norm(c["name"]).split()[-1] if "mc" not in norm(c["name"]) else None
            got = {k: v for k, v in dash.get(num, {}).items()}
            key = next((k for k in got if norm(c["name"]).startswith(k) or norm(c["name"]).endswith(k) or (surname and k.startswith(surname))), None)
            if key is None or got[key] != c["votes"]:
                bad += 1
                print(f"dashboard differs for {d['name']} {c['name']}: release {c['votes']}, dashboard {got}", file=sys.stderr)
    return bad


def load_results(release, totals):
    divisions = {}
    for num in sorted(release, key=int):
        d = release[num]
        cands = sorted(d["candidates"], key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in cands)
        w, r = cands[0], cands[1]
        shares = Counter()
        for c in cands:
            shares[c["party"]] += c["votes"]
        t = totals.get(num, {})
        rec = {
            "num": num, "name": d["name"],
            "winner_2025": w["name"], "party_2025": w["party"], "runnerup_2025": r["name"], "runnerup_party_2025": r["party"],
            "votes_2025": w["votes"], "runnerup_votes_2025": r["votes"],
            "margin_votes": w["votes"] - r["votes"], "margin_pts": round(100 * (w["votes"] - r["votes"]) / valid, 1),
            "shares_2025": {p: round(100 * v / valid, 1) for p, v in shares.most_common()},
            "valid_votes_2025": valid, "rejected_ballots_2025": t.get("rejected"),
            "turnout_pct": round(100 * t["cast"] / t["electors"], 1) if t.get("cast") and t.get("electors") else None,
            "registered_voters_2025": t.get("electors"),
        }
        if num in RESULT_NOTES:
            rec["result_note"] = RESULT_NOTES[num]
        divisions[num] = rec
    return divisions


def load_mhas(divisions):
    by_name = {norm(d["name"]): d for d in divisions.values()}
    text = open(RAW / "members-index.js", encoding="utf-8").read()
    seen = set()
    for name, district, party in re.findall(r"name:\s*'(.*?)',\s*district:\s*'(.*?)',\s*party:\s*'(.*?)'", text, re.S):
        d = by_name.get(norm(district.replace("\\'", "'")))
        if not d:
            print("MHA district matches no result:", district, file=sys.stderr)
            continue
        seen.add(d["num"])
        d["mla"] = person(re.sub(r"<[^>]+>", "", name).replace("\\'", "'"))
        d["mla_party"] = CAUCUS.get(party, party)
        if party not in CAUCUS:
            print("unknown caucus label", party, file=sys.stderr)
        d["mla_note"] = MLA_NOTES.get(d["num"], "")
        if norm(d["mla"]).split()[-1] != norm(d["winner_2025"]).split()[-1]:
            d["mla_note"] = d["mla_note"] or f"Not the 2025 winner ({d['winner_2025']}, {d['party_2025']}); by-election or change since."
            print("note:", d["name"], d["mla_note"], file=sys.stderr)
        elif d["mla_party"] != d["party_2025"]:
            d["mla_note"] = d["mla_note"] or f"Elected as {d['party_2025']}, now sits as {d['mla_party']}."
            print("note:", d["name"], d["mla_note"], file=sys.stderr)
    for d in divisions.values():
        if d["num"] not in seen:
            d["mla"], d["mla_party"], d["mla_note"] = "Vacant", "", "not in the Assembly's member list on the download date"
            print("note:", d["name"], "has no sitting member listed", file=sys.stderr)


def commission_population(divisions):
    """Appendix 1 of the 2015 commission's final report: 2011 census population per district."""
    by_name = {norm(d["name"]): d for d in divisions.values()}
    found = 0
    for page in pdf_lines(RAW / "nledbc_Appendix1.pdf"):
        for line in page:
            m = re.match(r"^\s*([A-Za-z][A-Za-z .'’\-]+?)\s{2,}([\d,]+)\s+(-?\s*[\d.]+%|-)\s*$", line)
            if not m:
                continue
            key = norm(m.group(1))
            key = COMMISSION_RENAMED.get(key, key)
            d = by_name.get(key)
            if not d:
                print("commission district matches no result:", repr(m.group(1)), file=sys.stderr)
                continue
            d["population_2011_commission"] = int(m.group(2).replace(",", ""))
            found += 1
    if found != 40:
        print(f"warning: commission population found for {found} districts", file=sys.stderr)


def scale_population(divisions):
    """population = registered electors scaled so the 40 sum to StatCan's NL estimate."""
    scale = json.load(open(ROOT / "data" / "population_scale.json"))
    estimate = scale["provinces"]["Newfoundland and Labrador"]["estimate"]
    total = sum(d["registered_voters_2025"] for d in divisions.values())
    factor = estimate / total if total else 1.0
    for d in divisions.values():
        d["population"] = round(d["registered_voters_2025"] * factor)
        d["population_basis"] = POPULATION_BASIS
    return factor, scale["latest_date"], total


def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def touches_inset(geom):
    x0, y0, x1, y1 = bounds(geom)
    return any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in INSETS)


def feature(num, geom, tol, min_extent):
    return {"type": "Feature", "id": num, "properties": {"num": num},
            "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, min_extent)}}


def load_shapes(divisions):
    data = json.load(open(RAW / "districts_2015.geojson", encoding="utf-8"))
    if data.get("properties", {}).get("exceededTransferLimit"):
        print("warning: the feature service truncated the district download", file=sys.stderr)
    coarse, fine = [], []
    for f in data["features"]:
        num = str(f["properties"]["id"])
        if num not in divisions:
            print("shape with no result:", num, f["properties"].get("dist_name"), file=sys.stderr)
            continue
        if norm(f["properties"].get("dist_name", "")) != norm(divisions[num]["name"]):
            print("shape name differs:", f["properties"].get("dist_name"), "/", divisions[num]["name"], file=sys.stderr)
        coarse.append(feature(num, f["geometry"], 0.002, 0.005))
        if touches_inset(f["geometry"]):
            fine.append(feature(num, f["geometry"], 0.0004, 0.001))
    key = lambda ft: int(ft["id"])
    return ({"type": "FeatureCollection", "features": sorted(coarse, key=key)},
            {"type": "FeatureCollection", "features": sorted(fine, key=key)})


def main():
    fetch_all()
    OUT.mkdir(parents=True, exist_ok=True)
    release = load_release()
    bad = cross_check(release)
    totals = report_totals(release)
    divisions = load_results(release, totals)
    load_mhas(divisions)
    commission_population(divisions)
    factor, pop_date, total = scale_population(divisions)
    geo, fine = load_shapes(divisions)
    missing = set(divisions) - {ft["id"] for ft in geo["features"]}
    if missing:
        print("districts with no shape:", sorted(missing), file=sys.stderr)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2025"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"{len(divisions)} districts, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in 2025, "
          f"seats 2025 {dict(seats)}, sitting {dict(now)}; dashboard cross-check: {bad} candidates differ")
    print(f"population: {total:,} registered electors scaled by {factor:.4f} to {pop_date}: "
          f"{sum(d['population'] for d in divisions.values()):,}; commission 2011 total "
          f"{sum(d.get('population_2011_commission', 0) for d in divisions.values()):,}")
    print("turnout: province", round(100 * sum(totals[n]["cast"] for n in totals) / sum(totals[n]["electors"] for n in totals), 1),
          "%; geo bytes:", (OUT / "divisions_geo.json").stat().st_size, "fine bytes:", (OUT / "divisions_geo_fine.json").stat().st_size)


if __name__ == "__main__":
    main()
