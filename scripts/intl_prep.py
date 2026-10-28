"""Inputs for the International page: country shapes, the UNDP Gender Inequality Index and
Global Affairs Canada's IATI activity files. Writes

  data/intl/world_geo.json      Natural Earth 1:50m admin-0 countries, coordinates rounded to
                                0.01 degree, slivers and specks dropped (each country keeps at
                                least its largest polygon), properties iso3/iso2/name/continent/pop
  data/raw/intl/gii.json        {iso3: {gii, rank, year}} from the latest UNDP HDR time series
  data/raw/intl/iati/*.xml      GAC (IATI publisher gac-amc, org id CA-3) activity files, listed
                                by the IATI Registry; data/raw/intl/iati/manifest.json records
                                what was fetched and when

Downloads use urllib with a timeout and resume short transfers (the GAC server drops long ones).
A file is re-downloaded only when it is missing or stale (IATI: older than IATI_MAX_AGE_H hours
and changed on the server), and a failed download keeps the previous copy. Everything downloaded
is treated as untrusted data: XML is parsed by intl_spending.py with ElementTree after a check
that it declares no DTD or entities, and nothing here executes anything it downloads.
"""
import concurrent.futures
import csv
import http.client
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
INTL_RAW = RAW / "intl"
IATI_DIR = INTL_RAW / "iati"
OUT = ROOT / "data" / "intl"

UA = "Mozilla/5.0 (riding-spending data build)"
TIMEOUT = 120
IATI_MAX_AGE_H = 20
GII_MAX_AGE_H = 24 * 30

NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson"
NE_FILE = RAW / "ne" / "ne_50m_admin_0_countries.geojson"
HDR_URLS = [  # newest first; the first that answers is used
    "https://hdr.undp.org/sites/default/files/2026_HDR/HDR26_Composite_indices_complete_time_series.csv",
    "https://hdr.undp.org/sites/default/files/2025_HDR/HDR25_Composite_indices_complete_time_series.csv",
    "https://hdr.undp.org/sites/default/files/2023-24_HDR/HDR23-24_Composite_indices_complete_time_series.csv",
]
REGISTRY = "https://iatiregistry.org/api/3/action/package_search?fq=organization:gac-amc&rows=1000"
PROJECT_BROWSER = "https://w05.international.gc.ca/projectbrowser-banqueprojets/project-projet/details/{p}"
# Used only when the registry cannot be reached and no earlier manifest exists.
GAC_FALLBACK = [f"https://w05.international.gc.ca/projectbrowser-banqueprojets/iita-iati/dfatd-maecd_activit_status_{s}.xml"
                for s in ("2", "3", "4", "4a", "4b", "4c")]

# Natural Earth files several small territories under "Seven seas (open ocean)"; give each the
# continent the UN geoscheme (M49) puts it in, except the uninhabited sub-Antarctic French lands.
SEVEN_SEAS = {"SGS": "South America", "IOT": "Africa", "SHN": "Africa", "SYC": "Africa", "MUS": "Africa",
              "MDV": "Asia", "ATF": "Antarctica", "HMD": "Oceania"}
# Display names: Natural Earth's NAME_LONG, except where it is a formal name nobody uses in prose.
NAMES = {"USA": "United States", "KOR": "South Korea", "PRK": "North Korea", "RUS": "Russia", "LAO": "Laos", "CZE": "Czechia",
         "SWZ": "Eswatini", "CPV": "Cabo Verde", "BRN": "Brunei", "FLK": "Falkland Islands", "FRO": "Faroe Islands",
         "SGS": "South Georgia and the South Sandwich Islands"}
DECIMALS = 2
MIN_AREA = 0.02     # square degrees (~250 km2 at the equator): smaller polygons are dropped ...
KEEP_ALL_BELOW = 0.5  # ... unless the country's largest polygon is itself smaller than this (island states)
SIMPLIFY = 0.03     # Douglas-Peucker tolerance in degrees (~3 km), applied after rounding


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- downloads

def head(url):
    """-> (content_length or None, last_modified) from a HEAD request; (None, "") on failure."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            n = r.headers.get("Content-Length")
            return (int(n) if n and n.isdigit() else None), r.headers.get("Last-Modified", "")
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError):
        return None, ""


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch(url, dest, attempts=30):
    """Download url to dest, resuming short transfers with Range requests; rename into place only
    when complete. Returns the byte count; raises RuntimeError on failure (dest is untouched)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    part.unlink(missing_ok=True)
    have, total, last_err = 0, None, None
    for attempt in range(attempts):
        headers = {"User-Agent": UA}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=TIMEOUT) as r:
                if have and r.status != 206:  # range ignored: start over
                    have = 0
                    part.unlink(missing_ok=True)
                if total is None:
                    cr, cl = r.headers.get("Content-Range", ""), r.headers.get("Content-Length")
                    if "/" in cr and cr.rsplit("/", 1)[1].isdigit():
                        total = int(cr.rsplit("/", 1)[1])
                    elif cl and cl.isdigit():
                        total = int(cl) + have
                with open(part, "ab") as f:
                    while True:
                        try:
                            chunk = r.read(1 << 16)
                        except http.client.IncompleteRead as e:
                            f.write(e.partial)
                            have += len(e.partial)
                            raise
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (400, 401, 403, 404, 410):
                break
            time.sleep(min(2 + attempt, 10))
            continue
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            last_err = e
            time.sleep(min(2 + attempt, 10))
            continue
        if total is None or have >= total:
            part.replace(dest)
            return have
        last_err = f"short read {have}/{total}"
    part.unlink(missing_ok=True)
    raise RuntimeError(f"download failed: {url}: {last_err}")


def age_hours(path):
    return (time.time() - os.path.getmtime(path)) / 3600 if Path(path).exists() else math.inf


# ---------------------------------------------------------------- world_geo.json

def ring_area(r):
    return abs(sum(r[i][0] * r[i + 1][1] - r[i + 1][0] * r[i][1] for i in range(len(r) - 1))) / 2


def dp(pts, tol):
    """Douglas-Peucker on an open polyline (iterative)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for i in range(a + 1, b):
            x, y = pts[i]
            d = abs(dy * (x - x1) - dx * (y - y1)) / norm if norm else math.hypot(x - x1, y - y1)
            if d > best:
                best, idx = d, i
        if best > tol:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [p for p, k in zip(pts, keep) if k]


def clean_ring(ring):
    pts = []
    for x, y in ring:
        p = [round(x, DECIMALS), round(y, DECIMALS)]
        if not pts or p != pts[-1]:
            pts.append(p)
    if len(pts) < 4:
        return None
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    # Simplify the ring as two halves so the closing point stays fixed.
    mid = len(pts) // 2
    pts = dp(pts[:mid + 1], SIMPLIFY)[:-1] + dp(pts[mid:], SIMPLIFY)
    return pts if len(pts) >= 4 else None


def is_code(s, n):
    return isinstance(s, str) and len(s) == n and s.isalpha() and s.isupper()


def build_world():
    if not NE_FILE.exists():
        log(f"downloading {NE_URL}")
        fetch(NE_URL, NE_FILE)
    src = json.load(open(NE_FILE, encoding="utf-8"))
    feats, seen = [], {}
    a2_taken = {f["properties"]["ISO_A2"] for f in src["features"] if is_code(f["properties"]["ISO_A2"], 2)}
    for f in src["features"]:
        q = f["properties"]
        iso3 = q["ISO_A3"] if is_code(q["ISO_A3"], 3) else q["ADM0_A3"]
        iso2 = q["ISO_A2"]
        if not is_code(iso2, 2):
            # France, Norway and Kosovo carry their code in ISO_A2_EH ("-99" in ISO_A2), Taiwan too
            # ("CN-TW"); Australia's external territories also carry AU there, which belongs to
            # Australia, so a code already taken is left blank.
            eh = q.get("ISO_A2_EH", "-99")
            iso2 = eh if is_code(eh, 2) and eh not in a2_taken else ""
        continent = q["CONTINENT"]
        if continent.startswith("Seven seas"):
            continent = SEVEN_SEAS.get(iso3, q.get("REGION_UN") or continent)
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        areas = [ring_area(p[0]) for p in polys]
        biggest = max(areas)
        out = []
        for p, a in sorted(zip(polys, areas), key=lambda t: -t[1]):
            if a < MIN_AREA and a != biggest and biggest >= KEEP_ALL_BELOW:
                continue
            outer = clean_ring(p[0])
            if not outer:
                if a == biggest and not out:  # a speck of a country: keep its rounded outline
                    pts = [[round(x, DECIMALS), round(y, DECIMALS)] for x, y in p[0]]
                    out.append([pts])
                continue
            holes = [h for h in (clean_ring(h) for h in p[1:] if ring_area(h) >= MIN_AREA) if h]
            out.append([outer] + holes)
        if not out:
            log(f"  {iso3} {q['ADMIN']}: no polygon survived; skipped")
            continue
        if iso3 in seen:
            log(f"  duplicate iso3 {iso3}: {seen[iso3]} / {q['ADMIN']}")
        seen[iso3] = q["ADMIN"]
        feats.append({"type": "Feature",
                      "properties": {"iso3": iso3, "iso2": iso2, "name": NAMES.get(iso3) or q["NAME_LONG"] or q["NAME"], "continent": continent,
                                     "pop": int(q["POP_EST"] or 0)},
                      "geometry": {"type": "MultiPolygon", "coordinates": out} if len(out) > 1 else {"type": "Polygon", "coordinates": out[0]}})
    feats.sort(key=lambda f: f["properties"]["iso3"])
    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "world_geo.json.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as g:
            json.dump({"type": "FeatureCollection", "source": "Natural Earth 1:50m admin-0 countries (public domain), simplified",
                       "features": feats}, g, ensure_ascii=False, separators=(",", ":"))
        tmp.replace(OUT / "world_geo.json")
    finally:
        tmp.unlink(missing_ok=True)
    log(f"world_geo.json: {len(feats)} countries, {(OUT / 'world_geo.json').stat().st_size / 1e3:.0f} KB")


# ---------------------------------------------------------------- UNDP Gender Inequality Index

def build_gii():
    dest = INTL_RAW / "hdr_composite_indices.csv"
    meta_path = INTL_RAW / "gii.json"
    used = None
    if age_hours(dest) > GII_MAX_AGE_H:
        for url in HDR_URLS:
            try:
                fetch(url, dest, attempts=4)
                used = url
                break
            except RuntimeError as e:
                log(f"  HDR: {e}")
        if not used and not dest.exists():
            raise SystemExit("UNDP HDR composite indices CSV unavailable at every known URL")
    if not used:
        prev = json.load(open(meta_path)) if meta_path.exists() else {}
        used = prev.get("url", "")
    raw = dest.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")  # the HDR25 file is Windows-1252 ("Côte d'Ivoire")
    rows = list(csv.DictReader(text.splitlines()))
    if not rows or "iso3" not in rows[0]:
        raise SystemExit(f"{dest}: not the HDR composite indices table")
    years = sorted(int(c[4:]) for c in rows[0] if c.startswith("gii_") and c[4:].isdigit())
    latest = years[-1]
    out = {}
    for r in rows:
        iso3 = (r["iso3"] or "").strip()
        if len(iso3) != 3 or not iso3.isalpha():  # regional aggregates are ZZA.VHHD etc.
            continue
        for y in reversed(years):
            v = (r.get(f"gii_{y}") or "").strip()
            if v:
                out[iso3] = {"name": r["country"], "gii": float(v), "year": y, "official_rank": (r.get(f"gii_rank_{y}") or "").strip()}
                break
    # Rank among countries with a latest-year value: 1 = most equal, ties share a rank.
    vals = sorted(v["gii"] for v in out.values() if v["year"] == latest)
    mismatches = 0
    for v in out.values():
        v["rank"] = (vals.index(v["gii"]) + 1) if v["year"] == latest else None
        off = v.pop("official_rank")
        if off and off.isdigit() and v["rank"] is not None and int(off) != v["rank"]:
            mismatches += 1
    json.dump({"url": used, "file": dest.name, "latest_year": latest, "countries": out}, open(meta_path, "w"), ensure_ascii=False, indent=0)
    log(f"gii.json: {len(out)} countries, latest year {latest}, {mismatches} ranks differ from the HDR's own gii_rank column")


# ---------------------------------------------------------------- GAC IATI activity files

def iati_urls():
    """Activity-file URLs for GAC from the IATI Registry; falls back to the last manifest, then a fixed list."""
    try:
        res = get_json(REGISTRY)["result"]["results"]
        urls = []
        for p in res:
            extras = {e["key"]: e["value"] for e in p.get("extras", [])}
            if extras.get("filetype", "activity") != "activity":
                continue
            urls += [r["url"].strip() for r in p.get("resources", []) if r.get("url")]
        if urls:
            return sorted(set(urls)), "registry"
        log("  IATI registry returned no activity files")
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError, KeyError) as e:
        log(f"  IATI registry unreachable: {e}")
    man = IATI_DIR / "manifest.json"
    if man.exists():
        return [f["url"] for f in json.load(open(man))["files"]], "previous manifest"
    return GAC_FALLBACK, "fixed list (registry unreachable)"


def check_project_browser(files, previous):
    """Does GAC's project browser resolve a project from the files? A redirect to its error page or a
    404 says no; a network failure keeps the previous answer."""
    import re
    for f in files:
        try:
            with open(IATI_DIR / f["file"], "rb") as fh:
                m = re.search(rb"<iati-identifier>CA-3-([A-Z0-9]+)</iati-identifier>", fh.read(1 << 16))
        except OSError:
            continue
        if not m:
            continue
        url = PROJECT_BROWSER.format(p=m.group(1).decode())
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                ok = r.status == 200 and "/error" not in r.geturl()
        except urllib.error.HTTPError:
            ok = False
        except (urllib.error.URLError, http.client.HTTPException, OSError):
            return previous
        log(f"  project browser link {url}: {'ok' if ok else 'does not resolve; links dropped'}")
        return ok
    return previous


def build_iati():
    IATI_DIR.mkdir(parents=True, exist_ok=True)
    urls, how = iati_urls()
    man_path = IATI_DIR / "manifest.json"
    prev = {f["url"]: f for f in json.load(open(man_path))["files"]} if man_path.exists() else {}

    def one(url):
        name = url.rsplit("/", 1)[1].split("?")[0]
        if not name.endswith(".xml") or "/" in name or name.startswith("."):
            raise RuntimeError(f"unexpected file name in {url}")
        dest = IATI_DIR / name
        p = prev.get(url, {})
        if dest.exists() and age_hours(dest) <= IATI_MAX_AGE_H:
            return {**p, "url": url, "file": name, "status": "fresh"}
        size, modified = head(url)
        if dest.exists() and size and size == dest.stat().st_size and modified and modified == p.get("last_modified"):
            os.utime(dest)
            return {**p, "url": url, "file": name, "status": "unchanged"}
        try:
            n = fetch(url, dest)
            return {"url": url, "file": name, "bytes": n, "last_modified": modified, "fetched": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "status": "downloaded"}
        except RuntimeError as e:
            if dest.exists():
                log(f"  {name}: {e}; keeping the previous copy")
                return {**p, "url": url, "file": name, "status": "stale (download failed)"}
            raise

    t0 = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        files = list(ex.map(one, urls))
    link_ok = check_project_browser(files, json.load(open(man_path)).get("project_browser_ok", True) if man_path.exists() else True)
    json.dump({"source": how, "registry": REGISTRY, "project_browser_ok": link_ok, "files": files}, open(man_path, "w"), indent=1)
    log(f"IATI: {len(files)} activity files via {how} "
        f"({', '.join(f['file'] + ' ' + f['status'] for f in files)}) in {time.time() - t0:.0f}s")


def main():
    build_world()
    build_gii()
    build_iati()


if __name__ == "__main__":
    main()
