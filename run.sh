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
curl -sSL --retry 4 -o data/raw/grants.csv "$GRANTS"
python3 scripts/trim_grants.py   # one pass over the 2 GB file; the other scripts read the trimmed copy
curl -sSL -o data/raw/ec2025_table11.csv "$EC/table_tableau11.csv"
curl -sSL -o data/raw/ec2025_table12.csv "$EC/table_tableau12.csv"
curl -sSL -o data/raw/mps.csv "https://www.ourcommons.ca/Members/en/search/csv"
curl -sSL -o data/raw/fed2023_list.json "$REP/?limit=400"
curl -sSL -o data/raw/fed2023_simple.json "$REP/simple_shape?limit=400"
if [[ ! -f data/raw/geonames/CA_full.txt ]]; then
  curl -sSL -o data/raw/geonames/CA_full.csv.zip https://download.geonames.org/export/zip/CA_full.csv.zip
  unzip -o -q data/raw/geonames/CA_full.csv.zip -d data/raw/geonames
fi
mkdir -p data/raw/ne
for f in ne_10m_admin_0_countries ne_10m_lakes ne_10m_rivers_lake_centerlines ne_10m_urban_areas; do
  [[ -f data/raw/ne/$f.geojson ]] || curl -sSL -o data/raw/ne/$f.geojson "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/$f.geojson"
done

# Alberta inputs
mkdir -p data/raw/ab data/raw/cra
AB=https://open.alberta.ca/dataset/faef5592-9ea0-4b60-92db-79a8a9673fe5/resource
curl -sSL -o data/raw/ab/grants-2025-26.csv "$AB/1e95ba75-b4b1-44df-9426-988d60b6cff7/download/tbf-grants-disclosure-2025-26.csv"
curl -sSL -o data/raw/ab/grants-2024-25.csv "$AB/f4197a5a-b3c3-4045-b2ce-7f77d700935f/download/tbf-grants-disclosure-2024-25.csv"
curl -sSL -o data/raw/ab/grants-2023-24.csv "$AB/0c7e93c1-1c28-460d-92eb-f6934e9ba4a8/download/tbf-grants-disclosure-2023-24.csv"
curl -sSL -o data/raw/ab/grants-2022-23.csv "$AB/a9a92ce7-c005-418d-a411-b663254c601a/download/tbf-grants-disclosure-2022-23.csv"
curl -sSL -o data/raw/ab/grants-2021-22.csv "$AB/bda2903e-8106-47be-824e-2b22636c8a05/download/tbf-grants-disclosure-2021-22.csv"
curl -sSL -o data/raw/ab/grants-2020-21.csv "$AB/ef6f0f85-7f5e-449e-8a54-3d45e37f3dc4/download/tbf-grants-disclosure-2020-21.csv"
curl -sSL -o data/raw/ab/sov-2023.xlsx https://www.elections.ab.ca/uploads/2023-Provincial-General-Election-Statement-of-Vote.xlsx
curl -sSL -o data/raw/ab/mlas.csv https://www.assembly.ab.ca/txt/mla_home/contacts.csv
curl -sSL -o data/raw/ab/ped-census-2021.csv https://open.alberta.ca/dataset/330635ba-632a-4ad1-a9f6-b8176216cf07/resource/81f483c1-b6c8-4ba3-9ab1-b26c03188c01/download/ped-profile-census-2021-report-data.csv
curl -sSL -o data/raw/ab/ab2017_simple.json "https://represent.opennorth.ca/boundaries/alberta-electoral-districts-2017/simple_shape?limit=100"
curl -sSL -o data/raw/ab/ab2017_list.json "https://represent.opennorth.ca/boundaries/alberta-electoral-districts-2017/?limit=100"
curl -sSL -o data/raw/cra/ident_2024.csv "https://open.canada.ca/data/dataset/80c00cdb-1358-415c-bb8b-0de7f12675b8/resource/694fdc72-eae4-4ee0-83eb-832ab7b230e3/download/ident_2024_updated.csv"
python3 scripts/fetch_csd.py
python3 scripts/fetch_shapes.py
python3 scripts/prep_ridings.py
python3 scripts/population.py && python3 scripts/prep_ridings.py
python3 scripts/build_spending.py > data/summary.json.tmp && mv data/summary.json.tmp data/summary.json
mkdir -p data/raw/contracts
[[ -s data/raw/contracts/contracts.csv ]] || curl -sSL --retry 3 -o data/raw/contracts/contracts.csv "https://open.canada.ca/data/dataset/d8f85d91-7dec-4fd1-8055-483b77225d8b/resource/fac950c0-00d5-4ec1-a4d3-9cbebf98a305/download/contracts.csv" || echo "contracts download failed"
python3 scripts/contracts.py || echo "contracts layer skipped"
(cd scripts && python3 budget.py)
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
    rm -rf "data/$dir"; mv "data/$dir.bak" "data/$dir"; echo "$label layer: rebuild failed or empty; using committed data"
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
python3 scripts/build_map.py
