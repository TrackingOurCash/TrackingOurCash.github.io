"""Inline the riding data and shapes into one HTML page: output/riding_spending_map.html."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

KEEP = ["num", "current_name", "province", "population", "party_2025", "runnerup_party_2025", "margin_pts",
        "shares_2025", "winner_2025", "mp", "mp_party", "after_total", "after_n", "after_adj", "after_adj_n",
        "before_adj", "before_total", "runnerup_2025", "votes_2025", "runnerup_votes_2025", "margin_votes", "pc_after", "pc_after_all", "pc_before", "change_pc", "change_pct", "score", "close",
        "lib_won", "group", "top_depts", "top_grants"]


def main():
    sp = json.load(open(DATA / "riding_spending.json"))
    geo = json.load(open(DATA / "ridings_geo.json"))
    ridings = {n: {k: r[k] for k in KEEP} for n, r in sp["ridings"].items()}
    meta = dict(sp["meta"])
    meta.pop("top_flagged_recipients", None)
    payload = {
        "meta": meta,
        "groups": sp["groups"],
        "ridings": ridings,
        "dept": sp["dept_by_riding"],
        "deptBefore": sp["dept_by_riding_before"],
        "geo": geo,
    }
    tpl = (ROOT / "scripts" / "map_template.html").read_text()
    html = tpl.replace("/*__DATA__*/null", json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    # Standalone file for opening on this Mac, plus the bare fragment the Artifact publisher wraps itself.
    out = ROOT / "output" / "riding_spending_map.html"
    out.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                   + html.replace("<div class=\"wrap\">", "</head>\n<body>\n<div class=\"wrap\">", 1)
                   + "</body>\n</html>\n")
    (ROOT / "output" / "artifact.html").write_text(html)
    print(out, f"{out.stat().st_size / 1e6:.2f} MB")

    cols = ["num", "current_name", "province", "population", "mp", "mp_party", "party_2025", "runnerup_party_2025",
            "margin_pts", "close", "group", "after_adj", "after_total", "after_n", "before_adj", "before_total",
            "pc_after", "pc_after_all", "pc_before", "change_pct", "score"]
    with open(ROOT / "output" / "riding_spending.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in sorted(sp["ridings"].values(), key=lambda r: -r["pc_after"]):
            w.writerow([r[c] for c in cols])


if __name__ == "__main__":
    main()
