"""Ontario: build the riding table (124 ridings of the Representation Act, 2015 as amended
by the Representation Statute Law Amendment Act, 2017; used at the 7 June 2018,
2 June 2022 and 27 February 2025 general elections).

Joins the 2025 results (every candidate's valid votes, so winner, runner-up, margin and
shares come from the data), the registered-elector and turnout statistics, the current
member list of the Legislative Assembly (by-elections and caucus changes since February
2025 included), the 2021 census population and Represent's boundaries. Mirrors nb_prep.py;
keys use "2025".

Inputs (data/raw/on/dl/, downloaded here when missing except where noted):
  represent_list.json, represent_simple.json
      Represent set ontario-electoral-districts-representation-act-2015 (list and
      simple_shape, one request each, limit=200). The list carries the official riding
      number as external_id.
  valid_votes_2025.csv       Elections Ontario results portal, report "Summary of Valid
                             Votes Cast for Each Candidate" (every candidate, party code,
                             valid votes, percentage, incumbent flag; the file also holds
                             the 2023 and 2024 by-elections, skipped here)
  district_stats_2025.csv    report "Statistical Summary by Electoral District" (names on
                             the list, ballots cast by type, turnout)
  party_codes.csv            report "Political Interest Codes" (code -> party name)
      The three CSVs are https://results.elections.on.ca/api/report-groups/48/
      report-outputs/{1096,1089,1094}/csv (report group 48 = 2025 general election).
  ola_members.tsv            current MPPs: name, party, riding, one per line, copied from the
                             table at https://www.ola.org/en/members/current. ola.org answers
                             scripted requests with 403 (Akamai), so this file was saved from
                             a browser session on 26 October 2026; if an ola_members.html copy
                             of the page is dropped in instead it is parsed in preference.
  statcan/98100010.csv       Statistics Canada table 98-10-0010-01, population and dwelling
                             counts for the 2013-order federal electoral districts, 2021
                             census (https://www150.statcan.gc.ca/n1/tbl/csv/98100010-eng.zip)
  statcan/98100002.csv       table 98-10-0002-01, the same for census subdivisions
                             (https://www150.statcan.gc.ca/n1/tbl/csv/98100002-eng.zip)
  ../csd_centroid/<csduid>.json
      Represent's record (centroid, extent) for each populated 2021 census subdivision in
      the northern census divisions (Muskoka, Nipissing, Parry Sound, Manitoulin, Sudbury,
      Greater Sudbury, Timiskaming, Cochrane, Algoma, Thunder Bay, Rainy River, Kenora);
      ~270 requests at 1.1 s apart on the first run, cached after
  ../shape/<slug>.json       Represent's full-detail shape for ridings whose bounding box
                             touches a city inset, ~1 request per 1.1 s, cached

Outputs:
  data/on/divisions.json          one record per riding, keyed by the official number
  data/on/divisions_geo.json      simplified GeoJSON (clean_polygons, tol 0.002, min 0.005)
  data/on/divisions_geo_fine.json lighter simplification (tol 0.0004, min 0.001) of the full
                                  shapes for the ridings that touch a city inset (Toronto and
                                  the GTA, Hamilton-Niagara, Kitchener-Waterloo, London,
                                  Ottawa, Windsor)

Choices made here:
  * The riding key ("num") is the official electoral district number (1-124, Elections
    Ontario's numbering, which Represent carries as external_id). Represent's URL slug
    ("toronto-centre") is kept as "slug".
  * Results: valid votes only (declined, rejected and unmarked ballots are left out of the
    shares and margins). Candidate names are re-cased from the portal's upper case
    ("LUCIA IANNANTUONO" -> "Lucia Iannantuono"; "MCCRIMMON" -> "McCrimmon").
    registered_voters_2025 is the total number of names on the list after revision
    (TotalNumberOfNames) and turnout_pct is the portal's VoterTurnoutPercentageOfList,
    i.e. ballots cast (valid, rejected, unmarked and declined) over that total.
  * Party codes (Elections Ontario political interest code -> short label): PCP -> PC,
    NDP -> NDP, LIB -> LIB, GPO -> GRN, IND -> IND, NBO -> NBP (New Blue), ONP -> OP
    (Ontario Party); every other party keeps Elections Ontario's own three-letter code
    (LTN Libertarian, NRT Northern Ontario Party, COM Communist, FRE Freedom, CCP
    Canadians' Choice, ERP Electoral Reform, SNS Stop the New Sex-Ed Agenda, OAL Ontario
    Alliance, NAP None of the Above, MOD Moderate, PRP Progress, PPR Populist, CEN
    Centrist, PSN Party for People with Special Needs).
  * Current MPPs: the Assembly's table (name with "Hon." for ministers, party, riding),
    matched by normalised riding name. Where the member is not the 2025 winner the 2025
    result is left as it was and "mla_note" says so: the 3 September 2026 by-elections in
    Hamilton East-Stoney Creek, Scarborough Southwest and York-Simcoe, and a member who
    now sits for another caucus (Sault Ste. Marie: elected PC, sits as Independent).
  * Population is the 2021 census. 111 of the 124 ridings are the 2013-order federal
    electoral districts (the Representation Act, 2015 adopted the federal map for southern
    Ontario), so Statistics Canada's count for the federal district is used as it stands.
    The 13 northern ridings are not federal districts: eleven kept the pre-2018 provincial
    boundaries (Algoma-Manitoulin, Kenora-Rainy River, Nickel Belt, Nipissing, Parry
    Sound-Muskoka, Sault Ste. Marie, Sudbury, Thunder Bay-Atikokan, Thunder Bay-Superior
    North, Timiskaming-Cochrane, Timmins) and two were carved out of them by the Far North
    Electoral Boundaries Commission (Kiiwetinoong, Mushkegowuk-James Bay). Their count is
    the sum of the 2021 census subdivisions (municipalities, reserves and unorganized
    areas) whose centroid falls inside the riding. Unorganized areas straddle riding lines,
    so a few thousand people per riding can sit on the wrong side; for the five northern
    ridings that share a name with a federal district the two figures are printed side by
    side as a check. The raw count is kept as "population_2021" and "population_basis"
    says which method applied; "population" is the count scaled by the province's growth
    since 2021 (prep_ridings.scale_population, data/population_scale.json).
"""
import csv
import html as htmlmod
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "on"
DL = RAW / "dl"
OUT = ROOT / "data" / "on"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import scale_population, clean_polygons, polys_of  # noqa: E402

API = "https://represent.opennorth.ca"
BOUNDARY_SET = "ontario-electoral-districts-representation-act-2015"
PORTAL = "https://results.elections.on.ca/api/report-groups/48/report-outputs"
SOURCES = {
    "represent_list.json": f"{API}/boundaries/{BOUNDARY_SET}/?limit=200",
    "represent_simple.json": f"{API}/boundaries/{BOUNDARY_SET}/simple_shape?limit=200",
    "valid_votes_2025.csv": f"{PORTAL}/1096/csv",
    "district_stats_2025.csv": f"{PORTAL}/1089/csv",
    "party_codes.csv": f"{PORTAL}/1094/csv",
    "statcan/98100010-eng.zip": "https://www150.statcan.gc.ca/n1/tbl/csv/98100010-eng.zip",
    "statcan/98100002-eng.zip": "https://www150.statcan.gc.ca/n1/tbl/csv/98100002-eng.zip",
}
OLA_URL = "https://www.ola.org/en/members/current"
# Toronto & GTA, Hamilton-Niagara, Kitchener-Waterloo, London, Ottawa, Windsor: (west, south, east, north).
INSETS = [(-79.85, 43.5, -79.0, 43.95), (-80.2, 43.0, -79.0, 43.45), (-80.7, 43.3, -80.2, 43.6),
          (-81.4, 42.85, -81.1, 43.1), (-76.05, 45.2, -75.4, 45.6), (-83.15, 42.22, -82.85, 42.38)]
PARTY = {"PCP": "PC", "NDP": "NDP", "LIB": "LIB", "GPO": "GRN", "IND": "IND", "NBO": "NBP", "ONP": "OP"}
CAUCUS = {"Progressive Conservative Party of Ontario": "PC", "New Democratic Party of Ontario": "NDP",
          "Ontario Liberal Party": "LIB", "Green Party of Ontario": "GRN", "Independent": "IND"}
BYELECTIONS = {"37": "3 September 2026", "98": "3 September 2026", "121": "3 September 2026"}
# Census divisions whose subdivisions are located one by one (the northern ridings are not
# federal districts): Muskoka, Nipissing, Parry Sound, Manitoulin, Sudbury, Greater Sudbury,
# Timiskaming, Cochrane, Algoma, Thunder Bay, Rainy River, Kenora.
NORTH_CDS = {"3544", "3548", "3549", "3551", "3552", "3553", "3554", "3556", "3557", "3558", "3559", "3560"}
# The 13 ridings whose population is the subdivision sum (official numbers).
NORTH_RIDINGS = {"2", "44", "72", "105", "107", "108", "123", "124",  # not federal districts by name
                 "71", "84", "92", "103", "106"}  # Nickel Belt, Parry Sound-Muskoka, Sault Ste. Marie, Sudbury, Thunder Bay-Superior North
SCALE_NOTE = "scaled to Statistics Canada's latest Ontario estimate by the province's growth since 2021"
BASIS_FED = f"2021 census count for the identical 2013-order federal electoral district (Statistics Canada table 98-10-0010-01), {SCALE_NOTE}"
BASIS_CSD = ("2021 census subdivisions (municipalities, reserves, unorganized areas; table 98-10-0002-01) summed by the "
             f"subdivision whose centroid lies in the riding, because the northern ridings are not federal districts; {SCALE_NOTE}")
UA = {"User-Agent": "riding-spending (research)"}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def get(url, path, pause=1.1):
    """Download url to path unless it is already there."""
    if path.exists() and path.stat().st_size > 0:
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url, file=sys.stderr, flush=True)
    time.sleep(pause)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r:
            data = r.read()
    except Exception as e:  # noqa: BLE001
        print("download failed:", url, e, file=sys.stderr)
        return False
    path.write_bytes(data)
    return True


def fetch_all():
    import zipfile
    DL.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        path = DL / name
        if name.endswith(".zip"):
            if (path.parent / (path.stem.split("-")[0] + ".csv")).exists():
                continue
            if get(url, path):
                zipfile.ZipFile(path).extractall(path.parent)
        else:
            get(url, path)
    if not (DL / "ola_members.tsv").exists() and not (DL / "ola_members.html").exists():
        if not get(OLA_URL, DL / "ola_members.html") or b"Access Denied" in (DL / "ola_members.html").read_bytes()[:2000]:
            (DL / "ola_members.html").unlink(missing_ok=True)
            sys.exit("ola.org refuses scripted downloads: save https://www.ola.org/en/members/current as "
                     "data/raw/on/dl/ola_members.html from a browser, or its table as ola_members.tsv (name, party, riding)")


def recase(name):
    """'LUCIA IANNANTUONO' -> 'Lucia Iannantuono'; 'KAREN MCCRIMMON' -> 'Karen McCrimmon'; "O'BRIEN" -> "O'Brien"."""
    def fix(word):
        if not (len(word) > 1 and word.isupper()):
            return word
        parts = re.split(r"([-'’.])", word)
        out = []
        for p in parts:
            if p in "-'’.":
                out.append(p)
            elif p.startswith("MC") and len(p) > 2:
                out.append("Mc" + p[2:].capitalize())
            elif p.startswith("MAC") and len(p) > 4 and p not in ("MACKAY",):
                out.append("Mac" + p[3:].capitalize())
            else:
                out.append(p.capitalize())
        return "".join(out)
    name = " ".join(fix(w) for w in name.split())
    # "(Jennie)" nicknames and roman numerals keep their case.
    return re.sub(r"\b(Ii|Iii|Iv)\b", lambda m: m.group(1).upper(), name)


def load_results(listing):
    """One record per riding from the candidate file; electors and turnout from the summary."""
    by_num = {o["external_id"]: o for o in listing}
    cands = {}
    with open(DL / "valid_votes_2025.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if r["IsGeneralElection"] != "1" or "2025" not in r["EventNameEnglish"]:
                continue
            num = str(int(r["ElectoralDistrictNumber"]))
            code = r["PoliticalInterestCode"].strip()
            cands.setdefault(num, {"name": r["ElectoralDistrictNameEnglish"].strip(), "cands": []})["cands"].append(
                {"name": recase(r["NameOfCandidates"].strip()), "party": PARTY.get(code, code), "votes": int(r["TotalValidBallotsCast"])})
    stats = {}
    with open(DL / "district_stats_2025.csv", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            if "2025" not in r["EventNameEnglish"] or "General" not in r["EventNameEnglish"]:
                continue
            stats[str(int(r["ElectoralDistrictNumber"]))] = r
    divisions = {}
    for num, d in cands.items():
        o = by_num.get(num)
        if not o:
            print("results riding matches no Represent boundary:", num, d["name"], file=sys.stderr)
            continue
        if norm(o["name"]) != norm(d["name"]):
            print(f"name differs for {num}: Elections Ontario {d['name']!r}, Represent {o['name']!r}", file=sys.stderr)
        results = sorted(d["cands"], key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        win, second = results[0], results[1]
        s = stats.get(num, {})
        registered = int(s.get("TotalNumberOfNames") or 0)
        cast = int(s.get("VoterTurnoutTotal") or 0)
        if s and int(s.get("ValidBallotsFromBoxes") or 0) != valid:
            print(f"{num} {d['name']}: candidates sum to {valid} valid votes, summary says {s.get('ValidBallotsFromBoxes')}", file=sys.stderr)
        divisions[num] = {
            "num": num, "slug": o["url"].rstrip("/").split("/")[-1],
            "winner_2025": win["name"], "party_2025": win["party"],
            "runnerup_2025": second["name"], "runnerup_party_2025": second["party"],
            "votes_2025": win["votes"], "runnerup_votes_2025": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2025": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "valid_votes_2025": valid,
            "turnout_pct": round(100 * float(s["VoterTurnoutPercentageOfList"]), 1) if s.get("VoterTurnoutPercentageOfList")
            else (round(100 * cast / registered, 1) if registered else 0),
            "registered_voters_2025": registered,
            "name": d["name"],
        }
    if len(divisions) != 124:
        print(f"warning: {len(divisions)} ridings parsed, expected 124", file=sys.stderr)
    return divisions


def person(name):
    """'Hon. Peter Bethlenfalvy' -> 'Peter Bethlenfalvy'."""
    name = re.sub(r"\s+", " ", name).strip()
    return re.sub(r"^(Hon\.|Honourable)\s+", "", name)


def ola_rows():
    """(name, party, riding) from the saved table."""
    path = DL / "ola_members.html"
    if path.exists():
        text = open(path, encoding="utf-8", errors="replace").read()
        rows = []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
            cells = [htmlmod.unescape(re.sub(r"<[^>]+>", " ", c)) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            cells = [re.sub(r"\s+", " ", c).strip() for c in cells]
            if len(cells) >= 3 and cells[1] and cells[2]:
                rows.append(cells[:3])
        if rows:
            return rows
    rows = []
    for line in open(DL / "ola_members.tsv", encoding="utf-8"):
        parts = line.rstrip("\n").split("\t")
        if len(parts) >= 3 and parts[0].strip():
            rows.append([p.strip() for p in parts[:3]])
    return rows


def load_mlas(divisions):
    by_name = {norm(d["name"]): d for d in divisions.values()}
    seen = set()
    for name, party, riding in ola_rows():
        d = by_name.get(norm(riding))
        if not d:
            print("MPP riding matches no result:", riding, file=sys.stderr)
            continue
        seen.add(d["num"])
        d["mla"] = person(name)
        d["mla_party"] = CAUCUS.get(party, party)
        # Compare surnames only: the Assembly writes "Jennifer (Jennie) Stevens", middle initials, etc.
        if norm(d["mla"]).split()[-1] != norm(d["winner_2025"]).split()[-1]:
            when = BYELECTIONS.get(d["num"])
            d["mla_note"] = (f"elected at the {when} by-election; the 2025 result is {d['winner_2025']}'s" if when else
                             f"not the 2025 winner ({d['winner_2025']}, {d['party_2025']}); by-election or change since")
        elif d["mla_party"] != d["party_2025"]:
            d["mla_note"] = f"elected as {d['party_2025']} in 2025, now sits as {d['mla_party']}"
        if d.get("mla_note"):
            print(f"note: {d['name']}: {d['mla_note']}", file=sys.stderr)
    for d in divisions.values():
        if d["num"] not in seen:
            d["mla"], d["mla_party"] = "Vacant", ""


# ------------------------------------------------------------------ population

def pop_column(fieldnames):
    return next(c for c in fieldnames if c.startswith("Population and dwelling counts") and "Population, 2021" in c)


def load_fed_population():
    """{normalised 2013 federal district name: 2021 population} for Ontario."""
    out = {}
    with open(DL / "statcan" / "98100010.csv", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        col = pop_column(rd.fieldnames)
        for r in rd:
            if r["DGUID"].startswith("2013A000435"):
                out[norm(r["GEO"])] = int(r[col] or 0)
    return out


def northern_csds():
    """[(csduid, name, 2021 population)] for populated subdivisions of the northern census divisions."""
    out = []
    with open(DL / "statcan" / "98100002.csv", encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        col = pop_column(rd.fieldnames)
        for r in rd:
            g = r["DGUID"]
            if g.startswith("2021A000535") and g[9:13] in NORTH_CDS and int(r[col] or 0) > 0:
                out.append((g[9:], r["GEO"], int(r[col])))
    return out


def csd_centroid(csduid):
    """(lat, lon) of the subdivision from Represent's 2016 census-subdivision set, cached."""
    cache = RAW / "csd_centroid"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{csduid}.json"
    if not path.exists() and not get(f"{API}/boundaries/census-subdivisions/{csduid}/", path):
        return None
    try:
        lon, lat = json.load(open(path))["centroid"]["coordinates"]
    except (KeyError, ValueError, TypeError):
        print("no centroid for subdivision", csduid, file=sys.stderr)
        return None
    return lat, lon


def load_population(divisions, simple):
    from geo import RidingIndex
    fed = load_fed_population()
    index = RidingIndex([(num, simple[num]) for num in divisions if num in simple])
    csd_sum = Counter()
    unplaced = []
    for csduid, name, pop in northern_csds():
        pt = csd_centroid(csduid)
        num = index.locate(*pt)[0] if pt else None
        if num:
            csd_sum[num] += pop
        else:
            unplaced.append((csduid, name, pop))
    if unplaced:
        print("subdivisions not placed:", unplaced, file=sys.stderr)
    for d in divisions.values():
        n = norm(d["name"])
        if d["num"] in NORTH_RIDINGS:
            d["population"] = csd_sum.get(d["num"], 0)
            d["population_basis"] = BASIS_CSD
            if n in fed:
                print(f"check {d['name']}: subdivision sum {d['population']:,} vs federal district {fed[n]:,}")
        elif n in fed:
            d["population"] = fed[n]
            d["population_basis"] = BASIS_FED
        else:
            d["population"] = 0
            print("no population for", d["num"], d["name"], file=sys.stderr)
        if d["population"] == 0:
            print("zero population for", d["num"], d["name"], file=sys.stderr)
    south_spill = {num: v for num, v in csd_sum.items() if num not in NORTH_RIDINGS}
    if south_spill:
        print("northern subdivisions whose centroid falls in a southern riding (already in that riding's federal count):",
              {divisions[k]["name"]: v for k, v in south_spill.items()})


# ------------------------------------------------------------------ shapes

def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def touches_inset(geom):
    x0, y0, x1, y1 = bounds(geom)
    return any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in INSETS)


def fetch_fine_shapes(divisions, simple):
    cache = RAW / "shape"
    cache.mkdir(parents=True, exist_ok=True)
    wanted = sorted((num for num, geom in simple.items() if num in divisions and touches_inset(geom)), key=int)
    for k, num in enumerate(wanted):
        slug = divisions[num]["slug"]
        out = cache / f"{slug}.json"
        if out.exists():
            continue
        if get(f"{API}/boundaries/{BOUNDARY_SET}/{slug}/shape", out):
            print(f"fine shape {k + 1}/{len(wanted)} {slug}", flush=True)
    return wanted


def feature(num, geom, tol, min_extent):
    return {"type": "Feature", "id": num, "properties": {"num": num},
            "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, min_extent)}}


def main():
    fetch_all()
    OUT.mkdir(parents=True, exist_ok=True)
    listing = json.load(open(DL / "represent_list.json"))["objects"]
    num_by_name = {norm(o["name"]): o["external_id"] for o in listing}
    simple = {num_by_name[norm(o["name"])]: o["simple_shape"] for o in json.load(open(DL / "represent_simple.json"))["objects"]}

    divisions = load_results(listing)
    load_mlas(divisions)
    load_population(divisions, simple)
    scale_population(divisions, lambda r: "Ontario")
    divisions = dict(sorted(divisions.items(), key=lambda kv: int(kv[0])))
    missing = set(simple) - set(divisions)
    if missing:
        print("boundaries with no result:", sorted(missing), file=sys.stderr)

    geo = {"type": "FeatureCollection", "features": [feature(n, simple[n], 0.002, 0.005) for n in divisions if n in simple]}
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))

    wanted = fetch_fine_shapes(divisions, simple)
    fine = {"type": "FeatureCollection", "features": []}
    for num in wanted:
        path = RAW / "shape" / f"{divisions[num]['slug']}.json"
        if path.exists():
            fine["features"].append(feature(num, json.load(open(path)), 0.0004, 0.001))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2025"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"{len(divisions)} ridings, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in 2025, "
          f"seats 2025 {dict(seats)}, now {dict(now)}")
    print(f"population 2021 {sum(d['population_2021'] for d in divisions.values()):,}, scaled "
          f"{sum(d['population'] for d in divisions.values()):,}; registered voters {sum(d['registered_voters_2025'] for d in divisions.values()):,}")


if __name__ == "__main__":
    main()
