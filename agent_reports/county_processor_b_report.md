# County Processor B — Kings & Lake Counties Report

Session date: 2026-08-08

## 1. Kings County — recorder BLOCKED (not by CAPTCHA — the feature doesn't exist online)

**Assessor**: `common1.mptsweb.com/mbap/kings/asr/` — CONFIRMED LIVE. Tested with a real
APN (024-270-019-000, sourced from a real, closed 2017 Bid4Assets Kings auction listing).
Returns real data (doc #2019R1810322, land value $5,801, etc.) but this MPTS install has
**no owner/assessee name field at all** in the property table.

**Recorder**: Tested `kingscountyca-web.tylerhost.net` past the disclaimer page.
- Disclaimer: GET + POST both return HTTP 200, `disclaimerAccepted` cookie set cleanly.
  **No CAPTCHA of any kind** — this is not a Fresno/Tehama-style wall.
- But the entire self-service menu (`POST /web/homeActions` and every action group:
  ACTIONGROUP201S1/S2/S3/S5, ACTIONGROUP483S1, wizard/COPYREQUEST400S1, fraudGuard) exposes
  **only Clerk-office record types**: Vital Records, Marriage License, Fictitious Business
  Names, Professional Registrations, CEQA/Notary/Registration search, DD-214 military
  discharge copies, and Owner/Fraud Alert. There is **no "Official Records" / real-property
  deed search** anywhere in the menu tree.
- Corroborated by web search: Kings County's own published guidance cites CA Assembly
  Bill 1785 — online access to the recorder index/APN-linked search is no longer offered;
  document access is in-person or by mail only. The county's legacy portal
  (`publicrecords.countyofkings.com`) is unreachable (connection timeout).

**Auction list**: Could not locate a real, current, open 2026 Bid4Assets storefront or
county-published defaulted-parcel list this session. Every Bid4Assets URL/slug checked
(`bid4assets.com/kings`, `KingsMar17`, `KingsCAMar22`, auction #739080, #937469) resolved
to stale historical content (a real closed 2017 sale, a real closed March-2022 sale) or an
empty/broken page — never a live 2026 listing. A real "Notice of Impending Power to Sell"
legal notice exists (Hanford Sentinel, parcels becoming sellable 7/1/2026) but both that
notice page and the delinquency notice page are now HTTP 410 (removed), and no
corresponding Bid4Assets storefront was found.

**Outcome**: 0 dossiers. Logged to the exception CSV as `blocked` (Kings recorder has no
online real-property document search of any kind, confirmed by direct testing of the full
menu, not assumption). Kings would need an in-person/mail workflow outside this pipeline's
automation model, or a paid third-party title source. Moved to Lake.

## 2. Lake County — recorder FULLY WORKING (RECORDER_FULL), 16 real dossiers generated

**Assessor**: `common1.mptsweb.com/mbap/lake/asr/` — CONFIRMED LIVE, tested against dozens
of real APNs. Same as Kings: no owner/assessee field.

**Recorder**: `lakecountyca-web.tylerhost.net` — **CONFIRMED FULLY WORKING, no CAPTCHA**.
Past the disclaimer, the menu includes a genuine **"Official Records Search - Web"**
(`DOCSEARCH4S3`) supporting `field_ParcelID` (APN, real parcel-tied search — not name-only)
plus `field_DocumentNumberID`, `field_GrantorID`/`field_GranteeID`, and a recording-date
range. Confirmed live with real results (doc type, date, grantor, grantee) parsed
correctly from dozens of real searches.

**Auction list**: Real, official Lake County Tax Collector list — **TDLS164**
(`lakecountyca.gov/DocumentCenter/View/15507`), 311 unique non-"REDEEMED" parcels extracted.
Critical finding: **this sale already concluded (March 20–31, 2026)**, ~4.5 months before
this session. Naively treating the list as still-open would have been wrong for the large
majority of parcels, so every candidate was individually re-verified via a real recorder
document-lifecycle check (`TAX DEFAULT PROPERTY LIEN` → `RELEASE OF LIEN` = redeemed;
→ `DEED TAX` = sold at auction; lien with neither = still genuinely defaulted).

Result across all 311 parcels: **178 sold, 111 redeemed, 17 still tax-defaulted with no
release or sale-deed found, 5 with no recorder activity in the window checked.** One of
the 17 (`032-042-330-000`) was held back — its assessor record shows a brand-new 2026-dated
document that doesn't appear anywhere in the recorder's own index for that parcel (an
unresolved discrepancy, logged, not shipped).

**16 real, both-sites-verified dossiers generated** at
`output/dashboard/lake_<apn>_prop_intel_dossier.md`:
005-012-300-000, 006-462-150-000, 031-113-560-000, 034-552-380-000, 034-866-170-000,
035-152-600-000, 035-385-180-000, 035-385-370-000, 038-234-400-000, 039-392-570-000,
040-330-280-000, 041-351-320-000, 050-192-020-000, 141-451-110-000, 142-035-060-000,
142-272-060-000.

Each dossier's owner is the recorder-confirmed grantor on that parcel's specific,
still-unreleased Tax Default Property Lien document (parcel-tied, not name-only); assessed
value/situs/vesting-document-date from the live assessor. `signal_priority.py` was left
untouched — Lake correctly falls through to its existing shared `NO_SCHEDULED_AUCTION`
signal since no TDLS165 has been published yet.

Source list: https://www.lakecountyca.gov/DocumentCenter/View/15507/BOS-SUBMITTED-LIST-OF-PARCELS-TDLS-164---March-20-2026

## 3. Exceptions logged

Three rows in `agent_reports/county_processor_b_exception_log_additions.csv`: Kings
recorder blocker (severity high), the Lake `032-042-330-000` discrepancy (needs_review),
and the Lake TDLS164-already-concluded finding (resolved_documented, explains the
methodology).

## 4. Matrix updates

`agent_reports/county_processor_b_matrix_updates.csv` — full rows for Kings and Lake in
the exact 31-column format, Recorder/Index Availability and Status columns reflect real
findings (Kings: Red/blocked; Lake: Green/fully working).

## Raw evidence

All saved under `kings/` and `lake/` at repo root (disclaimer pages, every action-group
page, MPTS samples, TDLS164 PDF + extracted text, full 311-parcel recorder classification
JSON, per-parcel assessor data, Bid4Assets pages).
