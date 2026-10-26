"""Québec: build the riding (circonscription) table for the 5 October 2026 general
election: 127 ridings of the 2026 electoral map.

Which map. The 2023-2025 redistribution by the Commission de la représentation électorale
was interrupted by a law of 2 May 2024 (Bill 59, Loi visant l'interruption du processus de
délimitation des circonscriptions électorales); the Cour d'appel struck that law down on
1 December 2025 and the Supreme Court of Canada upheld it on 22 April 2026, so the
Commission's delimitation (published in the Gazette officielle on 14 January 2026) stood.
On 12 June 2026 the National Assembly then passed a law raising the Assembly from 125 to
127 seats, keeping the Montréal and Gaspésie ridings the Commission had merged while
adding the Commission's new ridings; the final boundaries were published in the Gazette
officielle on 17 June 2026 and were the ones used on 5 October 2026. Compared with the
2017 map: two ridings added (Bellefeuille in the Laurentides, Marie-Lacoste-Gérin-Lajoie
in Estrie-Centre-du-Québec), 39 boundaries changed, and renamings (Johnson -> Daniel-Johnson,
Laporte -> Pierre-Laporte, Arthabaska -> Arthabaska-L'Érable, Matane-Matapédia ->
Matane-Matapédia-Mitis, Rivière-du-Loup-Témiscouata -> Rivière-du-Loup-Témiscouata-Les
Basques, Vimont -> Vimont-Auteuil). Represent's quebec-electoral-districts-2017 set (125
ridings) therefore does NOT apply; the boundaries come from Élections Québec's own open
data for the 2026 map.

Inputs (data/raw/qc/, downloaded here when missing; Élections Québec open data,
https://www.electionsquebec.qc.ca/donnees-ouvertes/ and https://www.dgeq.org/donnees.html):
  circonscriptions_2026.json   GeoJSON of the 127 ridings, water removed ("sans eau"),
                               full detail (2.4 MB; properties CO_CEP = riding code,
                               NM_CEP = name)
  liste_circonscriptions2026.csv   official list: name (with en dashes and typographic
                               apostrophes, Élections Québec's spelling), code (cp1252)
  results_2026/resultats.json  "résultats tout-en-un" of the 2026 general election: every
                               candidate's votes per riding, valid/rejected ballots,
                               registered electors, and an isResultatsFinaux flag. This is
                               the file behind the "résultats en direct" page; it is updated
                               after judicial recounts (last update 23 October 2026, after
                               the Vachon recount). The Rapport des résultats officiels was
                               not yet published on 26 October 2026 because the Champlain
                               recount was still before the Court of Québec.
  mnas_current.html            https://www.assnat.qc.ca/fr/deputes/index.html, the list of
                               sitting members (the site's WAF refuses python-urllib's
                               default User-Agent, so a browser one is sent)

Outputs:
  data/qc/divisions.json          one record per riding, keyed by Élections Québec's
                                  riding code ("689" = Abitibi-Est), NB/MB schema with
                                  the year 2026 in the key names
  data/qc/divisions_geo.json      simplified GeoJSON (clean_polygons, tol 0.002, min 0.005)
  data/qc/divisions_geo_fine.json lighter simplification (tol 0.0004, min 0.001) of the
                                  full shapes for the ridings touching a city inset
                                  (Montréal, Québec, Gatineau, Sherbrooke, Trois-Rivières,
                                  Saguenay)

Choices made here:
  * Results: the live results file, valid votes only. Margins and shares are over the
    riding's valid votes (nbVoteValide, which equals the sum of the candidates' votes);
    turnout_pct is Élections Québec's tauxParticipation, registered_voters_2026 the
    registered electors. Candidate names are "Prénom Nom".
  * Party codes (ballot abbreviation -> label): PQ -> PQ, PLQ/QLP -> PLQ, CAQ -> CAQ,
    QS -> QS, PCOQ (Parti conservateur du Québec) -> PCQ, Ind. -> IND. Minor parties keep
    a short code: PVQ (Parti vert, ballot PVQ/GPQ), CQ (Climat Québec - Équipe Martine
    Ouellet, ballot CQ-EMO), PCAN (Parti canadien du Québec, ballot PCQ/CPQ, renamed so it
    cannot be confused with the conservatives), PCOM (Parti communiste, ballot PCQ), PN
    (Parti nul), DD (Démocratie directe), PRQ (Présence Québec), PCUQ (Parti culinaire),
    PLIQ (Parti libertarien), PMLQ (marxiste-léniniste), BP (Bloc pot), PAPE (Parti accès
    propriété et équité, ballot PAPE-EQD), EA (Équipe autonomiste), OQ (Osons Québec),
    QI (Québec innovant). None of them placed in the top four anywhere.
  * Current MNAs: the assnat.qc.ca table (name "Nom, Prénom", riding, party), matched by
    normalised riding name. Champlain is absent from the table (126 members listed on
    26 October 2026) because a judicial recount of its result (Adriana Szalontai, PCQ,
    ahead of René Branchaud, PQ, by 191 votes) was pending; it is recorded as "Vacant"
    with an mla_note. Vachon's result in the file is the one after the 21 October 2026
    recount (Stephan Fogaing, PQ, three votes ahead of Affine Lwalalika, PLQ, who led by
    ten on election night; the Liberals announced an appeal); a result_note says so.
  * Population: Québec's Commission de la représentation électorale works with electors,
    not census population, and Statistics Canada publishes no profile for Québec's
    provincial ridings, so "population" is the REGISTERED ELECTORS of each riding at the
    5 October 2026 election (kept raw as "electors_2026"), scaled as mb_prep.scale_population
    does: multiplied by the ratio of Statistics Canada's latest Québec estimate
    (data/population_scale.json) to the elector total, so the 127 figures sum to the
    province's population and per-capita figures sit on the same footing as the other
    provinces'. Within the province they are per elector (ridings with many children or
    non-citizens, e.g. in Montréal, look more populous than they are). population_2021 is
    the raw elector count, as nb_prep writes it, for schema consistency; population_basis
    says all this.
  * Names: Élections Québec's official spelling from liste_circonscriptions2026.csv (en
    dashes between compound parts, typographic apostrophes: "Anjou–Louis-Riel",
    "Arthabaska-L’Érable"); the results file writes plain hyphens and the GeoJSON mixes
    both, so matching is on a normalised key.
"""
import csv
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "qc"
OUT = ROOT / "data" / "qc"
sys.path.insert(0, str(ROOT / "scripts"))
from prep_ridings import clean_polygons, polys_of  # noqa: E402

DATA = "https://donnees.electionsquebec.qc.ca"
SOURCES = {
    "circonscriptions_2026.json": f"{DATA}/autres/provincial/circonscriptions_electorales_sans_eau_2026.json",
    "liste_circonscriptions2026.csv": f"{DATA}/autres/provincial/liste_circonscriptions2026.csv",
    "results_2026/resultats.json": f"{DATA}/production/provincial/resultats/resultats.json",
    "mnas_current.html": "https://www.assnat.qc.ca/fr/deputes/index.html",
}
# Montréal, Québec, Gatineau, Sherbrooke, Trois-Rivières, Saguenay: [west, south, east, north].
INSETS = [[-74.05, 45.38, -73.4, 45.75], [-71.55, 46.68, -71.1, 46.98], [-75.95, 45.4, -75.6, 45.55],
          [-72.0, 45.33, -71.8, 45.45], [-72.7, 46.3, -72.5, 46.42], [-71.3, 48.35, -70.95, 48.5]]
PARTY = {"PQ": "PQ", "PLQ/QLP": "PLQ", "CAQ": "CAQ", "QS": "QS", "PCOQ": "PCQ", "Ind.": "IND",
         "PVQ/GPQ": "PVQ", "CQ-EMO": "CQ", "PCQ/CPQ": "PCAN", "PCQ": "PCOM", "PN": "PN", "DD": "DD", "PRQ": "PRQ",
         "PCUQ": "PCUQ", "PLIQ": "PLIQ", "PMLQ": "PMLQ", "BP": "BP", "PAPE-EQD": "PAPE", "EA": "EA", "OQ": "OQ", "QI": "QI"}
CAUCUS = {"Parti québécois": "PQ", "Parti libéral du Québec": "PLQ", "Parti conservateur du Québec": "PCQ",
          "Québec solidaire": "QS", "Coalition avenir Québec": "CAQ", "Indépendant": "IND", "Indépendante": "IND"}
POPULATION_BASIS = ("registered electors at the 5 October 2026 election (Élections Québec results file), scaled to "
                    "Statistics Canada's latest Québec estimate by the ratio of that estimate to the elector total; "
                    "Québec's boundary commission counts electors, and no census population exists for its ridings")
# Hand-written notes on results that changed after election night (Élections Québec results
# file; Wikipedia, 2026 Quebec general election, for the dates), keyed by normalised name.
RESULT_NOTES = {
    "vachon": "after the 21 October 2026 judicial recount (Stephan Fogaing, PQ, by 3 votes; Affine Lwalalika, PLQ, led by 10 on election night; the Liberals announced an appeal)",
    "champlain": "judicial recount ordered by the Court of Québec (Adriana Szalontai, PCQ, 191 votes ahead); result shown as counted, not yet in the official report",
}
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 riding-spending",
      "Accept-Language": "fr-CA,fr;q=0.9"}


def norm(name):
    s = re.sub(r"[–—\-'’]", " ", name or "")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s)).strip()


def get(url, path, pause=1.0):
    if path.exists() and path.stat().st_size > 0:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print("downloading", url, file=sys.stderr)
    time.sleep(pause)
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r, open(path, "wb") as f:
        f.write(r.read())


def fetch_all():
    for name, url in SOURCES.items():
        get(url, RAW / name)


def official_names():
    """{code: official name} from liste_circonscriptions2026.csv (cp1252, ';')."""
    out = {}
    with open(RAW / "liste_circonscriptions2026.csv", encoding="cp1252", newline="") as f:
        for r in csv.DictReader(f, delimiter=";"):
            out[r["CODE 2026"].strip()] = r["CIRCONSCRIPTION 2026"].strip()
    return out


def load_results(names):
    data = json.load(open(RAW / "results_2026" / "resultats.json", encoding="utf-8"))
    print("results file updated", data["statistiques"]["iso8601DateMAJ"], "final:", data["statistiques"]["isResultatsFinaux"])
    out = {}
    for c in data["circonscriptions"]:
        num = str(c["numeroCirconscription"])
        if not c["isResultatsFinaux"]:
            print("warning: results not final for", c["nomCirconscription"], file=sys.stderr)
        cands = sorted(({"name": f"{x['prenom']} {x['nom']}".strip(), "party": PARTY.get(x["abreviationPartiPolitique"], x["abreviationPartiPolitique"]),
                         "votes": int(x["nbVoteTotal"])} for x in c["candidats"]), key=lambda k: -k["votes"])
        for x in c["candidats"]:
            if x["abreviationPartiPolitique"] not in PARTY:
                print("unknown party code", x["abreviationPartiPolitique"], "in", c["nomCirconscription"], file=sys.stderr)
        valid = int(c["nbVoteValide"]) or 1
        if sum(k["votes"] for k in cands) != int(c["nbVoteValide"]):
            print(f"warning: {c['nomCirconscription']}: candidates sum to {sum(k['votes'] for k in cands)}, file says {c['nbVoteValide']} valid", file=sys.stderr)
        win, second = cands[0], cands[1]
        name = names.get(num)
        if not name or norm(name) != norm(c["nomCirconscription"]):
            print("warning: name mismatch", num, name, c["nomCirconscription"], file=sys.stderr)
            name = name or c["nomCirconscription"]
        rec = {
            "num": num,
            "winner_2026": win["name"], "party_2026": win["party"],
            "runnerup_2026": second["name"], "runnerup_party_2026": second["party"],
            "votes_2026": win["votes"], "runnerup_votes_2026": second["votes"],
            "margin_votes": win["votes"] - second["votes"],
            "margin_pts": round(100 * (win["votes"] - second["votes"]) / valid, 1),
            "shares_2026": {k["party"]: round(100 * k["votes"] / valid, 1) for k in cands[:4]},
            "valid_votes_2026": valid,
            "turnout_pct": float(str(c["tauxParticipation"]).replace(",", ".")),
            "registered_voters_2026": int(c["nbElecteurInscrit"]),
            "name": name,
        }
        if norm(name) in RESULT_NOTES:
            rec["result_note"] = RESULT_NOTES[norm(name)]
        out[num] = rec
    if len(out) != 127:
        print(f"warning: {len(out)} ridings in the results file, expected 127", file=sys.stderr)
    return out


def person(name):
    """'Bérubé,\\xa0Pascal' -> 'Pascal Bérubé'."""
    name = re.sub(r"\s+", " ", name.replace("\xa0", " ")).strip()
    if "," in name:
        last, first = name.split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return name


def load_mnas(divisions):
    by_name = {norm(d["name"]): d for d in divisions.values()}
    text = open(RAW / "mnas_current.html", encoding="utf-8", errors="replace").read()
    seen = set()
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < 3 or cells[0] == "Nom":
            continue
        d = by_name.get(norm(cells[1]))
        if not d:
            print("MNA riding matches no result:", cells[:3], file=sys.stderr)
            continue
        seen.add(d["num"])
        d["mla"] = person(cells[0])
        party = re.sub(r"\s+", " ", cells[2]).strip()
        d["mla_party"] = CAUCUS.get(party, party)
        if party not in CAUCUS:
            print("unknown caucus label", party, file=sys.stderr)
        # Compare surnames only (the Assembly may write a fuller given name than the ballot).
        if norm(d["mla"]).split()[-1] != norm(d["winner_2026"]).split()[-1]:
            d["mla_note"] = f"not the 2026 winner ({d['winner_2026']}, {d['party_2026']}); by-election or change since"
            print("note:", d["name"], d["mla_note"], file=sys.stderr)
        elif d["mla_party"] != d["party_2026"]:
            d["mla_note"] = f"elected as {d['party_2026']}, now sits as {d['mla_party']}"
    for d in divisions.values():
        if d["num"] not in seen:
            d["mla"], d["mla_party"] = "Vacant", ""
            d["mla_note"] = "not yet in the Assembly's member list on the download date (judicial recount of the 2026 result pending)"
            print("note:", d["name"], "has no sitting member listed", file=sys.stderr)


def scale_population(divisions):
    """population = registered electors scaled so the 127 sum to StatCan's Québec estimate."""
    scale = json.load(open(ROOT / "data" / "population_scale.json"))
    estimate = scale["provinces"]["Quebec"]["estimate"]
    total = sum(d["registered_voters_2026"] for d in divisions.values())
    factor = estimate / total if total else 1.0
    for d in divisions.values():
        d["electors_2026"] = d["registered_voters_2026"]
        d["population_2021"] = d["registered_voters_2026"]
        d["population"] = round(d["registered_voters_2026"] * factor)
        d["population_basis"] = POPULATION_BASIS
    return factor, scale["latest_date"], total


def bounds(geom):
    pts = [p for poly in polys_of(geom) for p in poly[0]]
    return min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)


def touches_inset(geom):
    x0, y0, x1, y1 = bounds(geom)
    return any(x1 > w and x0 < e and y1 > s and y0 < n for w, s, e, n in INSETS)


def feature(num, geom, tol, min_extent):
    return {"type": "Feature", "id": num, "properties": {"num": num},
            "geometry": {"type": "MultiPolygon", "coordinates": clean_polygons(polys_of(geom), tol, min_extent)}}


def load_shapes(divisions):
    coarse, fine = [], []
    for f in json.load(open(RAW / "circonscriptions_2026.json", encoding="utf-8"))["features"]:
        num = str(f["properties"]["CO_CEP"])
        if num not in divisions:
            print("shape with no result:", num, f["properties"].get("NM_CEP"), file=sys.stderr)
            continue
        if norm(f["properties"].get("NM_CEP", "")) != norm(divisions[num]["name"]):
            print("shape name differs:", f["properties"].get("NM_CEP"), divisions[num]["name"], file=sys.stderr)
        coarse.append(feature(num, f["geometry"], 0.002, 0.005))
        if touches_inset(f["geometry"]):
            fine.append(feature(num, f["geometry"], 0.0004, 0.001))
    order = {num: i for i, num in enumerate(divisions)}
    key = lambda ft: order[ft["id"]]
    return ({"type": "FeatureCollection", "features": sorted(coarse, key=key)},
            {"type": "FeatureCollection", "features": sorted(fine, key=key)})


def main():
    fetch_all()
    OUT.mkdir(parents=True, exist_ok=True)
    names = official_names()
    divisions = load_results(names)
    load_mnas(divisions)
    factor, pop_date, total = scale_population(divisions)
    divisions = dict(sorted(divisions.items(), key=lambda kv: norm(kv[1]["name"])))
    geo, fine = load_shapes(divisions)
    missing = set(divisions) - {ft["id"] for ft in geo["features"]}
    if missing:
        print("ridings with no shape:", sorted(missing), file=sys.stderr)
    json.dump(divisions, open(OUT / "divisions.json", "w"), ensure_ascii=False, indent=1)
    json.dump(geo, open(OUT / "divisions_geo.json", "w"), separators=(",", ":"))
    json.dump(fine, open(OUT / "divisions_geo_fine.json", "w"), separators=(",", ":"))
    close = sum(d["margin_pts"] < 10 for d in divisions.values())
    seats = Counter(d["party_2026"] for d in divisions.values())
    now = Counter(d["mla_party"] for d in divisions.values())
    print(f"{len(divisions)} ridings, {len(geo['features'])} shapes ({len(fine['features'])} fine), {close} close in 2026, "
          f"seats 2026 {dict(seats)}, sitting {dict(now)}")
    print(f"population: {total:,} registered electors scaled by {factor:.4f} to {pop_date}: "
          f"{sum(d['population'] for d in divisions.values()):,}")
    print("geo bytes:", (OUT / "divisions_geo.json").stat().st_size, "fine bytes:", (OUT / "divisions_geo_fine.json").stat().st_size)


if __name__ == "__main__":
    main()
