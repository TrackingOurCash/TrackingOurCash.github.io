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
     contract's date is the original award (the earliest contract row's
     contract_date; when only amendment rows survive the 2024 filter, the
     earliest contract_period_start, so an amendment to a 2000 contract is not
     counted as new money); its value is the latest row's contract_value (the
     current total, as the data dictionary defines "Total Contract Value").
     Standing offers and supply arrangements (instrument_type SOSA) are
     frameworks, not spending, and are dropped.
  2b. Large flag: contracts of $100M or more are nearly all multi-year defence,
     shipbuilding and IT deals whose whole value is booked on the award date
     (a $10.8B frigate contract runs to 2037). They are kept in the totals but
     flagged, and the adjusted figures (after_adj, pc_after) leave them out,
     as the grants layer leaves out national bodies.
  3. Riding: the file publishes only the first three characters of the vendor's
     postal code (the forward sortation area, FSA), never the full code, and no
     city. Each FSA is scored by where its GeoNames postal codes fall inside the
     2023 boundaries, and a contract's dollars are apportioned across those
     ridings in that proportion (shares under 5% are dropped and the rest
     renormalized). Only half of after-window dollars sit in FSAs that lie 80%+
     in one riding, so a plurality rule would misplace too much. A vendor with
     no FSA borrows the one its other contracts carry. Riding contract counts
     are therefore fractional (rounded in the output).
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
FSA_SHARES = RAW / "fsa_shares.json"
MIN_SHARE = 0.05
KEEP_FROM = "2024-01-01"
LARGE = 100_000_000  # flag threshold: multi-year megaprojects booked on one day

csv.field_size_limit(sys.maxsize)

KEEP_COLS = ["reference_number", "procurement_id", "vendor_name", "vendor_postal_code", "contract_date",
             "contract_period_start", "delivery_date", "contract_value", "original_value", "amendment_value",
             "economic_object_code", "description_en", "commodity_type", "commodity_code", "agreement_type_code",
             "country_of_vendor", "solicitation_procedure", "contracting_entity", "instrument_type",
             "ministers_office", "reporting_period", "owner_org", "owner_org_title"]

SUFFIX = re.compile(r"\b(inc|incorporated|ltd|limited|ltee|corp|corporation|co|company|llc|lp|llp|limited partnership|"
                    r"gmbh|plc|sa|senc|s e n c|the)\b")


def vendor_key(name):
    return re.sub(r"\s+", " ", SUFFIX.sub(" ", norm(name))).strip() or norm(name)


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
    """The full postal code when one is given, else the FSA (first three characters), else ""."""
    pc = re.sub(r"[^A-Za-z0-9]", "", pc or "").upper()
    if re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", pc):
        return pc
    return pc[:3] if re.fullmatch(r"[A-Z]\d[A-Z].*", pc) else ""


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
                "date": cdate, "award": cdate if itype != "A" else "", "period": iso(row["contract_period_start"]) or cdate,
                "value": value, "order": (row["reporting_period"] or "", cdate),
                "dept": first(row["owner_org_title"]), "org": row["owner_org"], "ref": row["reference_number"].strip(), "pid": pid,
                "vendor": (row["vendor_name"] or "").strip(), "pc": pc, "country": country,
                "desc": (row["description_en"] or "").strip()[:100], "how": PROCEDURE.get((row["solicitation_procedure"] or "").strip(), ""),
                "itype": itype, "ministers": row["ministers_office"] == "Y", "ctype": row["commodity_type"],
                "n_rows": 1, "orig": to_float(row["original_value"]), "reported": (row["reporting_period"] or "").strip(),
            }
            prev = contracts.get(key)
            if prev is None:
                contracts[key] = rec
                continue
            stats["rows_merged"] += 1
            award = min(a for a in (prev["award"], rec["award"]) if a) if (prev["award"] or rec["award"]) else ""
            period = min(prev["period"], rec["period"])
            # The latest row carries the current total; the original row carries the award date.
            if rec["order"] >= prev["order"]:
                rec["pc"] = rec["pc"] or prev["pc"]
                rec["country"] = rec["country"] or prev["country"]
                rec["desc"] = rec["desc"] or prev["desc"]
                rec["n_rows"] = prev["n_rows"] + 1
                rec["orig"] = prev["orig"] or rec["orig"]  # the earliest row's original value
                contracts[key] = rec
            else:
                prev["n_rows"] += 1
                prev["orig"] = rec["orig"] or prev["orig"]
            contracts[key]["award"], contracts[key]["period"] = award, period
    for rec in contracts.values():
        # Date = original award; for amendment-only groups the period start stands in for it.
        if rec["award"]:
            rec["date"] = rec["award"]
        else:
            rec["date"] = min(rec["period"], rec["date"])
            stats["amendment_only_contracts"] += 1
        rec["flag"] = "large" if rec["value"] >= LARGE else ""
    stats["duplicate_reference_numbers"] = sum(1 for n in seen_refs.values() if n > 1)
    stats["contracts"] = len(contracts)

    # Vendors with no postal code: borrow the one their other contracts carry.
    for rec in contracts.values():
        if not rec["pc"] and rec["country"] in ("", "CA"):
            pc = vendor_pc.get(norm(rec["vendor"]))
            if pc:
                rec["pc"], rec["pc_borrowed"] = pc, True
                stats["postal_codes_borrowed"] += 1

    # FSA -> {riding: share of the FSA's postal codes}, from GeoNames centroids placed in the
    # 2023 boundaries. Cached, since it is the slow step (~900k point-in-polygon lookups).
    # The cache is committed; delete it to force a rebuild after changing geo.py or the boundaries.
    if FSA_SHARES.exists():
        fsa_shares = json.load(open(FSA_SHARES))
    else:
        t1 = time.time()
        centroids = load_centroids()
        index = RidingIndex()
        votes = defaultdict(Counter)
        for pc, (lat, lon) in centroids.items():
            num, _ = index.locate(lat, lon)
            if num:
                votes[pc[:3]][num] += 1
        fsa_shares = {}
        for fsa, c in votes.items():
            total = sum(c.values())
            keep = {n: v / total for n, v in c.items() if v / total >= MIN_SHARE}
            scale = sum(keep.values())
            fsa_shares[fsa] = {n: round(v / scale, 4) for n, v in keep.items()}
        json.dump(fsa_shares, open(FSA_SHARES, "w"))
        print(f"fsa shares built: {len(fsa_shares)} FSAs in {time.time() - t1:.0f}s", file=sys.stderr)
    needed = {rec["pc"] for rec in contracts.values() if rec["pc"]}
    stats["fsas_needed"] = len({pc[:3] for pc in needed})
    stats["fsas_located"] = len({pc[:3] for pc in needed if pc[:3] in fsa_shares})
    stats["fsas_split"] = sum(1 for pc in {pc[:3] for pc in needed} if len(fsa_shares.get(pc, {})) > 1)

    per = {num: {"after": Counter(), "before": Counter(), "depts": Counter(), "top": [], "series": Counter()} for num in ridings}
    dept_totals = defaultdict(lambda: defaultdict(float))
    dept_after = Counter()
    vendor_after = Counter()
    vendor_names = defaultdict(Counter)
    large_after = []
    large_all = []  # every $100M+ contract in either window, placed or not, for the page's megacontracts card
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
        if window and rec["flag"]:
            foreign = rec["country"] not in ("", "CA")
            sh = None if foreign else (fsa_shares.get(rec["pc"][:3]) if rec["pc"] else None)
            large_all.append((rec, window, sh or {}, "foreign vendor" if foreign else ("" if sh else "no usable postal code")))
        if rec["country"] not in ("", "CA"):
            if window:
                method_counts[(window, "foreign")] += 1
                method_counts[(window, "foreign $")] += rec["value"]
            continue
        shares = fsa_shares.get(rec["pc"][:3]) if rec["pc"] else None
        method = ("vendor's address on other contracts" if rec.get("pc_borrowed") else "postal area") if shares else ""
        if len(shares or ()) > 1:
            method += " (split)"
        if not shares:
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
        if window:
            method_counts[(window, method)] += 1
            if window == "after":
                dept_after[rec["dept"]] += rec["value"]
                vendor_after[vendor_key(rec["vendor"])] += rec["value"]
                vendor_names[vendor_key(rec["vendor"])][rec["vendor"][:80]] += 1
                if rec["flag"]:
                    large_after.append(rec)
        for num, share in shares.items():
            v = rec["value"] * share
            p = per[num]
            if not rec["flag"]:
                p["series"][qlabel(d)] += v
            if not window:
                continue
            p[window]["total"] += v
            p[window]["n"] += share
            if not rec["flag"]:
                p[window]["adj"] += v
                p[window]["adj_n"] += share
            if window == "after":
                p["depts"][rec["dept"]] += v
                if not rec["flag"]:
                    dept_totals[rec["dept"]][num] += v
                p["top"].append((v, rec, method if share == 1 else f"{method}, {share:.0%} of {rec['pc'][:3]} in riding"))

    out = {}
    for num, r in ridings.items():
        p = per[num]
        pop = r["population"] or 1
        a, b = p["after"], p["before"]
        out[num] = {
            "after_total": round(a["total"]), "after_n": round(a["n"]),
            "after_adj": round(a["adj"]), "after_adj_n": round(a["adj_n"]),
            "before_total": round(b["total"]), "before_n": round(b["n"]), "before_adj": round(b["adj"]),
            "pc_after": round(a["adj"] / pop / years, 2), "pc_after_all": round(a["total"] / pop / years, 2),
            "pc_before": round(b["adj"] / pop / years, 2),
            "change_pct": (round(100 * (a["adj"] - b["adj"]) / b["adj"], 1) if b["adj"] > 0 else None),
            "top_depts": [[d, round(v)] for d, v in p["depts"].most_common(4)],
            "top_contracts": [
                {"v": round(v), "who": c["vendor"][:80], "dept": c["dept"][:60], "desc": c["desc"], "date": c["date"],
                 "city": "", "how": how + (", minister's office" if c["ministers"] else ""), "ref": c["ref"], "org": c["org"],
                 "flag": c["flag"]}
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
        "large_threshold": LARGE,
        "large_after": [{"v": round(c["value"]), "who": c["vendor"][:80], "dept": c["dept"][:60], "desc": c["desc"], "date": c["date"],
                         "fsa": c["pc"][:3], "ref": c["ref"], "org": c["org"]} for c in sorted(large_after, key=lambda c: -c["value"])],
        "large": [{"v": round(c["value"]), "orig": round(c["orig"]) if c["orig"] else None, "who": c["vendor"][:80], "dept": c["dept"][:60],
                   "desc": c["desc"], "date": c["date"], "reported": c["reported"], "window": w, "ridings": sh, "why": why,
                   "fsa": c["pc"][:3], "ref": c["ref"], "org": c["org"]}
                  for c, w, sh, why in sorted(large_all, key=lambda t: -t[0]["value"])],
        "departments": [d for d, _ in dept_after.most_common(60)],
        "top_vendors": [[vendor_names[k].most_common(1)[0][0], round(x)] for k, x in vendor_after.most_common(50)],
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
