"""Shared helpers for the three territorial district tables (yt_prep.py, nt_prep.py, nu_prep.py).

Everything here is standard-library only: a cached downloader, a minimal ESRI shapefile reader
(Elections Nunavut publishes its constituencies only as a shapefile), a parser for the 2021
census populations in Wikipedia's community lists (Statistics Canada's own census-profile API
sits behind a bot check), the record builder that writes the PEI/NB schema, and the population
scaling that pe_prep.scale_population does.

Record schema (data/pe/divisions.json, with the election year in the key names):
  num, name, winner_Y, party_Y, runnerup_Y, runnerup_party_Y, votes_Y, runnerup_votes_Y,
  margin_votes, margin_pts, shares_Y, turnout_pct, registered_voters_Y, mla, mla_party,
  mla_note, population, population_basis
An acclamation has no runner-up: runnerup_Y, runnerup_party_Y, votes_Y, runnerup_votes_Y and
margin_votes are null, margin_pts is 100.0 (so "close seat" tests still work), shares_Y is
empty, and a result_note says "acclaimed".
"""
import json
import re
import struct
import sys
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons, polys_of  # noqa: E402,F401

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0 Safari/537.36 riding-spending (research)"}


def fetch(url, path, timeout=300):
    """Download url to path unless it is already there; return the path."""
    path = Path(path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        print("downloading", url, file=sys.stderr)
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        path.write_bytes(data)
    return path


def strip_html(text):
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    import html
    return html.unescape(re.sub(r"\s+", " ", text))


# ---------------------------------------------------------------- shapefile
def _ring_area(ring):
    return sum(ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1] for i in range(len(ring) - 1)) / 2


def _inside(pt, ring):
    x, y = pt
    ok = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi, xj, yj = ring[i][0], ring[i][1], ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            ok = not ok
        j = i
    return ok


def read_shapefile(shp_path):
    """Read an ESRI polygon shapefile (+ its .dbf) -> list of (attributes, GeoJSON geometry).
    Shapefile outer rings run clockwise and holes counter-clockwise; holes are attached to the
    outer ring that contains their first vertex."""
    shp_path = Path(shp_path)
    shp = shp_path.read_bytes()
    dbf = shp_path.with_suffix(".dbf").read_bytes()
    try:
        encoding = shp_path.with_suffix(".cpg").read_text().strip() or "utf-8"
    except FileNotFoundError:
        encoding = "latin-1"
    # dbf
    n_rec = struct.unpack("<I", dbf[4:8])[0]
    hlen, rlen = struct.unpack("<HH", dbf[8:12])
    fields, p = [], 32
    while dbf[p] != 0x0D:
        name = dbf[p:p + 11].split(b"\0")[0].decode("ascii")
        fields.append((name, chr(dbf[p + 11]), dbf[p + 16]))
        p += 32
    records = []
    for i in range(n_rec):
        rec = dbf[hlen + i * rlen: hlen + (i + 1) * rlen]
        q, attrs = 1, {}
        for name, typ, ln in fields:
            raw = rec[q:q + ln]
            q += ln
            val = raw.decode(encoding, "replace").strip()
            if typ in "FN" and val:
                try:
                    val = float(val) if typ == "F" or "." in val else int(val)
                except ValueError:
                    pass
            attrs[name] = val
        records.append(attrs)
    # shp
    shape_type = struct.unpack("<i", shp[32:36])[0]
    if shape_type not in (5, 15, 25):
        raise ValueError(f"not a polygon shapefile (type {shape_type})")
    geoms, pos = [], 100
    while pos < len(shp):
        length = struct.unpack(">i", shp[pos + 4:pos + 8])[0] * 2
        body = shp[pos + 8:pos + 8 + length]
        pos += 8 + length
        if struct.unpack("<i", body[:4])[0] == 0:
            geoms.append(None)
            continue
        n_parts, n_points = struct.unpack("<ii", body[36:44])
        parts = struct.unpack(f"<{n_parts}i", body[44:44 + 4 * n_parts])
        pts_off = 44 + 4 * n_parts
        pts = struct.unpack(f"<{2 * n_points}d", body[pts_off:pts_off + 16 * n_points])
        rings = []
        for k, start in enumerate(parts):
            end = parts[k + 1] if k + 1 < n_parts else n_points
            ring = [[pts[2 * i], pts[2 * i + 1]] for i in range(start, end)]
            if ring and ring[0] != ring[-1]:
                ring.append(ring[0])
            if len(ring) >= 4:
                rings.append(ring)
        outers = [[r] for r in rings if _ring_area(r) < 0]  # clockwise = outer
        holes = [r for r in rings if _ring_area(r) >= 0]
        if not outers:  # degenerate winding: treat everything as outer
            outers = [[r] for r in rings]
            holes = []
        for h in holes:
            for poly in outers:
                if _inside(h[0], poly[0]):
                    poly.append(h)
                    break
        geoms.append({"type": "MultiPolygon", "coordinates": outers} if len(outers) > 1
                     else {"type": "Polygon", "coordinates": outers[0]})
    if len(geoms) != len(records):
        raise ValueError(f"{len(geoms)} shapes but {len(records)} dbf records")
    return list(zip(records, geoms))


# ---------------------------------------------------------------- geometry output
def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def touches_inset(geom, insets):
    x0, y0, x1, y1 = bounds(geom)
    return any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in insets)


def feature(num, geom, tol, min_extent, cap_lat=None):
    return {"type": "Feature", "id": num, "properties": {"num": num},
            "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, min_extent, cap_lat=cap_lat)}}


def write_outputs(out_dir, divisions, geoms, insets, tol, min_extent, fine_tol=0.0004, fine_min=0.001, cap_lat=None):
    """geoms: {num: GeoJSON geometry}. Writes divisions.json, divisions_geo.json, divisions_geo_fine.json."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    coarse, fine = [], []
    for num in divisions:
        g = geoms.get(num)
        if g is None:
            print("no shape for", num, divisions[num]["name"], file=sys.stderr)
            continue
        coarse.append(feature(num, g, tol, min_extent, cap_lat=cap_lat))
        if touches_inset(g, insets):
            fine.append(feature(num, g, fine_tol, fine_min))
    geo = {"type": "FeatureCollection", "features": coarse}
    fine_fc = {"type": "FeatureCollection", "features": fine}
    json.dump(divisions, open(out_dir / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(out_dir / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine_fc, open(out_dir / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    return geo, fine_fc


# ---------------------------------------------------------------- records
def make_record(year, num, name, candidates, electors, turnout_pct, mla, mla_party, mla_note, valid=None, result_note=None):
    """candidates: list of (votes, name, party); votes None for an acclamation."""
    y = str(year)
    rec = {"num": num, "name": name}
    if len(candidates) == 1 and candidates[0][0] is None:
        w = candidates[0]
        rec.update({f"winner_{y}": w[1], f"party_{y}": w[2], f"runnerup_{y}": None, f"runnerup_party_{y}": None,
                    f"votes_{y}": None, f"runnerup_votes_{y}": None, "margin_votes": None, "margin_pts": 100.0,
                    f"shares_{y}": {}, "turnout_pct": None, f"registered_voters_{y}": electors})
        result_note = result_note or "acclaimed"
    else:
        cands = sorted(candidates, key=lambda c: -c[0])
        total = valid or sum(c[0] for c in cands)
        w, r = cands[0], cands[1]
        shares = Counter()
        for c in cands:
            shares[c[2]] += c[0]
        rec.update({f"winner_{y}": w[1], f"party_{y}": w[2], f"runnerup_{y}": r[1], f"runnerup_party_{y}": r[2],
                    f"votes_{y}": w[0], f"runnerup_votes_{y}": r[0],
                    "margin_votes": w[0] - r[0], "margin_pts": round(100 * (w[0] - r[0]) / total, 1),
                    f"shares_{y}": {p: round(100 * v / total, 1) for p, v in shares.most_common()},
                    "turnout_pct": turnout_pct, f"registered_voters_{y}": electors})
    rec.update({"mla": mla, "mla_party": mla_party, "mla_note": mla_note})
    if result_note:
        rec["result_note"] = result_note
    return rec


def scale_population(divisions, region, base, basis):
    """base: {num: raw population figure}. Scales to Statistics Canada's latest estimate for the
    territory (data/population_scale.json) by the ratio of that estimate to the sum of base."""
    scale = json.load(open(ROOT / "data" / "population_scale.json"))
    estimate = scale["provinces"][region]["estimate"]
    total = sum(base.values())
    factor = estimate / total
    for num, d in divisions.items():
        d["population"] = round(base[num] * factor)
        d["population_basis"] = basis
    return factor, scale["latest_date"], total


# ---------------------------------------------------------------- census populations
def wiki_wikitext(page, path):
    """Cached wikitext of an English Wikipedia page (the MediaWiki API, which is open to scripts)."""
    url = ("https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json&formatversion=2&page="
           + urllib.parse.quote(page))
    return json.load(open(fetch(url, path)))["parse"]["wikitext"]


def census_2021_nunavut(wikitext):
    """'List of municipalities in Nunavut': rows '!scope="row"| [[Name]]...' then '{{change|2021|2016|...'."""
    pops = {}
    for m in re.finditer(r'!scope="row"\|\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\].*?\{\{change\|(\d+)\|', wikitext, flags=re.S):
        name = re.sub(r",.*", "", m.group(1)).strip()
        pops[name] = int(m.group(2))
    return pops


def census_2021_nwt(wikitext):
    """'List of communities in the Northwest Territories': row starts '| [[Name]]', the first
    'align=right| N' cell of the row is the 2021 census count."""
    pops = {}
    for m in re.finditer(r"\n\|\s*\[\[([^\]|]+)(?:\|[^\]]*)?\]\](.*?)(?=\n\|-|\n\|\}|\Z)", wikitext, flags=re.S):
        name = re.sub(r",.*", "", m.group(1)).strip()
        nums = re.findall(r"align=right\|\s*([\d,]+)", m.group(2))
        if nums:
            pops[name] = int(nums[0].replace(",", ""))
    return pops


import urllib.parse  # noqa: E402  (used by wiki_wikitext)
