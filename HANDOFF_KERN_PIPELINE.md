# Handoff: Kern County Delinquency Intelligence Pipeline

**Owner:** Chuck Terrell / Logic Flow Systems
**Contact:** mrt@logicflowsystems.io
**Date started:** 2026-07-29

## Objective

Build a Kern County delinquent-parcel intelligence catalog, filterable by delinquency length (2yr, 3yr, 4yr, 5+yr), that feeds the Logic Flow Systems parcel marketplace. Model is **cheap catalog + on-demand deep dossier enrichment when a buyer pays**.

## Business context

- Chuck sells $299 per-parcel dossiers on a marketplace (currently Butte only, 104 dossiers ready)
- Cash deadline: 14 days from 2026-07-29
- Butte pipeline is the reference implementation; Kern is expansion #1
- Do NOT bulk-enrich all parcels. Enrichment ONLY runs when a buyer orders a specific parcel.

## Architecture

**Two-tier system:**
1. **Lightweight catalog** (all delinquent Kern parcels): APN, owner, situs, defaulted balance, years delinquent, category tag. Cheap fields only.
2. **Deep dossier** (per order): full recorder crawl + tax bill + environmental + aerial. Runs on-demand when a $299 purchase fires.

**Categories to bucket parcels into (based on years delinquent):**

| Category | Years | Buyer type |
|---|---|---|
| A — Fresh Distress | 2-3 | D2S wholesalers |
| B — Pre-Auction Warning | 4 | Pre-auction acquirers |
| C — Power to Sell | 5+ (not on block) | Note buyers, land bankers |
| D — Next Auction Block | 5+ (on published Notice of Sale) | Auction bidders |

## Data sources to find (Task 1: endpoint recon, ~4 hours)

1. **Kern County Assessor GIS** — public ArcGIS FeatureServer for parcel base (situs, owner, APN)
2. **Kern County Treasurer-Tax Collector** — kcttc.co.kern.ca.us — per-APN tax status + years delinquent
3. **Kern County Recorder** — public doc search (deeds, NODs, liens) for distress signals
4. **Kern's published PDFs** to grab:
   - **Notice of Impending Default** (annual, June-July publication — CA R&TC §3351)
   - **Notice of Power to Sell** (5+ year delinquent parcels)
5. **GovEase** — only for the Sept 14-16 auction subset (Category D)

## Existing code to reuse (in `C:\Users\chuck\Downloads\county_pipeline\`)

- `butte/build_dossiers.py` — dossier PDF generator (reuse; make county-agnostic)
- `butte/enrich_tax_bills.py` — MPTS pattern; adapt for Kern KCTTC
- `butte/enrich_environmental.py` — FEMA + CalFire (county-agnostic already)
- `butte/fetch_parcel_images.py` — Esri satellite (county-agnostic)
- `butte/package_delivery.py` — orchestration pattern
- `verification/*` — verification substrate (schema, writer, scoring)
- `tax_pipeline/recorder_config.py` — recorder platform registry

## First deliverable

**Endpoint recon report** — 1-2 pages covering:
- URL + auth needed for each of the 3 endpoints
- Sample JSON/HTML response from each
- Pagination + rate-limit observations
- Field mapping: what Kern field = what Butte field
- Sample pull: 20 delinquent APNs through lightweight extract to prove it works
- Time estimate to build the full pipeline

## Second deliverable

Once endpoints are validated:
- Kern lightweight catalog CSV (all delinquent parcels, bucketed A/B/C/D)
- Marketplace tiles (HTML) — one per parcel, mailto: order button at $299
- Documented CLI: `python run_county.py --county kern --stage catalog`

## Do NOT

- Do NOT bulk-enrich every parcel (waste of compute; not the business model)
- Do NOT scrape aggressively (rate limits → bans → broken product)
- Do NOT invent data (Chuck already caught synthetic data in the excess_proceeds pipeline; do not repeat this)
- Do NOT commit deliverables until endpoints are proven working
- Do NOT hardcode Kern-specific values; use `counties/kern.yaml` config file pattern

## Related context

- Full multi-county roadmap: 7 upcoming 2026 auctions after Butte (Fresno, Kern, San Benito, Nevada, El Dorado, Calaveras, Mono). Kern is #1.
- Landing page: `lead_magnet/index.html` (FormSubmit wired, ready to deploy to Netlify)
- CA Auction Calendar: `data/california_tax_auction_calendar_2025_2027.csv` (108 entries, all 58 CA counties)

## Escalate to Chuck if

- Endpoints require paid subscription or FOIA request (not free/public)
- Rate limits force >7 day pipeline runtime
- Scope creep beyond delinquency catalog + on-demand dossier
- Any ambiguity about what buyer type to target
