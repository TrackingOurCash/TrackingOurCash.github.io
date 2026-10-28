"""Federal money that goes abroad, by country and Government of Canada fiscal year (1 April to
31 March), for the International page. Writes data/intl/intl_spending.json (via a temp file, so a
failed run leaves the committed copy alone) and prints a short summary to stderr.

Three sources, never added together (they overlap: see meta.overlap and meta.notes):
  contracts  Proactive Publication - Contracts over $10,000 (data/raw/contracts/contracts.csv, read
             once, streaming, rows dated from the first fiscal year on). Foreign = country_of_vendor
             not CA and not blank. Amendments merged exactly as contracts.py does: rows sharing
             (owner_org, procurement_id), or reference_number when procurement_id is blank, are one
             contract; value = the latest row's contract_value (else original + amendment); date =
             the original award (earliest non-amendment contract_date, else earliest
             contract_period_start). Standing offers / supply arrangements (SOSA) dropped.
  grants     Proactive Disclosure - Grants and Contributions (data/raw/grants.csv, read once,
             streaming). Foreign = recipient_country not CA and not blank. Amendments merged as in
             build_spending.py: per (owner_org, ref_number) the highest amendment_number's
             agreement_value, dated by the original agreement_start_date.
  iati       Global Affairs Canada's IATI activity files (data/raw/intl/iati/, fetched by
             intl_prep.py). Disbursements (transaction type 3) and expenditures (4), one record per
             activity per recipient country per fiscal year (that year's transactions summed, dated
             by the latest), split by recipient-country percentages; the recipient-region share is
             "unplaced" under the region's name.
A record's fiscal year is that of its date. Fiscal years run from FIRST_FY (2023-24) to the current
one; records dated after the build date (forward-dated agreements) are left out and counted in
meta.future_dated. If contracts.csv is missing, recent.csv (rows from 2024-01-01) is read instead
and every source starts at 2024-25, so no year is half-covered. Money is CAD, whole dollars.

Keyword flags (W women/girls, M men/boys, G gender, L LGBTQ2+) are whole-word, case-insensitive
matches over title, description, program and expected results (contracts: description_en only);
French patterns are used only when every English field is empty. IATI also carries GAC's own
gender-equality policy marker (OECD DAC vocabulary 1, code 1): P = principal, S = significant.

Records are arrays [s, d, v, who, c, r, o, t, ref, k]: s "c"/"g"/"i"; o indexes meta.orgs; ref is
the open.canada.ca reference (contracts, grants) or the GAC project number without "CA-3-" (iati).
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

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTL_RAW = RAW / "intl"
IATI_DIR = INTL_RAW / "iati"
OUT = ROOT / "data" / "intl"
GAC = "dfatd-maecd"  # GAC's owner_org code in both open.canada.ca files; IATI records use it too
GAC_NAME = "Global Affairs Canada"
FIRST_FY = 2023  # fiscal year 2023-24 (1 April 2023 to 31 March 2024)
SRC = ("contracts", "grants", "iati")
CODE = {"contracts": "c", "grants": "g", "iati": "i"}

csv.field_size_limit(sys.maxsize)

GRANTS_DATASET = "https://open.canada.ca/data/en/dataset/432527ab-7aac-45b5-81d6-7597107a7013"
CONTRACTS_DATASET = "https://open.canada.ca/data/en/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b"
# {org} and {ref} must be URL-encoded (encodeURIComponent): a few references carry spaces or
# non-ASCII hyphens.
GRANT_URL = "https://search.open.canada.ca/grants/record/{org}%2C{ref}%2Ccurrent"
CONTRACT_URL = "https://search.open.canada.ca/contracts/record/{org}%2C{ref}"
PROJECT_URL = "https://w05.international.gc.ca/projectbrowser-banqueprojets/project-projet/details/{ref}"

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
FLAG_LETTERS = {"contracts": "WMGL", "grants": "WMGL", "iati": "WMGLPS"}


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


def fy_start_year(d):
    y, m = int(d[:4]), int(d[5:7])
    return y if m >= 4 else y - 1


def fy_label(start_year):
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def fy_of(d):
    return fy_label(fy_start_year(d))


def quarter_of(d):
    m = int(d[5:7])
    return f"{fy_of(d)} Q{(m - 4) // 3 + 1 if m >= 4 else 4}"


class Span:
    """The dates a record may carry: first fiscal year's 1 April to the build date."""

    def __init__(self, first_fy, today):
        self.start, self.end = f"{first_fy}-04-01", today
        self.future = Counter()

    def ok(self, d, src):
        if not d or d < self.start:
            return False
        if d > self.end:
            self.future[src + "_n"] += 1
            return False
        return True


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


class Orgs:
    """owner_org code -> index into meta.orgs, named by the most common short English title."""

    def __init__(self):
        self.names = defaultdict(Counter)

    def see(self, code, title):
        self.names[code][first(title) or code] += 1

    def table(self):
        codes = sorted(self.names, key=lambda c: (self.names[c].most_common(1)[0][0].lower(), c))
        return [[c, self.names[c].most_common(1)[0][0]] for c in codes], {c: i for i, c in enumerate(codes)}


def csv_columns(f):
    reader = csv.reader(f)
    head = [h.lstrip("﻿") for h in next(reader)]
    return reader, head, {h: i for i, h in enumerate(head)}


# ---------------------------------------------------------------- contracts

def load_contracts(places, orgs, span, path):
    """Foreign contracts dated in the span, merged across amendments as contracts.py does."""
    stats = Counter()
    contracts = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader, head, ix = csv_columns(f)
        C = {k: ix[k] for k in ("reference_number", "procurement_id", "vendor_name", "contract_date", "contract_period_start",
                                "contract_value", "original_value", "amendment_value", "description_en", "country_of_vendor",
                                "instrument_type", "reporting_period", "owner_org", "owner_org_title")}
        for row in reader:
            stats["rows"] += 1
            if len(row) != len(head):
                stats["malformed_rows"] += 1
                continue
            cd, ps = iso(row[C["contract_date"]]), iso(row[C["contract_period_start"]])
            if max(cd, ps) < span.start:  # the same row filter contracts.py applies for its cache, from the first fiscal year
                continue
            stats["rows_in_span"] += 1
            itype = row[C["instrument_type"]].strip().upper()
            if itype == "SOSA":
                stats["sosa_rows_dropped"] += 1
                continue
            cdate = cd or ps
            if not cdate:
                continue
            org = row[C["owner_org"]]
            pid = row[C["procurement_id"]].strip()
            ref = row[C["reference_number"]].strip()
            key = (org, "p:" + pid if pid else "r:" + ref)
            value = to_float(row[C["contract_value"]]) or (to_float(row[C["original_value"]]) + to_float(row[C["amendment_value"]]))
            rec = {"date": cdate, "award": cdate if itype != "A" else "", "period": ps or cdate, "value": value,
                   "order": (row[C["reporting_period"]], cdate), "title": row[C["owner_org_title"]], "org": org, "ref": ref,
                   "vendor": row[C["vendor_name"]].strip(), "country": row[C["country_of_vendor"]].strip().upper(),
                   "desc": row[C["description_en"]].strip()}
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
        if not span.ok(rec["date"], "contracts"):
            if rec["date"] > span.end:
                span.future["contracts_$"] += rec["value"]
            continue
        orgs.see(rec["org"], rec["title"])
        stats["foreign_contracts"] += 1
        out.append({"s": "contracts", "d": rec["date"], "v": rec["value"], "who": rec["vendor"], "c": places.iso3(rec["country"]),
                    "code": rec["country"], "r": "", "org": rec["org"], "t": rec["desc"], "ref": rec["ref"], "k": kw_flags([rec["desc"]])})
    stats["contracts"] = len(contracts)
    return out, stats


# ---------------------------------------------------------------- grants and contributions

def load_grants(places, orgs, span):
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
        reader, head, ix = csv_columns(f)

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
            if start < span.start:
                continue
            country = col(row, "recipient_country").strip().upper()
            if country in ("", "CA"):
                continue
            key = (org, col(row, "ref_number").strip())
            a_no = amend_no(col(row, "amendment_number"))
            rec = {"a": a_no, "start": start, "value": to_float(col(row, "agreement_value")), "org": org, "ref": key[1],
                   "title_org": col(row, "owner_org_title"), "country": country, "rtype": col(row, "recipient_type"),
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
        if not span.ok(rec["start"], "grants"):
            if rec["start"] > span.end:
                span.future["grants_$"] += rec["value"]
            continue
        orgs.see(rec["org"], rec["title_org"])
        stats["foreign_agreements"] += 1
        if rec["rtype"] == "P":  # recipient_type P = individual or sole proprietorship (I = international organization)
            stats["individuals"] += 1
        en = [rec["title"], rec["prog"], rec["desc"], rec["results"]]
        fr = [rec["title_fr"], rec["prog_fr"], rec["desc_fr"], rec["results_fr"]]
        out.append({"s": "grants", "d": rec["start"], "v": rec["value"],
                    # Individuals abroad (fellowships, athletes) are counted but not named.
                    "who": "Individual recipient" if rec["rtype"] == "P" else rec["who"],
                    "c": places.iso3(rec["country"]), "code": rec["country"], "r": "", "org": rec["org"],
                    "t": rec["title"] or rec["prog"] or rec["title_fr"] or first(rec["prog_fr"]), "ref": rec["ref"],
                    "k": kw_flags(en, fr), "proj": proj_rx.findall(rec["agreement_number"]) if rec["org"] == GAC else []})
    return out, stats, gac_projects


# ---------------------------------------------------------------- IATI

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


def narrative(el, lang="en"):
    if el is None:
        return ""
    for n in el.findall("narrative"):
        if (n.get(XML_LANG) or "").lower() == lang and (n.text or "").strip():
            return n.text.strip()
    return ""


def any_narrative(el):
    if el is None:
        return ""
    return narrative(el, "en") or narrative(el, "fr") or next((n.text.strip() for n in el.findall("narrative") if (n.text or "").strip()), "")


def check_xml(path):
    """Refuse files that declare a DTD or entities (entity-expansion attacks); IATI needs neither."""
    with open(path, "rb") as f:
        head = f.read(1 << 16)
    if b"<!DOCTYPE" in head or b"<!ENTITY" in head:
        raise ValueError(f"{path.name} declares a DTD/entities; refusing to parse")


def load_iati(places, orgs, span):
    man_path = IATI_DIR / "manifest.json"
    manifest = json.load(open(man_path)) if man_path.exists() else {"files": [{"file": p.name, "url": ""} for p in sorted(IATI_DIR.glob("*.xml"))]}
    stats = Counter()
    out, seen_ids, iati_fy, iati_all = [], set(), defaultdict(dict), set()
    orgs.see(GAC, GAC_NAME)
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
            fy_sum, fy_last, q_sum = defaultdict(float), {}, defaultdict(float)
            for t in a.findall("transaction"):
                tt = t.find("transaction-type")
                if tt is None or tt.get("code") not in ("3", "4"):
                    continue
                td = t.find("transaction-date")
                d = iso(td.get("iso-date") if td is not None else "")
                v = t.find("value")
                if v is None or not span.ok(d, "iati"):
                    if v is not None and d > span.end:
                        span.future["iati_$"] += to_float(v.text)
                    continue
                cur = (v.get("currency") or dcur).upper()
                if cur != "CAD":
                    stats["non_cad_transactions_skipped"] += 1
                    continue
                if t.find("recipient-country") is not None or t.find("recipient-region") is not None:
                    stats["transactions_with_own_recipient"] += 1  # none in GAC's files; split like the rest
                stats["transactions"] += 1
                f = fy_of(d)
                fy_sum[f] += to_float(v.text)
                fy_last[f] = max(fy_last.get(f, ""), d)
                q_sum[quarter_of(d)] += to_float(v.text)
            if not fy_sum:
                a.clear()
                continue
            for f, v in fy_sum.items():
                iati_fy[f][proj] = v
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
            orgs_ = [any_narrative(p) for p in a.findall("participating-org") if p.get("role") == "4"]
            if not any(orgs_):
                orgs_ = [any_narrative(p) for p in a.findall("participating-org") if p.get("role") == "2"]
            who = "; ".join(dict.fromkeys(o for o in orgs_ if o))
            for f, total in fy_sum.items():
                qs = {q: v for q, v in q_sum.items() if q.startswith(f + " ")}
                for kind, code, pct in targets:
                    share = pct / total_pct
                    if not total * share:
                        continue
                    c = places.iso3(code) if kind == "c" else ""
                    region = code if kind == "r" else ("" if c else f"Unrecognised country code {code}")
                    out.append({"s": "iati", "d": fy_last[f], "v": total * share, "who": who, "c": c, "code": code if kind == "c" else "",
                                "r": region, "org": GAC, "t": title_en or title_fr, "ref": proj, "k": k + marker,
                                "qv": {q: v * share for q, v in qs.items()}})
            stats["activities_with_money"] += 1
            a.clear()
    return out, stats, manifest, iati_fy, iati_all


# ---------------------------------------------------------------- assemble

def order(r):
    """Largest first, ties broken by reference so the output is stable across Python versions."""
    return (SRC.index(r["s"]), -int(round(r["v"])), r["ref"], r["c"], r["r"], r["d"])


def main():
    t0 = time.time()
    today = date.today().isoformat()
    places = Places()
    orgs = Orgs()
    gii_meta = json.load(open(INTL_RAW / "gii.json", encoding="utf-8"))
    gii = gii_meta["countries"]

    full_contracts = RAW / "contracts" / "contracts.csv"
    recent = RAW / "contracts" / "recent.csv"
    if full_contracts.exists():
        first_fy, contracts_path = FIRST_FY, full_contracts
    elif recent.exists():
        # recent.csv starts 2024-01-01, so 2023-24 would be a quarter short: start every source a year later.
        first_fy, contracts_path = max(FIRST_FY, 2024), recent
        log(f"  {full_contracts} missing: reading recent.csv and starting at {fy_label(first_fy)}")
    else:
        raise SystemExit(f"missing {full_contracts}")
    span = Span(first_fy, today)

    contracts, cstats = load_contracts(places, orgs, span, contracts_path)
    log(f"contracts: {cstats['foreign_contracts']} foreign contracts ({time.time() - t0:.0f}s)")
    grants, gstats, gac_projects = load_grants(places, orgs, span)
    log(f"grants: {gstats['foreign_agreements']} foreign agreements ({time.time() - t0:.0f}s)")
    iati, istats, manifest, iati_fy, iati_all = load_iati(places, orgs, span)
    log(f"iati: {istats['activities_with_money']} activities with disbursements ({time.time() - t0:.0f}s)")

    allrecs = contracts + grants + iati
    for r in allrecs:
        r["fy"] = fy_of(r["d"])
    fys = sorted({r["fy"] for r in allrecs})
    last_date = max(r["d"] for r in allrecs)
    quarters = []
    y = first_fy
    while fy_label(y) <= fy_of(last_date):
        quarters += [f"{fy_label(y)} Q{n}" for n in (1, 2, 3, 4)]
        y += 1
    quarters = quarters[:quarters.index(quarter_of(last_date)) + 1]
    qix = {q: i for i, q in enumerate(quarters)}
    org_table, org_ix = orgs.table()

    totals = {f: {s: 0.0 for s in SRC} for f in fys}
    unplaced = {f: {s: 0.0 for s in SRC} for f in fys}
    regions = {f: Counter() for f in fys}
    flags = {f: {s: {L: [0, 0.0] for L in FLAG_LETTERS[s]} for s in SRC} for f in fys}
    latest = {s: None for s in SRC}
    fy_latest = {}
    countries = {}

    def country(c):
        if c not in countries:
            info = places.info.get(c, {"name": c, "continent": "", "pop": 0})
            g = gii.get(c) or {}
            countries[c] = {"name": info["name"], "continent": info["continent"], "pop": info["pop"],
                            "gii": g.get("gii"), "gii_rank": g.get("rank"), "gii_year": g.get("year", gii_meta["latest_year"]),
                            "fy": {f: {s: 0.0 for s in SRC} for f in fys}, "n": {f: {s: 0 for s in SRC} for f in fys},
                            "q": {s: [0.0] * len(quarters) for s in SRC}, "latest": {s: None for s in SRC}}
        return countries[c]

    for c in sorted(places.info):  # every country on the map, even with no money
        country(c)
    for r in allrecs:
        s, f, d = r["s"], r["fy"], r["d"]
        totals[f][s] += r["v"]
        latest[s] = max(latest[s] or "", d)
        fy_latest[f] = max(fy_latest.get(f, ""), d)
        for L in r["k"]:
            flags[f][s][L][0] += 1
            flags[f][s][L][1] += r["v"]
        if not r["c"]:
            unplaced[f][s] += r["v"]
            if s == "iati":
                regions[f][r["r"]] += r["v"]
            if not r["r"]:
                r["r"] = f"Unrecognised country code {r.get('code') or '(blank)'}"
            continue
        cc = country(r["c"])
        cc["fy"][f][s] += r["v"]
        cc["n"][f][s] += 1
        cc["latest"][s] = max(cc["latest"][s] or "", d)
        for q, v in (r["qv"].items() if "qv" in r else [(quarter_of(d), r["v"])]):
            cc["q"][s][qix[q]] += v

    for cc in countries.values():
        cc["fy"] = {f: {s: int(round(v)) for s, v in m.items()} for f, m in cc["fy"].items()}
        cc["q"] = {s: [int(round(v)) for v in arr] for s, arr in cc["q"].items()}

    # Overlap, per fiscal year: GAC agreements in the grants file carry the IATI project number in agreement_number.
    overlap = {}
    for f in fys:
        gac = [r for r in grants if r["fy"] == f and r["org"] == GAC]
        matched = [r for r in gac if any(p in iati_all for p in r["proj"])]
        ia = iati_fy.get(f, {})
        in_gc = [p for p in ia if p in gac_projects]
        overlap[f] = {"gac_foreign_grants": len(gac), "gac_foreign_grants_$": int(round(sum(r["v"] for r in gac))),
                      "with_iati_project": len(matched), "with_iati_project_$": int(round(sum(r["v"] for r in matched))),
                      "iati_activities": len(ia), "iati_activities_in_grants_file": len(in_gc),
                      "iati_$": int(round(sum(ia.values()))), "iati_$_in_grants_file": int(round(sum(ia[p] for p in in_gc)))}

    complete = [f for f in fys if f"{int(f[:4]) + 1}-03-31" <= today]
    ref_fy = complete[-1] if complete else fys[-1]
    o = overlap[ref_fy]
    fy_through = {f: fy_latest[f] for f in fys if f"{int(f[:4]) + 1}-03-31" > today}
    big = [r for r in contracts if r["v"] >= 100_000_000]
    noshape = sorted(c for c, v in countries.items() if not places.info.get(c, {}).get("shape") and any(any(m.values()) for m in v["fy"].values()))
    notes = [
        "Fiscal years run 1 April to 31 March. A record counts in the fiscal year of its date: contracts by original award date, grants by "
        "agreement start date, IATI by disbursement date. The current year is partial (see fy_through), and the latest quarter or two of "
        "contracts and grants are thin because departments publish them quarterly, a month or more after the quarter ends.",
        "Contracts: 'country' is the vendor's country (country_of_vendor), i.e. where the supplier is based, not where the work is done; "
        "a U.S. firm supplying a Canadian base counts as United States. Value is the contract's current total value booked on its award date, "
        "so multi-year deals count in full in the year they were signed.",
        "Grants and contributions: 'country' is the recipient's mailing address (recipient_country), not where the money is spent. "
        "UN agencies and international NGOs are mostly addressed in New York, Geneva, Rome, Vienna, Paris or London, so those cities' "
        "countries collect money spent elsewhere. Value is the agreement's current total (latest amendment), counted in the year of the original "
        "start date, as on the federal page. Canadian NGOs delivering aid abroad are addressed in Canada and are not counted here.",
        "IATI (Global Affairs Canada only): 'country' is the activity's recipient country as GAC reports it, the best measure of where aid goes. "
        "Money is actual disbursements in the year (a flow), not agreement totals (a commitment), so it is not comparable dollar for dollar with "
        "grants. Multi-country activities are split by GAC's recipient-country percentages; the share GAC assigns to a region rather than a "
        "country is listed as unplaced under the region's name. Other departments' aid (e.g. Finance, IRCC) is not in this file.",
        f"Do not add the sources together: GAC's aid appears both in the grants file (by agreement) and in IATI (by disbursement). In {ref_fy}, "
        f"{o['iati_activities_in_grants_file']} of the {o['iati_activities']} GAC activities with disbursements "
        f"(${o['iati_$_in_grants_file'] / 1e9:.1f}B of ${o['iati_$'] / 1e9:.1f}B) match a GAC agreement in the grants file by project number "
        f"(any start date, any recipient address), and {o['with_iati_project']} of the {o['gac_foreign_grants']} foreign-addressed GAC grants "
        f"(${o['with_iati_project_$'] / 1e9:.1f}B of ${o['gac_foreign_grants_$'] / 1e9:.1f}B) are IATI activities; the rest are mostly "
        "multi-year institutional pledges (Global Fund, Gavi, IFAD, development banks) and assessed contributions to the UN, NATO, OECD and "
        "similar bodies, which GAC does not report at project level.",
        "Keyword flags are whole-word matches on English text (French only when no English is given): W women/girls, M men/boys, G gender, "
        "L LGBTQ2+ terms. A flag means the words appear in the title, description, program name or expected results, not that the money is "
        "targeted at that group. Contract descriptions are standard category labels (e.g. 'Management consulting'), so contracts almost never "
        "carry a flag. P and S are GAC's own OECD gender-equality policy marker (principal objective / significant objective) and exist for "
        "IATI records only.",
        "Gender Inequality Index: UNDP Human Development Report, " + str(gii_meta["latest_year"]) + " values; rank 1 = most equal among the "
        f"{sum(1 for v in gii.values() if v['rank'])} countries with a value. Lower is more equal.",
        "Grants to individuals with a foreign address (mostly NSERC, SSHRC and CIHR fellowships held abroad and Canadian athletes "
        "training abroad) are counted under that country but not named.",
    ]
    if big:
        notes.append(f"{len(big)} foreign contracts of $100M or more across these years, worth ${sum(r['v'] for r in big) / 1e9:.1f}B; "
                     "they are multi-year deals booked in full in the year they were awarded.")
    if span.future:
        notes.append("Left out as forward-dated (dated after " + today + "): " + ", ".join(
            f"{s} {span.future[s + '_n']:,} (${span.future[s + '_$'] / 1e6:,.0f}M)" for s in SRC if span.future[s + "_n"]) + ".")
    if noshape:
        notes.append("Countries with money but no shape on the 1:50m map (listed, not drawn): "
                     + ", ".join(f"{countries[c]['name']} ({c})" for c in noshape) + ".")
    if places.unknown:
        notes.append("Unrecognised country codes (unplaced): " + ", ".join(f"{k or '(blank)'} x{v}" for k, v in places.unknown.most_common()))

    meta = {
        "generated": today,
        "fys": fys,
        "fy_through": fy_through,
        "latest": latest,
        "quarters": quarters,
        "sources": {
            "contracts": {"label": "Proactive Publication - Contracts over $10,000 (open.canada.ca)", "url": CONTRACTS_DATASET,
                          "file": f"data/raw/contracts/{contracts_path.name}", "rows_used": {k: int(v) for k, v in cstats.items()},
                          "record_url": CONTRACT_URL},
            "grants": {"label": "Proactive Disclosure - Grants and Contributions (open.canada.ca)", "url": GRANTS_DATASET,
                       "file": "data/raw/grants.csv", "rows_used": {k: int(v) for k, v in gstats.items()}, "record_url": GRANT_URL},
            "iati": {"label": "Global Affairs Canada IATI activity files (IATI Registry publisher gac-amc, CA-3)",
                     "url": "https://iatiregistry.org/publisher/gac-amc", "registry_api": manifest.get("registry", ""),
                     "files": [f.get("url") or f["file"] for f in manifest["files"]], "fetched_via": manifest.get("source", ""),
                     "rows_used": {k: int(v) for k, v in istats.items()},
                     "record_url": PROJECT_URL if manifest.get("project_browser_ok", True) else ""},
            "gii": {"label": "UNDP Human Development Report: Gender Inequality Index (composite indices time series)", "url": gii_meta["url"],
                    "year": gii_meta["latest_year"], "countries": len(gii)},
        },
        "totals": {f: {s: int(round(v)) for s, v in t.items()} for f, t in totals.items()},
        "unplaced": {f: {**{s: int(round(v)) for s, v in unplaced[f].items()},
                         "iati_regions": [[k, int(round(v))] for k, v in regions[f].most_common(15)]} for f in fys},
        "orgs": org_table,
        "flags": {f: {s: {L: [n, int(round(v))] for L, (n, v) in m.items()} for s, m in fs.items()} for f, fs in flags.items()},
        "keywords": dict(KEYWORDS),
        "keywords_fr": {k: KEYWORDS[k] + "|" + KEYWORDS_FR[k] for k in KEYWORDS},
        "future_dated": {k: int(round(v)) for k, v in span.future.items()},
        "overlap": overlap,
        "notes": notes,
    }
    allrecs.sort(key=order)
    records = [[CODE[r["s"]], r["d"], int(round(r["v"])), short(r["who"], 80), r["c"], r["r"], org_ix[r["org"]],
                short(r["t"], 110), r["ref"], r["k"]] for r in allrecs]
    data = {"meta": meta, "countries": countries, "records": records}
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "intl_spending.json.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as g:
            json.dump(data, g, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(OUT / "intl_spending.json")
    finally:
        tmp.unlink(missing_ok=True)

    size = (OUT / "intl_spending.json").stat().st_size
    log(f"intl_spending.json: {size / 1e6:.2f} MB, {len(records)} records, fiscal years {', '.join(fys)} "
        f"(latest: {', '.join(f'{s} {d}' for s, d in latest.items())}) in {time.time() - t0:.0f}s")
    counts = Counter((r["s"], r["fy"]) for r in allrecs)
    for f in fys:
        log(f"  {f}: " + ", ".join(f"{s} ${meta['totals'][f][s] / 1e6:,.0f}M ({counts[(s, f)]:,} records, "
                                   f"unplaced ${meta['unplaced'][f][s] / 1e6:,.0f}M)" for s in SRC))
    log(f"  overlap {ref_fy}: {json.dumps(overlap[ref_fy])}")
    if span.future:
        log(f"  forward-dated, left out: {dict(span.future)}")


if __name__ == "__main__":
    main()
