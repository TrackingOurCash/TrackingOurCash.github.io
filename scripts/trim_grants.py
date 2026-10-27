"""Write data/raw/grants_trim.csv: the Proactive Disclosure grants file cut to the columns the
pipeline reads. The full file is over 2 GB, mostly bilingual descriptions; the trimmed copy is a
fraction of that, and build_spending.py and fed_prov_spending.py read it when it exists, so the
file is parsed once instead of seven times per build."""
import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
COLS = ["ref_number", "amendment_number", "recipient_type", "recipient_business_number", "recipient_legal_name",
        "recipient_operating_name", "recipient_country", "recipient_province", "recipient_city", "recipient_postal_code",
        "federal_riding_name_en", "federal_riding_number", "prog_name_en", "agreement_title_en", "agreement_value",
        "agreement_start_date", "agreement_end_date", "coverage", "owner_org", "owner_org_title"]


def main():
    src, out, tmp = RAW / "grants.csv", RAW / "grants_trim.csv", RAW / "grants_trim.csv.tmp"
    if not src.exists():
        sys.exit(f"missing {src}")
    t0, n = time.time(), 0
    with open(src, encoding="utf-8-sig", newline="") as f, open(tmp, "w", encoding="utf-8", newline="") as g:
        reader = csv.DictReader(f)
        writer = csv.DictWriter(g, fieldnames=COLS, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            writer.writerow(row)
            n += 1
    tmp.replace(out)
    print(f"{n} rows, {out.stat().st_size / 1e6:.0f} MB in {time.time() - t0:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
