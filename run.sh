#!/usr/bin/env bash
# Refresh everything: download the latest data, rebuild the riding table, aggregate grants, write the map.
set -e
cd "$(dirname "$0")"
mkdir -p data/raw/geonames output
GRANTS=https://open.canada.ca/data/dataset/432527ab-7aac-45b5-81d6-7597107a7013/resource/1d15a62f-5656-49ad-8c88-f40ce689d831/download/grants.csv
EC=https://www.elections.ca/res/rep/off/ovrGE45/62/data_donnees
REP=https://represent.opennorth.ca/boundaries/federal-electoral-districts-2023-representation-order
curl -sSL --retry 4 -o data/raw/grants.csv "$GRANTS"
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
python3 scripts/build_spending.py > data/summary.json
python3 scripts/contracts.py || echo "contracts layer skipped"
(cd scripts && python3 budget.py)
python3 scripts/merge_news.py
python3 scripts/wiki_links.py || true
# Alberta layer (skipped if the Alberta downloads are missing)
if [[ -f data/raw/ab/grants-2025-26.csv ]]; then python3 scripts/ab_prep.py && python3 scripts/ab_spending.py > data/ab/summary.json; fi
# British Columbia layer
if python3 scripts/bc_prep.py && python3 scripts/bc_spending.py > data/bc/summary.json; then :; else echo "BC layer skipped"; fi
# Saskatchewan layer
if python3 scripts/sk_prep.py && python3 scripts/sk_spending.py > data/sk/summary.json; then :; else echo "SK layer skipped"; fi
# Manitoba layer
if python3 scripts/mb_prep.py && python3 scripts/mb_spending.py > data/mb/summary.json; then :; else echo "MB layer skipped"; fi
# New Brunswick layer
if python3 scripts/nb_prep.py && python3 scripts/nb_spending.py > data/nb/summary.json; then :; else echo "NB layer skipped"; fi
# Prince Edward Island layer (federal grants on the provincial districts; PEI publishes no payee list)
if python3 scripts/pe_prep.py && python3 scripts/fed_prov_spending.py pe > data/pe/summary.json; then :; else echo "PEI layer skipped"; fi
# Ontario layer
if python3 scripts/on_prep.py && python3 scripts/on_spending.py > data/on/summary.json; then :; else echo "ON layer skipped"; fi
# Nova Scotia layer (archived Public Accounts supplements; the live site refuses connections)
if python3 scripts/ns_prep.py && python3 scripts/ns_spending.py > data/ns/summary.json; then :; else echo "NS layer skipped"; fi
# Quebec layer (federal grants on the 2026 ridings; Quebec publishes no payee list either)
if python3 scripts/qc_prep.py && python3 scripts/fed_prov_spending.py qc > data/qc/summary.json; then :; else echo "QC layer skipped"; fi
# Newfoundland and Labrador layer (federal grants on the provincial districts; NL publishes no payee list)
if python3 scripts/nl_prep.py && python3 scripts/fed_prov_spending.py nl > data/nl/summary.json; then :; else echo "NL layer skipped"; fi
# Territories (federal grants on the territorial districts)
for t in yt nt nu; do if python3 scripts/${t}_prep.py && python3 scripts/fed_prov_spending.py $t > data/$t/summary.json; then :; else echo "$t layer skipped"; fi; done
python3 scripts/build_map.py
