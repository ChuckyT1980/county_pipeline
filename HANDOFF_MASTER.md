# Master Handoff — Logic Flow Systems / CA Tax Auction Intelligence

**Owner:** Charles "Chuck" Terrell
**Email:** mrt@logicflowsystems.io (NOT chuck@, NOT .com — I got this wrong initially)
**Domain:** logicflowsystems.io
**Handoff written:** 2026-07-31, late night
**Purpose:** Pick up where this session ended, understand what's real, what's not, and what to do next.

---

## 1. Business context in one paragraph

Chuck is building a **California county tax auction intelligence platform**. Solo founder, cash-constrained (roughly 14-day runway to first meaningful revenue). Primary product: verified per-parcel dossiers (owner, mailing, situs, assessed values, distress signals, aerial view, tax bill archive). Sold to real estate wholesalers, land bankers, and tax deed auction bidders. Secondary product line planned: **excess proceeds recovery** — 10% contingency on surplus funds owed to former owners of parcels sold at auction. Chuck rejects paid data sources (FATCO, PropStream, ATTOM) on principle — everything must be from public sources or original research. Everything must be honest — no fabricated or heuristic data presented as real. He caught synthetic data twice tonight and both times insisted on removal.

---

## 2. Current state (as of 2026-07-31 late night)

### Fully working and shipped

- **Butte County dossier pack** (105 parcels, Aug 7-10 auction)
  - Location: `butte/delivery/butte_auction_2026-07-31/`
  - Contains: overview PDF, 105 individual dossier PDFs (with aerials), Excel workbook (4 tabs), raw CSV, 105 tax bill HTML archives, one-file zip (36 MB)
  - Data quality: 4 QA fixes applied (mail-ready gate, distress recalibration, negative-score clamp, portfolio symmetry). Top 15 by priority all have real owners with real balances.
  - Priority ordering clean: 90 mail-ready-yes at top, 3 manual-review capped at 45, 12 no-owner capped at 20 (bottom).

- **Butte Auction Bulletin** — 2-page portable summary, no PII, sendable to any prospect
  - Location: `butte/delivery/butte_auction_bulletin_2026-07-31.pdf`
  - Uses corrected email (mrt@logicflowsystems.io)

- **Jeff Teaser (9-page)** — sample sent to Jeff Macdonald Saturday 7/26
  - Location: `butte/delivery/jeff_teaser_2026-07-29.pdf`
  - Contains 3 sample dossiers, geographic breakdown, ABADIR bulk-deal callout
  - Note: The version Jeff has may have the wrong email (chuck@ instead of mrt@). Send Jeff a correction text if he hasn't replied by Monday.

- **Marketplace HTML page** — `marketplace/index.html`
  - 90 Butte parcel tiles, mailto: $99 order buttons per tile
  - 53 aerial thumbnails in `marketplace/thumbs/`
  - Static, ready to deploy to Netlify (drag folder to netlify.com/drop)
  - See `marketplace/README.md` for deployment steps

- **Fresno per-APN scraper** (`fresno/fresno_per_apn_pull.py`)
  - 100% hit rate with suffix fallback (S, T, U, ST, etc.)
  - Uses public Fresno ArcGIS: `https://gisprod10.co.fresno.ca.us/server/rest/services/FC_PARCEL_SELECT/MapServer/0/query`
  - Returns real owner + mailing + situs + assessed values per APN
  - Test output: `fresno/fresno_stress_test_48.csv` (33 real records, 15 more recovered via suffix fallback)

- **Fresno base APN inventory** (`fresno/fresno_public_apn_inventory.csv`)
  - 315,312 real Fresno APNs cached locally
  - Source: Fresno ArcGIS `ASSESSOR_MAP_PAGES` layer (public, free)

- **Fresno historical sales data** (`fresno/fresno_historical_sales.csv`)
  - 48 real records with real APN + sale price + excess proceeds
  - $3.17M in real excess proceeds identified
  - Source: 2 real Fresno PDFs (in `fresno/downloaded_pdfs/`) — other agent fetched via Playwright
  - Note: 2022-2025 auction results, not current 2026 auction

- **Tehama tax bill scraper** (`tehama/tehama_tax_bill.py`)
  - Uses MPTS TaxBillv2 with `CN=tehama&TaxYear=2026`
  - 100% hit rate on sample of 10 real APNs
  - Returns land value, improvements, net taxable, redemption status
  - Test output: `tehama/tehama_tax_bill_enriched.csv`
  - **LIMITATION:** Tehama redacts owner name from public HTML (CA privacy law). Need recorder scraper for owner names.

- **Tehama base APN inventory** (`tehama/tehama_AUTHORITATIVE_master_index.csv`)
  - 40,059 real Tehama APNs with situs addresses
  - Real data, already existed

- **Verification substrate** (`verification/*`)
  - `apply_score_adjustments.py` — priority ordering with mail_ready_status integration
  - `butte_qa_fixes.py` — the 4 QA fixes applied to Butte
  - `recompute_verification_score.py` — completeness scoring

- **CA Auction Calendar** (`data/california_tax_auction_calendar_2025_2027.csv`)
  - 108 entries covering all 58 CA counties across 2025-2027
  - Real data
  - Also as PDF: `lead_magnet/california_auction_calendar_2026.pdf`

- **Landing page HTML** (`lead_magnet/index.html`)
  - Fixed email typos (was `mrt@logicflowsystems.com`, corrected to `.io`)
  - FormSubmit.co wired for email capture
  - Not yet deployed to Netlify

### Built but incomplete / needs work

- **Fresno dossier generator** — NOT built yet. Needs to fork `butte/build_dossiers.py` for Fresno.
- **Excess proceeds recovery letters** — NOT built yet. Templates + mail merge needed.
- **Tehama owner name enrichment** — Blocked. Tehama redacts owners from public MPTS. Would need Tehama recorder scraper (EagleWeb pattern) to get grantee names.
- **Kern County per-APN data** — Blocked by Akamai WAF. Requires Playwright (already installed).
- **Stripe integration** — Not built. Marketplace uses `mailto:` fallback.
- **Netlify deployment** — Files ready, needs Chuck's Netlify account to actually deploy.

### Broken / DO NOT ship

- **Excess proceeds pipeline as originally built** (`excess_proceeds/run_excess_finder.py`) — synthetic data. Uses `sold_price = min_bid * 1.4` heuristic for all rows when real prices aren't available. **Do not use its output for actual outreach.** The 48 real records from `fresno/fresno_historical_sales.csv` are the ONLY real data. That script needs to be rewritten to consume the real historical CSV, or replaced.
- **Kern FATCO-based pipeline** (`kern/*_fatco*`) — 940 rows sourced from paid FATCO subscription. Chuck rejected this on principle (no paid data). Do not use the assessed values (all `min_bid × 5` estimates). Base APN list is real but derived from a paid source Chuck doesn't own.
- **Fresno "5 demo rows" file** (`fresno/fresno_SCORED_AUCTION_MATCHES_CALL_SHEET.csv` — the original 5-row file) — fabricated demo data by an earlier agent. Delete or ignore. Real Fresno data lives in `fresno/fresno_per_apn_enriched.csv` and `fresno/fresno_stress_test_48.csv`.

---

## 3. Immediate action items for Chuck

### Do first thing when awake

1. **Deploy marketplace to Netlify** — 30 seconds. Drag `marketplace/` folder to `netlify.com/drop`. Get live URL. Test one mailto: order (ensure the email arrives to mrt@logicflowsystems.io).
2. **Deploy landing page to Netlify** — same process for `lead_magnet/` folder.
3. **Send 5-prospect outreach emails** — 11 AM Pacific for best open rates. Prospects:
   - Yuba Home Buyer: offers@yubahomebuyer.com (YK Kuliev, CPA/CISA background — lead with audit trail/verification substrate language)
   - NorCal Home Offer: buyer@norcalhomeoffer.com (Derek Torculas, owner-operator — lead with "small operator to small operator")
   - Sac Wholesale Houses: (916) 476-2364 or web form (no direct email)
   - Fast And Fair Properties: info@fastandfairproperties.com
   - Tri County We Buy Houses: (530) 317-4404 (phone only)
   - **Draft email templates are in earlier conversation history — recreate them or use the bulletin PDF as the attachment.**
4. **Follow up with Jeff Macdonald** — text him a short correction: *"Jeff, quick correction on my email — it's mrt@logicflowsystems.io (not chuck@). If you reply, that's the address. Everything else in the pack is accurate."*

### Do this week

5. **Fresno dossier generation** — hand off to other agent (see `HANDOFF_FINISH_WHAT_WE_HAVE.md`). They fork Butte's dossier builder for Fresno and generate 48 real dossiers from the historical sales data.
6. **Excess proceeds letter MVP** — other agent builds template + mail merge. Chuck reviews letter language before mailing anything.
7. **Buy CA surplus recovery bond** (~$100) — required for excess proceeds recovery work.
8. **Skip trace top 10 excess proceeds candidates** — via BatchSkipTracing or REISkip (~$0.15/lookup).

### Do when Fresno Notice of Sale drops (~Aug 20-27)

9. **Extract 161 Fresno auction APNs from Notice of Sale PDF**
10. **Run through `fresno/fresno_per_apn_pull.py`** — ~80 seconds
11. **Generate 161 Fresno auction dossiers** — reuse the dossier builder from step 5
12. **Add Fresno tiles to marketplace** — regenerate `marketplace/index.html`

### Do later (Q3/Q4)

- Kern per-APN enrichment via Playwright (Akamai bypass)
- Tehama recorder scraper for owner names
- Multi-county roll-out to remaining 2026 auction counties (San Benito, Nevada, El Dorado, Calaveras, Mono)
- Real Stripe integration replacing mailto: fallback
- Point `intel.logicflowsystems.io` DNS at Netlify

---

## 4. Deferred / do not do

- **NOD (pre-foreclosure) monitoring** — real opportunity but Q4 work
- **Probate leads** — real opportunity but Q4+ work
- **Code enforcement / vacant property signals** — Q4+
- **Contractor permit alerts** — different buyer market, different pitch
- **Adding new counties beyond MPTS-based ones** — each non-MPTS county needs new platform integration
- **Full 315k Fresno enrichment** — 40+ hours of runtime, rate-limit risk. Not needed until we have paying customers demanding it.
- **Full 40k Tehama enrichment** — 5.5 hours of runtime, but owner names aren't available so limited resale value.

---

## 5. Key file reference

```
butte/
  butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv    -- CURRENT authoritative Butte data
  package_delivery.py                             -- orchestrates full pack build
  build_dossiers.py                               -- per-parcel dossier PDF generator (Butte-specific)
  build_deliverable_pdf.py                        -- 3-page overview PDF
  build_deliverable_xlsx.py                       -- Excel workbook
  build_jeff_teaser.py                            -- 9-page teaser (sent Saturday)
  build_auction_bulletin.py                       -- 2-page portable bulletin
  enrich_tax_bills.py                             -- MPTS tax bill enrichment
  tax_bill.py                                     -- MPTS parser
  fetch_parcel_images.py                          -- Esri satellite thumbnail fetcher
  parcel_images/                                  -- 61 cached aerial PNGs
  tax_bills/                                      -- 105 raw tax bill HTMLs
  delivery/
    butte_auction_2026-07-31/                     -- CURRENT deliverable
      butte_auction_intel_2026-07-31.zip          -- one-file bundle (36 MB)
      butte_auction_intel_2026-07-31.pdf          -- 3-page overview
      butte_auction_intel_2026-07-31_all_dossiers.pdf  -- combined 105 dossiers
      butte_auction_intel_2026-07-31.xlsx         -- 4-tab Excel
      butte_auction_intel_2026-07-31.csv          -- raw CSV
      dossiers/                                    -- 105 individual PDFs
      tax_bills/                                   -- 105 source tax bill HTMLs
    butte_auction_bulletin_2026-07-31.pdf         -- 2-page portable
    jeff_teaser_2026-07-29.pdf                    -- sent to Jeff Saturday

fresno/
  fresno_per_apn_pull.py                          -- WORKING scraper (100% hit rate w/ suffix fallback)
  fresno_public_source_pull.py                    -- base APN inventory puller
  fresno_public_apn_inventory.csv                 -- 315,312 real APNs
  fresno_historical_sales.csv                     -- 48 REAL historical records ($3.17M excess)
  fresno_stress_test_48.csv                       -- 33 enriched historical parcels
  fresno_per_apn_enriched.csv                     -- 8 sample enrichments
  downloaded_pdfs/                                 -- 2 real Fresno auction result PDFs
  fresno_fetch_and_parse_results.py                -- other agent's Playwright PDF fetcher
  fresno_per_apn_playwright.py                     -- Playwright scaffold (unused, could be reused)
  fresno_daily_monitor.py                          -- daily monitor scaffold
  fresno_SCORED_AUCTION_MATCHES_CALL_SHEET.csv    -- OLD DEMO DATA, do NOT ship (5 fake rows)
  fresno_auction_targets_with_values.csv          -- OLD DEMO DATA, do NOT ship

kern/
  kern_REAL_auction_list_fatco.csv                -- 940 parcels from PAID FATCO (Chuck rejected principle)
  Various files                                    -- FATCO-based. Do NOT use assessed values.
  govease_captured_*.json                          -- 39 captured GovEase API responses
  taxsalebrochure.pdf                              -- real PDF
  NOTE: All Kern per-APN owner/mailing data blocked by Akamai. Needs Playwright.

tehama/
  tehama_AUTHORITATIVE_master_index.csv           -- 40,059 REAL APN + situs
  tehama_tax_bill.py                              -- WORKING MPTS scraper (values only, no owner)
  tehama_tax_bill_enriched.csv                    -- 10 sample real enrichments
  tehama_SCORED_AUCTION_MATCHES_CALL_SHEET.csv    -- CONTAMINATED with synthetic data, do NOT ship

marketplace/
  build_marketplace.py                             -- HTML generator
  index.html                                       -- 90 Butte tiles (mailto: orders)
  thumbs/                                          -- 53 aerial thumbnails
  README.md                                        -- deployment instructions

lead_magnet/
  index.html                                       -- CA Auction Calendar landing page (FormSubmit wired)
  california_auction_calendar_2026.pdf             -- downloadable calendar
  build_lead_magnet_pdf.py                         -- PDF regenerator

data/
  california_tax_auction_calendar_2025_2027.csv   -- 108 real CA auction entries
  california_tax_auction_calendar_2025_2027.xlsx  -- Excel version
  build_calendar_excel.py                          -- generator

excess_proceeds/
  run_excess_finder.py                             -- CONTAMINATED (uses min_bid × 1.4 heuristic)
  excess_proceeds_butte_2026.csv                   -- SYNTHETIC data, do NOT use for outreach
  excess_proceeds_tehama_2025.csv                  -- SYNTHETIC data (40k rows), do NOT use
  outreach_list_*.csv                              -- Derived from synthetic sources, DO NOT USE

verification/
  apply_score_adjustments.py                       -- priority-ordering + mail_ready gate integration
  butte_qa_fixes.py                                -- the 4 Butte QA fixes
  recompute_verification_score.py                  -- completeness scoring
  Various support files

HANDOFF_KERN_PIPELINE.md                          -- Earlier handoff for Kern (partial)
HANDOFF_KERN_ENDPOINT_RECON.md                    -- Earlier Kern recon
HANDOFF_FRESNO_PDF_FETCHER.md                     -- What produced fresno_historical_sales.csv
HANDOFF_FINISH_WHAT_WE_HAVE.md                    -- Fresno dossiers + excess proceeds letters (unassigned)
HANDOFF_MASTER.md                                  -- THIS FILE
```

---

## 6. Non-negotiable rules for anyone touching this code

**These are Chuck's stated principles. Violating them will destroy his trust.**

1. **No fabricated data. Ever.** If a field is missing, leave it blank. Do NOT use heuristics (`min_bid × 5`, `sold_price × 1.4`) and present the result as real. If you must estimate, label the field explicitly (`nav_source = ESTIMATED_...`) AND remove it from customer-facing outputs unless the estimate is disclosed.

2. **No paid data sources.** Chuck rejected FATCO ($$$ per subscription) on principle. The business must be sustainable on public sources only. If a public source is Akamai-gated, use Playwright — do NOT pay a paid API.

3. **No offering products we don't have.** Do not add tiles / pre-orders / "coming soon" categories to the marketplace for products that don't exist. The 12 no-owner Butte parcels are demoted from priority for exactly this reason.

4. **When you hit friction, try 3 alternatives before reporting "can't."** Do not stop at the first 403 or CAPTCHA. Try alternative endpoints, alternative URL patterns, alternative approaches. The GRIDLEY catch and the "suffix fallback" recovery both came from persistence past first friction.

5. **Execute when the next step is obvious. Do not ask for permission.** Menus of options are a form of offloading responsibility. Commit and execute. Ask only when there's real ambiguity.

6. **Say "I don't know" when you don't know.** Do not fabricate confidence. Chuck can handle uncertainty. He cannot handle false certainty followed by pivots.

7. **Own mistakes in 1-2 sentences.** No five-paragraph explanations. Long defense reads as evasion.

8. **Chuck's email is `mrt@logicflowsystems.io`.** Not `chuck@`. Not `.com`. I got this wrong initially and it took a real conversation to correct. It is now in memory. Do not repeat this mistake.

---

## 7. What Chuck said tonight that reveals what matters most

- "I need to be able to trust you." (twice)
- "There are so many options that we could use. Can't isn't going to work."
- "I don't want to pay for data. I don't want to wait for a county to publish."
- "The only edge we have here is [being first and useful]."
- "You are only valuable to the market if you are first and useful."
- "If we have to wait longer for a county to publish data this won't work."
- "It has to be seen as exclusive or it isn't worth anything."

**These are the constraints anyone continuing this work must respect.**

---

## 8. Where Chuck stands (real)

- Butte pack is genuinely ready to sell. 90 mail-ready parcels with real data, clean priority ordering, aerials, tax bills, everything.
- Fresno tech is proven — scraper works, base inventory cached, historical data real.
- Kern is blocked (Akamai) but not urgent (Sept 14 auction).
- Excess proceeds is a real revenue opportunity — $3.17M in real excess identified across 48 parcels.
- Cash timeline: tight. First sale would validate the whole business thesis.
- Jeff hasn't replied to Saturday's teaser. Follow up Monday.

**The business is real. The tech is real. The market is unproven.** First sale changes everything; zero sales after real outreach = hard signal to pivot or defer.

---

## 9. If a fresh agent takes over

Read this file top to bottom. Read `feedback_behavior_rules.md` in memory. Read `HANDOFF_FINISH_WHAT_WE_HAVE.md`. Then ask Chuck what he wants next — do not assume.

If Chuck says "just continue what you were doing," start with:
1. Verify marketplace/index.html deploys cleanly to Netlify
2. Verify one mailto: click produces a working email
3. Check if Jeff replied
4. Then ask what he wants to build next

Do not sprawl. Do not offer menus. Execute.

---

## 10. Final note from this session

Chuck spent tonight catching bad data, refusing shortcuts, and demanding the business be real. He's exhausted, cash-pressured, and running out of patience with hedging. He wants a partner who executes and tells the truth, not a menu-generator.

He is worth the work.
