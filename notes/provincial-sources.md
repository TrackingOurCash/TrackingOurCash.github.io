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


---

# Source survey, part 2 (Manitoba, New Brunswick, Nova Scotia, PEI, Newfoundland and Labrador)

Checked 25–26 October 2026 with curl -sI / GET from the user's Mac (plus the desktop app's browser pane for JavaScript-only pages). Every URL below returned HTTP 200 unless a status is noted.

## The short version

Same pattern as AB/BC/SK: none of the five publishes a recipient's postal code. Two useful differences: **Manitoba's payee list prints the payee's town** (except Winnipeg), and **New Brunswick's list is a proper open-data CSV**. Nova Scotia is a PDF with a low ($5,000) threshold. **Newfoundland and Labrador publishes no payee or grant-recipient list at all**, so it cannot be mapped from provincial data. **PEI could not be checked**: princeedwardisland.ca and electionspei.ca sit behind Radware bot protection that returns a CAPTCHA to this network's IP (curl, WebFetch and the browser pane all land on validate.perfdrive.com; I did not attempt to solve it). Two Nova Scotia hosts (notices.novascotia.ca, which holds the public accounts PDFs, and nslegislature.ca) also refuse connections from here (TLS handshake fails in curl, WebFetch and the browser pane), so their URLs are quoted from search results, not verified.

Timing points:
- **Nova Scotia now has 56 districts, not 55.** The 2024 election (26 Nov 2024) used the 2019 55-district map; a 56th district, Chéticamp-Margarees-Pleasant Bay, was carved out of Inverness (release date 9 April 2026 in the provincial map service) and filled by by-election on 23 June 2026. Represent's `nova-scotia-electoral-districts-2019` set is the old 55. Elections NS posts an "Election Readiness Update" for the 43rd general election; the fixed-date rule points to July 2028 (not verified).
- **NL voted on 14 October 2025** (PC government, 20 PC / 15 Lib / 2 NDP / 3 Ind), on the 2015 40-district map.
- **Manitoba** voted 3 Oct 2023 (next fixed date 5 Oct 2027; by-elections Tuxedo 2024, Transcona and Spruce Woods 2025, The Pas-Kameesak 2026). **NB** voted 21 Oct 2024 (49 new districts; Miramichi West by-election 6 Oct 2025; next 2028). **PEI** voted 3 Apr 2023 (27 districts; next fixed date Oct 2027). Nothing imminent anywhere.

## Manitoba

**Payees.** "Vendor Payments over $50,000", one PDF per fiscal year, published with the Public Accounts each autumn. 2025-26:
https://www.gov.mb.ca/asset_library/en/finances/vendor-payments-over-50k-2025-26.pdf (PDF, 660 KB, 56 pages). Per department/SOA: every payee whose total from that department exceeded $50,000 (purchase-card payees $25,000+), grants included (school divisions, immigrant-serving agencies, First Nations councils all appear alongside suppliers). Fields are just name and amount, but note 6 in the preamble: "The location of the payee is shown except where payment was made to an address in Winnipeg" — the town is appended to the name as free text ("WESTMAN IMMIGRANT SERVICES BRANDON $441,188", "BELL MOBILITY INC BURLINGTON ON $71,513"; no town = Winnipeg). No program, no dates, no open-data CSV. Earlier years are linked from https://www.gov.mb.ca/government/finances/financial-reports-archive.html (2019-20 through 2024-25, e.g. https://manitoba.ca/asset_library/en/proactive/20242025/publicaccounts/VendorPaymentsover50k2024-25.pdf; listed there, not individually checked). Index page: https://www.gov.mb.ca/government/finances/annualreports-publicaccounts.html. OpenMB/DataMB has no payee dataset.

**Boundaries (57, 2018 commission; used 2019 and 2023).** Elections Manitoba shapefile
https://www.electionsmanitoba.ca/downloads/2018_Final_ED_Manitoba_Public_Urban.zip (1.7 MB; EDBC2018_FinalBoundaries_Rural.shp inside) plus the Winnipeg/Brandon detail file 2018_Final_ED_Winnipeg_Public_Urban.zip (74 KB). Also Represent `manitoba-electoral-districts-2018`. 2023 voting areas: VA_MB2023_public.zip (4.1 MB). Next commission 2028.

**2023 results.** https://www.electionsmanitoba.ca/en/Results/PreviousElections/2023 links
`/downloads/Summary_of_Results_GE2023.xlsx` (20 KB; one sheet: division, member elected, party, registered voters, votes cast, turnout, votes by party, plurality), `/downloads/Candidates_Elected_GE2023_En.xlsx` (12 KB), `/downloads/43GE Summary of Votes Received.xlsx` (44 KB) and poll-by-poll `/downloads/43GE.zip` (1.0 MB). Easy.

**MLAs.** https://www.gov.mb.ca/legislature/members/mla_list_constituency.html (28 KB HTML table: constituency | name | party, e.g. "Agassiz | BYRAM, Jodie | PC").

**Population.** 2018 commission final report https://www.boundariescommission.mb.ca/wp-content/uploads/edbc-final-report-2018-en.pdf (1.1 MB; the "names, populations and variations" web page is a JavaScript lookup, the table is in the PDF).

**Judgement.** Name plus town for everything outside Winnipeg (roughly 40% of payees), so rural recipients can often be placed to a district directly and Winnipeg ones need the usual name matching. Format is the cost: a 56-page two-column PDF where town is glued to the name with no delimiter; a parser needs a Manitoba place-name list to split it. Medium effort, best location information of the five.

## New Brunswick

**Payees.** Open data (Socrata) since FY2020, one pair of datasets per year, published in December with Public Accounts Volume 2. FY2025 (year ended 31 March 2025):
- by department: https://gnb.socrata.com/Public-Accounts/2025-Supplier-and-Grant-Payments-by-Department-Pai/s6c2-tumt — CSV https://gnb.socrata.com/api/views/s6c2-tumt/rows.csv?accessType=DOWNLOAD (text/csv, streamed, well under 1 MB; 6,197 rows)
- one row per payee across government: https://gnb.socrata.com/Public-Accounts/2025-Combined-Supplier-and-Grant-Payments-Paiement/edw7-9596
Fields: Department, Supplier Name, Payment, Payment Type. Payment Type values: "Payments & Grants" (6,109 rows, $8.54 B), Other Payments, Purchase Cards, Loan Disbursements — suppliers and grant recipients are not separated. Threshold: payees whose total exceeded $25,000; HST excluded; departments plus "some government organizations". No location, program or date. Earlier years: 2024 8dbf-suub / fiqg-25wy, 2022 wn4e-kwa9 / mgzd-ju37, 2021 3ctu-s8ip / eqn9-injj, 2020 pbau-pyvt; yearly index "stories" at https://gnb.socrata.com/stories/s/kntu-qzem (2025), wx36-5q5c (2024), v7mi-qgvc (2023). Publications index with Volume 2 PDFs: https://www.gnb.ca/en/org/finance-treasury-board/ftb-publications.html (e.g. 2025 Volume 2, PDF 1.9 MB).

**Boundaries (49, 2023 commission; used 2024).** Elections NB shapefile
https://www.electionsnb.ca/content/dam/enb/pdf/2023-ped-maps-cep-cartes/2024_Prov_PED_2026.zip (1.34 MB; Prov_PED_2024.shp dated Nov 2024), polls ProvPolls_SdV_2025_2026.zip, from https://www.electionsnb.ca/content/enb/en/maps/PED.html. Also Represent `new-brunswick-electoral-districts-2024`. GeoNB's Socrata copies stop at the 2020 map.

**2024 results.** https://www.electionsnb.ca/content/enb/en/resources/publications/election-results.html →
https://www.electionsnb.ca/content/dam/enb/xls/prov-2024-10-21/2024-10-21-Results-Resultats.zip (175 KB): two XLSX, results per poll (one sheet, all 49 districts, candidate columns "Name - Party") and per tabulator; CEO report PDF `.../pdf/october-21-2024-forty-first-provincial-general-election.pdf`; 2025-10-06 Miramichi West by-election zip alongside. (The www3.gnb.ca results app only serves current events; 2024 URLs there return 500.)

**MLAs.** https://www.legnb.ca/en/members/current (HTML: name, party, district).

**Population.** Commission amended final report https://www2.gnb.ca/content/dam/gnb/Corporate/Promo/electoral-electorales/amended-final-report.pdf (3.5 MB), from https://www2.gnb.ca/content/gnb/en/corporate/promo/boundaries-representation-commission.html.

**Judgement.** Name only, but the easiest format of the five: clean CSV, bilingual column names, stable yearly ids. Same name-matching job as BC, with the extra wrinkle that grants and purchases share one payment type so the "grant" subset has to be inferred from the department and the recipient type.

## Nova Scotia

**Payees.** Public Accounts Volume 3 "Supplementary Information": cash payments by department, itemised per payee at $5,000+ (salaries $25,000+, travel $3,500+). PDF only, e.g. FY2024 https://notices.novascotia.ca/files/public-accounts/2024/pa-supplementary-2024.pdf and FY2023 .../2023/pa-supplementary-information-2023.pdf. **Unverified from here**: notices.novascotia.ca rejects this machine's TLS handshake (curl, WebFetch, browser pane), so status, size and the FY2025/2026 filenames are unknown; the index https://www.novascotia.ca/public-accounts (200) points to the atom feed https://notices.novascotia.ca/feeds/public-accounts.atom on the same host. No open-data CSV. Program-level CSVs with named recipients on data.novascotia.ca (location not checked): Agriculture Funding Programs Details (jv92-pedy), Mineral Resources Development Fund grant recipients (iz26-kkmn), university/NSCC operating grants (jivi-kv67), 911 Municipal Grants (4hyt-4nhy), Emergency Services Provider Fund (m64k-6mnd).

**Boundaries (56 since April 2026; 55 in 2024).** Provincial map service, GeoJSON straight from it:
`https://nsgiwa.novascotia.ca/arcgis/rest/services/BND/BND_ElectoralBoundaries_UT83/MapServer/4/query?where=1%3D1&outFields=ED_NO,ED_NAME,electorcount,Release_Date&outSR=4326&f=geojson` (6.1 MB, 56 polygons; fields ED_NO, ED_NAME, electorcount, Release_Date — 54 dated 30 Oct 2019, Inverness and Chéticamp-Margarees-Pleasant Bay dated 9 Apr 2026). Layers 0–3 of the same service hold points, lines and polling divisions. Represent `nova-scotia-electoral-districts-2019` is the 55-district map the 2024 results belong to. Elections NS wall map ED2026ofNS.pdf (13 MB) and district lookup tool https://enstools.electionsnovascotia.ca/edinfo/.

**2024 results (26 Nov 2024).** Poll-by-poll workbook
https://electionsnovascotia.ca/files/GeneralElection_42nd/42PGE_PollbyPoll_AllEDs_TurnOut_FINAL.xlsx (221 KB; 55 sheets ED01–ED55, header cells "Name / Party", poll rows with polling location). Volume 1 Statement of Votes PDF Volume1_Statistics_May2025.pdf is 97 MB. The page https://electionsnovascotia.ca/GeneralElection_42nd is a JavaScript app (needs a browser) and carries the list of elected: PC 43, NDP 9, Liberal 2, Independent 1. By-elections: Pictou West 21 May 2024, Chéticamp-Margarees-Pleasant Bay 23 Jun 2026.

**MLAs.** https://nslegislature.ca/members/profiles is unreachable from this network (same TLS failure). Substitute: Elections NS "Distribution of seats by party, June 2026" map https://electionsnovascotia.ca/files/ElectoralDistrictMapInformation/DistributionOfSeatsByParty_2026_06.pdf (7 MB) plus the 2024 list of elected.

**Population.** 2019 commission site nselectoralboundaries.ca also unreachable (connection fails). The map service's `electorcount` gives registered electors for all 56 districts (e.g. Annapolis 16,018); no census population by district found.

**Judgement.** Name only, PDF, but a low threshold so small community groups appear. Harder than Saskatchewan's PDF because of volume (every $5,000 payment, hundreds of pages); worth trying a text-layer extraction before committing. Two hosts must be fetched from another network. Map the 2024 results onto the 55 map and only the Inverness/Chéticamp split needs special handling on the 56 map.

## Prince Edward Island

**Payees.** Not verifiable: every page on princeedwardisland.ca (Public Accounts topic page, Finance pages) 302s to validate.perfdrive.com with a Radware CAPTCHA that says this network is flagged; the Wayback Machine confirms a snapshot of https://www.princeedwardisland.ca/en/topic/public-accounts (31 Jan 2024) but rate-limited (429) before I could read it. Whether PEI's Public Accounts Volume II lists payees by name, and at what threshold, needs checking from another network or by the user in their own browser.

**Boundaries (27, 2017 commission; used 2019 and 2023).** GeoLinc ArcGIS REST (reachable):
https://geolinc.gov.pe.ca/server/rest/services/Provincial_Electoral_Districts_2017_ELC/MapServer/0 — 270 polling-division polygons with DIST_NO, DISTRICT, POLL_NO, POLL_NAME, electorcou; query supports GeoJSON (`/query?where=DIST_NO>0&outFields=*&outSR=4326&f=geojson`); dissolve on DIST_NO for the 27 districts (drop the blank DIST_NO 0 row; the service description text is mis-copied Nova Scotia metadata, the geometry is PEI). No Represent set for PEI. Elections PEI's own map downloads (electionspei.ca/district-maps) are blocked.

**Results (3 Apr 2023).** electionspei.ca blocked (the browser pane also hit the CAPTCHA; not attempted).

**MLAs.** https://www.assembly.pe.ca/members (200, JavaScript-rendered; read in the browser pane): 27 members with constituency and party — PC 18, Liberal 4, Green 4, Independent 1.

**Population.** Commission report lives on electionspei.ca (blocked). Registered electors per district can be summed from the GeoLinc layer with `groupByFieldsForStatistics=DIST_NO,DISTRICT&outStatistics=[sum electorcou]` (e.g. Alberton-Bloomfield 4,496); its censuspopu field is all zeros.

**Judgement.** Unknown until the payee source is seen; boundaries and member list are in hand. Expect PDF, name only, as in the other Atlantic provinces.

## Newfoundland and Labrador

**Payees.** None. Treasury Board Secretariat's Public Accounts page https://www.gov.nl.ca/exec/tbs/home/publications/public-accounts/ (updated 16 Oct 2026 with 2025-26) holds only Consolidated Summary Financial Statements, Cash Statements, the Report on the Program Expenditures and Revenues of the Consolidated Revenue Fund (program level, e.g. .../files/Report-on-the-Program-Expenditures-and-Revenues-of-the-CRF-WEB.pdf, 4.2 MB) and Crown corporation statements (the 2015 "A–M / N–Z" files, 33 and 82 MB, are those, not payee lists). opendata.gov.nl.ca has no payee or grant dataset. NL recipients can only come from federal data or individual program announcements.

**Boundaries (40, 2015 commission; used 2015–2025).** Open data shapefile "Provincial Electoral Districts (2015)" https://opendata.gov.nl.ca/public/opendata/filedownload/?file-id=3323 (polygons, 15.5 MB; lines file-id=2243, 87 KB; catalogue page page-id=datasetdetails&id=361). Also Elections NL's results layer with geometry: https://services8.arcgis.com/aCyQID5qQcyrJMm2/arcgis/rest/services/2025_Provincial_Electoral_Districts_view/FeatureServer/0 (GeoJSON query returns 40 polygons, 30 MB, with id, dist_name, LeadingCandidate, LeadingParty). Represent `newfoundland-and-labrador-electoral-districts` (2015 map). Polling divisions: https://www.elections.gov.nl.ca/files/NL-Polls-2019.zip (2.9 MB). Boundary commission site https://www.nledbc.ca/ is the archived 2015 commission; no new commission yet.

**2025 results (14 Oct 2025).** Feature services behind the official dashboard (https://gnl.maps.arcgis.com/apps/dashboards/db575c86709a40cea5a22592040d16bf), same host as above: `2025_NL_Provincial_Election_Votes_by_Candidate_view/FeatureServer/0` (129 rows: districtid, districtname, candidatename, party, partyname, votes, votepercentage, leadingcandidate) and `2025_NL_Provincial_Election_Polls_By_District_view/FeatureServer/0` (1,665 poll rows, one column per party). Export with `/query?where=1%3D1&outFields=*&f=json`. Official report PDF https://www.elections.gov.nl.ca/files/2025-General-Election-Report.pdf (20 MB); page https://www.elections.gov.nl.ca/2025-general-election-official-results/.

**MHAs.** https://www.assembly.nl.ca/Members/members.aspx (200; JavaScript-rendered table Name | District | Party; standings PC 20, Liberal 15, NDP 2, Independent 3).

**Population.** 2015 commission appendices at https://www.nledbc.ca/reports: Appendix 4 "2011 Census" https://www.nledbc.ca/final/Appendix4.pdf (307 KB) and Appendix 1 summary. Dated (2011 census).

**Judgement.** Nothing to locate: no provincial payee disclosure exists, so NL stays a federal-only layer unless program-specific lists are scraped. Everything else (boundaries, results, members) is excellent and machine-readable.

## Ontario and Quebec, briefly

- **Ontario**: data.ontario.ca "Public Accounts: Detailed Schedule of Payments" (formerly Volume 3), one CSV per year, 2025-26 English file https://data.ontario.ca/dataset/56c9a95f-c7b6-40ee-a4b8-d2343e51c83d/resource/3ab37bb7-4f51-4d90-951b-b9d566f65898/download/tbs-public-accounts-detailed-schedule-payments-2025-26-en.csv (2.0 MB; columns Amount, Ministry, Category, Payment Detail, Recipient, Statutory, Additional Detail; vendors and transfer-payment recipients above the usual thresholds; no location). Represent `ontario-electoral-districts-representation-act-2015`.
- **Quebec**: Données Québec "Comptes publics – Volume 2" CSVs exist but the "Dépenses de transfert du fonds général par bénéficiaires 2024-2025" file is only 8.6 KB and is aggregated by beneficiary *category* (Portefeuille; Bénéficiaire; Montant), not named recipients; named grants are only in the Volume 2 PDF. Represent `quebec-electoral-districts-2017`.

## Summary

| Province | Best grants source | Format | Location field | Verdict |
|---|---|---|---|---|
| Manitoba | Vendor Payments over $50,000, per department, yearly since 2019-20 | PDF, ~0.7 MB/yr | town appended to name (blank = Winnipeg) | name + town; PDF parsing needed, but the only province with a usable location |
| New Brunswick | Supplier and Grant Payments by Department (Socrata), payees over $25,000, yearly since 2020 | CSV, <1 MB/yr | none | name only; easiest format; grants mixed with suppliers |
| Nova Scotia | Public Accounts Vol. 3 Supplementary Information, payments $5,000+ by department | PDF (host unreachable from this network; size unknown) | none | name only; large PDF; fetch from another network |
| PEI | Public Accounts (presumed Vol. II), unverified | unknown (sites blocked by Radware CAPTCHA) | unknown | cannot judge; boundaries (GeoLinc) and MLAs in hand |
| Newfoundland and Labrador | none exists (program-level reports only) | — | — | not mappable from provincial data; boundaries/results/MHAs all open and machine-readable |

Scratch downloads (boundary zips, GeoJSON, workbooks, PDFs) are under /private/tmp/claude-501/-Users-hmac-Documents-claude-io/da6d2708-833f-4d6d-97b0-1cd182bb4db6/scratchpad/dl/ if the parent wants to inspect them; nothing was written into the project.
