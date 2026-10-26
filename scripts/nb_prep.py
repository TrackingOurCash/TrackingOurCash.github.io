"""New Brunswick: build the electoral-district table (49 districts, 2023 commission map,
first used at the 21 October 2024 general election).

Joins the 2024 results per poll (winner, runner-up, votes, margin), the current member
list of the Legislative Assembly, the boundaries commission's elector counts, and
Represent's boundaries. Mirrors bc_prep.py; keys use "2024" as BC does.

Inputs (data/raw/nb/; URLs in notes/provincial-sources.md, "Source survey, part 2"):
  represent_list.json, represent_simple.json
      Represent set new-brunswick-electoral-districts-2024 (list and simple_shape, one
      request each, limit=100)
  shape/<slug>.json
      Represent's full-detail shape for districts whose bounding box touches the Moncton,
      Saint John or Fredericton inset; fetched here when missing, ~1 request per 1.1 s
  results_2024.zip -> results_2024/results_per_poll.xlsx, results_per_tab.xlsx
      Elections NB 2024-10-21-Results-Resultats.zip (the zip's file names have accents
      that unzip rejects, so they are extracted here with plain names)
  mlas_current.html          https://www.legnb.ca/en/members/current
  ebrc-final-report.pdf      commission final report (70 MB, Appendix B riding profiles)
  amended-final-report.pdf   amended final report (3.5 MB; revised table for EDs 15, 16)
  commission_electors.json   cache of the table read from the two PDFs (written here), so
                             the 70 MB PDF can be deleted once it has been read once

Outputs:
  data/nb/divisions.json          one record per district, keyed by Represent's slug
  data/nb/divisions_geo.json      simplified GeoJSON (clean_polygons, tol 0.002, min 0.005)
  data/nb/divisions_geo_fine.json lighter simplification (tol 0.0004) of the full shapes
                                  for the 25 districts that touch a city inset

Choices made here:
  * The district key ("num") is Represent's URL slug ("moncton-centre"): the Represent
    list carries no external_id for this set. The official 1-49 number from the results
    workbook is kept as "ed_num".
  * Results: the per-poll workbook, one sheet, a block per district headed
    "MLA / Député, NN Name / Nom (Vote for / Voter pour 1)", then a "Poll/Sdv" header row
    whose candidate columns read "Given SURNAME - PARTY", poll rows, an
    "Undetermined/Indéterminée" row (counted: these are valid votes assigned to no poll)
    and a "Total" row. Votes are summed over the poll rows and checked against the Total
    row. Candidate surnames are re-cased ("Diane CYR" -> "Diane Cyr"). No registered
    elector count is in the workbook, so there is no turnout_pct.
  * Party codes (ballot label -> short label): PC -> PC, L -> LIB, PVNBGP -> GRN,
    NBNDP -> NDP, PANB -> PANB (People's Alliance), LPNB -> LBT (Libertarian),
    CNBP -> CNBP (Consensus NB), SJPNB -> SJP (Social Justice), IND -> IND.
  * Current MLAs: the member cards on legnb.ca (name "Surname, Given", party, district),
    matched by normalised district name. Where the member is not the 2024 winner
    (Miramichi West: Kevin Russell, PC, elected at the 6 October 2025 by-election) the
    2024 result is left as it was and "mla_note" says so.
  * Population: no census population by provincial district is published for New
    Brunswick, and the commission reports count electors, not residents. "population"
    is therefore the commission's ESTIMATED ELECTORS per district (final report Appendix
    B, 2022 register), with the amended final report's revised figures for Shediac-Cap-
    Acadie (15) and Tantramar (16). The raw figure is kept as "electors_commission" and
    "population_basis" says what it is. scale_population() is still applied for schema
    consistency (population_2021 = the elector count, population = that count scaled by
    the province's growth since 2021), so per-capita figures are per elector, not per
    resident; they are comparable within the province but not with other provinces.
    The PDFs' body text uses CID fonts (Identity-H, hex strings of glyph ids), which
    sk_pdf cannot read on its own; the fonts' ToUnicode maps are parsed here and
    sk_pdf._decode_string is wrapped to use them.
"""
import json
import re
import sys
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "nb"
OUT = ROOT / "data" / "nb"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import scale_population, clean_polygons, polys_of  # noqa: E402

API = "https://represent.opennorth.ca"
BOUNDARY_SET = "new-brunswick-electoral-districts-2024"
# Moncton, Saint John, Fredericton: (west, south, east, north).
INSETS = [(-64.9, 46.03, -64.65, 46.17), (-66.2, 45.2, -65.95, 45.35), (-66.75, 45.88, -66.55, 46.0)]
PARTY = {"PC": "PC", "L": "LIB", "PVNBGP": "GRN", "NBNDP": "NDP", "PANB": "PANB", "LPNB": "LBT", "CNBP": "CNBP",
         "SJPNB": "SJP", "IND": "IND"}
CAUCUS = {"Liberal Party": "LIB", "Progressive Conservative Party": "PC", "Green Party": "GRN",
          "New Democratic Party": "NDP", "People's Alliance": "PANB", "Independent": "IND"}
POPULATION_BASIS = ("estimated electors per district from the Electoral Boundaries and Representation Commission's "
                    "final report (Appendix B, 2022 register), amended for districts 15 and 16; New Brunswick "
                    "publishes no census population by provincial district")


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def xlsx_sheets(path):
    """Yield (sheet name, rows as {column letter: value}) for every sheet, stdlib only."""
    z = zipfile.ZipFile(path)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", ns):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
    for s in wb.find("m:sheets", ns):
        target = rels[s.get("{%s}id" % ns["r"])]
        target = target if target.startswith("xl/") else "xl/" + target.lstrip("/")
        rows = []
        for row in ET.fromstring(z.read(target)).iter("{%s}row" % ns["m"]):
            cells = {}
            for c in row.findall("m:c", ns):
                col = re.match(r"([A-Z]+)", c.get("r")).group(1)
                v = c.find("m:v", ns)
                if v is not None:
                    cells[col] = shared[int(v.text)] if c.get("t") == "s" else v.text
                elif c.get("t") == "inlineStr":
                    cells[col] = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
            rows.append(cells)
        yield s.get("name"), rows


def recase(name):
    """'Hugh J. (Ted) FLEMMING' -> 'Hugh J. (Ted) Flemming'; 'Tom L'HUILLIER' -> "Tom L'Huillier"."""
    def fix(word):
        if not (len(word) > 1 and word.isupper()):
            return word
        parts = re.split(r"([-'’])", word)
        out = []
        for p in parts:
            if p in "-'’":
                out.append(p)
            elif p.startswith("MC") and len(p) > 2:
                out.append("Mc" + p[2:].capitalize())
            else:
                out.append(p.capitalize())
        return "".join(out)
    return " ".join(fix(w) for w in name.split())


def extract_results_zip():
    """Write results_2024/results_per_poll.xlsx and results_per_tab.xlsx from the zip."""
    folder = RAW / "results_2024"
    if (folder / "results_per_poll.xlsx").exists():
        return
    folder.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(RAW / "results_2024.zip")
    for info in z.infolist():
        if not info.filename.lower().endswith(".xlsx"):
            continue
        name = "results_per_poll.xlsx" if "Poll" in info.filename else "results_per_tab.xlsx"
        (folder / name).write_bytes(z.read(info))


def load_results(slug_by_name):
    extract_results_zip()
    _, rows = next(xlsx_sheets(RAW / "results_2024" / "results_per_poll.xlsx"))
    divisions = {}
    i = 0
    while i < len(rows):
        head = rows[i].get("A") or ""
        m = re.match(r"MLA / Député, (\d+) (.+?) \(Vote for", head)
        if not m:
            i += 1
            continue
        ed_num = str(int(m.group(1)))
        name = m.group(2).split(" / ")[0].strip()
        i += 1
        while not (rows[i].get("A") or "").startswith("Poll/Sdv"):
            i += 1
        header = rows[i]
        cands = {}
        for col, label in header.items():
            if col == "A":
                continue
            label = re.sub(r"\s*\((withdrew|retir).*\)\s*", " ", label, flags=re.S | re.I).strip()
            who, party = label.rsplit(" - ", 1)
            cands[col] = (recase(who.strip()), PARTY.get(party.split(" / ")[0].strip(), party.split(" / ")[0].strip()))
        votes = {col: 0 for col in cands}
        total_row = None
        i += 1
        while i < len(rows) and not (rows[i].get("A") or "").startswith("MLA / Député"):
            r = rows[i]
            label = (r.get("A") or "").strip()
            if label == "Total":
                total_row = r
            elif label and r.get("B") is not None:
                for col in cands:
                    votes[col] += int(float(r.get(col) or 0))
            i += 1
        if total_row:
            for col in cands:
                if int(float(total_row.get(col) or 0)) != votes[col]:
                    print(f"ED {ed_num}: summed {votes[col]} but Total row says {total_row.get(col)} for {cands[col][0]}", file=sys.stderr)
        results = sorted(({"name": n, "party": p, "votes": votes[col]} for col, (n, p) in cands.items()), key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        win, second = results[0], results[1]
        slug = slug_by_name.get(norm(name))
        if not slug:
            print("results district matches no Represent boundary:", name, file=sys.stderr)
            continue
        divisions[slug] = {
            "num": slug, "ed_num": ed_num,
            "winner_2024": win["name"], "party_2024": win["party"],
            "runnerup_2024": second["name"], "runnerup_party_2024": second["party"],
            "votes_2024": win["votes"], "runnerup_votes_2024": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2024": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "valid_votes_2024": valid,
            "name": name,
        }
    return divisions


def person(name):
    """'Miles, Cindy' -> 'Cindy Miles'; 'McKee, K.C., Robert' -> 'Robert McKee'."""
    parts = [p.strip() for p in name.split(",")]
    if len(parts) >= 2:
        return f"{parts[-1]} {parts[0]}"
    return name.strip()


def load_mlas(divisions):
    import html
    text = open(RAW / "mlas_current.html", encoding="utf-8").read()
    by_name = {norm(d["name"]): d for d in divisions.values()}
    seen = set()
    for card in re.findall(r'<div class="member-card.*?</ul>', text, re.S):
        name = html.unescape(re.search(r"<h3>(.*?)</h3>", card).group(1)).strip()
        party = re.search(r'member-card-party-dot"[^>]*></div>\s*(.*?)\s*</li>', card, re.S).group(1).strip()
        riding = html.unescape(re.search(r'fa-map-marker-alt"></i><span>(.*?)</span>', card, re.S).group(1)).strip()
        d = by_name.get(norm(riding))
        if not d:
            print("MLA district matches no result:", riding, file=sys.stderr)
            continue
        seen.add(d["num"])
        d["mla"] = person(name)
        d["mla_party"] = CAUCUS.get(party, party)
        # Compare surnames only: the assembly writes "Robert McKee" where the ballot had "Rob McKee".
        if norm(d["mla"]).split()[-1] != norm(d["winner_2024"]).split()[-1]:
            d["mla_note"] = f"not the 2024 winner ({d['winner_2024']}, {d['party_2024']}); by-election or change since"
            if d["num"] == "miramichi-west":
                d["mla_note"] = "elected at the 6 October 2025 by-election; the 2024 result is Mike Dawson's"
    for d in divisions.values():
        if d["num"] not in seen:
            d["mla"], d["mla_party"] = "Vacant", ""


# ------------------------------------------------------------------ commission PDFs

def pdf_text_pages(path):
    """sk_pdf.pdf_pages with the document's ToUnicode maps applied to CID-font hex strings."""
    import sk_pdf
    data = open(path, "rb").read()
    objs = sk_pdf._objects(data)
    cmap = {}

    def add(code, text):
        cmap.setdefault(code, text)

    for n, (d, _) in objs.items():
        if b"/Type0" not in d:
            continue
        m = re.search(rb"/ToUnicode\s+(\d+)\s+0\s+R", d)
        if not m or int(m.group(1)) not in objs:
            continue
        td, tr = objs[int(m.group(1))]
        body = sk_pdf._inflate(tr or b"", td)
        for blk in re.finditer(rb"beginbfchar(.*?)endbfchar", body, re.S):
            for src, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk.group(1)):
                add(int(src, 16), bytes.fromhex(dst.decode()).decode("utf-16-be", "replace"))
        for blk in re.finditer(rb"beginbfrange(.*?)endbfrange", body, re.S):
            for lo, hi, dst in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk.group(1)):
                lo, hi, base = int(lo, 16), int(hi, 16), int(dst, 16)
                for c in range(lo, min(hi, lo + 255) + 1):
                    add(c, chr(base + c - lo))
            for lo, hi, arr in re.findall(rb"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*\[(.*?)\]", blk.group(1), re.S):
                for k, dst in enumerate(re.findall(rb"<([0-9A-Fa-f]+)>", arr)):
                    add(int(lo, 16) + k, bytes.fromhex(dst.decode()).decode("utf-16-be", "replace"))
    original = sk_pdf._decode_string

    def decode(tok):
        if tok.startswith(b"<") and cmap:
            h = re.sub(rb"\s", b"", tok[1:-1])
            if h and len(h) % 4 == 0:
                return "".join(cmap.get(int(h[k:k + 4], 16), "�") for k in range(0, len(h), 4))
        return original(tok)

    sk_pdf._decode_string = decode
    try:
        return sk_pdf.pdf_pages(path)
    finally:
        sk_pdf._decode_string = original


ELECTORS_LINE = re.compile(r"^(\d{1,2})\s+(?:\D+?\s+)?(\d{1,3}(?:,\d{3})?)\s+11,?667\s")


def read_commission_table(path):
    """{ed number: estimated electors} from the 'ESTIMATED ELECTORS ... ELECTORAL QUOTIENT' tables."""
    out = {}
    for page in pdf_text_pages(path):
        if not any("ESTIMATED" in line and "ELECTOR" in line for line in page):
            continue
        for line in page:
            m = ELECTORS_LINE.match(line)
            if m:
                out[m.group(1)] = int(m.group(2).replace(",", ""))
    return out


def load_population(divisions):
    cache = RAW / "commission_electors.json"
    electors = {}
    final, amended = RAW / "ebrc-final-report.pdf", RAW / "amended-final-report.pdf"
    if final.exists():
        electors.update(read_commission_table(final))
        print("final report:", len(electors), "districts with elector counts")
    if amended.exists():
        revised = read_commission_table(amended)
        print("amended report revises:", revised)
        electors.update(revised)
    if len(electors) == 49:
        json.dump(electors, open(cache, "w"), indent=1)
    elif cache.exists():
        print("using cached commission_electors.json", file=sys.stderr)
        electors = json.load(open(cache))
    for d in divisions.values():
        d["population"] = electors.get(d["ed_num"], 0)
        d["electors_commission"] = d["population"]
        d["population_basis"] = POPULATION_BASIS
        if d["population"] == 0:
            print("no elector count for", d["ed_num"], d["name"], file=sys.stderr)


# ------------------------------------------------------------------ shapes

def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def touches_inset(geom):
    x0, y0, x1, y1 = bounds(geom)
    return any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in INSETS)


def fetch_fine_shapes(simple):
    cache = RAW / "shape"
    cache.mkdir(parents=True, exist_ok=True)
    wanted = sorted(slug for slug, geom in simple.items() if touches_inset(geom))
    for k, slug in enumerate(wanted):
        out = cache / f"{slug}.json"
        if out.exists():
            continue
        time.sleep(1.1)
        url = f"{API}/boundaries/{BOUNDARY_SET}/{slug}/shape"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "riding-spending (research)"}), timeout=120) as r:
                shp = json.load(r)
        except Exception as e:  # noqa: BLE001
            print("shape fetch failed:", slug, e, file=sys.stderr)
            continue
        json.dump(shp, open(out, "w"))
        print(f"fine shape {k + 1}/{len(wanted)} {slug}", flush=True)
    return wanted


def feature(slug, geom, tol, min_extent):
    return {"type": "Feature", "id": slug, "properties": {"num": slug},
            "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, min_extent)}}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    listing = json.load(open(RAW / "represent_list.json"))["objects"]
    slug_by_name = {norm(o["name"]): o["url"].rstrip("/").split("/")[-1] for o in listing}
    simple = {slug_by_name[norm(o["name"])]: o["simple_shape"] for o in json.load(open(RAW / "represent_simple.json"))["objects"]}

    divisions = load_results(slug_by_name)
    load_mlas(divisions)
    load_population(divisions)
    scale_population(divisions, lambda r: "New Brunswick")
    divisions = dict(sorted(divisions.items(), key=lambda kv: int(kv[1]["ed_num"])))
    missing = set(simple) - set(divisions)
    if missing:
        print("boundaries with no result:", sorted(missing), file=sys.stderr)

    geo = {"type": "FeatureCollection", "features": [feature(s, simple[s], 0.002, 0.005) for s in divisions if s in simple]}
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))

    wanted = fetch_fine_shapes(simple)
    fine = {"type": "FeatureCollection", "features": []}
    for slug in wanted:
        path = RAW / "shape" / f"{slug}.json"
        if path.exists() and slug in divisions:
            fine["features"].append(feature(slug, json.load(open(path)), 0.0004, 0.001))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    print("fine shapes:", len(fine["features"]))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    print(f"{len(divisions)} districts, {len(geo['features'])} shapes, {close} close in 2024,",
          sum(d["population"] for d in divisions.values()), "electors (scaled)")


if __name__ == "__main__":
    main()
