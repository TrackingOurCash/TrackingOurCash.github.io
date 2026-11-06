#!/usr/bin/env bash
# Refresh everything: download the latest data, rebuild the riding table, aggregate grants, write the map.
set -e
# Timestamp every command so a slow step shows up in the build log.
PS4='+ [$(date -u +%H:%M:%S)] '
set -x
cd "$(dirname "$0")"
mkdir -p data/raw/geonames output
GRANTS=https://open.canada.ca/data/dataset/432527ab-7aac-45b5-81d6-7597107a7013/resource/1d15a62f-5656-49ad-8c88-f40ce689d831/download/grants.csv
EC=https://www.elections.ca/res/rep/off/ovrGE45/62/data_donnees
REP=https://represent.opennorth.ca/boundaries/federal-electoral-districts-2023-representation-order
# Every download goes through fetch(): it writes to a temporary file, needs a successful HTTP status and a
# minimum size, and only then replaces the copy. If the source is down, the previous copy stands (and a
# warning is logged for the status page and the alert); a step that has no previous copy fails.
WARN=data/build_warnings.txt; : > "$WARN"
warn() { echo "WARNING: $*" | tee -a "$WARN" >&2; }
fetch() {  # fetch <url> <dest> [min_bytes]
  local url=$1 dest=$2 min=${3:-1000}
  if curl -fsSL --retry 4 --retry-delay 10 --connect-timeout 30 -o "$dest.part" "$url" && [[ $(wc -c < "$dest.part") -ge $min ]]; then
    mv "$dest.part" "$dest"
  else
    rm -f "$dest.part"
    if [[ -s $dest ]]; then warn "download failed, kept the previous copy: $url"; else warn "download failed, no previous copy: $url"; return 1; fi
  fi
}
# The federal layer: grants, ridings, results, MPs. Built into the working files, checked by check_federal.py,
# and only then copied to data/lastgood/ (kept between runs by the workflow's cache). If any step fails or the
# check rejects the result, the last good copy and the committed ledger are put back and the rest of the site
# still builds. Nothing here can publish an empty or shrunken federal map.
LASTGOOD=(data/ridings.json data/ridings_geo.json data/ridings_geo_fine.json data/land_geo.json data/population_scale.json data/riding_spending.json data/summary.json
          data/raw/ec2025_table11.csv data/raw/ec2025_table12.csv data/raw/mps.csv data/raw/fed2023_list.json data/raw/fed2023_simple.json)
federal_build() {
  fetch "$GRANTS" data/raw/grants.csv 500000000 &&
  python3 scripts/trim_grants.py &&  # one pass over the 2 GB file; the other scripts read the trimmed copy
  fetch "$EC/table_tableau11.csv" data/raw/ec2025_table11.csv 20000 &&
  fetch "$EC/table_tableau12.csv" data/raw/ec2025_table12.csv 100000 &&
  fetch "https://www.ourcommons.ca/Members/en/search/csv" data/raw/mps.csv 10000 &&
  fetch "$REP/?limit=400" data/raw/fed2023_list.json 50000 &&
  fetch "$REP/simple_shape?limit=400" data/raw/fed2023_simple.json 1000000 &&
  geonames && natural_earth &&
  python3 scripts/fetch_csd.py && python3 scripts/fetch_shapes.py &&
  python3 scripts/prep_ridings.py && python3 scripts/population.py && python3 scripts/prep_ridings.py &&
  python3 scripts/build_spending.py > data/summary.json.tmp && mv data/summary.json.tmp data/summary.json
}
geonames() {
  [[ -f data/raw/geonames/CA_full.txt ]] && return 0
  fetch https://download.geonames.org/export/zip/CA_full.csv.zip data/raw/geonames/CA_full.csv.zip 1000000 &&
  unzip -o -q data/raw/geonames/CA_full.csv.zip -d data/raw/geonames
}
natural_earth() {
  mkdir -p data/raw/ne
  for f in ne_10m_admin_0_countries ne_10m_lakes ne_10m_rivers_lake_centerlines ne_10m_urban_areas; do
    [[ -f data/raw/ne/$f.geojson ]] || fetch "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/$f.geojson" data/raw/ne/$f.geojson 100000 || return 1
  done
}
fetch_soft() { fetch "$@" || true; }  # optional input: a provincial layer falls back to its committed copy without it
# Alberta inputs
mkdir -p data/raw/ab data/raw/cra
AB=https://open.alberta.ca/dataset/faef5592-9ea0-4b60-92db-79a8a9673fe5/resource
fetch_soft "$AB/1e95ba75-b4b1-44df-9426-988d60b6cff7/download/tbf-grants-disclosure-2025-26.csv" data/raw/ab/grants-2025-26.csv
fetch_soft "$AB/f4197a5a-b3c3-4045-b2ce-7f77d700935f/download/tbf-grants-disclosure-2024-25.csv" data/raw/ab/grants-2024-25.csv
fetch_soft "$AB/0c7e93c1-1c28-460d-92eb-f6934e9ba4a8/download/tbf-grants-disclosure-2023-24.csv" data/raw/ab/grants-2023-24.csv
fetch_soft "$AB/a9a92ce7-c005-418d-a411-b663254c601a/download/tbf-grants-disclosure-2022-23.csv" data/raw/ab/grants-2022-23.csv
fetch_soft "$AB/bda2903e-8106-47be-824e-2b22636c8a05/download/tbf-grants-disclosure-2021-22.csv" data/raw/ab/grants-2021-22.csv
fetch_soft "$AB/ef6f0f85-7f5e-449e-8a54-3d45e37f3dc4/download/tbf-grants-disclosure-2020-21.csv" data/raw/ab/grants-2020-21.csv
fetch_soft https://www.elections.ab.ca/uploads/2023-Provincial-General-Election-Statement-of-Vote.xlsx data/raw/ab/sov-2023.xlsx
fetch_soft https://www.assembly.ab.ca/txt/mla_home/contacts.csv data/raw/ab/mlas.csv
fetch_soft https://open.alberta.ca/dataset/330635ba-632a-4ad1-a9f6-b8176216cf07/resource/81f483c1-b6c8-4ba3-9ab1-b26c03188c01/download/ped-profile-census-2021-report-data.csv data/raw/ab/ped-census-2021.csv
fetch_soft "https://represent.opennorth.ca/boundaries/alberta-electoral-districts-2017/simple_shape?limit=100" data/raw/ab/ab2017_simple.json
fetch_soft "https://represent.opennorth.ca/boundaries/alberta-electoral-districts-2017/?limit=100" data/raw/ab/ab2017_list.json
fetch_soft "https://open.canada.ca/data/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8/resource/694fdc72-eae4-4ee0-83eb-832ab7b230e3/download/ident_2024_updated.csv" data/raw/cra/ident_2024.csv

mkdir -p data/lastgood data/ledger
if federal_build && python3 scripts/check_federal.py; then
  for f in "${LASTGOOD[@]}"; do cp "$f" data/lastgood/; done
  cp data/ledger/federal_grants_since_election.csv.gz data/lastgood/
  mv data/ledger_counts.json.tmp data/lastgood/ledger_counts.json
  echo "Federal layer refreshed"
else
  warn "federal layer: rebuild failed or was rejected; publishing the last good copy"
  if [[ -s data/lastgood/riding_spending.json ]]; then
    for f in "${LASTGOOD[@]}"; do [[ -s data/lastgood/$(basename "$f") ]] && cp "data/lastgood/$(basename "$f")" "$f"; done
  fi
  # The ledger only ever grows: put back the committed copy (or the last good one) over a rejected rewrite.
  git checkout -- data/ledger 2>/dev/null || cp data/lastgood/federal_grants_since_election.csv.gz data/ledger/ 2>/dev/null || true
  [[ -s data/riding_spending.json ]] || { echo "No federal data at all (first run and the sources are down); stopping."; exit 1; }
fi
mkdir -p data/raw/contracts
[[ -s data/raw/contracts/contracts.csv ]] || fetch "https://open.canada.ca/data/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b/resource/fac950c0-00d5-4ec1-a4d3-9cbebf98a305/download/contracts.csv" data/raw/contracts/contracts.csv 100000000 || true
python3 scripts/contracts.py || warn "contracts layer: rebuild failed; using the committed copy"
(cd scripts && python3 budget.py) || warn "budget places: rebuild failed; using the committed copy"
# Budget estimate by riding (data/budget_measures.json) and the by-election ridings page (data/byelections.json).
derived() {  # derived <label> <output json> <command...>: on failure, put back the last good output
  local label=$1 out=$2; shift 2
  if "$@" && [[ -s $out ]]; then cp "$out" data/lastgood/; else warn "$label: rebuild failed; using the last good copy"; cp "data/lastgood/$(basename "$out")" "$out" 2>/dev/null || true; fi
}
derived "budget estimate" data/budget_estimate.json python3 scripts/budget_estimate.py
derived "by-election detail" data/byelection_detail.json python3 scripts/byelections.py
python3 scripts/merge_news.py
python3 scripts/wiki_links.py || true
# Provincial layers. Each one rebuilds from its sources when they are reachable; otherwise the
# committed copy under data/<dir>/ stands. The layer is snapshotted first and restored if the
# rebuild fails or produces an empty map (check_layer.py), so a bad day at a source never publishes zeros.
layer() {  # layer <label> <dir> <command...>
  local label=$1 dir=$2; shift 2
  rm -rf "data/$dir.bak"; cp -R "data/$dir" "data/$dir.bak"
  if "$@" > "data/$dir/summary.json.tmp" && python3 scripts/check_layer.py "data/$dir"; then
    mv "data/$dir/summary.json.tmp" "data/$dir/summary.json"; rm -rf "data/$dir.bak"; echo "$label layer refreshed"
  else
    rm -rf "data/$dir"; mv "data/$dir.bak" "data/$dir"; warn "$label layer: rebuild failed or empty; using committed data"
  fi
}
prov() { python3 "scripts/$1_prep.py" >&2 && python3 "scripts/$1_spending.py"; }
grid() { python3 "scripts/$1_prep.py" >&2 || echo "$1 prep skipped (inputs missing); using committed divisions" >&2; python3 scripts/fed_prov_spending.py "$1"; }
layer AB ab prov ab
layer BC bc prov bc
layer SK sk prov sk
layer MB mb prov mb
layer NB nb prov nb
layer ON on prov on
layer NS ns prov ns        # archived Public Accounts supplements; the live site refuses connections
layer PEI pe grid pe       # federal grants on the provincial districts (no provincial payee list)
layer QC qc grid qc
layer NL nl grid nl
for t in yt nt nu; do layer "$t" "$t" grid "$t"; done
# International page data (data/intl/): country shapes, UNDP GII, GAC IATI files; the committed copy stands if this fails.
if python3 scripts/intl_prep.py >&2 && python3 scripts/intl_spending.py; then echo "INTL layer refreshed"; else warn "INTL layer: rebuild failed; using committed data"; fi
python3 scripts/build_map.py
# Last gate before publishing: every page built, none empty or shrunken against the live site; writes output/status.json.
python3 scripts/check_site.py
