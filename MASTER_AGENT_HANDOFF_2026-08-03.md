# MASTER AGENT HANDOFF — Logic Flow Systems County Pipeline
**Written:** 2026-08-03 14:49 PDT  
**For:** Any fresh agent picking this up  
**Owner:** Chuck Terrell | mrt@logicflowsystems.io  
**Workspace:** `C:\Users\chuck\Downloads\county_pipeline\`  
**Read this file first. Then read nothing else until you ask Chuck what is most pressing.**

---

## BUSINESS IN 60 SECONDS

Chuck builds California county tax-auction property intelligence. Two revenue legs:

1. **Property Intelligence** — Pull delinquent parcel data from CA county public portals before auctions. Score, enrich, package as PDF dossiers + call sheets. Sell to real estate investors before they bid.
   - Catalog (all parcels, ranked): $47–$97 per county per buyer
   - Deep dossier (one parcel, full detail): $97–$149 per parcel
   - Do the work once per county, sell to 10–30 investors going to the same auction

2. **Excess Proceeds Recovery** — After a tax auction, if the sale price exceeds what was owed, the former owner gets the surplus. They have 1 year (CA R&TC §4675) before it escheats to the county. Chuck finds them, files the claim, takes 30–40% contingency. No upfront cost to the former owner.

**The hedge:** Excess proceeds fills revenue gaps between auction cycles. Counter-cyclical by design.

**The bigger picture:** This is a fragmented public records aggregation framework deployed first in CA property tax data. The platform adapter pattern (10–15 vendor platforms cover all 58 CA counties) is generalized enough to extend to probate records, UCC liens, building permits, court judgments — any fragmented government data market. The verification schema already seeds PACER, CA SOS, and court records as future sources.

**Cardinal rules (do not violate):**
1. NEVER invent data. Every APN, owner name, address must come from a live verified public source.
2. Endpoint recon before catalog build. Prove endpoints return real data first.
3. Do NOT bulk-enrich all parcels. Deep dossier enrichment only when a buyer orders.
4. Do NOT commit deliverables until endpoints are proven.

---

## ARCHITECTURE — HOW IT WORKS

### The Unification Design
```
counties/{name}.yaml (config)
        ↓
tax_pipeline/config.py (COUNTY_CONFIG — 21 counties registered)
        ↓
tax_pipeline/multi_county_engine.py (universal processor)
    python multi_county_engine.py --county kern
        ↓
Stage 1: MPTS/ArcGIS/GovEase discovery (platform-specific)
Stage 2: Tax bill verification + scoring
Stage 3: AI adjudication (Gemini)
Stage 4: Owner enrichment (MBAP AsrPrint + TaxBillv2)
Stage 5: PDF merge
Stage 6: APN direct extraction
Stage 7: Recorder enrichment (Tyler EagleWeb — Playwright)
Stage 8: Cross-county rollup + skip trace
        ↓
verification/ (5-layer SQLite verification system)
        ↓
butte/delivery/ or kern/ etc. (output packages)
```

### Platform Adapters (the moat)
| Platform | Counties | Status |
|---|---|---|
| **MPTS** (`common1/2.mptsweb.com`) | Tehama, Shasta, Glenn, Colusa, Plumas, Lassen, Siskiyou, Trinity, Modoc, Butte, Humboldt + more | ✅ Generic adapter proven — `test_discovery_mpts.py` |
| **Tyler EagleWeb** (recorder) | Tehama, Shasta, Butte, Lassen | ✅ `recorder_config.py` has 4 counties |
| **FATCO ArcGIS FeatureServer** | Kern (proven), others possible | ✅ `enrich_kern_real.py` proven |
| **GovEase** | Kern (captured), Butte, Fresno | ⚠️ 70+ JSON captures, full adapter not wired |
| **KCTTC** (Kern Tax Collector) | Kern | ⚠️ CAPTCHA blocks automation |
| **ttc.lacounty.gov** | Los Angeles | ❌ No adapter built |

### Config Registry (`tax_pipeline/config.py`)
21 counties registered. Run `python multi_county_engine.py --county {slug}` for any of:
`tehama, shasta, glenn, colusa, plumas, lassen, siskiyou, trinity, modoc, butte, humboldt, kern, fresno, riverside, los_angeles, san_bernardino, el_dorado, calaveras, yuba, merced, alameda`

**⚠️ Two config bugs:** `kern` and `fresno` entries point to MPTS hosts but neither county uses MPTS. Do not run MPTS discovery for these — they will return wrong data.

---

## COUNTY STATUS — COMPLETE TABLE

| County | Parcels | Pipeline | Auction | Urgency | Notes |
|---|---|---|---|---|---|
| **Butte** | 105 auction | ✅ ALL 8 STAGES DONE | **Aug 7–10 (4 days)** | 🔴 CONFIRM DELIVERY | Dossiers built, delivery zip ready. Jeff teaser sent July 29. |
| **Tehama** | 40,059 master | ✅ COMPLETE | No date | 🔴 EXCESS PROCEEDS NOW | Outreach list is empty (181 bytes = headers only). Skip trace `excess_proceeds/excess_proceeds_tehama_2025.csv` (5.4MB) immediately — some 2025 deeds already past 1-year escheat. |
| **Shasta** | 94,414 master | ✅ COMPLETE | No date | 🟡 Productize | All stages done. 14MB scored call sheet. 5.7MB CRM-ready. |
| **Kern** | 940 auction | ⚡ DATA PULLED | **Sept 14–16 (41 days)** | 🔴 SEND CPRA EMAIL | FATCO data pulled. Assessor roll not requested. Run `CPRA_ASSESSOR_ROLL_REQUEST_PACKAGE.md`. Then `join_assessor_roll.py` when roll arrives. |
| **Fresno** | APN base | ⏳ WAITING | **Sept 10–11 (41 days)** | 🟡 MONITOR DAILY | List drops ~Aug 10. Run `fresno/fresno_daily_monitor.py` daily. Same FATCO pipeline as Kern once list appears. |
| **Colusa** | 90 (test) | Stage 1 only | No date | 🟢 Run full discovery | Generic MPTS adapter proven. 90 parcels in test. Run full Stage 1. |
| **Lassen** | 0 | Stage 7 config only | No date | 🟢 Run after Stage 7 fix | Tyler legacy platform. `recorder_config.py` ready. Blocked on Stage 7 fix. |
| **Glenn** | 0 (test returned 0) | Not run | No date | 🟢 Retry | Empty book used in test. Retry with different book prefix. |
| **Plumas, Siskiyou, Trinity, Modoc, Humboldt** | 0 | Not run | No date | 🟢 Validate MPTS | Each needs 15-min endpoint probe before full run. |
| **Riverside, El Dorado, Calaveras, Yuba, Merced, Alameda, San Bernardino** | 0 | Config only | No date | 🟢 Validate | Config entries unvalidated. May or may not be on MPTS. |
| **Los Angeles** | 0 | Not started | No date | ⚪ Future | ttc.lacounty.gov — completely different platform. No adapter. |

## RECENT COMPLETIONS (2026-08-03)

- **Casey check CLOSED**: APN 305-073-053-000 verified as Humboldt, CASEY B A, $11,481.75.
- **owner_resolve.py BUILT**: Unified single-command owner lookup created and wired into pipeline.
- **Humboldt Bridge Status**: Bridge runner script is currently resuming from APN 24,250 (374 parcels remaining).
- **Humboldt Tyler APN ID**: Added DOCSEARCH201S9 to humboldt.yaml.

---

## IMMEDIATE ACTION ITEMS (PRIORITY ORDER)

### 🔴 Do Right Now

**1. Fix `stage7_recorder_enrich.py`** — This is the #1 technical priority. The script is hardcoded and ignores `recorder_config.py`. Until fixed, Stage 7 only works for whichever county it was last hardcoded for. After fix, all 4 recorder-configured counties (Tehama, Shasta, Butte, Lassen) flow through automatically.

See exact fix instructions in the section below.

**2. Send Kern CPRA email** — Template is in `CPRA_ASSESSOR_ROLL_REQUEST_PACKAGE.md`. Assessors have 10 days to respond. Kern auction is Sept 14 — 41 days away. Every day waiting is a day less to verify the data.

**3. Tehama excess proceeds skip trace** — Open `excess_proceeds/excess_proceeds_tehama_2025.csv` (5.4MB). Sort by deed date ascending. Any deed recorded before July 2025 may already be past the 1-year window. Run skip trace on the most recent 100 parcels first (most likely still within window). Generate `outreach_list_tehama_2025.csv` with mailing addresses. Send letters immediately.

**4. Confirm Butte delivery** — Auction Aug 7. Email Jeff to confirm he received `butte_auction_intel_2026-07-29.zip`. If not, resend from `butte/delivery/butte_auction_2026-07-29/`.

**5. Rotate Gemini API key** — It is hardcoded as a string literal in:
- `tax_pipeline/butte_e2e_test.py` line 3
- `tax_pipeline/butte_stage3_test.py` line 3
Replace with `os.environ.get("GEMINI_API_KEY")`. Rotate the key itself in Google Cloud Console.

### 🟡 This Week

**6. Start running Fresno monitor daily** — `python fresno/fresno_daily_monitor.py`. List expected ~Aug 10.

**7. Restore `cps1_outcomes.db`** — Copy from `archive/tax_pipeline/cps1_outcomes.db` (766KB) to `tax_pipeline/cps1_outcomes.db`. Without it, Stage 2 starts a fresh empty de-dup cache and loses all historical verification.

**8. Fix `dashboard.py`** — It crashes on launch because `northern_ca_MASTER_merged.csv` is missing. Either restore this file or update `dashboard.py` to use an existing CSV as the default.

**9. Rebuild `requirements.txt`** — It was deleted from root. Copy from `archive/requirements.txt` and update with:
`requests pandas beautifulsoup4 playwright pydantic streamlit numpy httpx pymupdf pdfplumber google-generativeai flask urllib3 openpyxl`

---

## THE STAGE 7 FIX — EXACT INSTRUCTIONS

**File:** `tax_pipeline/stage7_recorder_enrich.py`  
**Problem:** All county selectors, URLs, and navigation logic are hardcoded. `recorder_config.py` exists with per-county config but is never imported.  
**Impact:** Stage 7 works only for the last county it was hard-coded for. Multi-county flow is broken at this stage.  
**Effort:** 2–4 hours of careful replacement work.  

**What `recorder_config.py` provides:**
```python
RECORDER_CONFIG = {
    "tehama": {
        "type": "tyler",
        "login_url": "https://recordsearch.tehama.gov/web/search/DOCSEARCH4S1",
        "name_search_url": "...",
        "doc_search_url": "...",
        "disclaimer_selector": "#submitDisclaimerAccept",
        "keepalive_text": ["Yes - Continue", "Yes, Continue"],
        "search_field": "#field_BothNamesID",
        "doc_search_field": "#field_DocumentNumberID",
        "search_button": "#searchButton",
        "results_selector": "li.ss-search-row",
        "needs_guest_login": False,
        "has_disclaimer": True
    },
    "shasta": { ... },
    "butte": { ... },  # type: tyler, has CivicPlus disclaimer variant
    "lassen": {
        "type": "tyler_legacy",
        "login_url": "https://eagleweb.co.lassen.ca.us/eweb/web/loginPOST.jsp?guest=true",
        "search_field": "#BothNamesIDSearchString",  # different from modern Tyler
        "needs_guest_login": True,
        "has_disclaimer": False
    }
}
```

**The fix pattern:**
```python
# Add at top of stage7_recorder_enrich.py:
from recorder_config import RECORDER_CONFIG

# In the main enrichment function, replace hardcoded values with:
def enrich_county(county, parcels):
    cfg = RECORDER_CONFIG.get(county)
    if not cfg:
        raise ValueError(f"No recorder config for county: {county}")
    
    login_url = cfg["login_url"]
    search_field = cfg["search_field"]
    disclaimer_selector = cfg.get("disclaimer_selector")
    has_disclaimer = cfg.get("has_disclaimer", True)
    needs_guest_login = cfg.get("needs_guest_login", False)
    results_selector = cfg["results_selector"]
    # ... replace all hardcoded selectors below with cfg["..."]
```

**Also noted in `STATUS_NOTE.md`:** Butte uses CivicPlus variant — needs `post_disclaimer_navigate` after accepting the disclaimer. This is already in `recorder_config.py` under `butte`.

---

## KEY FILES — COMPLETE MAP

```
C:\Users\chuck\Downloads\county_pipeline\
│
├── AI_SESSION_HANDOFF_2026-07-31.md    ← Previous session handoff
├── MASTER_HANDOFF.md                   ← Business overview + proven data sources
├── HANDOFF_KERN_PIPELINE.md            ← Kern business spec
├── HANDOFF_KERN_ENDPOINT_RECON.md      ← Kern proven endpoints
├── HEALTH_REPORT.md                    ← July 22 audit (older)
├── CPRA_ASSESSOR_ROLL_REQUEST_PACKAGE.md ← Template + 21 county contacts
├── MISSION.md                          ← Business mission statement
├── .env                                ← GEMINI_API_KEY (single key, 55 bytes)
│
├── tax_pipeline/
│   ├── config.py                       ← 21-county COUNTY_CONFIG registry
│   ├── recorder_config.py              ← 4-county recorder adapter registry
│   ├── multi_county_engine.py          ← Universal processor (--county flag)
│   ├── stage1_discover.py              ← MPTS discovery
│   ├── test_discovery_mpts.py          ← Generic multi-county MPTS (PROVEN)
│   ├── stage2_verify.py                ← Tax bill verify + HOT/WARM/COLD scoring
│   ├── stage3_adjudicate.py            ← Gemini AI adjudication
│   ├── stage4_owner_enrich.py          ← MBAP AsrPrint + TaxBillv2 owner data
│   ├── stage7_recorder_enrich.py       ← ⚠️ Hardcoded — NEEDS FIX (see above)
│   ├── stage8_all_counties.py          ← Cross-county rollup
│   ├── integrity_gate.py               ← Writes *_integrity_history.jsonl files
│   ├── full_county_integrity_pipeline.py ← 6-stage integrity checker
│   ├── join_assessor_roll.py           ← CPRA assessor roll joiner (ready)
│   ├── generate_auction_report.py      ← Report generator (22KB)
│   ├── butte_recorder_adapter.py       ← Butte-specific recorder (12KB)
│   ├── butte_buyer_tracker.py          ← Buyer tracking across cycles (16KB)
│   ├── shasta_feature_server_adapter.py ← Shasta ArcGIS adapter (6KB)
│   ├── STATUS_NOTE.md                  ← ⭐ READ THIS — exact next steps noted
│   ├── butte_eagleweb_state.json       ← Butte session state (July 19)
│   ├── tyler_session_cookies.json      ← Tyler session cookies
│   └── [225 total files — many are debug/test scripts, safe to ignore]
│
├── verification/
│   ├── schema.sql                      ← 5-layer verification SQLite schema
│   ├── __init__.py                     ← Package init
│   ├── distress_signals.py             ← Distress signal detection (9.5KB)
│   ├── ownership.py                    ← Ownership verification (9.8KB)
│   ├── graph.py                        ← Cross-parcel actor network (12.8KB)
│   ├── outcomes.py                     ← Post-auction outcome tracking (9.4KB)
│   ├── environmental.py                ← CalFire + FEMA overlays (8KB)
│   ├── consistency.py                  ← Data consistency checks (7.2KB)
│   └── [16 total Python files]
│
├── verification.sqlite                 ← Live verification DB (1.7MB)
│
├── connectors/
│   ├── base.py                         ← BaseConnector + RawPayload
│   ├── shasta.py                       ← Shasta MPTS connector
│   └── tehama.py                       ← Tehama MPTS connector
│
├── butte/
│   ├── delivery/
│   │   ├── butte_auction_2026-07-29/   ← ⭐ FULL DELIVERY PACKAGE
│   │   │   ├── dossiers/               ← 105 individual PDFs (score_name.pdf)
│   │   │   ├── butte_auction_intel_2026-07-29_all_dossiers.pdf (11.8MB)
│   │   │   ├── butte_auction_intel_2026-07-29.csv
│   │   │   └── butte_auction_intel_2026-07-29.xlsx
│   │   └── jeff_teaser_2026-07-29.pdf  ← Teaser sent to Jeff
│   ├── butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv (72KB)
│   ├── butte_repeat_distress_leads.csv (14KB)
│   ├── butte_DELINQUENT_ONLY_ENRICHED_VESTED_ADJUDICATED_REPAIRED_CRM_READY.csv (253KB)
│   ├── butte_15_percent_sample_ADJUDICATED_CRM_READY.csv (5.7MB)
│   └── [69 total files]
│
├── kern/
│   ├── kern_REAL_auction_list_fatco.csv (709KB — raw FATCO pull, 1,079 rows)
│   ├── kern_REAL_AUCTION_PARCELS_CLEAN.csv (239KB)
│   ├── kern_SCORED_AUCTION_MATCHES_CALL_SHEET.csv (157KB — 940 scored parcels)
│   ├── Kern_Auction_Intel_Workbook_REAL.xlsx (225KB — 4-tab)
│   ├── ca_property_tax_levies.csv (22.9MB — CA State Controller data)
│   ├── govease_captured_*.json (70+ files — GovEase API captures)
│   └── verify_top10_assessor.py, enrich_kern_real.py, govease_intercept.py
│
├── fresno/
│   ├── fresno_daily_monitor.py         ← Run daily until list drops
│   ├── fresno_public_apn_inventory.csv (33.5MB — full APN base)
│   └── fresno_per_apn_pull.py, fresno_per_apn_playwright.py
│
├── shasta/
│   ├── shasta_AUTHORITATIVE_master_index.csv (4.1MB)
│   ├── shasta_SCORED_AUCTION_MATCHES_CALL_SHEET.csv (14MB)
│   ├── shasta_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv (5.7MB)
│   └── Shasta_Auction_Intel_Workbook.xlsx (5.5MB)
│
├── tehama/
│   ├── tehama_AUTHORITATIVE_master_index.csv
│   └── Tehama_Auction_Intel_Workbook.xlsx
│
├── excess_proceeds/
│   ├── excess_proceeds_butte_2026.csv  ← 433 parcels, $3.34M, Jun 2027 deadline
│   ├── excess_proceeds_tehama_2025.csv ← 5.4MB — URGENT, some past deadline
│   ├── outreach_list_butte_2026.csv    ← Ready to send
│   ├── outreach_list_tehama_2025.csv   ← 181 bytes = EMPTY, not run yet
│   └── run_excess_finder.py
│
├── lead_magnet/
│   ├── index.html                      ← Landing page (Netlify-ready, FormSubmit wired)
│   ├── california_auction_calendar_2026.pdf ← 58-county lead magnet
│   └── leads.csv                       ← 1 test lead only — needs real traffic
│
├── monitor/
│   ├── run_monitor.py                  ← Weekly auction date tracker
│   └── monitor_log.csv
│
├── data/
│   └── california_tax_auction_calendar_2025_2027.csv (108 entries, all 58 CA counties)
│
└── dashboard.py                        ← Streamlit UI (crashes — missing CSV)
```

---

## KNOWN BUGS — COMPLETE LIST

| # | Severity | File | Issue | Fix |
|---|---|---|---|---|
| 1 | 🔴 | `tax_pipeline/stage7_recorder_enrich.py` | Hardcoded — ignores recorder_config.py | Import RECORDER_CONFIG, replace all hardcoded selectors |
| 2 | 🔴 | `tax_pipeline/butte_e2e_test.py:3` | Gemini API key hardcoded as string literal | `os.environ.get("GEMINI_API_KEY")` + rotate key |
| 3 | 🔴 | `tax_pipeline/butte_stage3_test.py:3` | Same as above | Same fix |
| 4 | 🔴 | `tax_pipeline/` (missing) | `cps1_outcomes.db` missing from tree | Copy from `archive/tax_pipeline/cps1_outcomes.db` |
| 5 | 🔴 | Root (missing) | `requirements.txt` deleted | Restore from `archive/requirements.txt`, update |
| 6 | 🟡 | `tax_pipeline/config.py` kern entry | Kern pointed at MPTS — wrong platform | Update or annotate as non-MPTS |
| 7 | 🟡 | `tax_pipeline/config.py` fresno entry | Fresno pointed at MPTS — wrong platform | Same |
| 8 | 🟡 | `dashboard.py` | Crashes on launch — `northern_ca_MASTER_merged.csv` missing | Restore file or update default path |
| 9 | 🟡 | `merge_v2.py` / `merge_master.py` | Instant FileNotFoundError — input CSVs missing | Update paths or restore CSVs |
| 10 | 🟡 | `batch_run.py` | 30-entry hardcoded RUNS list — not driven by config.py | Refactor to iterate COUNTY_CONFIG |

---

## PROVEN TECHNICAL ENDPOINTS

### Works — Do Not Break
| Endpoint | What | Used By |
|---|---|---|
| `common1.mptsweb.com/MBC/api/search/{county}/...` | MPTS tax + owner data | stage1, stage2, connectors |
| `common2.mptsweb.com/MBC/api/search/{county}/...` | Same (Shasta, Butte) | stage1, stage2, connectors |
| `services.arcgis.com/VYsrLd1WbPJ93eyz/arcgis/rest/services/Kern_County_Auction_List/FeatureServer/0/query` | Kern 940 parcels | enrich_kern_real.py |
| `recordsearch.tehama.gov/web/search/DOCSEARCH4S1` | Tehama recorder | stage7 / recorder_config |
| `recorderselfservice.shastacounty.gov/web/search/DOCSEARCH344S4` | Shasta recorder | stage7 / recorder_config |
| `recorder.buttecounty.net/web/search/DOCSEARCH481S1` | Butte recorder | stage7 / recorder_config |
| `eagleweb.co.lassen.ca.us/eweb/web/loginPOST.jsp?guest=true` | Lassen recorder (legacy) | recorder_config |
| `apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN={county}&Asmt={apn}` | Live tax bill | stage4, butte_tax_api |

### Dead Ends — Do Not Retry
| Endpoint | Problem |
|---|---|
| `kcttc.co.kern.ca.us/Payment/mainsearch.aspx` | CAPTCHA |
| `maps.kerncounty.com/Kern_AGS_Parcels/MapServer/0` | Empty layer |
| `kcttc.co.kern.ca.us/index.cfm?fuseaction=...showTaxSaleList` | Dead ColdFusion |
| `assessor.co.kern.ca.us` | 403 Forbidden |
| `api.govease.com` | DNS does not resolve |

---

## REVENUE — CURRENT STATE

### Property Intelligence
- **Butte package:** Built. 105 dossiers. No confirmed sale yet.
- **Kern catalog:** Built. 940 parcels. No buyers yet.
- **Lead magnet:** `lead_magnet/index.html` Netlify-ready, 1 test lead in `leads.csv`.
- **Fastest path to first sale:** Post in CA tax auction Facebook groups (search "California Tax Deed Investing"). Post: *"940 Kern County auction parcels, scored and equity-graded, $67 for the full catalog. Auction Sept 14. Anyone want it?"* — PayPal + Google Drive link. No website needed for first sale.

### Excess Proceeds
- **Butte:** 433 parcels, $3.34M, June 2027 deadline. Outreach list ready. Letters not sent yet.
- **Tehama:** Large dataset, URGENT, some past deadline. Skip trace not run. Outreach list empty.
- **Process:** Skip trace → mailing address → send letter → contingency agreement → file claim with county tax collector → collect 30–40% of recovery.

---

## AUCTION CALENDAR

| County | Dates | Days Out | Status |
|---|---|---|---|
| **Butte** | Aug 7–10, 2026 | **4 days** | ✅ 105 dossiers ready |
| **Fresno** | Sept 10–11, 2026 | 38 days | ⏳ List drops ~Aug 10 |
| **Kern** | Sept 14–16, 2026 | 42 days | ⚡ Data ready, assessor verify needed |
| San Benito | TBD | — | ❌ Not started |
| Nevada | TBD | — | ❌ Not started |
| El Dorado | TBD | — | ❌ Not started |

Full 58-county calendar: `data/california_tax_auction_calendar_2025_2027.csv`

---

## VERIFICATION SYSTEM — WHAT'S BEEN DESIGNED

`verification/schema.sql` defines a 5-layer system written to `verification.sqlite` (1.7MB, live):

- **Layer 0:** Every field value has source, confidence, fetch timestamp
- **Layer 1:** Completeness — did every expected source return data?
- **Layer 2:** Consistency — does data agree across sources?
- **Layer 3:** Graph — cross-parcel actor network (person → deed → parcel)
- **Layer 4:** Ownership — is identified owner actually current?
- **Layer 5:** Outcome — post-auction feedback into scoring calibration (self-improving)

Pre-seeded future source integrations (in schema): `ca_sos_bizfile`, `pacer`, `court_superior`, `code_enforcement`, `batch_skip_trace`, `fema_flood`, `calfire_hazard`. This is the blueprint for expanding beyond property tax into probate, UCC, court records.

---

## STRATEGIC CONTEXT — DO NOT LOSE THIS

What Chuck has built is a **public records intelligence framework** deployed first in CA county property tax data. The adapter pattern (few vendor platforms, many jurisdictions) generalizes to any fragmented government data market.

The pipeline's real value:
1. **It is platform-first, not county-first** — Tyler EagleWeb adapter works nationwide. MPTS has national footprint. One new county = 1–3 days of work.
2. **The verification system tracks provenance** — every field value has a source and confidence. This is institutional-grade data quality most data vendors don't achieve.
3. **Post-auction calibration loop** — Layer 5 feeds auction outcomes back into scoring. The model gets smarter with each auction cycle.
4. **Replacement cost:** $36K–$120K to rebuild. With customers: $1.5M–$5M. With national expansion: $3M–$10M.

**Do not suggest building more features until Chuck has a paying customer for Kern.** The product is good enough. The gap is marketing, not technology.

---

## FOR THE NEXT AGENT — START HERE

1. Read this file ✓
2. Ask Chuck: *"What's the most pressing thing right now?"*
3. Expected answers in priority order:
   - **Stage 7 fix** — see exact instructions above
   - **Fresno monitor** — run daily, list drops Aug 10
   - **Tehama skip trace** — excess proceeds emergency
   - **Kern CPRA** — send the email
   - **First sale** — help write the Facebook post

Do not start any new features. Do not touch the MAR-1 legacy files at root (120+ files with `cfv`, `cars`, `arc`, `mar1` prefixes — they are dead research code, safe to ignore entirely). Do not attempt to run `merge_v2.py` or `dashboard.py` without first fixing the missing file issues.

---

*Handoff written: 2026-08-03 14:49 PDT*  
*Previous handoff: `AI_SESSION_HANDOFF_2026-07-31.md`*  
*Health reports: `HEALTH_REPORT_2026-08-03.md`, `HEALTH_REPORT.md` (July 22)*
