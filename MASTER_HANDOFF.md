# Logic Flow Systems — Property Intelligence Pipeline
## Master Handoff Document
**Owner:** Charles Terrell | Logic Flow Systems | mrt@logicflowsystems.io  
**Workspace:** `C:\Users\chuck\Downloads\county_pipeline\`  
**Last Updated:** 2026-07-29

---

## ⚡ Assessor Data — Permanent Free Solution (ALL Counties)

**The Problem:** Every county assessor portal blocks automated scraping. No free API exists for parcel-level assessed values.

**The Solution:** California R&TC §408.3 — send one CPRA email to each county assessor. They are legally required to send you the full assessment roll in electronic format within 10 days, at no charge.

**Files:**
- 📄 `CPRA_ASSESSOR_ROLL_REQUEST_PACKAGE.md` — template letter + all 21 county contacts + status tracker
- 🔧 `tax_pipeline/join_assessor_roll.py` — when roll arrives, run this to auto-match APNs and replace estimated values with real verified values

**Command when a county roll arrives:**
```bash
python tax_pipeline/join_assessor_roll.py --county kern --roll kern/assessor_roll_kern_2026.csv
```

**Send Kern first** (auction Sept 14 — every day counts). Then all others.

---

## The Business in One Paragraph

Charles sells tax-auction property intelligence to real estate investors, wholesalers, and acquisition managers. The product is a **scored, enriched parcel dossier** ($299 per parcel on-demand) backed by a **lightweight catalog** of every delinquent parcel in a county. The lead magnet is a free 58-county California tax auction calendar that captures investor emails. A parallel revenue line recovers **excess proceeds** (surplus auction funds owed to former owners) on a 30–40% contingency before the 1-year escheat deadline.

---

## The Cardinal Rules

> [!CAUTION]
> 1. **NEVER invent data.** Charles caught synthetic data being fabricated. Every APN, owner name, address, and bid amount must come from a live verified public source or it does not go in the file.
> 2. **Endpoint recon before catalog build.** Prove endpoints return real data with 20+ sample records before building any output file.
> 3. **Do NOT bulk-enrich all parcels.** Deep dossier enrichment (recorder crawl, environmental, aerial) runs ONLY when a buyer pays $299 for a specific parcel.
> 4. **Do NOT commit deliverables until endpoints are proven.**

---

## What Has Been Built & Proven

### ✅ Butte County — COMPLETE (Reference Implementation)
- **105 real parcels** from official auction list
- Full pipeline: MPTS tax bill scrape → Assessor roll → Recorder crawl → Priority scoring → PDF dossier
- Teaser PDF built: `butte/jeff_teaser_2026-07-27.pdf`
- Auction: **Aug 7–10, 2026** (live now)
- Key scripts: `butte/build_dossiers.py`, `butte/enrich_tax_bills.py`, `butte/package_delivery.py`

### ✅ Kern County — REAL DATA PULLED (In Progress)
- **940 real parcels** pulled from **First American Title (FATCO) ArcGIS FeatureServer**
- Source URL: `https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Kern_County_Auction_List/FeatureServer`
- GovEase Auction ID: **1348** | Auction: **Sept 14–16, 2026**
- Enrichment complete: bid math, 70% thresholds, priority scoring, use code classification, IRS lien flags
- **Top find:** HCB MVB CAL LLC — two Vineland Rd parcels, $1M+ equity cushion each
- Files:
  - `kern/kern_REAL_auction_list_fatco.csv` — raw 1,079-row FATCO pull
  - `kern/kern_SCORED_AUCTION_MATCHES_CALL_SHEET.csv` — 940 scored parcels
  - `kern/Kern_Auction_Intel_Workbook_REAL.xlsx` — 4-tab formatted workbook
- **NEXT STEP:** Verify assessor values by cross-referencing APNs against Kern Assessor roll

### ⏳ Fresno County — WAITING ON COUNTY PUBLICATION (No Workaround)
- Auction: **Sept 10–11, 2026** (GovEase)
- **FATCO has NOT published a Fresno ArcGIS layer** — Kern was unique
- **Fresno County portal blocks all automated requests** (403 Forbidden on every endpoint)
- **GovEase has not listed Fresno yet** — auction list publishes ~30 days before = approx **Aug 10, 2026**
- **There is no way around this.** The data does not exist publicly yet.
- **Action when list goes live:** Run `fresno/fresno_daily_monitor.py` daily — it will detect the moment GovEase or FATCO publishes. Then run the same FATCO pull + enrichment pipeline used for Kern.
- Monitor script: `fresno/fresno_daily_monitor.py`

---

## Proven Data Sources (What Actually Works)

| Source | What It Returns | How to Access |
|---|---|---|
| **FATCO ArcGIS FeatureServer** | Full auction parcel list — APN, Owner, Min Bid, Situs, Zoning, Description | `https://www.arcgis.com/sharing/rest/search?q=<County>+County+Auction+List` then query FeatureServer/0 |
| **GovEase Auction Portal** | Live auction listings, registration pages | `https://www.govease.com/auctions` — search for county; auction IDs in KCTTC links |
| **KCTTC Tax Sale Brochure PDF** | Auction dates, rules, GovEase redirect | `https://www.kcttc.co.kern.ca.us/Forms/taxsalebrochure.pdf` |
| **Kern ArcGIS MapServer** | 15 map services including Kern_AGS_Parcels | `https://maps.kerncounty.com/arcgis/rest/services` |
| **Butte MPTS TaxBillv2** | Live tax bill per APN — proven working | `butte/enrich_tax_bills.py` — adapt pattern for each county |
| **CalFire FHSZ GIS** | Fire hazard zone per parcel | `butte/enrich_environmental.py` — already county-agnostic |
| **FEMA NFHL GIS** | Flood zone per parcel | Same as CalFire — county-agnostic |

## What Does NOT Work / Known Dead Ends

| Endpoint | Problem |
|---|---|
| `kcttc.co.kern.ca.us/Payment/mainsearch.aspx` | CAPTCHA blocks automated APN lookups |
| `maps.kerncounty.com/Kern_AGS_Parcels/MapServer/0` | Returns empty JSON — layer exists in name only |
| `kcttc.co.kern.ca.us/index.cfm?fuseaction=kcttcinternet.showTaxSaleList` | "No handler" error — dead ColdFusion routes |
| `assessor.co.kern.ca.us` | 403 Forbidden |
| GovEase API (`api.govease.com`) | DNS does not resolve — no public API |

---

## File Map (Every Important File)

```
C:\Users\chuck\Downloads\county_pipeline\
│
├── MASTER_HANDOFF.md                          ← THIS FILE
├── HANDOFF_KERN_PIPELINE.md                   ← Kern business spec
├── HANDOFF_KERN_ENDPOINT_RECON.md             ← Kern proven endpoints
│
├── index.html                                 ← Multi-county sales landing page (Netlify-ready)
│
├── butte\                                     ← REFERENCE IMPLEMENTATION
│   ├── build_dossiers.py                      ← PDF dossier generator
│   ├── enrich_tax_bills.py                    ← MPTS live tax bill scraper
│   ├── enrich_environmental.py                ← CalFire + FEMA (county-agnostic)
│   ├── fetch_parcel_images.py                 ← Esri satellite imagery
│   ├── package_delivery.py                    ← Orchestrator
│   ├── butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv
│   └── delivery\butte_auction_2026-07-25\     ← Final buyer deliverables
│
├── kern\                                      ← ACTIVE — DATA PULLED, NEEDS ASSESSOR VERIFY
│   ├── kern_REAL_auction_list_fatco.csv       ← 1079-row raw FATCO pull (REAL)
│   ├── kern_SCORED_AUCTION_MATCHES_CALL_SHEET.csv  ← 940 scored parcels (REAL)
│   ├── Kern_Auction_Intel_Workbook_REAL.xlsx  ← 4-tab Excel workbook (REAL)
│   ├── enrich_kern_real.py                    ← Enrichment engine
│   └── taxsalebrochure.pdf                    ← Official KCTTC brochure
│
├── fresno\                                    ← IN PROGRESS — Endpoint recon running
│   └── fresno_real_pull.py                    ← Running now
│
├── shasta\                                    ← 94,414 parcels from existing pipeline
│   ├── shasta_AUTHORITATIVE_master_index.csv
│   └── Shasta_Auction_Intel_Workbook.xlsx
│
├── tehama\                                    ← 40,059 parcels from existing pipeline
│   ├── tehama_AUTHORITATIVE_master_index.csv
│   └── Tehama_Auction_Intel_Workbook.xlsx
│
├── lead_magnet\
│   ├── index.html                             ← Email capture landing page
│   ├── california_auction_calendar_2026.pdf   ← 58-county lead magnet PDF
│   └── leads.csv                             ← Captured emails
│
├── monitor\
│   ├── run_monitor.py                         ← Weekly auction date tracker
│   └── monitor_log.csv
│
├── excess_proceeds\
│   ├── run_excess_finder.py                   ← Excess proceeds finder
│   ├── excess_proceeds_butte_2026.csv         ← 433 surplus parcels, $3.34M
│   └── outreach_list_tehama_2025.csv          ← URGENT — escheat deadlines approaching
│
├── data\
│   ├── california_tax_auction_calendar_2025_2027.xlsx  ← 4-tab master calendar
│   └── california_tax_auction_calendar_2025_2027.csv   ← 108 records, 2025-2027
│
└── tax_pipeline\
    ├── config.py                              ← 21-county configuration
    ├── multi_county_engine.py                 ← Universal county scoring engine
    ├── full_county_integrity_pipeline.py      ← 6-stage data integrity pipeline
    ├── kern_endpoint_recon.py                 ← Kern endpoint probe
    ├── kern_deep_recon.py                     ← Kern deep probe
    ├── kern_work_audit.py                     ← Honest audit of what works
    ├── kern_real_pull.py                      ← Real Kern data pull (FATCO)
    ├── kern_multi_source.py                   ← Multi-source probe
    ├── fresno_real_pull.py                    ← Fresno real data pull (RUNNING)
    └── investor_pipeline\
        ├── bid4assets_extractor.py
        └── recorder_linker.py
```

---

## Upcoming County Auction Calendar (Priority Order)

| County | Auction Dates | Platform | Status |
|---|---|---|---|
| **Butte** | Aug 7–10, 2026 | GovEase | ✅ 105 parcels ready |
| **Fresno** | Sept 10–11, 2026 | GovEase | 🔄 Recon running now |
| **Kern** | Sept 14–16, 2026 | GovEase (ID: 1348) | ✅ 940 real parcels pulled |
| **San Benito** | TBD 2026 | GovEase | ❌ Not started |
| **Nevada** | TBD 2026 | GovEase | ❌ Not started |
| **El Dorado** | TBD 2026 | GovEase | ❌ Not started |
| **Calaveras** | TBD 2026 | GovEase | ❌ Not started |
| **Mono** | TBD 2026 | GovEase | ❌ Not started |

---

## How to Pull Real Data for Any New County (Proven Method)

```bash
# Step 1: Search FATCO ArcGIS for the county auction list
# https://www.arcgis.com/sharing/rest/search?q=<County>+County+Auction+List+tax+defaulted&f=json

# Step 2: Query the FeatureServer
# https://services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/<Layer>/FeatureServer/0/query
# ?where=1=1&outFields=*&f=json&resultRecordCount=2000&returnGeometry=false

# Step 3: Run enrichment
python kern\enrich_kern_real.py   # adapt for new county

# Step 4: Verify assessor values against county assessor roll
# Step 5: Build Excel workbook
```

---

## Excess Proceeds — URGENT

- **Butte:** 433 surplus parcels, $3.34M unclaimed — deed dates Jun 2026 → escheat Jun 2027
- **Tehama:** Outreach list ready — 2025 deeds → some may already be past deadline
- **Action needed:** Run skip trace on top 20 Tehama parcels for owner mailing addresses

---

## Key Contacts

| Name | Role | Contact |
|---|---|---|
| Charles Terrell | Owner / Logic Flow Systems | mrt@logicflowsystems.io |
