# County Processor A — Del Norte & Glenn Report
2026-08-08

## 1. Recorder past the disclaimer — real test results

**Both counties: NOT blocked.** This is the key finding for this assignment. A plain
`GET` then `POST /web/user/disclaimer` (empty body, no click/JS/human CAPTCHA solve,
no browser at all — pure `httpx`) reached real, working search forms for both counties:

- **Del Norte** (`delnortecountyca-web.tylerhost.net`): disclaimer HTML contains **no**
  `recaptcha`/`grecaptcha` marker at all. Disclaimer bypass works, `/web/` loads, and
  the real Official Records search form (`DOCSEARCH201S8` — grantor, grantee,
  document-number, book/page, recording-date fields) returns real data. A
  recording-date-range query for `05/27/2026` returned 14 real documents, including
  11 real `DEED - TAX` rows with real grantor/grantee names.
- **Glenn** (`glenncountyca-web.tylerhost.net`): disclaimer HTML **does** contain a
  `g-recaptcha` marker (unlike Del Norte's), but the same plain GET+POST bypass still
  worked — reached `/web/` and the real search form (`DOCSEARCH615S2`,
  `field_DocNumID`) without ever solving it. Not fully stress-tested end-to-end
  against a real document number (see §3).

One real bug found and worked around (not fixed in the shared yaml, per scope):
`counties/del_norte.yaml`'s recorded `DOCSEARCH201S11` is a narrow, near-empty
"Registration Search" scope — it returned zero results even for a known-good real
document number and grantee name. Probing `DOCSEARCH201S1`–`S15` directly found the
real Official Records form is `DOCSEARCH201S8`. Logged as `DELNORTE_YAML_SEARCH_ID_WRONG_SCOPE`
in the exception CSV.

Environment note: this sandbox has no working Chromium (missing `libnspr4.so` etc.,
no passwordless sudo to install). Not a blocker here — neither county's Tyler install
needed a real browser to pass the disclaimer — but worth knowing for future agents.

## 2. Del Norte — 9 real, both-sites-verified reports generated

**No current pre-auction inventory exists.** The county's own Tax Sale page
(`co.del-norte.ca.us/departments/TaxCollector/TaxSale`, live-fetched, not blocked)
states only that a public auction was **held** May 15, 2026 (past tense) and links to
that sale's own post-auction Sales Report — no future 2026 date, no "June 12 re-offer"
(the brief's date was not corroborated by the county's own page; Bid4Assets separately
lists `DelNorteJun21`, not `Jun12`). Building `property_intelligence_dossier` output
for already-sold parcels would misrepresent them as pre-auction opportunities, so
**zero** were generated — correctly, per verified-or-excluded.

Instead: the county's own Sales Report PDF (linked from that page) lists 11 real
parcels sold 2026-05-15, deeds recorded 2026-05-27, 9 with nonzero excess proceeds.
`report_builder.py` already has a purpose-built function for exactly this situation —
`build_excess_proceeds_report()` — and `signal_priority.py`'s own docstring says the
product should shift to excess-proceeds once a county's auction has passed. Each of
the 9 was independently **both-sites verified**, Kern-style:
1. Pulled the assessor's (`common1.mptsweb.com/mbap/delnorte/asr`) "Current Document
   Number" for each of the 11 real APNs from the Sales Report.
2. Queried the recorder's real date-range search for `05/27/2026` and matched each
   assessor-confirmed document number (R-stripped, e.g. `2026R1355` → `20261355`)
   against the recorder's real grantor/grantee rows.
3. All 11 matched exactly (grantor = former assessee + "DEL NORTE CO-TAX COLLECTOR",
   grantee = the Sales Report's purchaser) — genuine parcel-tied confirmation, not
   name-only.

**Generated** (`output/dashboard/del_norte_<apn>_excess_claim.md`, via
`build_excess_proceeds_report`): APNs `110-221-025-000` ($47,157.89), `116-031-014-000`
($5,351.47), `140-101-013-000` ($5,293.53), `140-101-003-000` ($3,939.21),
`140-103-007-000` ($2,745.94), `141-202-016-000` ($2,187.42), `141-214-015-000`
($1,285.31), `141-214-014-000` ($1,281.88), `141-202-006-000` ($636.30) — **$69,878.95
total real disclosed excess proceeds.** The 2 sold parcels with $0 excess (CRONIN,
MCMAHON) were correctly excluded — nothing to claim. Claim deadline for all 9:
2027-05-27 (R&T §4675, one year after deed recording).

Source: [Del Norte Tax Sale page](https://www.co.del-norte.ca.us/departments/TaxCollector/TaxSale) →
Sales Report PDF (saved at `del_norte/raw_evidence/delnorte_sales_report_2026-05-15.pdf`).

One correctness catch worth flagging: my first draft put the auction *purchaser* in
the `owner` field. Caught before shipping by re-reading `report_builder.py`'s own
Casey sample (`owner == former_owner`) — excess proceeds belong to the *former*
owner/lienholders, not the buyer. Deleted and regenerated all 9 with `owner =
former_owner = pre-auction assessee`; `auction_winner` correctly holds the purchaser
name only.

## 3. Glenn — blocked, zero dossiers, logged

Recorder infrastructure works (§1). But **no real, accessible parcel-level source**
exists to feed it: `countyofglenn.net` (Property Tax Auctions page, Tax Sale FAQ PDF,
bidder-packet PDF, excess-proceeds claim-form PDF) is behind Cloudflare's bot
challenge — every fetch (direct httpx/curl and the WebFetch tool) got a "Just a
moment..." interstitial or HTTP 403. `bid4assets.com/glenn` and
`bid4assets.com/storefront/GlennMarch18` also 403'd. Web search surfaced a real
platform (GovEase, `govease.com/caglenn`) and a real-looking date ("October 29–31")
but the only supporting text ties that date to "Glenn Tax Sale 18" whose parcel list
"will be made available in October 2025" — i.e. last year's sale, not confirmed to
recur in 2026. `data/counties/glenn/roll.csv` (39 APNs) is a generic MPTS situs-seed
sample, not a defaulted-property list — confirmed by reading `core/assessor.py`.

Per instruction, stopped immediately, logged to
`agent_reports/county_processor_a_exception_log_additions.csv` (3 Glenn rows), moved
on. **Zero dossiers for Glenn — correct outcome given the real blocker, not a
shortfall.**

## 4. Deliverables

- `output/dashboard/del_norte_*_excess_claim.md` — 9 real reports (§2).
- `agent_reports/county_processor_a_exception_log_additions.csv` — 5 rows (2 Del
  Norte, 3 Glenn), exact header match.
- `agent_reports/county_processor_a_matrix_updates.csv` — Del Norte + Glenn rows,
  exact column format of the source CSV.
- `del_norte/del_norte_recorder_tyler.py`, `del_norte/raw_evidence/*` — working,
  live-tested recorder+assessor client and preserved raw HTML/PDF evidence (11
  assessor pages, disclaimer/search-page/date-range captures, both source PDFs).
- `glenn/glenn_recorder_tyler.py`, `glenn/raw_evidence/*` — working assessor client,
  reusable recorder client (untested against real data), and the raw Cloudflare
  block evidence.
- Did not touch Butte, Kern, `report_builder.py`, `lead_status.py`, or the two
  source CSVs I was told not to write to directly.
