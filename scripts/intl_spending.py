"""Federal money that goes abroad, by country, for the International page. Writes
data/intl/intl_spending.json (via a temp file, so a failed run leaves the committed copy alone)
and prints a short summary to stderr.

Three sources, never added together (they overlap: see the overlap check in meta.notes):
  contracts  Proactive Publication - Contracts over $10,000 (data/raw/contracts/recent.csv, the
             2024+ cache contracts.py writes). Foreign = country_of_vendor not CA and not blank.
             Amendments merged exactly as contracts.py does: rows sharing (owner_org,
             procurement_id), or reference_number when procurement_id is blank, are one contract;
             value = the latest row's contract_value (else original + amendment); date = the
             original award (earliest non-amendment contract_date, else earliest
             contract_period_start). Standing offers / supply arrangements (SOSA) dropped.
  grants     Proactive Disclosure - Grants and Contributions (data/raw/grants.csv, read once,
             streaming). Foreign = recipient_country not CA and not blank. Amendments merged as in
             build_spending.py: per (owner_org, ref_number) the highest amendment_number's
             agreement_value, dated by the original agreement_start_date.
  iati       Global Affairs Canada's IATI activity files (data/raw/intl/iati/, fetched by
             intl_prep.py). Disbursements (transaction type 3) and expenditures (4) summed per
             activity per window by transaction date, split by recipient-country percentages; the
             recipient-region share is "unplaced" under the region's name.
Windows are the federal page's (data/riding_spending.json meta): "after" = election day to the
cutoff, "before" = before_start to before_end, both inclusive. Money is CAD, whole dollars.

Keyword flags (W women/girls, M men/boys, G gender, L LGBTQ2+) are whole-word, case-insensitive
matches over title, description, program and expected results (contracts: description_en only);
French patterns are used only when every English field is empty. IATI also carries GAC's own
gender-equality policy marker (OECD DAC vocabulary 1, code 1): P = principal, S = significant.
"""
import csv
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTL_RAW = RAW / "intl"
IATI_DIR = INTL_RAW / "iati"
OUT = ROOT / "data" / "intl"
GAC = "dfatd-maecd"
KEEP_FROM = "2024-01-01"

csv.field_size_limit(sys.maxsize)

GRANTS_DATASET = "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"
CONTRACTS_DATASET = "https://open.canada.ca/data/en/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b"
GRANT_URL = "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent"
CONTRACT_URL = "https://search.open.canada.ca/contracts/record/{org}%2C{ref}"
PROJECT_URL = "https://w05.international.gc.ca/projectbrowser-banqueprojets/project-projet/details/{p}"

# ---------------------------------------------------------------- keyword flags
KEYWORDS = {
    "women": r"\b(?:women|woman|girls?|females?|feminist|maternal|mothers?|widows?)\b",
    "men": r"\b(?:men|boys?|males?|fathers?|masculinit(?:y|ies))\b",
    "gender": r"\b(?:gender(?:[- ](?:based|equality|responsive|transformative))?|s?gbv|feminist international assistance)\b",
    "lgbtq": r"(?<![\w])(?:(?:2s)?lgbt[qia2s]*\+?|sogi(?:esc)?|sexual orientation|gender identit(?:y|ies)|transgender|queer|intersex|"
             r"sexual (?:and gender )?minorit(?:y|ies))(?![\w])",
}
# Added to the English patterns when a record has French text only.
KEYWORDS_FR = {
    "women": r"\b(?:femmes?|filles?)\b",
    "men": r"\b(?:hommes?|garçons?)\b",
    "gender": r"\b(?:genres?|vfg|vsbg)\b",
    "lgbtq": r"(?<![\w])(?:orientation sexuelle|identité de genre|minorités sexuelles)(?![\w])",
}
LETTER = {"women": "W", "men": "M", "gender": "G", "lgbtq": "L"}
RX = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}
RX_FR = {k: re.compile(KEYWORDS[k] + "|" + KEYWORDS_FR[k], re.I) for k in KEYWORDS}


def kw_flags(en_parts, fr_parts=()):
    en = " ".join(p for p in en_parts if p)
    if en.strip():
        text, rx = en, RX
    else:
        text, rx = " ".join(p for p in fr_parts if p), RX_FR
    return "".join(LETTER[k] for k, r in rx.items() if text and r.search(text))


# ---------------------------------------------------------------- places
# OECD DAC recipient-region codes (IATI Region vocabulary 1).
REGIONS = {
    "88": "States Ex-Yugoslavia, unspecified", "89": "Europe, regional", "189": "North of Sahara, regional",
    "289": "South of Sahara, regional", "298": "Africa, regional", "380": "West Indies, regional",
    "389": "North and Central America, regional", "489": "South America, regional", "498": "America, regional",
    "589": "Middle East, regional", "619": "Central Asia, regional", "679": "South Asia, regional",
    "689": "South and Central Asia, regional", "789": "Far East Asia, regional", "798": "Asia, regional",
    "889": "Oceania, regional", "998": "Developing countries, unspecified", "1027": "Eastern Africa, regional",
    "1028": "Middle Africa, regional", "1029": "Southern Africa, regional", "1030": "Western Africa, regional",
    "1031": "Caribbean, regional", "1032": "Central America, regional", "1033": "Melanesia, regional",
    "1034": "Micronesia, regional", "1035": "Polynesia, regional",
}
# Codes that appear in the sources but have no Natural Earth 1:50m shape of their own (looked up in
# the 1:10m file first when it is present).
EXTRA_CODES = {
    "AN": ("ANT", "Netherlands Antilles (former)", "North America", 0),
    "BQ": ("BES", "Caribbean Netherlands", "North America", 26000),
    "MQ": ("MTQ", "Martinique", "North America", 350000),
    "TK": ("TKL", "Tokelau", "Oceania", 1500),
    "GI": ("GIB", "Gibraltar", "Europe", 33701),
    "UM": ("UMI", "U.S. Minor Outlying Islands", "Oceania", 300),
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def first(v):
    return (v or "").split("|")[0].strip()


def to_float(v):
    try:
        return float(str(v).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return 0.0


def iso(v):
    v = (v or "").strip()[:10]
    return v if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) else ""


def amend_no(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def short(s, n):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


class Places:
    """ISO2 -> ISO3 and country facts from world_geo.json, then the 1:10m file, then EXTRA_CODES."""

    def __init__(self):
        geo = json.load(open(OUT / "world_geo.json", encoding="utf-8"))
        self.info, self.by2 = {}, {}
        for f in geo["features"]:
            p = f["properties"]
            self.info[p["iso3"]] = {"name": p["name"], "continent": p["continent"], "pop": p["pop"], "shape": True}
            if p["iso2"]:
                self.by2[p["iso2"]] = p["iso3"]
        self.extra10 = {}
        ten = RAW / "ne" / "ne_10m_admin_0_countries.geojson"
        if ten.exists():
            for f in json.load(open(ten, encoding="utf-8"))["features"]:
                q = f["properties"]
                a2 = q["ISO_A2"] if len(q["ISO_A2"]) == 2 else q.get("ISO_A2_EH", "")
                a3 = q["ISO_A3"] if len(q["ISO_A3"]) == 3 and q["ISO_A3"] != "-99" else q["ADM0_A3"]
                if len(a2) == 2 and a2.isalpha() and a2 not in self.by2:
                    self.extra10[a2] = (a3, q.get("NAME_LONG") or q["NAME"], q["CONTINENT"], int(q["POP_EST"] or 0))
        self.unknown = Counter()

    def iso3(self, code2):
        c = (code2 or "").strip().upper()
        if c in self.by2:
            return self.by2[c]
        hit = self.extra10.get(c) or EXTRA_CODES.get(c)
        if hit:
            a3, name, cont, pop = hit
            if a3 not in self.info:
                self.info[a3] = {"name": name, "continent": cont, "pop": pop, "shape": False}
            self.by2[c] = a3
            return a3
        self.unknown[c] += 1
        return ""


# ---------------------------------------------------------------- contracts

def load_contracts(places, win):
    path = RAW / "contracts" / "recent.csv"
    if not path.exists():
        raise SystemExit(f"missing {path}; run scripts/contracts.py first (it writes the 2024+ cache)")
    stats = Counter()
    contracts = {}
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            stats["rows"] += 1
            itype = (row["instrument_type"] or "").strip().upper()
            if itype == "SOSA":
                stats["sosa_rows_dropped"] += 1
                continue
            cdate = iso(row["contract_date"]) or iso(row["contract_period_start"])
            if not cdate:
                continue
            pid = (row["procurement_id"] or "").strip()
            key = (row["owner_org"], "p:" + pid if pid else "r:" + row["reference_number"].strip())
            value = to_float(row["contract_value"]) or (to_float(row["original_value"]) + to_float(row["amendment_value"]))
            rec = {"date": cdate, "award": cdate if itype != "A" else "", "period": iso(row["contract_period_start"]) or cdate,
                   "value": value, "order": (row["reporting_period"] or "", cdate), "dept": first(row["owner_org_title"]),
                   "org": row["owner_org"], "ref": row["reference_number"].strip(), "vendor": (row["vendor_name"] or "").strip(),
                   "country": (row["country_of_vendor"] or "").strip().upper(), "desc": (row["description_en"] or "").strip()}
            prev = contracts.get(key)
            if prev is None:
                contracts[key] = rec
                continue
            award = min(a for a in (prev["award"], rec["award"]) if a) if (prev["award"] or rec["award"]) else ""
            period = min(prev["period"], rec["period"])
            if rec["order"] >= prev["order"]:
                rec["country"] = rec["country"] or prev["country"]
                rec["desc"] = rec["desc"] or prev["desc"]
                contracts[key] = rec
            contracts[key]["award"], contracts[key]["period"] = award, period
    out = []
    for rec in contracts.values():
        rec["date"] = rec["award"] or min(rec["period"], rec["date"])
        if rec["country"] in ("", "CA") or rec["value"] <= 0:
            continue
        w = win(rec["date"])
        if not w:
            continue
        stats[f"foreign_{w}"] += 1
        out.append({"s": "contract", "w": w, "d": rec["date"], "v": rec["value"], "who": rec["vendor"], "c": places.iso3(rec["country"]),
                    "code": rec["country"], "r": "", "dept": rec["dept"], "t": rec["desc"], "ref": rec["ref"],
                    "u": CONTRACT_URL.format(org=quote(rec["org"], safe=""), ref=quote(rec["ref"], safe="")), "k": kw_flags([rec["desc"]])})
    stats["contracts"] = len(contracts)
    return out, stats


# ---------------------------------------------------------------- grants and contributions

def load_grants(places, win):
    full = RAW / "grants.csv"
    path = full if full.exists() else RAW / "grants_trim.csv"
    if not path.exists():
        raise SystemExit(f"missing {full}")
    if path != full:
        log(f"  {full} missing: reading {path.name} (no descriptions, so keyword flags use titles and programs only)")
    stats = Counter()
    agreements = {}
    gac_projects = defaultdict(set)  # project number -> {ref_number} for every GAC agreement in the file, any date or country
    proj_rx = re.compile(r"\b([A-Z]\d{9})\b")
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        head = [h.lstrip("﻿") for h in next(reader)]
        ix = {h: i for i, h in enumerate(head)}

        def col(row, name):
            i = ix.get(name)
            return row[i] if i is not None else ""
        for row in reader:
            stats["rows"] += 1
            if len(row) != len(head):
                stats["malformed_rows"] += 1
                continue
            org = col(row, "owner_org")
            if org == GAC:
                for p in proj_rx.findall(col(row, "agreement_number")):
                    gac_projects[p].add(col(row, "ref_number").strip())
            start = col(row, "agreement_start_date")[:10]
            if start < KEEP_FROM:
                continue
            country = col(row, "recipient_country").strip().upper()
            if country in ("", "CA"):
                continue
            key = (org, col(row, "ref_number").strip())
            a_no = amend_no(col(row, "amendment_number"))
            rec = {"a": a_no, "start": start, "value": to_float(col(row, "agreement_value")), "org": org, "ref": key[1],
                   "dept": first(col(row, "owner_org_title")), "country": country, "rtype": col(row, "recipient_type"),
                   "who": first(col(row, "recipient_operating_name") or col(row, "recipient_legal_name")),
                   "title": col(row, "agreement_title_en").strip(), "prog": first(col(row, "prog_name_en")),
                   "desc": col(row, "description_en"), "results": col(row, "expected_results_en"),
                   "title_fr": col(row, "agreement_title_fr").strip(), "prog_fr": col(row, "prog_name_fr"),
                   "desc_fr": col(row, "description_fr"), "results_fr": col(row, "expected_results_fr"),
                   "agreement_number": col(row, "agreement_number").strip()}
            prev = agreements.get(key)
            if prev is None:
                agreements[key] = rec
                continue
            stats["amendment_rows_merged"] += 1
            first_start = min(prev["start"], start)
            if a_no >= prev["a"]:
                for k in ("title", "prog", "desc", "results", "title_fr", "prog_fr", "desc_fr", "results_fr", "agreement_number", "who"):
                    rec[k] = rec[k] or prev[k]
                agreements[key] = rec
            agreements[key]["start"] = first_start
    out = []
    for rec in agreements.values():
        if rec["value"] <= 0:
            continue
        w = win(rec["start"])
        if not w:
            continue
        stats[f"foreign_{w}"] += 1
        if rec["rtype"] == "P":  # recipient_type P = individual or sole proprietorship (I = international organization)
            stats[f"individuals_{w}"] += 1
        en = [rec["title"], rec["prog"], rec["desc"], rec["results"]]
        fr = [rec["title_fr"], rec["prog_fr"], rec["desc_fr"], rec["results_fr"]]
        out.append({"s": "grant", "w": w, "d": rec["start"], "v": rec["value"],
                    # Individuals abroad (fellowships, prizes) are counted but not named, as on the federal page.
                    "who": "Individual recipient" if rec["rtype"] == "P" else rec["who"],
                    "c": places.iso3(rec["country"]), "code": rec["country"], "r": "", "dept": rec["dept"],
                    "t": rec["title"] or rec["prog"] or rec["title_fr"] or first(rec["prog_fr"]), "ref": rec["ref"],
                    "u": GRANT_URL.format(org=quote(rec["org"], safe=""), ref=quote(rec["ref"], safe="")), "k": kw_flags(en, fr),
                    "org": rec["org"], "proj": proj_rx.findall(rec["agreement_number"]) if rec["org"] == GAC else []})
    stats["foreign_agreements"] = sum(1 for r in agreements.values())
    return out, stats, gac_projects


# ---------------------------------------------------------------- IATI

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def narrative(el, lang="en"):
    if el is None:
        return ""
    ns = el.findall("narrative")
    for n in ns:
        if (n.get(XML_LANG) or "").lower() == lang and (n.text or "").strip():
            return n.text.strip()
    return ""


def any_narrative(el):
    return narrative(el, "en") or narrative(el, "fr") or next((n.text.strip() for n in (el.findall("narrative") if el is not None else []) if (n.text or "").strip()), "")


def check_xml(path):
    """Refuse files that declare a DTD or entities (entity-expansion attacks); IATI needs neither."""
    with open(path, "rb") as f:
        head = f.read(1 << 16)
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError(f"{path.name} declares a DTD/entities; refusing to parse")


def load_iati(places, win):
    man_path = IATI_DIR / "manifest.json"
    manifest = json.load(open(man_path)) if man_path.exists() else {"files": [{"file": p.name, "url": ""} for p in sorted(IATI_DIR.glob("*.xml"))]}
    link_ok = manifest.get("project_browser_ok", True)
    stats = Counter()
    out, seen_ids, iati_projects, iati_all = [], set(), {}, set()
    for entry in manifest["files"]:
        path = IATI_DIR / entry["file"]
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts/intl_prep.py")
        check_xml(path)
        for _, a in ET.iterparse(path, events=("end",)):
            if a.tag != "iati-activity":
                continue
            stats["activities"] += 1
            aid = (a.findtext("iati-identifier") or "").strip()
            if aid in seen_ids:  # the same activity in two files: count it once
                stats["duplicate_activities"] += 1
                a.clear()
                continue
            seen_ids.add(aid)
            proj = aid[5:] if aid.startswith("CA-3-") else aid
            iati_all.add(proj)
            dcur = (a.get("default-currency") or "CAD").upper()
            sums = defaultdict(float)  # window -> $
            last = {}
            for t in a.findall("transaction"):
                tt = t.find("transaction-type")
                if tt is None or tt.get("code") not in ("3", "4"):
                    continue
                td = t.find("transaction-date")
                d = iso(td.get("iso-date") if td is not None else "")
                v = t.find("value")
                if v is None or not d:
                    continue
                w = win(d)
                if not w:
                    continue
                cur = (v.get("currency") or dcur).upper()
                if cur != "CAD":
                    stats["non_cad_transactions_skipped"] += 1
                    continue
                if t.find("recipient-country") is not None or t.find("recipient-region") is not None:
                    stats["transactions_with_own_recipient"] += 1  # none in GAC's files; split like the rest
                stats[f"transactions_{w}"] += 1
                sums[w] += to_float(v.text)
                last[w] = max(last.get(w, ""), d)
            if not sums:
                a.clear()
                continue
            iati_projects[proj] = sums.get("after", 0.0)  # activities with money in either window
            # Where: recipient-country and recipient-region percentages (normalised if they do not sum to 100).
            targets = []
            for rc in a.findall("recipient-country"):
                targets.append(("c", (rc.get("code") or "").upper(), to_float(rc.get("percentage") or 100)))
            for rr in a.findall("recipient-region"):
                if rr.get("vocabulary", "1") == "1":
                    code = rr.get("code") or ""
                    name = REGIONS.get(code) or any_narrative(rr) or f"Region {code}"
                else:
                    name = any_narrative(rr) or "Region (other vocabulary)"
                targets.append(("r", name, to_float(rr.get("percentage") or 100)))
            total_pct = sum(p for *_, p in targets)
            if not targets or total_pct <= 0:
                targets, total_pct = [("r", "Unspecified (no country or region given)", 100.0)], 100.0
                stats["activities_without_place"] += 1
            title_el = a.find("title")
            title_en, title_fr = narrative(title_el, "en"), narrative(title_el, "fr")
            desc_en = " ".join(narrative(d, "en") for d in a.findall("description"))
            desc_fr = " ".join(narrative(d, "fr") for d in a.findall("description"))
            k = kw_flags([title_en, desc_en], [title_fr, desc_fr])
            marker = ""
            for pm in a.findall("policy-marker"):
                if pm.get("vocabulary", "1") == "1" and pm.get("code") == "1":
                    marker = {"2": "P", "1": "S"}.get(pm.get("significance") or "", "")
            orgs = [any_narrative(p) for p in a.findall("participating-org") if p.get("role") in ("4",)]
            if not any(orgs):
                orgs = [any_narrative(p) for p in a.findall("participating-org") if p.get("role") == "2"]
            who = "; ".join(dict.fromkeys(o for o in orgs if o))
            for w, total in sums.items():
                for kind, code, pct in targets:
                    v = total * pct / total_pct
                    if not v:
                        continue
                    c = places.iso3(code) if kind == "c" else ""
                    region = code if kind == "r" else ("" if c else f"Unrecognised country code {code}")
                    out.append({"s": "iati", "w": w, "d": last[w], "v": v, "who": who, "c": c, "code": code if kind == "c" else "",
                                "r": region, "dept": "Global Affairs Canada", "t": title_en or title_fr, "ref": aid,
                                "u": PROJECT_URL.format(p=quote(proj, safe="")) if link_ok and aid.startswith("CA-3-") else "", "k": k + marker})
            stats["activities_with_money"] += 1
            if "after" in sums:
                stats["activities_after"] += 1
            a.clear()
    return out, stats, manifest, iati_projects, iati_all


# ---------------------------------------------------------------- assemble

def order(r):
    """Largest first, ties broken by reference so the output is stable across Python versions."""
    return (-int(round(r["v"])), r["ref"], r["c"], r["r"])


def compact(r):
    return {"s": r["s"], "d": r["d"], "v": int(round(r["v"])), "who": short(r["who"], 80), "c": r["c"], "r": r["r"],
            "dept": short(r["dept"], 60), "t": short(r["t"], 110), "ref": r["ref"], "u": r["u"], "k": r["k"]}


def main():
    t0 = time.time()
    fed = json.load(open(ROOT / "data" / "riding_spending.json"))["meta"]
    election, cutoff = fed["election"], fed["cutoff"]
    before_start, before_end = fed["before_start"], fed["before_end"]

    def win(d):
        if election <= d <= cutoff:
            return "after"
        if before_start <= d <= before_end:
            return "before"
        return None

    places = Places()
    gii_meta = json.load(open(INTL_RAW / "gii.json", encoding="utf-8"))
    gii = gii_meta["countries"]

    contracts, cstats = load_contracts(places, win)
    log(f"contracts: {cstats['foreign_after']} foreign after, {cstats['foreign_before']} before ({time.time() - t0:.0f}s)")
    grants, gstats, gac_projects = load_grants(places, win)
    log(f"grants: {gstats['foreign_after']} foreign after, {gstats['foreign_before']} before ({time.time() - t0:.0f}s)")
    iati, istats, manifest, iati_projects, iati_all = load_iati(places, win)
    log(f"iati: {istats['activities_after']} activities with after-window disbursements ({time.time() - t0:.0f}s)")

    SRC = ("contracts", "grants", "iati")
    key_of = {"contract": "contracts", "grant": "grants", "iati": "iati"}
    totals = {w: {s: 0.0 for s in SRC} for w in ("after", "before")}
    unplaced = {s: 0.0 for s in SRC}
    regions = Counter()
    countries = {}

    def country(c):
        if c not in countries:
            info = places.info.get(c, {"name": c, "continent": "", "pop": 0})
            g = gii.get(c) or {}
            countries[c] = {"name": info["name"], "continent": info["continent"], "pop": info["pop"],
                            "gii": g.get("gii"), "gii_rank": g.get("rank"), "gii_year": g.get("year", gii_meta["latest_year"]),
                            "after": {s: 0.0 for s in SRC}, "before": {s: 0.0 for s in SRC}, "n_after": {s: 0 for s in SRC},
                            "flag_after": {"contracts": {"women": 0.0, "men": 0.0, "gender": 0.0, "lgbtq": 0.0},
                                           "grants": {"women": 0.0, "men": 0.0, "gender": 0.0, "lgbtq": 0.0},
                                           "iati": {"women": 0.0, "men": 0.0, "gender": 0.0, "lgbtq": 0.0,
                                                    "gender_marker_principal": 0.0, "gender_marker_significant": 0.0}},
                            "top": {s: [] for s in SRC}}
        return countries[c]

    for c in sorted(places.info):  # every country on the map, even with no money
        country(c)
    records = []
    flag_names = {"W": "women", "M": "men", "G": "gender", "L": "lgbtq", "P": "gender_marker_principal", "S": "gender_marker_significant"}
    for r in contracts + grants + iati:
        s = key_of[r["s"]]
        totals[r["w"]][s] += r["v"]
        if not r["c"]:
            if r["w"] == "after":
                unplaced[s] += r["v"]
                if s == "iati":
                    regions[r["r"]] += r["v"]
                if not r["r"]:
                    r["r"] = f"Unrecognised country code {r.get('code') or '(blank)'}"
                records.append(r)
            continue
        cc = country(r["c"])
        cc[r["w"]][s] += r["v"]
        if r["w"] != "after":
            continue
        cc["n_after"][s] += 1
        for letter in r["k"]:
            name = flag_names[letter]
            if name in cc["flag_after"][s]:
                cc["flag_after"][s][name] += r["v"]
        cc["top"][s].append(r)
        records.append(r)

    for cc in countries.values():
        for w in ("after", "before"):
            cc[w] = {s: int(round(v)) for s, v in cc[w].items()}
        cc["flag_after"] = {s: {k: int(round(v)) for k, v in m.items()} for s, m in cc["flag_after"].items()}
        cc["top"] = {s: [compact(r) for r in sorted(lst, key=order)[:10]] for s, lst in cc["top"].items()}

    # Overlap: GAC agreements in the grants file whose agreement_number carries an IATI project number.
    gac_after = [r for r in grants if r["w"] == "after" and r["org"] == GAC]
    matched = [r for r in gac_after if any(p in iati_all for p in r["proj"])]
    iati_after_projects = {p for p, v in iati_projects.items() if v > 0}
    iati_in_gc = {p for p in iati_after_projects if p in gac_projects}
    iati_after_total = sum(v for v in iati_projects.values())
    iati_in_gc_total = sum(iati_projects[p] for p in iati_in_gc)
    overlap = {
        "gac_foreign_grants_after": len(gac_after), "gac_foreign_grants_after_$": int(round(sum(r["v"] for r in gac_after))),
        "with_iati_project": len(matched), "with_iati_project_$": int(round(sum(r["v"] for r in matched))),
        "iati_after_activities": len(iati_after_projects), "iati_after_activities_in_grants_file": len(iati_in_gc),
        "iati_after_$_in_grants_file": int(round(iati_in_gc_total)), "iati_after_$": int(round(iati_after_total)),
    }

    def rows_used(st):
        return {k: int(v) for k, v in st.items()}

    flag_counts = Counter()
    flag_dollars = Counter()
    for r in records:
        for letter in r["k"]:
            flag_counts[(r["s"], letter)] += 1
            flag_dollars[(r["s"], letter)] += r["v"]
    big = [r for r in contracts if r["w"] == "after" and r["v"] >= 100_000_000]
    gac_share_grants = sum(r["v"] for r in gac_after)
    notes = [
        "Contracts: 'country' is the vendor's country (country_of_vendor), i.e. where the supplier is based, not where the work is done; "
        "a U.S. firm supplying a Canadian base counts as United States. Value is the contract's current total value booked on its award date, "
        "so multi-year deals count in full in the window they were signed.",
        "Grants and contributions: 'country' is the recipient's mailing address (recipient_country), not where the money is spent. "
        "UN agencies and international NGOs are mostly addressed in New York, Geneva, Rome, Vienna, Paris or London, so those cities' "
        "countries collect money spent elsewhere. Value is the agreement's current total (latest amendment), dated by the original agreement "
        "start date, as on the federal page. Canadian NGOs delivering aid abroad are addressed in Canada and are not counted here.",
        "IATI (Global Affairs Canada only): 'country' is the activity's recipient country as GAC reports it, the best measure of where aid goes. "
        "Money is actual disbursements in the window by transaction date (a flow), not agreement totals (a commitment), so it is not comparable "
        "dollar for dollar with grants. Multi-country activities are split by GAC's recipient-country percentages; the share GAC assigns to a "
        "region rather than a country is listed as unplaced under the region's name. Other departments' aid (e.g. Finance, IRCC) is not in this file.",
        "Do not add the sources together: GAC's aid appears both in the grants file (by agreement) and in IATI (by disbursement). "
        f"{overlap['iati_after_activities_in_grants_file']} of the {overlap['iati_after_activities']} GAC activities with disbursements after the "
        f"election (${overlap['iati_after_$_in_grants_file'] / 1e9:.1f}B of ${overlap['iati_after_$'] / 1e9:.1f}B) match a GAC agreement in the "
        "grants file by project number (any start date, any recipient address); "
        f"{overlap['with_iati_project']} of the {overlap['gac_foreign_grants_after']} foreign-addressed GAC grants signed after the election "
        f"(${overlap['with_iati_project_$'] / 1e9:.1f}B of ${overlap['gac_foreign_grants_after_$'] / 1e9:.1f}B) are already IATI activities; the rest are "
        "mostly new multi-year institutional pledges (Global Fund, Gavi, IFAD, African Development Bank) not yet in GAC's IATI files and assessed "
        "contributions to the UN, NATO, OECD and similar bodies.",
        "Keyword flags are whole-word matches on English text (French only when no English is given): W women/girls, M men/boys, G gender, "
        "L LGBTQ2+ terms. A flag means the words appear in the title, description, program name or expected results, not that the money is "
        "targeted at that group. Contract descriptions are standard category labels (e.g. 'Management consulting'), so contracts almost never "
        "carry a flag. P and S are GAC's own "
        "OECD gender-equality policy marker (principal objective / significant objective) and exist for IATI records only.",
        "Gender Inequality Index: UNDP Human Development Report, " + str(gii_meta["latest_year"]) + " values; rank 1 = most equal among the "
        f"{sum(1 for v in gii.values() if v['rank'])} countries with a value. Lower is more equal.",
        "Grants to individuals with a foreign address (mostly NSERC, SSHRC and CIHR fellowships held abroad and Canadian athletes "
        "training abroad) are counted under that country but not named.",
    ]
    if big:
        notes.append(f"{len(big)} foreign contracts of $100M or more were awarded after the election, worth ${sum(r['v'] for r in big) / 1e9:.1f}B "
                     f"of the ${totals['after']['contracts'] / 1e9:.1f}B contracts total; they are multi-year deals booked on the award date.")
    noshape = sorted((c for c, v in countries.items() if not places.info.get(c, {}).get("shape") and any(v["after"].values())))
    if noshape:
        notes.append("Countries with money but no shape on the 1:50m map (listed, not drawn): "
                     + ", ".join(f"{countries[c]['name']} ({c})" for c in noshape) + ".")
    if places.unknown:
        notes.append("Unrecognised country codes (unplaced): " + ", ".join(f"{k or '(blank)'} x{v}" for k, v in places.unknown.most_common()))

    meta = {
        "generated": date.today().isoformat(), "election": election, "cutoff": cutoff,
        "before_start": before_start, "before_end": before_end,
        "sources": {
            "contracts": {"label": "Proactive Publication - Contracts over $10,000 (open.canada.ca)", "url": CONTRACTS_DATASET,
                          "file": "data/raw/contracts/recent.csv (2024+ rows of contracts.csv)", "rows_used": rows_used(cstats),
                          "record_url": CONTRACT_URL},
            "grants": {"label": "Proactive Disclosure - Grants and Contributions (open.canada.ca)", "url": GRANTS_DATASET,
                       "file": "data/raw/grants.csv", "rows_used": rows_used(gstats), "record_url": GRANT_URL,
                       "gac_share_after": int(round(gac_share_grants))},
            "iati": {"label": "Global Affairs Canada IATI activity files (IATI Registry publisher gac-amc, CA-3)",
                     "url": "https://iatiregistry.org/publisher/gac-amc", "registry_api": manifest.get("registry", ""),
                     "files": [f.get("url") or f["file"] for f in manifest["files"]], "fetched_via": manifest.get("source", ""),
                     "rows_used": rows_used(istats), "record_url": PROJECT_URL if manifest.get("project_browser_ok", True) else ""},
            "gii": {"label": "UNDP Human Development Report: Gender Inequality Index (composite indices time series)", "url": gii_meta["url"],
                    "year": gii_meta["latest_year"], "countries": len(gii)},
        },
        "totals": {w: {s: int(round(v)) for s, v in t.items()} for w, t in totals.items()},
        "unplaced_after": {**{s: int(round(v)) for s, v in unplaced.items()},
                           "iati_regions": [[k, int(round(v))] for k, v in regions.most_common(20)]},
        "keywords": dict(KEYWORDS),
        "keywords_fr": {k: KEYWORDS[k] + "|" + KEYWORDS_FR[k] for k in KEYWORDS},
        "flags_after": {f"{s}|{letter}": [n, int(round(flag_dollars[(s, letter)]))] for (s, letter), n in sorted(flag_counts.items())},
        "overlap": overlap,
        "notes": notes,
    }
    records.sort(key=lambda r: (r["s"],) + order(r))
    data = {"meta": meta, "countries": countries, "records": [compact(r) for r in records]}
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "intl_spending.json.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as g:
            json.dump(data, g, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(OUT / "intl_spending.json")
    finally:
        tmp.unlink(missing_ok=True)

    size = (OUT / "intl_spending.json").stat().st_size
    rec_size = len(json.dumps(data["records"], ensure_ascii=False, separators=(",", ":")).encode())
    log(f"intl_spending.json: {size / 1e6:.2f} MB ({len(records)} records, {rec_size / 1e6:.2f} MB of them) in {time.time() - t0:.0f}s")
    for w in ("after", "before"):
        log(f"  {w}: " + ", ".join(f"{s} ${v / 1e6:,.0f}M" for s, v in meta["totals"][w].items()))
    log("  unplaced after: " + ", ".join(f"{s} ${unplaced[s] / 1e6:,.0f}M" for s in SRC))
    for s in SRC:
        top = sorted(((c, v["after"][s]) for c, v in countries.items() if v["after"][s]), key=lambda t: -t[1])[:10]
        log(f"  top {s}: " + ", ".join(f"{c} ${v / 1e6:,.0f}M" for c, v in top))
    log("  flags after: " + ", ".join(f"{k} {n} (${v / 1e6:,.0f}M)" for k, (n, v) in meta["flags_after"].items()))
    log(f"  overlap: {json.dumps(overlap)}")


if __name__ == "__main__":
    main()
