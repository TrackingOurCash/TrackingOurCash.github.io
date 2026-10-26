"""Aggregate federal contracts over $10,000 by 2023-order riding.

Reads data/raw/contracts/contracts.csv (Proactive Publication - Contracts,
open.canada.ca dataset d8f85d91-7dec-4fd1-8055-483b77225d8b) and writes
data/contracts_by_riding.json, mirroring data/riding_spending.json so the page
can switch between grants and contracts.

Method, in order:
  1. One pass over the full file (streaming, nothing held in memory) writes two
     caches next to it: recent.csv (rows whose contract_date or
     contract_period_start is 2024-01-01 or later) and vendor_postal.json (each
     vendor's most common postal code across every year, so a later contract
     with no postal code can be placed). Both are rebuilt only when the source
     file is newer.
  2. Amendments: rows sharing (owner_org, procurement_id), or reference_number
     when the department leaves procurement_id blank, are one contract. The
     contract's date is the earliest contract_date (the original award); its
     value is the latest row's contract_value (the current total, as the data
     dictionary defines "Total Contract Value"). Standing offers and supply
     arrangements (instrument_type SOSA) are frameworks, not spending, and are
     dropped.
  3. Riding: the vendor postal code's GeoNames centroid inside the 2023
     boundaries; otherwise the vendor's address on its other contracts; otherwise
     the centroid of the first three characters (FSA), marked approximate.
     Contracts carry no city, so there is no city fallback.
  4. Vendors outside Canada (country_of_vendor not CA) are counted under
     meta.foreign and never placed in a riding.
  5. Windows, cutoff and quarter labels are taken from data/riding_spending.json
     so both layers cover the same dates: "after" = election day to the cutoff,
     "before" = the same calendar dates one year earlier. Per-person figures use
     data/ridings.json population and years_per_window.
"""
import csv
import json
import os
import re
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from geo import RidingIndex, load_centroids

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "contracts"
OUT = ROOT / "data"
SOURCE = RAW / "contracts.csv"
RECENT = RAW / "recent.csv"
VENDOR_PC = RAW / "vendor_postal.json"
KEEP_FROM = "2024-01-01"

csv.field_size_limit(sys.maxsize)

KEEP_COLS = ["reference_number", "procurement_id", "vendor_name", "vendor_postal_code", "contract_date",
             "contract_period_start", "delivery_date", "contract_value", "original_value", "amendment_value",
             "economic_object_code", "description_en", "commodity_type", "commodity_code", "agreement_type_code",
             "country_of_vendor", "solicitation_procedure", "contracting_entity", "instrument_type",
             "ministers_office", "reporting_period", "owner_org", "owner_org_title"]

PROCEDURE = {"AC": "advance contract award notice", "OB": "competitive (open bidding)", "ST": "competitive (selective)",
             "TC": "competitive (traditional)", "TN": "non-competitive"}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def first(v):
    return (v or "").split("|")[0].strip()


def clean_postal(pc):
    pc = re.sub(r"[^A-Za-z0-9]", "", pc or "").upper()
    return pc if re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", pc) else ""


def to_float(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return 0.0


def iso(v):
    v = (v or "").strip()[:10]
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else ""


def build_cache():
    """Stream the full file once: keep recent rows, and remember each vendor's postal code."""
    t0 = time.time()
    stats = Counter()
    votes = defaultdict(Counter)
    with open(SOURCE, encoding="utf-8-sig", newline="") as f, open(RECENT, "w", encoding="utf-8", newline="") as g:
        reader = csv.DictReader(f)
        writer = csv.DictWriter(g, fieldnames=KEEP_COLS, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            stats["rows"] += 1
            if None in row or row.get("owner_org") is None:
                stats["malformed"] += 1
                continue
            pc = clean_postal(row["vendor_postal_code"])
            if pc and (row["country_of_vendor"] or "CA") == "CA":
                votes[norm(row["vendor_name"])][pc] += 1
            if max(iso(row["contract_date"]), iso(row["contract_period_start"])) >= KEEP_FROM:
                stats["recent"] += 1
                writer.writerow(row)
    json.dump({k: c.most_common(1)[0][0] for k, c in votes.items() if k}, open(VENDOR_PC, "w"))
    stats["vendors_with_postal"] = len(votes)
    stats["seconds"] = round(time.time() - t0, 1)
    print("cache built:", dict(stats), file=sys.stderr)
    return stats


def main():
    t0 = time.time()
    if not SOURCE.exists():
        sys.exit(f"missing {SOURCE}; download it first (see run.sh / README)")
    cache_stats = {}
    if not RECENT.exists() or not VENDOR_PC.exists() or os.path.getmtime(SOURCE) > os.path.getmtime(RECENT):
        cache_stats = dict(build_cache())

    ridings = json.load(open(OUT / "ridings.json"))
    gmeta = json.load(open(OUT / "riding_spending.json"))["meta"]
    election = date.fromisoformat(gmeta["election"])
    cutoff = date.fromisoformat(gmeta["cutoff"])
    before_start = date.fromisoformat(gmeta["before_start"])
    before_end = date.fromisoformat(gmeta["before_end"])
    years = gmeta["years_per_window"]
    labels = gmeta["series"]["labels"]
    qlabel = lambda d: f"{d.year}Q{(d.month - 1) // 3 + 1}"

    vendor_pc = json.load(open(VENDOR_PC))
    stats = Counter()
    contracts = {}
    seen_refs = Counter()
    with open(RECENT, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            stats["recent_rows"] += 1
            seen_refs[(row["owner_org"], row["reference_number"].strip())] += 1
            itype = (row["instrument_type"] or "").strip().upper()
            if itype == "SOSA":
                stats["sosa_rows_dropped"] += 1
                continue
            cdate = iso(row["contract_date"]) or iso(row["contract_period_start"])
            if not cdate:
                stats["rows_without_date"] += 1
                continue
            pid = (row["procurement_id"] or "").strip()
            key = (row["owner_org"], "p:" + pid if pid else "r:" + row["reference_number"].strip())
            # The data dictionary says contract_value is the total including amendments; where a
            # department leaves it blank, original + amendment is the best reconstruction.
            value = to_float(row["contract_value"])
            if not value:
                value = to_float(row["original_value"]) + to_float(row["amendment_value"])
            amend = to_float(row["amendment_value"])
            if itype == "A":
                stats["amendment_rows"] += 1
                if amend < 0:
                    stats["negative_amendments"] += 1
                    stats["negative_amendment_$"] += amend
            pc = clean_postal(row["vendor_postal_code"])
            country = (row["country_of_vendor"] or "").strip().upper()
            if not country:
                stats["rows_without_country"] += 1
            if not pc:
                stats["rows_without_postal"] += 1
            rec = {
                "date": cdate, "value": value, "order": (row["reporting_period"] or "", cdate),
                "dept": first(row["owner_org_title"]), "org": row["owner_org"], "ref": row["reference_number"].strip(), "pid": pid,
                "vendor": (row["vendor_name"] or "").strip(), "pc": pc, "country": country,
                "desc": (row["description_en"] or "").strip()[:100], "how": PROCEDURE.get((row["solicitation_procedure"] or "").strip(), ""),
                "itype": itype, "ministers": row["ministers_office"] == "Y", "ctype": row["commodity_type"],
                "n_rows": 1,
            }
            prev = contracts.get(key)
            if prev is None:
                contracts[key] = rec
                continue
            stats["rows_merged"] += 1
            earliest = min(prev["date"], cdate)
            # The latest row carries the current total; the original row carries the award date.
            if rec["order"] >= prev["order"]:
                rec["pc"] = rec["pc"] or prev["pc"]
                rec["country"] = rec["country"] or prev["country"]
                rec["desc"] = rec["desc"] or prev["desc"]
                rec["n_rows"] = prev["n_rows"] + 1
                contracts[key] = rec
            else:
                prev["n_rows"] += 1
            contracts[key]["date"] = earliest
    stats["duplicate_reference_numbers"] = sum(1 for n in seen_refs.values() if n > 1)
    stats["contracts"] = len(contracts)

    # Vendors with no postal code: borrow the one their other contracts carry.
    for rec in contracts.values():
        if not rec["pc"] and rec["country"] in ("", "CA"):
            pc = vendor_pc.get(norm(rec["vendor"]))
            if pc:
                rec["pc"], rec["pc_borrowed"] = pc, True
                stats["postal_codes_borrowed"] += 1

    centroids = load_centroids()
    fsa_pts = defaultdict(list)
    for pc, (lat, lon) in centroids.items():
        fsa_pts[pc[:3]].append((lat, lon))
    index = RidingIndex()
    needed = {rec["pc"] for rec in contracts.values() if rec["pc"]}
    postal_to_riding, fsa_to_riding = {}, {}
    for pc in needed:
        if pc in centroids:
            num, _ = index.locate(*centroids[pc])
            if num:
                postal_to_riding[pc] = num
    for fsa in {pc[:3] for pc in needed if pc not in postal_to_riding}:
        pts = fsa_pts.get(fsa)
        if pts:
            num, _ = index.locate(sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
            if num:
                fsa_to_riding[fsa] = num
    stats["postal_codes_needed"] = len(needed)
    stats["postal_codes_located"] = len(postal_to_riding)

    per = {num: {"after": Counter(), "before": Counter(), "depts": Counter(), "top": [], "series": Counter()} for num in ridings}
    dept_totals = defaultdict(lambda: defaultdict(float))
    dept_after = Counter()
    vendor_after = Counter()
    method_counts = Counter()
    unmapped = defaultdict(lambda: [0.0, 0, "", ""])
    windows = Counter()

    for rec in contracts.values():
        if rec["value"] <= 0:
            stats["contracts_nonpositive"] += 1
            continue
        d = date.fromisoformat(rec["date"])
        if before_start <= d <= before_end:
            window = "before"
        elif election <= d <= cutoff:
            window = "after"
        else:
            window = None
        if window:
            windows[window + "_n"] += 1
            windows[window + "_$"] += rec["value"]
        if rec["country"] not in ("", "CA"):
            if window:
                method_counts[(window, "foreign")] += 1
                method_counts[(window, "foreign $")] += rec["value"]
            continue
        num, method = None, ""
        if rec["pc"] in postal_to_riding:
            num, method = postal_to_riding[rec["pc"]], "vendor's address on other contracts" if rec.get("pc_borrowed") else "postal code"
        elif rec["pc"][:3] in fsa_to_riding:
            num, method = fsa_to_riding[rec["pc"][:3]], "postal area (approx.)"
        if not num:
            if window:
                method_counts[(window, "unmapped")] += 1
                method_counts[(window, "unmapped $")] += rec["value"]
            if window == "after":
                u = unmapped[norm(rec["vendor"])]
                u[0] += rec["value"]
                u[1] += 1
                u[2] = u[2] or rec["vendor"]
                u[3] = u[3] or rec["dept"]
            continue
        p = per[num]
        p["series"][qlabel(d)] += rec["value"]
        if not window:
            continue
        method_counts[(window, method)] += 1
        p[window]["total"] += rec["value"]
        p[window]["n"] += 1
        if window == "after":
            p["depts"][rec["dept"]] += rec["value"]
            dept_totals[rec["dept"]][num] += rec["value"]
            dept_after[rec["dept"]] += rec["value"]
            vendor_after[rec["vendor"][:80]] += rec["value"]
            p["top"].append((rec["value"], rec, method))

    out = {}
    for num, r in ridings.items():
        p = per[num]
        pop = r["population"] or 1
        a, b = p["after"], p["before"]
        pc_after = round(a["total"] / pop / years, 2)
        pc_before = round(b["total"] / pop / years, 2)
        out[num] = {
            "after_total": round(a["total"]), "after_n": a["n"],
            "before_total": round(b["total"]), "before_n": b["n"],
            "pc_after": pc_after, "pc_before": pc_before,
            "change_pct": (round(100 * (a["total"] - b["total"]) / b["total"], 1) if b["total"] > 0 else None),
            "top_depts": [[d, round(v)] for d, v in p["depts"].most_common(4)],
            "top_contracts": [
                {"v": round(v), "who": c["vendor"][:80], "dept": c["dept"][:60], "desc": c["desc"], "date": c["date"],
                 "city": "", "how": how + (", minister's office" if c["ministers"] else ""), "ref": c["ref"], "org": c["org"]}
                for v, c, how in sorted(p["top"], key=lambda t: -t[0])[:10]
            ],
            "series": [round(p["series"].get(q, 0)) for q in labels],
        }

    placed_after = sum(v for (w, m), v in method_counts.items() if w == "after" and not m.endswith("$") and m not in ("unmapped", "foreign"))
    meta = {
        "generated": date.today().isoformat(), "source": "Proactive Publication - Contracts over $10,000 (open.canada.ca)",
        "election": election.isoformat(), "cutoff": cutoff.isoformat(), "before_start": before_start.isoformat(),
        "before_end": before_end.isoformat(), "years_per_window": years,
        "methods": {f"{w}|{m}": round(v) for (w, m), v in method_counts.items()},
        "placed_after": placed_after,
        "placed_after_$": round(sum(x["after_total"] for x in out.values())),
        "total_after": windows["after_n"], "total_after_$": round(windows["after_$"]),
        "total_before": windows["before_n"], "total_before_$": round(windows["before_$"]),
        "foreign_after": method_counts[("after", "foreign")], "foreign_after_$": round(method_counts[("after", "foreign $")]),
        "unmapped_after": method_counts[("after", "unmapped")], "unmapped_after_$": round(method_counts[("after", "unmapped $")]),
        "stats": {**cache_stats, **{k: round(v) for k, v in stats.items()}},
        "series": {"kind": "quarter", "labels": labels, "complete": gmeta["series"]["complete"], "election_index": gmeta["series"]["election_index"]},
        "departments": [d for d, _ in dept_after.most_common(60)],
        "top_vendors": [[v, round(x)] for v, x in vendor_after.most_common(50)],
    }
    with open(ROOT / "output" / "contracts_unmapped.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["value", "vendor", "contracts", "department"])
        for k, (v, n, name, dept) in sorted(unmapped.items(), key=lambda kv: -kv[1][0])[:2000]:
            w.writerow([round(v), name, n, dept])
    dept_matrix = {d: {n: round(v) for n, v in m.items()} for d, m in dept_totals.items()}
    json.dump({"meta": meta, "ridings": out, "dept_by_riding": dept_matrix},
              open(OUT / "contracts_by_riding.json", "w"), ensure_ascii=False)
    meta["seconds"] = round(time.time() - t0, 1)
    print(json.dumps({k: v for k, v in meta.items() if k not in ("departments",)}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
