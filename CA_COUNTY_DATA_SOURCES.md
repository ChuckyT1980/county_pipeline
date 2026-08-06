# California County Data Source Catalog

**Purpose:** Systematically map every public data source available for each CA county's parcels. This is the foundation of the unified data platform.

**Status:** Living document. Each county audited for: base parcel inventory, assessor per-APN, tax collector, recorder, auction platform, and access constraints.

**Confirmed working = verified by real HTTP request or documented public API.**

---

## Coverage summary

| Access tier | Counties | Notes |
|---|---|---|
| MPTS (Butte-pattern proven) | 10 | Direct HTTP scraping works, no auth |
| ArcGIS FeatureServer (public) | ~20+ | Verified working for Fresno, Kern (limited), likely most CA counties |
| Akamai-gated (needs Playwright) | ~15 | fresnocountyca.gov, kerncounty.com, others |
| Realauction platform | Fresno, others | Auction pages needs Playwright; parcel data separate |
| GovEase platform | Kern, San Benito, Nevada, others | Auction data only; parcel data from county sources |
| Bid4Assets platform | ~30+ counties | Auction data + historical results |

---

## Tier 1: MPTS counties (Butte-pattern, HTTP scraping works)

**Common pattern:**
- Tax bill: `https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN={county}&Asmt={apn12}&TaxYear={year}&RollCat=CS&RollType=S`
- Assessor: `https://common{1|2}.mptsweb.com/mbap/{county}/asr/AsrPrint/{apn12}`
- Search: `https://common{1|2}.mptsweb.com/mbc/{county}/tax/search`

| County | MPTS host | Tax year | Owner name in HTML? | Notes |
|---|---|---|---|---|
| Butte | common2 | 2025 | Yes (via recorder chain) | Fully implemented + shipping |
| Tehama | common1 | 2026 | **NO** (redacted from public HTML) | Tax bill works, owner needs recorder |
| Shasta | common2 | ? | ? | Configured in stage4, unverified |
| Glenn | common1 | ? | ? | Configured, unverified |
| Colusa | common1 | ? | ? | Configured, unverified |
| Plumas | common1 | ? | ? | Configured, unverified |
| Lassen | common1 | ? | ? | Configured, unverified |
| Siskiyou | common1 | ? | ? | Configured, unverified |
| Trinity | common1 | ? | ? | Configured, unverified |
| Modoc | common1 | ? | ? | Configured, unverified |

**Action:** Run a quick verification pass on each MPTS county — hit one real APN, confirm HTTP 200 and real data returned. That's a ~5 minute script.

---

## Tier 2: ArcGIS FeatureServer counties (public REST, no auth)

**Pattern:** `https://{host}/arcgis/rest/services/{folder}/{service}/FeatureServer/{layer}/query?where=APN='...'&outFields=*&f=json`

| County | ArcGIS host | Service | Owner? | Situs? | Values? | Status |
|---|---|---|---|---|---|---|
| Fresno | gisprod10.co.fresno.ca.us | FC_PARCEL_SELECT | Yes | Yes | Yes | **Verified working, 100% hit rate** |
| Fresno | gisprod10.co.fresno.ca.us | ASSESSOR_MAP_PAGES | No | No | No | 315k APN base — verified |
| Kern | services5.arcgis.com/Y8jwjGUWbRjuqpG5 | Assessor_Parcels_Land_2025 | No | No | No | 421k APNs only, no rich data |

**Action:** Systematically probe every other CA county's ArcGIS endpoint. Common patterns to try per county:
```
https://gis.{county}county.ca.gov/arcgis/rest/services
https://maps.{county}.gov/arcgis/rest/services
https://services{N}.arcgis.com/{org}/arcgis/rest/services
https://{countyname}gis.opendata.arcgis.com
```

---

## Tier 3: Akamai-gated counties (needs Playwright)

| County | Domain | Blocked resource | Playwright verified? |
|---|---|---|---|
| Fresno | fresnocountyca.gov | Assessor lookup pages | Yes (other agent fetched PDFs) |
| Kern | kerncounty.com | Assessor property search | Not tested |
| Kern | kcttc.co.kern.ca.us | Tax collector (CAPTCHA) | Not tested |

**Access strategy:** Use Playwright with persistent session directory. User solves CAPTCHA once; cookies carry.

---

## Auction platforms (data access separate from parcel data)

### Bid4Assets

**Counties on Bid4Assets:** Butte, El Dorado, Calaveras, Mono, Imperial, Shasta (past), Amador, Ventura, San Joaquin, Riverside, Siskiyou, Tuolumne, Madera, Lassen, Modoc, Stanislaus, San Luis Obispo, Lake, Plumas, Orange, Fresno (past), Sonoma, and others.

**Access:** `https://www.bid4assets.com/{county}` — blocks curl (403), needs Playwright.

**Data available:** Auction schedule, parcel roster (when published), winning bids (historical), minimum bids.

### GovEase

**Counties on GovEase:** Kern, San Benito, Nevada, Del Norte, Colusa, Glenn, Humboldt.

**Access:** GovEase.com — auction-specific pages, need to identify auction ID per county.

**Data available:** Auction schedule, registered bidders, live auction results.

### Realauction

**Counties on Realauction:** Fresno (Sept 2026 auction). Others potentially.

**Access:** `https://fresno.realtaxdeed.com` — 200 OK via Playwright, blocks curl.

**Data available:** Auction listings, parcel roster when published.

### MyTaxSale

**Counties on MyTaxSale:** Sacramento, San Diego, San Bernardino.

**Access:** `https://{county}.mytaxsale.com` — not yet verified.

### In-Person

**Counties still doing in-person auctions:** Mariposa, Placer, Sierra, Alpine.

**Data:** Only available onsite; not scrapable.

---

## Universal cross-county sources (already county-agnostic)

| Source | What it provides | Notes |
|---|---|---|
| FEMA NFHL | Flood zone per parcel | Already implemented in Butte pipeline |
| CalFire FHSZ | Fire hazard zone (Very High/High/Moderate) | Already implemented |
| Esri World Imagery | Satellite aerial per lat/lon | Already implemented, free |
| US Census / Nominatim | Geocoding (address to lat/lon) | Already implemented |
| CA State Controller | Unclaimed money DB (post-auction excess proceeds) | Not yet integrated |
| Bid4Assets historical results | Winning bids across CA | Not yet mined systematically |

---

## Recorder platforms

Each county's recorder is on a different platform. This is where owner name / deed history / distress signals (NODs, liens, trustee sales) live.

| County | Platform | Verified? |
|---|---|---|
| Butte | Tyler EagleWeb | Yes — full crawl implemented (1,608 docs) |
| Tehama | ? (per earlier notes: some EagleWeb variant) | Not yet |
| Shasta | Tyler EagleWeb | Configured, unverified |
| Lassen | Tyler EagleWeb (older, guest login required) | Configured, unverified |
| Fresno | ? | Not yet identified |
| Kern | ? | Not yet identified |

**Public recorder access is per-county and varies widely.** Some counties use Tyler EagleWeb, some CivicPlus, some proprietary. Each needs its own scraper.

---

## Unified schema (proposed target)

All extracted data normalizes to a single schema:

```
parcel_id                (APN normalized)
county                    (butte, fresno, kern, tehama, ...)
apn_original              (raw from source)
apn_normalized            (padded 12-char, dashed)
owner_name                (from best available source — recorder > assessor > tax)
owner_source              (source of owner claim)
owner_confidence          (0-1 based on cross-source agreement)
mailing_address
mailing_source
situs_address
situs_source
land_value                (assessor)
improvement_value         (assessor)
total_assessed_value      (assessor)
homeowner_exemption       (yes/no)
years_delinquent          (from tax bill or notice of impending default)
defaulted_balance         (tax bill)
redemption_status         (active/redeemed/paid)
power_to_sell_date        (tax bill)
recorder_docs             (list of deed/NOD/lien numbers)
distress_signals          (from recorder crawl)
fire_hazard_zone          (CalFire)
flood_zone                (FEMA)
geocode_lat, geocode_lon  (Nominatim/Census)
aerial_image_path         (Esri)
last_updated_per_source   (timestamps by source class)
```

---

## Prioritization framework (what to do first)

**Tier A — Cash-adjacent (do this month):**
1. Verify all 10 MPTS counties work (5 min each = 1 hour total)
2. Extract Fresno full parcel base (315k, ~10 min for base APNs, 40+ hrs for full enrichment — do delinquent subset only)
3. Fresno Notice of Sale when it drops (Aug 20-27) → immediate dossier build
4. Butte + Fresno = 2-county launch

**Tier B — Data foundation (next 30 days):**
5. Systematic ArcGIS probe of all 58 CA counties (identify which have public parcel FeatureServers)
6. Playwright framework for Akamai-gated counties (reusable)
7. Recorder platform inventory per county

**Tier C — Multi-county expansion (Q4):**
8. Onboard next 3-5 counties from MPTS-verified list
9. Onboard 1-2 non-MPTS counties (proves generalization)
10. Unified database (Postgres or SQLite) consolidating all extracted data

**Tier D — Products on top of unified data:**
11. Tax auction dossiers per county (current product)
12. Pre-foreclosure NOD monitoring (from recorder streams)
13. Excess proceeds recovery (from historical auction results)
14. Motivated seller signals (multi-source distress aggregation)
15. Owner intelligence (cross-parcel portfolio detection)

---

## Immediate next task

**Systematic verification pass on the 10 MPTS counties.** For each: hit one real APN, confirm HTTP 200, confirm real data returned, log the tax year and owner-name availability.

That produces a definitive Tier 1 status matrix — 10 counties in an hour, no ambiguity about what works.

Then proceed to systematic ArcGIS probe of remaining 48 counties (Tier B).
