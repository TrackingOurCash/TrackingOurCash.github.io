# PEI results: sources for data/pe_results.json

Built 2026-10-26. Election: 3 April 2023 (67th General Assembly). Current MLAs as of 26 October 2026.

## What loaded and what did not

- `princeedwardisland.ca` and `electionspei.ca` inner pages are behind Radware; curl, the browser pane and WebFetch all land on `validate.perfdrive.com`. Only the electionspei.ca home page got through WebFetch once (probably a cache). The site was NOT used directly.
- The official material was instead taken from the **Wayback Machine** (web.archive.org, not behind Radware):
  - **Report of the Chief Electoral Officer, Provincial General Election April 3, 2023** (PDF, 106 pp.) - `https://web.archive.org/web/2025/https://www.electionspei.ca/sites/www.electionspei.ca/files/2023%20PGE_CEO_Report_FINAL.pdf`. Per-district "District Analysis" pages (pp. 26-78): poll-by-poll votes per candidate, TOTALS row (ballots cast, votes, rejected ballots) and the "Registered Electors / Used a VIC / Total Voted" chart.
  - **2023 Province-Wide Summary** ("2023 Provincial General Election Official Results", party votes by district) - `https://web.archive.org/web/20230419165220/https://www.electionspei.ca/2023-province-wide-summary`.
  - **results.electionspei.ca/districtN.html** (N = 1..27; candidate names, party, votes, poll-by-poll; snapshot June 2023) - `https://web.archive.org/web/2023/https://results.electionspei.ca/district1.html` etc.
- **assembly.pe.ca/members** (live, loads fine) - current member list with party, used to verify the MLA column.
- **Wikipedia** (raw wikitext via the API): `2023 Prince Edward Island general election` (candidate table and "Synopsis of results" with turnout), the 27 `Template:2023 Prince Edward Island general election/<district>` templates (candidate names in mixed case), the 27 district articles (by-election boxes), `67th General Assembly of Prince Edward Island`, `Legislative Assembly of Prince Edward Island`, `Gilles Arsenault`.
- SaltWire (cited by Wikipedia for turnout) does not load.

## Where each field comes from

| field | source | cross-check |
|---|---|---|
| `candidates[].name` | Wikipedia per-district template (mixed case); accents/casing corrected to the CEO report / election-page form for Ahava Kálnássy de Kálnás, Kristi MacKay, Nick LeClair | surname and party checked against the archived results.electionspei.ca district page (upper case) |
| `candidates[].party`, `candidates[].votes` | Wikipedia template | every figure matches the archived results.electionspei.ca district page AND the CEO report TOTALS row (one exception, D4, below). Party totals across the 27 districts reproduce the official province-wide totals exactly: PC 41,828; Green 16,134; Liberal 12,876; NDP 3,359; Island 411; Independent 184 |
| `valid_votes` | sum of candidate votes | equals the Wikipedia template "Total valid votes" except D7 (template says 2,698, typo) and D18 (template says 3,408, typo); equals the Wikipedia synopsis "Total" column for all 27 |
| `registered` | CEO report, per-district "Registered Electors" bar (26 districts) | D23 derived, see below |
| `turnout_pct` | CEO report ballots cast (TOTALS row) / registered x 100, rounded to 0.1 | within 0.35 pp of the Wikipedia synopsis turnout column for every district (Wikipedia tends to be 0.1-0.2 lower; its source for the column is a SaltWire article) |
| `mla` | assembly.pe.ca member list == Wikipedia 67th GA == Wikipedia LA page (identical rosters) | by-election dates/votes from the Wikipedia district articles and by-election templates; Arsenault details from the Wikipedia article (citing CBC, 28-30 Mar, 8 Apr, 25 May 2026) |

Party codes: PC, LIB, GRN, NDP, IND, plus **ISL = Island Party of Prince Edward Island** (ran 11 candidates in 2023, 411 votes province-wide).

Name forms: MLA and candidate names follow common usage (Wikipedia): "Matt MacFarlane" (ballot and assembly.pe.ca: Matthew MacFarlane), "Gord McNeilly" (assembly.pe.ca: Gordon McNeilly), "Jill Burridge" (assembly.pe.ca: Jill (Cheverie) Burridge), "Herb Dickieson" (ballot: Dr. Herb Dickieson), "Lana Beth Barkhouse" (ballot: Dr. Lana Beth Barkhouse), "Olalekan Faromika" (ballot: Olalekan (Lekan) Faromika), "Angela Reine Barton".

## Discrepancies found and how they were resolved

1. **D4 Belfast-Murray River, Green (Laverne MacInnis):** CEO report TOTALS row says 419; the official Province-Wide Summary, the results.electionspei.ca district page and the Wikipedia template all say **420**. 420 is used: it is the only value that reproduces the official Green province total of 16,134 and the district total of 2,574. (The Wikipedia synopsis table copies the 419.)
2. **D23 Tyne Valley-Sherbrooke, registered electors:** the CEO report's VIC chart for District 23 is a copy of District 22's (4,488 / 2,065 / 2,598; its "Total Voted" 2,598 does not match D23's own 2,602 ballots cast). No official per-district figure is available. `registered` = **4,023 is DERIVED**: CEO province total 109,587 minus the 26 trusted district figures (105,564). Implied turnout 64.7% agrees with Wikipedia's 64.9%. Treat as approximate (the CEO per-district ballot counts themselves sum to 75,189 against the report's province total of 75,057, so the derivation carries roughly +/-0.3% slack). Set to null if a sourced value is required.
3. **CEO report arithmetic slips** (ballots cast - rejected != valid votes by 1-16 ballots) in D3, D4, D5, D7. Candidate votes are unaffected (they match the website). Turnout uses the report's own "ballots cast" figure, so these districts' turnout may be off by at most 0.4 pp.
4. **Wikipedia-only figures:** none of the vote counts are Wikipedia-only (all are confirmed by two official sources). Wikipedia-only items are: the candidate name spellings in mixed case (official pages are upper case), by-election vote counts and percentages quoted in the `mla.note` strings (templates cite Elections PEI, which could not be reached), and the dates in the notes (Wikipedia citing CBC).

## Current standings check (vs the project's legislature record)

Roster as of 2026-10-26: **PC 18, Liberal 4, Green 4, Independent 1, no vacancy** - matches the existing record. Premier Rob Lantz (PC, Charlottetown-Brighton; premier 21 Feb-12 Dec 2025 as interim, Bloyce Thompson interim 12 Dec 2025-9 Feb 2026, Lantz again from 9 Feb 2026); Opposition leader Hal Perry (Liberal, Tignish-Palmer Road, since 12 Apr 2023); Green leader Matt MacFarlane (Borden-Kinkora, elected leader 7 Jun 2025) - all match. Speaker: Brad Trivers (PC, Rustico-Emerald) since 25 Mar 2026.

Changes since 3 April 2023 (election night: PC 22, Green 2, Liberal 3):

| date | district | change |
|---|---|---|
| 2023-11-11 | 19 Borden-Kinkora | Jamie Fox (PC) resigned to run federally |
| 2024-02-07 | 19 Borden-Kinkora | by-election: Matt MacFarlane (GRN) 1,226 (49.0%) - Green gain |
| 2025-02-11 | 9 Charlottetown-Hillsborough Park | Natalie Jameson (PC) resigned to run federally |
| 2025-02-21 | 15 Brackley-Hunter River | Dennis King (PC, premier) resigned |
| 2025-08-12 | 9 | by-election: Carolyn Simpson (LIB) 979 (47.8%) - Liberal gain |
| 2025-08-12 | 15 | by-election: Kent Dollar (PC) 1,140 (50.3%) - PC hold |
| 2025-10-03 | 2 Georgetown-Pownal | Steven Myers (PC) resigned |
| 2025-12-08 | 2 | by-election: Brendan Curran (PC) 986 (46.8%) - PC hold |
| 2026-03-17 | 16 Cornwall-Meadowbank | Mark McLane (PC) died in office |
| 2026-03-29 | 24 Evangeline-Miscouche | Gilles Arsenault dismissed from cabinet (28 Mar) and suspended from PC caucus (29 Mar); sits as Independent; on formal leave of absence since 22 May 2026 (RCMP investigation) |
| 2026-07-13 | 16 | by-election: Tayte Willows (GRN) 1,184 (39.7%) - Green gain |
