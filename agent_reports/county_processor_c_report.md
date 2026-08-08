# COUNTY_PROCESSOR_C Report — Riverside & San Diego (2026-08-08)

**Scope note:** Original assignment was Riverside + San Joaquin. Mid-session the coordinator
redirected scope to Riverside + San Diego (San Joaquin reassigned elsewhere) and specified a
recorder-capability probe protocol before any full build-out. This report reflects the redirected
scope. No San Joaquin work was performed beyond reading the existing matrix row and yaml (no
artifacts touched, nothing to undo).

**Bottom line: zero dossiers produced for either county. Both are honest, well-evidenced stops,
not failures of effort.** Riverside has the most promising *technical* infrastructure of the two
(and arguably one of the cleanest found in the matrix — live, real, CAPTCHA-free assessor and
recorder) but is blocked by a real backend data gap. San Diego is blocked by a combination of a
permanent legal restriction, an edge-blocked recorder, and a closed auction cycle.

All raw artifacts are preserved under `riverside/raw/` and `san_diego/raw/` (hashes in
`riverside/raw/SHA256SUMS.txt`). Full findings are also in
`agent_reports/county_processor_c_exception_log_additions.csv` (6 rows) and
`agent_reports/county_processor_c_matrix_updates.csv` (2 rows, exact 31-column format).

## Riverside

**Assessor — CONFIRMED LIVE.** Real ArcGIS REST service at
`gis.countyofriverside.us/arcgis_mapping/rest/services/OpenData/Assessor/MapServer` (found via the
county's own DCAT open-data feed, not guessed). Four layers live and queried directly: PARCELS
(869,058 features), PARCELS_CREST (situs, mail address, acreage, class code, LAND/STRUCTURES
value), CREST_GENERAL, CREST_TAXYEAR. Cross-verified against 3 of 5 real APNs pulled from the
actual April 2026 auction list — situs address and land value matched exactly across two
independent tables for the same APN (e.g. APN 102083027: 1037 Serfas Club Dr, Corona, LAND
$174,084, matching both the auction PDF and two separate ArcGIS layers). This replaces
`counties/riverside.yaml`'s guessed endpoint, which is wrong/untested.

**The blocker:** none of the live layers expose an owner name or a per-parcel current recorded
document number. The one service that would (`OpenData/AssessorTables`, explicitly described by
the county as carrying "assessee ... recorded book" data) returns a real, reproducible
`HTTP 400 "Failure to access the DBMS server"` — tested twice, ~5s apart, on both hosting paths.
This is a live outage, not a permanent legal block.

**Recorder — CONFIRMED LIVE, REAL, NO CAPTCHA.** Tyler Self-Service at
`webselfservice.rivcoacr.org/Web/` (found by tracing real links from rivcoacr.org, after an
initial web-search-suggested domain, `webselfservice.riversideacr.com`, turned out to be dead —
DNS failure, a bad third-party citation, not a real county domain). Five real search modes
confirmed by fetching the actual pages: Name, **Document Number** (format `YYYY-NNNNNN`,
mechanically identical to Kern's proven `Osearchn.mbr` method), Document Type, Book/Page/Map,
Advanced. No CAPTCHA on any of them. No APN field on any of them either — so even though the
mechanism is Kern-shaped, there's no live source to feed it a parcel-specific doc number right now
because of the AssessorTables outage above.

**Auction list — CONFIRMED REAL, downloaded, hashed.** 946 parcels, April 23–28 2026, Bid4Assets
(storefront/RiversideCountyApr26). Real source:
`countytreasurer.org/sites/g/files/aldnop296/files/2026-01/Parcel List.xlsx` (+ matching PDF),
found via targeted web search after the county's own tc-223 page 403'd behind Cloudflare Turnstile
(not bypassed, per instruction). SHA256 hashes in `riverside/raw/SHA256SUMS.txt`.

**Verdict: STOP.** Both sides are real and live — better than most of the matrix — but the
specific link needed for both-sites verification is unavailable today. Logged as
`RIVERSIDE_ASSESSORTABLES_DBMS_DOWN` (high), `RIVERSIDE_RECORDER_NO_APN_FIELD` (medium),
`RIVERSIDE_YAML_ENDPOINT_WRONG` (medium, scaffolding correction only).

## San Diego

**Assessor — CONFIRMED LIVE**, real endpoint `sdarcc.gov/bin/cosd/parcel-request?parcelNumber={apn}`
(reverse-engineered from the site's own `parcelSearch` client JS after the yaml's guessed Socrata
URL, `data.sandiegocounty.gov/resource/parcels.json`, was confirmed a dead 404 — the county's real
Socrata portal exists and is live but has no parcel dataset among its 610 catalog entries). Real
fields identified: situs components, Land_Value, Improvements_Value, Fixtures_value,
Personal_property_value, Total_assessed_value, Net_taxable_value.

**Legal blocker (permanent):** the search page itself states "property ownership information
cannot be provided on the internet in accordance with California Government Code section
6254.21" — the same statute already documented in the matrix as Fresno's confirmed-permanent
owner-lookup block. No owner/assessee field exists anywhere in the client code either.

**Recorder — BLOCKED.** `arcc-acclaim.sdcounty.ca.gov` returns `HTTP 403 Access Denied` from an
Akamai edge (server-level deny, reproducible), not a CAPTCHA challenge page. Per the coordinator's
explicit instruction, no bypass was attempted (no stealth browser, no header spoofing, no proxy).
Recorder search-mode capability (name vs. document-number vs. APN) could not be determined.

**Auction — CLOSED, no active cycle.** The matrix's "686 properties, $18.2M" reference is the
March 13–18 2026 sale, which ended roughly 5 months before this probe. Web search confirms the
`sdttc.mytaxsale.com` platform's own messaging: next auction "to be announced in 2027." No live
parcel list exists to source candidates from right now, independent of the two blockers above.

**Verdict: STOP**, on three independent grounds. Logged as
`SANDIEGO_OWNER_LOOKUP_GOV_CODE_6254_21` (high), `SANDIEGO_ARCC_ACCLAIM_AKAMAI_BLOCKED` (high),
`SANDIEGO_NO_ACTIVE_AUCTION_CYCLE` (high).

## Files delivered
- `agent_reports/county_processor_c_report.md` (this file)
- `agent_reports/county_processor_c_exception_log_additions.csv` (6 rows, validated column count)
- `agent_reports/county_processor_c_matrix_updates.csv` (2 rows, exact 31-column header match)
- `riverside/raw/` — real auction xlsx+PDF, Terms of Sale PDF, live-probe JSON, SHA256SUMS.txt
- `san_diego/raw/` — 4 real HTML captures (search page, press release, tax-sales page, Akamai 403
  response) + live-probe JSON

No files under `report_builder.py`, `lead_status.py`, `county-name-assessor-data-access-58.csv`,
`county-signal-exception-log.csv`, or any Butte/Kern/San Joaquin excess-proceeds path were
modified.
