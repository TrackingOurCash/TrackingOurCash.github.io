# Provincial grant data: source survey (Alberta, BC, Saskatchewan)

Checked 25 October 2026. Every URL below returned HTTP 200 when checked.

## The short version

None of the three provinces publishes where a grant recipient is. Each lists the recipient's
name and the amount, nothing more. So the federal method (place each award by the recipient's
postal code) cannot be reused as is. Recipients have to be matched by name to something with a
known location: a municipality, school division, First Nation, university, health authority, a
registered charity (the CRA charity list carries city and postal code), or the same name in the
federal grants file, which does carry postal codes. Individuals and unmatched names stay unplaced.

| Province | Best grants source | Format, size | Location field | Verdict |
|---|---|---|---|---|
| Alberta | Grant payments disclosure: every payment, with program and date, quarterly since 2014 | CSV, 20 to 30 MB per fiscal year | none | name only, but the richest data of the three |
| BC | Public Accounts "Government Transfers", payees of $25,000 or more, one line per payee per ministry per year | CSV, 1 to 2 MB per year | none | name only; the Community Gaming Grants file does have a city |
| Saskatchewan | Public Accounts Volume 2, transfers of $50,000 or more by program and recipient | PDF, 4 to 9 MB per year | none | name only, and needs PDF table extraction |

Two timing points:

- **BC voted on 24 October 2026.** Final count runs 6 to 10 November, final results 18 November.
  The 2024 results are the last machine-readable set; the 2026 results should appear in the same
  data file after the final count. The legislature site shows no MLA list until the new house sits.
- **Alberta's boundaries are being redrawn.** The 2026 commission report (89 divisions) was rejected
  by the Legislature in April 2026; a committee is to produce a 91-division map for the October 2027
  election. No new map file exists yet, so the 2019 map (87 divisions, used in 2023) is the one to use.

## Alberta

**Grants.** https://open.alberta.ca/dataset/grant-disclosure (Treasury Board and Finance, Open
Government Licence - Alberta). One CSV per fiscal year, for example
`.../resource/1e95ba75-b4b1-44df-9426-988d60b6cff7/download/tbf-grants-disclosure-2025-26.csv` (26 MB),
plus a live export of the current year at
https://grants.dataservices.alberta.ca/GrantsDataService.svc/file.exportcsv (18 MB).
Fields: Ministry, BUName, Recipient, Program, Amount, Lottery, PaymentDate, FiscalYear,
DisplayFiscalYear. No threshold; negative adjustments included; some names withheld for privacy.
Excludes most agencies, Crown corporations and the school/university/health sector's own grants.

**Boundaries (87, 2019).** Elections Alberta shapefile
https://www.elections.ab.ca/uploads/2019Boundaries_ED-Shapefiles.zip (2.9 MB). Also on Represent
as `alberta-electoral-districts-2017` (same map).

**2023 results.** Statement of Vote workbook
https://www.elections.ab.ca/uploads/2023-Provincial-General-Election-Statement-of-Vote.xlsx (474 KB):
87 sheets, one per division, poll-level rows, candidate cells as "Name / party". Needs a small parser.

**MLAs.** https://www.assembly.ab.ca/txt/mla_home/contacts.csv (27 KB, 87 rows; caucus codes
reflect current standing, for example PTP for a floor-crosser).

**Population.** 2021 census profile by electoral division, CSV:
https://open.alberta.ca/dataset/330635ba-632a-4ad1-a9f6-b8176216cf07/resource/81f483c1-b6c8-4ba3-9ab1-b26c03188c01/download/ped-profile-census-2021-report-data.csv

## British Columbia

**Transfers.** https://catalogue.data.gov.bc.ca/dataset/crf-detailed-schedules-of-payments-government-transfers
(OGL-BC, annual with the public accounts in August). For example FYE2026:
`.../resource/c5eecccf-3f4f-4144-8d8d-de3a51e65a54/download/fye26-govt-transfers.csv` (1.1 MB).
Fields: NAME, MINISTRY, AMOUNT. Payees under $25,000 are not listed; no dates, no programs.

**City-level extra.** Community Gaming Grants, with fiscal year, city, organization, sector and amount:
https://catalogue.data.gov.bc.ca/dataset/gaming-grants-paid-to-community-organizations

**Boundaries (93, 2023 redistribution; used in 2024 and 2026).** GeoJSON straight from the BC map server:
`https://openmaps.gov.bc.ca/geo/pub/WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS11_SVW/ows?service=WFS&version=2.0.0&request=GetFeature&typeName=pub:WHSE_ADMIN_BOUNDARIES.EBC_ELECTORAL_DISTS_BS11_SVW&outputFormat=json&srsName=EPSG:4326`
Also on Represent as `british-columbia-electoral-districts-2023-redistribution`.

**Results.** Provincial voting results by voting place (2024 general election and recent by-elections):
https://catalogue.data.gov.bc.ca/dataset/44914a35-de9a-4830-ac48-870001ef8935/resource/4e7be8e3-0805-4f39-87f3-47c4c29e262d/download/provincial_voting_results_by_voting_place.csv (1.6 MB).
Fields include ED_NAME, CANDIDATE, ELECTED, AFFILIATION, VOTES_CONSIDERED. The 2026 election should
be appended after 18 November 2026.

**Population.** BC Stats census profiles for the 93 districts:
https://catalogue.data.gov.bc.ca/dataset/da0326f2-2191-4345-84d3-d14cd6ee76eb/resource/a32273fb-0f47-4f11-a57d-49a20c398daa/download/census_profile_2021_ped93_part1.csv

## Saskatchewan

**Transfers.** Public Accounts Volume 2, PDF only. 2024-25:
https://www.saskatchewan.ca/-/media/news-release-backgrounders/2025/oct/2024-25-volume-2---5155.pdf (4.2 MB).
Per ministry, transfers of $50,000 or more listed by program and recipient name. No open-data CSV exists.

**Boundaries (61, 2022 commission; used 2024).** Elections Saskatchewan KML and shapefiles:
https://cdn.elections.sk.ca/maps-ge30/ESK_KML_Shape_Files_Mar2024.zip (12 MB; the constituency shapefile inside is 1 MB).
Also https://cdn.elections.sk.ca/maps-ge30/ESK_PollKeys_April2024.zip contains a postal code to
constituency table (old .xls), useful once a postal code is known.

**2024 results.** Poll-by-poll CSV https://cdn.elections.sk.ca/upload/2024-GE-POLL-BY-POLL-RESULTS-v1.0.csv (221 KB),
one column per party.

**MLAs.** https://www.legassembly.sk.ca/umbraco/api/mlacontactinformation/GetCsv/1095 (61 rows; shows
caucus, not party name).

**Population.** Only inside the 2022 commission's final report PDF
(https://cdn.elections.sk.ca/scbcmedia/2022-Sask-Constituency-Boundaries-Commission-Final-Report-low-res.pdf),
and on a voting-age basis.
