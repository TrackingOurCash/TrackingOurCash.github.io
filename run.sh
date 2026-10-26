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
for f in ne_10m_admin_0_countries ne_10m_lakes; do
  [[ -f data/raw/ne/$f.geojson ]] || curl -sSL -o data/raw/ne/$f.geojson "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/$f.geojson"
done
python3 scripts/prep_ridings.py
python3 scripts/build_spending.py > data/summary.json
python3 scripts/build_map.py
