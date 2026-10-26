"""Nova Scotia: build the electoral-district table (56 districts: the 55 of the 2019
commission map used at the 26 November 2024 general election, plus
Chéticamp-Margarees-Pleasant Bay, carved out of Inverness in 2026 and filled at the
23 June 2026 by-election).

Joins the 2024 results per district (winner, runner-up, votes, margin), the current
member list of the House of Assembly, the electors on the final list, and Elections
Nova Scotia's 2026 district boundaries. Mirrors nb_prep.py; keys use "2024".

Inputs (data/raw/ns/dl/; fetched here when missing, except the Wayback copy):
  42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx
      Elections Nova Scotia, 42nd general election poll-by-poll results: one sheet per
      district (ED01..ED55), candidate columns headed "Given SURNAME\\nParty", a "Total"
      row (electors on the final list, total votes, votes per candidate, rejected,
      declined) and an "Elected:" row.
      https://electionsnovascotia.ca/files/GeneralElection_42nd/42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx
  NS_2026ED_Bnds.zip -> bnds/NS_2026ED_Bnds.{shp,dbf,prj}
      Elections Nova Scotia's 2026 electoral district boundaries (56 districts, 57
      records: Halifax Citadel-Sable Island is two records, the peninsula and Sable
      Island), NAD83(CSRS) UTM zone 20N, with the elector count of each district
      (electorcou). Read here with a stdlib shapefile reader and an inverse Transverse
      Mercator; NAD83(CSRS) is treated as WGS84 (sub-metre difference).
      https://electionsnovascotia.ca/files/ElectoralDistrictMapInformation/NS_2026ED_Bnds.zip
  cmpb_byelection_2026_report.pdf
      Elections Nova Scotia's non-financial report on the 23 June 2026 by-election
      (Table 2: votes by candidate; Appendix C: 4,002 electors, 32 rejected ballots).
      The figures are copied into BYELECTION_2026 below; the PDF is kept for checking.
  mlas_profiles_wayback.html
      https://nslegislature.ca/members/profiles as archived by the Internet Archive on
      15 October 2026 (nslegislature.ca refuses connections from here); 56 member rows
      with name "Surname, Hon. Given", party (PC, NDP, Liberal, Independent) and
      constituency.

Outputs:
  data/ns/divisions.json          one record per district, keyed by the ED number ("1".."56")
  data/ns/divisions_geo.json      simplified GeoJSON (clean_polygons, tol 0.002, min 0.005)
  data/ns/divisions_geo_fine.json lighter simplification (tol 0.0004, min 0.001) of the
                                  full shapes for the districts that touch the Halifax,
                                  Sydney or Truro inset

Choices made here:
  * Results: the 2024 "Total" row of each sheet; margins and shares use valid votes
    (candidate votes only). Candidate names are re-cased ("David BOWLBY" -> "David
    Bowlby"). Party codes: PC Party -> PC, Liberal -> LIB, NSNDP -> NDP, Green Party ->
    GRN, Independent -> IND; anything else keeps its label.
  * The split district: Inverness (34) keeps its 2024 result (Kyle MacQuarrie, PC, on the
    pre-split boundary) and Chéticamp-Margarees-Pleasant Bay (56) carries the 2026
    by-election result (Claude Bourgeois, PC); "result_note" says so on both. The
    by-election result has no "2024" counterpart, so its fields use the same 2024 keys
    (winner_2024, ...) for schema consistency and the note explains the date.
  * Current MLAs: the archived member list, matched by normalised constituency name;
    "mla_note" marks the members who are not the 2024 winner on the ballot label
    (Becky Druhan, Lunenburg West: elected PC, sat as an independent from 27 October
    2025, joined the Liberal caucus on 11 May 2026).
  * Population: no census population by provincial district is published for Nova
    Scotia, and the 2019 commission's report is on nslegislature.ca (unreachable), so
    "population" is the ELECTORS ON THE FINAL LIST at the 2024 election (the workbook's
    Total row), scaled to Statistics Canada's latest Nova Scotia estimate by the ratio of
    that estimate to the elector total (as mb_prep.scale_population does). The raw count
    is kept as "electors_2024" and population_2021 (for schema consistency), and
    "population_basis" says what it is. Inverness's 2024 electors are apportioned between
    Inverness and Chéticamp-Margarees-Pleasant Bay by the elector counts in the 2026
    boundary file (10,609 : 3,889).
"""
import html
import json
import math
import re
import struct
import sys
import unicodedata
import urllib.request
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ns"
DL = RAW / "dl"
OUT = ROOT / "data" / "ns"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons, polys_of  # noqa: E402
from nb_prep import xlsx_sheets  # noqa: E402

UA = {"User-Agent": "Mozilla/5.0 riding-spending (research)"}
RESULTS_URL = "https://electionsnovascotia.ca/files/GeneralElection_42nd/42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx"
BOUNDS_URL = "https://electionsnovascotia.ca/files/ElectoralDistrictMapInformation/NS_2026ED_Bnds.zip"
MLAS_WAYBACK = "http://web.archive.org/web/20261015215420/https://nslegislature.ca/members/profiles"
# Halifax, Sydney, Truro: (west, south, east, north); also in build_map.py.
INSETS = [(-63.85, 44.55, -63.4, 44.85), (-60.3, 46.05, -60.1, 46.2), (-63.35, 45.33, -63.2, 45.4)]
PARTY = {"PC Party": "PC", "Liberal": "LIB", "NSNDP": "NDP", "Green Party": "GRN", "Independent": "IND",
         "Green Party of NS": "GRN", "Atlantica": "ATL"}
CAUCUS = {"PC": "PC", "Liberal": "LIB", "NDP": "NDP", "Green": "GRN", "Independent": "IND"}
POPULATION_BASIS = ("electors on the final list at the 26 November 2024 election (Elections Nova Scotia poll-by-poll "
                    "results), scaled to Statistics Canada's latest Nova Scotia estimate by the ratio of that estimate "
                    "to the elector total; Inverness's electors are apportioned between Inverness and "
                    "Chéticamp-Margarees-Pleasant Bay by the elector counts in the 2026 boundary file; Nova Scotia "
                    "publishes no census population by provincial district")
# Elections Nova Scotia, Chéticamp-Margarees-Pleasant Bay by-election report (23 June 2026), Table 2 and Appendix C.
BYELECTION_2026 = {
    "date": "2026-06-23", "electors": 4002, "rejected": 32,
    "candidates": [("Claude Bourgeois", "PC", 1315), ("Denis Cormier", "LIB", 1080), ("Trevor Poirier", "NDP", 258),
                   ("Nik Boisvert", "GRN", 44)],
}
MLA_NOTES = {
    "39": "elected PC in 2024; sat as an independent from 27 October 2025 and joined the Liberal caucus on 11 May 2026",
}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def fetch(url, path):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
        path.write_bytes(r.read())
    print("fetched", path.name)


def recase(name):
    """'David BOWLBY' -> 'David Bowlby'; 'Nick D'ENTREMONT' -> "Nick D'Entremont"."""
    def fix(word):
        if not (len(word) > 1 and word.isupper()):
            return word
        out = []
        for p in re.split(r"([-'’])", word):
            if p in "-'’":
                out.append(p)
            elif p.startswith("MC") and len(p) > 2:
                out.append("Mc" + p[2:].capitalize())
            elif p.startswith("MAC") and len(p) > 4:
                out.append("Mac" + p[3:].capitalize())
            else:
                out.append(p.capitalize())
        return "".join(out)
    return " ".join(fix(w) for w in name.split())


# ------------------------------------------------------------------ results

def load_results():
    fetch(RESULTS_URL, DL / "42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx")
    divisions = {}
    for sheet, rows in xlsx_sheets(DL / "42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx"):
        if not re.fullmatch(r"ED\d{2}", sheet):
            continue
        title = next(v for r in rows[:3] for v in r.values() if re.match(r"\d{2}\s*-\s*\S", v or ""))
        ed_num, name = re.split(r"\s*-\s*", title, maxsplit=1)
        ed_num = str(int(ed_num))
        header = next(r for r in rows if (r.get("A") or "").strip() == "Poll")
        cands = {}
        for col, label in header.items():
            if col in "ABCD" or "Ballots" in label:
                continue
            who, party = [x.strip() for x in label.strip().split("\n")[:2]]
            cands[col] = (recase(who), PARTY.get(party, party))
        total = next(r for r in rows if (r.get("B") or "").strip() == "Total")
        results = sorted(({"name": n, "party": p, "votes": int(float(total.get(col) or 0))} for col, (n, p) in cands.items()),
                         key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        electors = int(float(total.get("C") or 0))
        cast = int(float(total.get("D") or 0))
        win, second = results[0], results[1]
        divisions[ed_num] = {
            "num": ed_num, "ed_num": ed_num, "name": name.strip(),
            "winner_2024": win["name"], "party_2024": win["party"],
            "runnerup_2024": second["name"], "runnerup_party_2024": second["party"],
            "votes_2024": win["votes"], "runnerup_votes_2024": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2024": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "valid_votes_2024": valid,
            "turnout_pct": round(100 * cast / electors, 1) if electors else None,
            "electors_2024": electors,
        }
    return divisions


def add_byelection(divisions, electors_bnds):
    """Chéticamp-Margarees-Pleasant Bay (56): the 2026 by-election result; Inverness keeps 2024."""
    b = BYELECTION_2026
    results = sorted(({"name": n, "party": p, "votes": v} for n, p, v in b["candidates"]), key=lambda c: -c["votes"])
    valid = sum(c["votes"] for c in results)
    win, second = results[0], results[1]
    inv = divisions["34"]
    share56 = electors_bnds["56"] / (electors_bnds["34"] + electors_bnds["56"])
    electors56 = round(inv["electors_2024"] * share56)
    divisions["56"] = {
        "num": "56", "ed_num": "56", "name": "Chéticamp-Margarees-Pleasant Bay",
        "winner_2024": win["name"], "party_2024": win["party"],
        "runnerup_2024": second["name"], "runnerup_party_2024": second["party"],
        "votes_2024": win["votes"], "runnerup_votes_2024": second["votes"],
        "margin_votes": win["votes"] - second["votes"],
        "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
        "shares_2024": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
        "valid_votes_2024": valid,
        "turnout_pct": round(100 * (valid + b["rejected"]) / b["electors"], 1),
        "electors_2024": electors56,
        "result_note": ("district created in 2026 out of Inverness; the result shown is the 23 June 2026 by-election "
                        "(the 2024 vote here was part of Inverness); electors are Inverness's 2024 electors apportioned "
                        "by the 2026 boundary file"),
    }
    inv["electors_2024"] -= electors56
    inv["result_note"] = ("the 2024 result on the pre-2026 boundary, which included Chéticamp-Margarees-Pleasant Bay "
                          "(carved out on 12 April 2026); electors apportioned by the 2026 boundary file")


# ------------------------------------------------------------------ MLAs

def load_mlas(divisions):
    path = DL / "mlas_profiles_wayback.html"
    if not path.exists():
        try:
            fetch(MLAS_WAYBACK, path)
        except Exception as e:  # noqa: BLE001
            print("member list fetch failed:", e, file=sys.stderr)
    by_name = {norm(d["name"]): d for d in divisions.values()}
    seen = set()
    if path.exists():
        text = open(path, encoding="utf-8", errors="replace").read()
        rows = re.findall(r'<div class="views-row.*?views-field-field-last-name">.*?<a href="[^"]*">(.*?)</a>.*?'
                          r'party-name-color party-name-(\w+)"></span>(.*?)</span>.*?'
                          r'field-constituency">\s*<div class="field-content">(.*?)</div>', text, re.S)
        for raw, _, party, riding in rows:
            raw = html.unescape(raw).strip()
            surname, given = [x.strip() for x in raw.split(",", 1)]
            given = re.sub(r"^Hon\.\s*", "", given)
            d = by_name.get(norm(html.unescape(riding)))
            if not d:
                print("MLA district matches no result:", riding, file=sys.stderr)
                continue
            seen.add(d["num"])
            d["mla"] = f"{given} {surname}"
            d["mla_party"] = CAUCUS.get(party.strip(), party.strip())
            d["mla_note"] = ""
            if norm(d["mla"]).split()[-1] != norm(d["winner_2024"]).split()[-1]:
                d["mla_note"] = f"not the 2024 winner ({d['winner_2024']}, {d['party_2024']}); by-election or change since"
            elif d["mla_party"] != d["party_2024"]:
                d["mla_note"] = MLA_NOTES.get(d["num"], f"elected {d['party_2024']} in 2024, now sits as {d['mla_party']}")
    for d in divisions.values():
        if d["num"] not in seen:
            d["mla"], d["mla_party"], d["mla_note"] = "Vacant", "", "no member in the archived list"


# ------------------------------------------------------------------ population

def scale_population(divisions):
    scale = json.load(open(ROOT / "data" / "population_scale.json"))
    estimate = scale["provinces"]["Nova Scotia"]["estimate"]
    total = sum(d["electors_2024"] for d in divisions.values())
    factor = estimate / total if total else 1.0
    for d in divisions.values():
        d["population_2021"] = d["electors_2024"]
        d["population"] = round(d["electors_2024"] * factor)
        d["population_basis"] = POPULATION_BASIS
    return factor, scale["latest_date"], total


# ------------------------------------------------------------------ shapes

def utm_to_lonlat(x, y, zone=20):
    """Inverse Transverse Mercator on GRS80 (NAD83 CSRS), UTM north."""
    a, f = 6378137.0, 1 / 298.257222101
    k0, e2 = 0.9996, 2 * f - f * f
    ep2 = e2 / (1 - e2)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    x -= 500000.0
    m = y / k0
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    phi1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
            + (151 * e1 ** 3 / 96) * math.sin(6 * mu) + (1097 * e1 ** 4 / 512) * math.sin(8 * mu))
    sp, cp, tp = math.sin(phi1), math.cos(phi1), math.tan(phi1)
    n1 = a / math.sqrt(1 - e2 * sp * sp)
    t1 = tp * tp
    c1 = ep2 * cp * cp
    r1 = a * (1 - e2) / (1 - e2 * sp * sp) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * tp / r1) * (d * d / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1 * c1 - 9 * ep2) * d ** 4 / 24
                                    + (61 + 90 * t1 + 298 * c1 + 45 * t1 * t1 - 252 * ep2 - 3 * c1 * c1) * d ** 6 / 720)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d ** 3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1 * c1 + 8 * ep2 + 24 * t1 * t1) * d ** 5 / 120) / cp
    return math.degrees(lon), math.degrees(lat)


def read_dbf(path):
    d = open(path, "rb").read()
    n, hl, rl = struct.unpack("<IHH", d[4:12])
    fields, p = [], 32
    while d[p] != 0x0D:
        fields.append((d[p:p + 11].split(b"\0")[0].decode(), d[p + 16]))
        p += 32
    rows = []
    for i in range(n):
        r, q, row = d[hl + i * rl:hl + (i + 1) * rl], 1, {}
        for name, ln in fields:
            row[name] = r[q:q + ln].decode("utf-8", "replace").strip()
            q += ln
        rows.append(row)
    return rows


def read_shp(path):
    """-> list of GeoJSON MultiPolygon geometries (lon/lat), one per record, record order."""
    f = open(path, "rb").read()
    p, geoms = 100, []
    while p < len(f):
        _, ln = struct.unpack(">ii", f[p:p + 8])
        rec = f[p + 8:p + 8 + ln * 2]
        p += 8 + ln * 2
        st = struct.unpack("<i", rec[:4])[0]
        if st not in (5, 15, 25):
            geoms.append(None)
            continue
        nparts, npts = struct.unpack("<ii", rec[36:44])
        parts = list(struct.unpack(f"<{nparts}i", rec[44:44 + 4 * nparts])) + [npts]
        pts = struct.unpack(f"<{2 * npts}d", rec[44 + 4 * nparts:44 + 4 * nparts + 16 * npts])
        rings = []
        for k in range(nparts):
            ring = [list(utm_to_lonlat(pts[2 * j], pts[2 * j + 1])) for j in range(parts[k], parts[k + 1])]
            area = sum(ring[j][0] * ring[j + 1][1] - ring[j + 1][0] * ring[j][1] for j in range(len(ring) - 1))
            rings.append((area < 0, ring))  # shapefile: clockwise = outer
        polys = []
        for outer, ring in rings:
            if outer or not polys:
                polys.append([ring])
            else:
                polys[-1].append(ring)
        geoms.append({"type": "MultiPolygon", "coordinates": polys})
    return geoms


def load_shapes():
    """{ed number: full-detail MultiPolygon}, {ed number: electors in the boundary file}."""
    fetch(BOUNDS_URL, DL / "NS_2026ED_Bnds.zip")
    folder = DL / "bnds"
    if not (folder / "NS_2026ED_Bnds.shp").exists():
        folder.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(DL / "NS_2026ED_Bnds.zip").extractall(folder)
    rows = read_dbf(folder / "NS_2026ED_Bnds.dbf")
    geoms = read_shp(folder / "NS_2026ED_Bnds.shp")
    shapes, electors = {}, {}
    for row, geom in zip(rows, geoms):
        num = str(int(re.sub(r"\D", "", row["ED_NO"])))
        if geom is None:
            continue
        if num in shapes:  # Halifax Citadel-Sable Island: peninsula and Sable Island records
            shapes[num]["coordinates"] += geom["coordinates"]
        else:
            shapes[num] = geom
        electors[num] = int(float(row["electorcou"] or 0))
    return shapes, electors


def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def touches_inset(geom):
    x0, y0, x1, y1 = bounds(geom)
    return any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in INSETS)


def feature(num, geom, tol, min_extent):
    return {"type": "Feature", "id": num, "properties": {"num": num},
            "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, min_extent)}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    shapes, electors_bnds = load_shapes()
    divisions = load_results()
    add_byelection(divisions, electors_bnds)
    load_mlas(divisions)
    factor, pop_date, total = scale_population(divisions)
    divisions = dict(sorted(divisions.items(), key=lambda kv: int(kv[0])))
    missing = set(shapes) - set(divisions)
    if missing or set(divisions) - set(shapes):
        print("boundary/result mismatch:", sorted(missing), sorted(set(divisions) - set(shapes)), file=sys.stderr)

    geo = {"type": "FeatureCollection", "features": [feature(n, shapes[n], 0.002, 0.005) for n in divisions if n in shapes]}
    fine = {"type": "FeatureCollection", "features": [feature(n, shapes[n], 0.0004, 0.001) for n in divisions
                                                       if n in shapes and touches_inset(shapes[n])]}
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2024"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"{len(divisions)} districts, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close, "
          f"seats 2024 (56th as by-election) {dict(seats)}, now {dict(now)}")
    print(f"population: electors 2024 total {total:,}, scaled by {factor:.4f} to {pop_date}: "
          f"{sum(d['population'] for d in divisions.values()):,}")


if __name__ == "__main__":
    main()
