"""Alberta: build the electoral-division table (87 divisions, 2019 boundaries).

Joins the 2023 Statement of Vote (winner, runner-up, votes, margin), the current MLA
list, 2021 census population by division, and Represent's simplified boundaries.

Outputs:
  data/ab/divisions.json   one record per division, keyed by division number
  data/ab/divisions_geo.json   simplified GeoJSON
"""
import csv
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "ab"
OUT = ROOT / "data" / "ab"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons, polys_of  # noqa: E402

# Ballot party codes -> short labels used on the map.
PARTY = {"UCP": "UCP", "NDP": "NDP", "AP": "AP", "GPA": "GPA", "IND": "IND", "WLC": "WLC", "SM": "SM", "SPA": "SPA",
         "APP": "APP", "BUZ": "BUZ", "CPA": "CPA", "IPA": "IPA", "PRO": "PRO", "ACP": "ACP"}
# Assembly caucus codes -> short labels (UC = United Conservative, PTP = Progressive... floor-crossers).
CAUCUS = {"UC": "UCP", "NDP": "NDP", "IND": "IND", "PTP": "PTP"}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def read_text(path):
    raw = open(path, "rb").read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


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


def load_results():
    divisions = {}
    for sheet, rows in xlsx_sheets(RAW / "sov-2023.xlsx"):
        num = str(int(sheet))
        header = next(r for r in rows if r.get("A") == "Voting Location")
        cands = {col: v.split("\n") for col, v in header.items() if "\n" in (v or "")}
        total = next(r for r in rows if (r.get("B") or "").startswith("Total (All Voting"))
        results = []
        for col, (name, party) in cands.items():
            votes = int(float(total.get(col) or 0))
            results.append({"name": name.strip(), "party": PARTY.get(party.strip(), party.strip()), "votes": votes})
        results.sort(key=lambda c: -c["votes"])
        valid = sum(c["votes"] for c in results) or 1
        win, second = results[0], results[1]
        divisions[num] = {
            "num": num,
            "winner_2023": win["name"], "party_2023": win["party"],
            "runnerup_2023": second["name"], "runnerup_party_2023": second["party"],
            "votes_2023": win["votes"], "runnerup_votes_2023": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2023": {c["party"]: round(100 * c["votes"] / valid, 1) for c in results[:4]},
            "turnout_pct": round(100 * float(total.get("Q") or 0), 1),
        }
    return divisions


def load_mlas(divisions):
    rows = list(csv.reader(read_text(RAW / "mlas.csv").splitlines()))
    header = next(i for i, r in enumerate(rows) if r and r[0] == "Constituency Number")
    for r in rows[header + 1:]:
        if len(r) < 7 or not r[0].strip().isdigit():
            continue
        d = divisions[str(int(r[0]))]
        d["name"] = r[1].strip()
        d["mla"] = " ".join(x for x in (r[3], r[5]) if x).strip()
        d["mla_party"] = CAUCUS.get(r[6].strip(), r[6].strip())
    for d in divisions.values():
        d.setdefault("name", f"Division {d['num']}")
        d.setdefault("mla", "Vacant")
        d.setdefault("mla_party", "")


def load_population(divisions):
    for row in csv.DictReader(read_text(RAW / "ped-census-2021.csv").splitlines()):
        if row["Dimension"].startswith("Total - Age groups") and row["group"] == "Total" and row["PED_Number"] in divisions:
            divisions[row["PED_Number"]]["population"] = int(row["Value"].replace(",", ""))
    for d in divisions.values():
        d.setdefault("population", 0)


def load_shapes(divisions):
    ids = {}
    for o in json.load(open(RAW / "ab2017_list.json"))["objects"]:
        ids[o["name"]] = o["external_id"]
    by_name = {norm(d["name"]): d["num"] for d in divisions.values()}
    features = []
    for o in json.load(open(RAW / "ab2017_simple.json"))["objects"]:
        num = ids[o["name"]]
        num = num if num in divisions else by_name.get(norm(o["name"]))
        if not num:
            print("no division for shape", o["name"], file=sys.stderr)
            continue
        features.append({"type": "Feature", "id": num, "properties": {"num": num},
                         "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(o["simple_shape"]), 0.002, 0.005)}})
    return {"type": "FeatureCollection", "features": features}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    divisions = load_results()
    load_mlas(divisions)
    load_population(divisions)
    geo = load_shapes(divisions)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    print(f"{len(divisions)} divisions, {len(geo['features'])} shapes, {close} close in 2023,",
          sum(d['population'] for d in divisions.values()), "people")


if __name__ == "__main__":
    main()
