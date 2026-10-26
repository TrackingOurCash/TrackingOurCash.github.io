"""Scale 2021 census populations to Statistics Canada's latest quarterly estimates.

Riding-level populations exist only from the census, so each riding's 2021 count is
scaled by its province's growth since the census: factor = latest quarterly estimate
(table 17-10-0009-01, the figure behind the population clock) / 2021 census total for
the province (summed from the ridings). Writes data/population_scale.json.
"""
import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "statcan"
URL = "https://www150.statcan.gc.ca/n1/tbl/csv/17100009-eng.zip"


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    zpath = RAW / "17100009.zip"
    if not zpath.exists():
        urllib.request.urlretrieve(URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        rows = list(csv.DictReader(io.TextIOWrapper(z.open("17100009.csv"), encoding="utf-8-sig")))
    latest = max(r["REF_DATE"] for r in rows)
    estimate = {r["GEO"]: int(r["VALUE"]) for r in rows if r["REF_DATE"] == latest and r["VALUE"]}
    ridings = json.load(open(ROOT / "data" / "ridings.json"))
    census = {}
    for r in ridings.values():
        census[r["province"]] = census.get(r["province"], 0) + r["population"]
    out = {"latest_date": latest, "source": URL, "provinces": {}}
    for prov, c in census.items():
        est = estimate.get(prov)
        out["provinces"][prov] = {"census_2021": c, "estimate": est, "factor": round(est / c, 4) if est and c else 1.0}
    json.dump(out, open(ROOT / "data" / "population_scale.json", "w"), indent=1)
    for prov, v in sorted(out["provinces"].items(), key=lambda kv: -kv[1]["factor"]):
        print(f"{prov:28} {v['census_2021']:>10,} -> {v['estimate']:>10,}  x{v['factor']}")
    print("as of", latest)


if __name__ == "__main__":
    main()
