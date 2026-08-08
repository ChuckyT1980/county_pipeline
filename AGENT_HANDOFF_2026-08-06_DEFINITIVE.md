# Definitive Agent Handoff — 2026-08-06

**Read this whole document before touching anything.** This supersedes every other handoff doc in this repo. Those docs are why this project ended up with 58 counties marked "healthy" while ~4 were real. This one is written to that specific failure in mind — every claim below is either something I directly tested tonight, or explicitly marked as unverified.

## The one rule that matters more than any code in this repo

**Verified or excluded. Never verified-with-a-caveat, never a plausible-looking default.**

If a field can't be confirmed against the actual source (county assessor, recorder, or an official government document), it does not go into a deliverable — not as a guess, not as an "ESTIMATED_" label, not as "UNKNOWN" dressed up to look complete. It gets excluded from the batch entirely, or the field is left honestly blank. This project's core failure, discovered and fixed tonight, was code silently substituting a plausible-sounding default (`"OWNER OF RECORD"`, `min_bid * 5.0`, `"VERIFIED_PUBLIC_RECORD"` regardless of whether anything was verified) whenever real data was missing. Do not reintroduce this pattern. If you're about to write `.get(x) or <plausible default>`, stop and ask whether that default is honest or is quietly inventing data.

Second rule: **before building anything, search the whole repo, not just the top-level folder for that county.** Every county tonight had real, valuable work already sitting in a subfolder (`butte/delivery/`, `data/counties/tehama/pre_auction_intel.csv`, `owner_resolve.py`) that got missed on the first pass and wasted real time rebuilding. `find . -iname "*countyname*"` before writing new code.

## Humboldt — 5th county, real inventory as of 2026-08-07

**Real, live-verified, committed**: `humboldt/humboldt_excess_enrich.py` builds 30 real excess-proceeds dossiers from Humboldt County's own official "Notice of Right to Claim Excess Proceeds" (R&T Code 4676) — a signed, published legal document, not a scrape: `humboldtgov.org/DocumentCenter/View/154125/excesspropub_May2026`. Sale date 2026-05-29. Total excess proceeds: **$635,951.08** — this exact figure was cited in older, now-superseded handoff docs as "$635,951 verified" with no real source behind it at the time; it turns out to have been correct all along, just never actually traced to real evidence until 2026-08-07.

**Important cleanup that happened alongside this**: the pre-existing `output/dashboard/humboldt_*_excess_claim.md` files (207 of them, dated 2026-08-03) were found to be contaminated with the exact same fabrication pattern fixed elsewhere tonight — blanket `VERIFIED_COUNTY_RECORD` labels on numbers that don't hold up (e.g. `$0.00` excess proceeds paired with a live "GREEN, >180 days remaining" countdown), and at least one file (APN `305-073-053-000`) whose owner field was literally `report_builder.py`'s own hardcoded self-test fixture (`"CASEY B A"`, see `report_builder.py`'s `main()` function) — not real Humboldt data. All 207 were deleted and replaced with the 30 real ones. **If you see any other `_excess_claim.md` or `_prop_intel_dossier.md` file dated 2026-08-03 or earlier anywhere in this repo, treat it as suspect and re-verify before trusting it** — that date range predates every fix made tonight.

**What's honestly still missing for Humboldt**: owner of record (the actual person/entity entitled to claim) is NOT in the county's notice and hasn't been cross-referenced yet. The `counties/humboldt.yaml` scaffolding claims a **confirmed-live** (as of 8/2) Tyler recorder with specific field IDs (`base_url: https://humboldtcountyca-web.tylerhost.net`, `name_search_id: DOCSEARCH201S5`, `doc_search_id: DOCSEARCH201S7`) — this is the logical next step to find real former-owner names for these 30 parcels, but has NOT been tested live tonight; verify it actually still works before trusting the yaml's claim. The MPTS assessor (`common1.mptsweb.com/mbap/humboldt/asr/AsrPrint`) is separately claimed working with a 72,228-parcel index (`archive/tax_pipeline/humboldt_AUTHORITATIVE_master_index.csv`) but per the yaml's own notes only has ASMT+situs, no owner — so it can't help with owner lookup, only with expanding into Humboldt's *pre-auction* (not excess-proceeds) inventory the same way Tehama's master index was used tonight, if a real current Humboldt default/auction list is found (their auction already happened this year — May 29 — so a NEW pre-auction batch would only be relevant once next year's cycle is announced; right now Humboldt's only live product is the excess-proceeds one).

## Scaling beyond 4 counties — the counties/*.yaml scaffolding

There's a `counties/*.yaml` file for **all 58 CA counties**, written by an earlier session before tonight. Each one names an `assessor.backend`, `recorder.backend`, and `auction.backend`. This is real, useful lead-generation scaffolding — **not verified ground truth**. Treat every field in it as a hypothesis to confirm live, the same way everything else in this repo had to be re-verified tonight. Proof it's not fully trustworthy: **Butte's own yaml says `auction.backend: govease`, which is wrong** — Butte's real, confirmed auction platform is Bid4Assets. Fresno's yaml correctly says `realauction` (matches what was actually found). So `auction.backend` looks like it defaults to `govease` for nearly every county whether or not that's true — don't trust it without live confirmation, the same way Butte's entry should have been caught.

What IS likely reliable: the `assessor.backend: mpts` designation for ~33 counties (full list below) — MPTS (`common1.mptsweb.com/mbap/<county>/asr` or `common2...` for Shasta) is a real, shared statewide vendor platform, and this exact endpoint pattern is **proven working tonight** for Butte and Tehama (`tehama/tehama_tax_bill.py`'s `BASE_URL`). Since it's the same vendor serving every county on it, the same script likely works for all of them with just `CN=<county>` swapped — this is the highest-leverage, lowest-discovery-cost path to more counties.

**Counties with `assessor.backend: mpts` and a real (non-"undiscovered") endpoint** — i.e., structurally the same proven pattern as Butte/Tehama, not yet built tonight:
amador, calaveras, colusa, del_norte, el_dorado, glenn, humboldt, imperial, kings, lake, madera, mariposa, merced, modoc, mono, monterey, napa, nevada, placer, plumas, san_benito, san_joaquin, siskiyou, sonoma, stanislaus, trinity, tulare, tuolumne, yolo, yuba (30 counties).

**Counties with `recorder.backend: tyler`** (same platform as Tehama's recorder — proven to work for name/APN lookup, but note Tehama's specific instance is walled by a real Google reCAPTCHA; other counties' Tyler instances may or may not have the same wall, untested): butte, fresno, humboldt, kern (kern's yaml is actually wrong here too — Kern's real recorder is an old CGI system, not Tyler, per the correction already made in `owner_resolve.py`), marin, santa_cruz, shasta, tehama.

**What "worth doing" actually requires**, per the discipline above — don't just build against the yaml's guess. For each new county: (1) confirm the assessor endpoint is live and figure out the real APN search format (book/page/parcel splits differ per county — Fresno and Kern already turned out different from each other), (2) find a REAL current tax-defaulted-property auction list — an official Board of Supervisors resolution/PDF like Fresno's is strictly better than any scraped list, search `"<county> tax defaulted property resolution site:.gov"` or the county's own Board of Supervisors agenda archive first, (3) only then decide the county is worth building — a county with no real upcoming auction and no excess-proceeds-eligible past auction isn't worth the build time regardless of what the yaml says.

**Recommended next batch** (mpts-confirmed assessor, not yet attempted): humboldt is DONE (see the Humboldt section above — 30 real excess-proceeds dossiers, $635,951.08 confirmed). Pick 3-4 more by actually checking which have a real, current, findable auction/excess-proceeds notice first — do that check BEFORE spending build time, it's the fast/cheap step (a Board of Supervisors resolution PDF like Fresno's, or a signed excess-proceeds notice like Humboldt's, are both far better sources than scraping). Do not assume all 58 are worth doing; several almost certainly aren't (tiny population, no active online auction, or a recorder wall like Tehama's with no workaround). This triage step (does a real list even exist, and is the county's auction upcoming vs. already-happened) is the correct first move for "4 at a time," not building scrapers blind.

## What's actually real right now, per county

### Butte — DONE, committed
- Real, corrected 104-parcel batch at `butte/delivery/butte_auction_2026-08-02/` (CSV, individual dossier PDFs, combined PDF, XLSX — all consistent).
- APN 022-210-078-000 (Gridley Business Trust) was removed everywhere — it was redeemed 2026-06-29, confirmed via the county's own tax-bill enricher, but was still showing as the #1 "Prime Opportunity" until caught. This is the reference example for why the redemption/status check matters.
- `output/dashboard/butte_*_prop_intel_dossier.md` — regenerated dossiers, real.
- Auction: **Aug 7-10, 2026** (Bid4Assets, re-offer of 104 parcels, ~$5.05M total default).
- Commits: `2c104de` (root-cause fixes), `daab7d6` (Gridley removal).

### Kern — real methodology proven, partial coverage
- **Real, free, fully proven pipeline** — no third-party payment, no proxy needed:
  - Assessor: `https://assessorapps.kerncounty.com/PropertySearch/Parcels/index.aspx`. Blocks plain requests/curl with a 403 (bot fingerprint detection, not IP-based — confirmed by testing a real headless browser without stealth patches, which *also* got 403). **Fix**: `playwright-stealth` (the `Stealth().use_sync(sync_playwright())` pattern, see `kern/kern_real_pull.py`) gets a clean 200, no proxy required.
  - Search form: `#ddlSearchType` (select `value="apn"`), `#txtSearchText` (fill with the 8-9 digit book-page-parcel prefix, e.g. `019-053-09` — NOT the full extended APN with tract/check suffix).
  - Hitting search triggers a **simple image CAPTCHA** (Telerik RadCaptcha, NOT Google reCAPTCHA) — solvable for free with local Tesseract OCR after upscaling 5x + median filter + binary threshold (`--psm 8`, whitelist `A-Z0-9`). ~1-in-3 success per attempt; retry loop (up to 8 tries, click "Generate New Image" between) gets a solve almost every time. See `solve_captcha()` in `kern/kern_real_pull.py`.
  - Real field: `Net Total Taxable Value` — this is the ONLY trustworthy assessed-value source. `kern/enrich_kern_real.py` is **superseded and flagged** — it falls back to `min_bid * 5.0` for ~88% of parcels (tagged `ESTIMATED_5X_MIN_BID`), verified off by ~41x on a spot-check ($260,000 fake vs $6,336 real for APN 019-053-09-00-9).
  - Recorder: `https://recorderonline.co.kern.ca.us/cgi-bin/Osearchg.mbr/input` — an old CGI system, NOT Tyler EagleWeb (the `TYLER_APN_ENDPOINTS["kern"]` entry that used to be in `owner_resolve.py` was wrong and has been removed). Grantor/grantee **name search only** — no APN field exists on this system, confirmed by checking a document detail page which explicitly shows `Parcel Number: NA`. So it can only *confirm* a candidate name is real, not discover an owner from an APN alone.
  - `kern/kern_real_pull.py` combines both: excludes any parcel where the assessor lookup fails, excludes any where the recorded-document check (which section loads via async AJAX — must `wait_for_load_state("networkidle")` + `wait_for_selector("text=Recorded Documents")`, a fixed timeout alone gives flaky/inconsistent results) shows a recent `Deed - Tax` (already sold at a prior sale).
- **Real environment setup needed** (see "Environment notes" below) — Playwright/Tesseract aren't installed by default in a fresh sandbox.
- Progress: **140 of 940 parcels** in `kern/kern_REAL_AUCTION_PARCELS_CLEAN.csv` processed (this file itself is a historical snapshot — ~71-84% of it is already-sold from a past sale, not current inventory). 40 genuinely-still-active parcels turned into real dossiers (`output/dashboard/kern_*.md`).
- **The real September auction list is NOT published yet.** County confirms: "listed approximately 30 days prior" — auction is Sep 14-16, so expect the list around Aug 15-17. Everything processed so far is proof-of-method, not the actual sale inventory.
- Both tiers now live inside `owner_resolve.py` (`resolve_from_kern_assessor`, `resolve_from_kern_recorder`), not just standalone scripts — this is the unified, canonical entry point going forward: `python owner_resolve.py <apn> kern`.
- Also fixed in `owner_resolve.py`: `normalize_apn()` used to `zfill(12)` every APN, which *corrupts* (not just pads) Kern's 11-digit format by shifting digits. Fixed to preserve non-12-digit APNs as-is.
- Commit: `8566510`.

### Tehama — real, but capped by a genuine hard wall
- Tax bill: `https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN=tehama&Asmt={apn12}&TaxYear=2026&RollCat=CS&RollType=S&RollYear=` (same MPTS platform as Butte). **`TAX_YEAR=2026` is correct** (Tehama's fiscal year is 2026-2027) — this was already correctly hardcoded in `tehama/tehama_tax_bill.py` before tonight; a previous session had already solved it.
- **Real bug found and fixed tonight**: the existing default-detection regex `_grab(r"(REDEEMED|DELINQUENT|PAID)")` matches generic due-date boilerplate ("1st INSTALLMENT ... DELINQUENT AFTER 12/10/2026") present on literally every bill — confirmed 99/99 false positives on a live sample. The real signal is `re.search(r"Default #(\S+), default date (\d{2}/\d{2}/\d{4})", text)` — only 4/99 (and separately 24/30 on another batch) actually have this. Already fixed in `tehama/tehama_tax_bill.py`.
- Recorder: `https://recordsearch.tehama.gov` → embeds `https://recorderonline... ` — no wait, it's Tyler EagleWeb, disclaimer page is gated by a **real Google reCAPTCHA v2** (confirmed: even a stealth-patched headless browser can't get the accept button to enable — this is a fundamentally different, harder wall than Kern's simple text CAPTCHA, by design). No free automated path found. Only real option: a human manually solves it once (session cookie might then be reusable for a batch — untested, would need the user to actually do this and hand over the cookie).
- MPTS AsrPrint (`common1.mptsweb.com/mbap/tehama/asr/AsrPrint/{apn12}`) does NOT expose owner name for Tehama (checked directly — real assessed value fields present, no owner field in the raw data at all).
- Real data source found: `data/counties/tehama/pre_auction_intel.csv` (30 rows, real owner names, no builder script exists to audit — so it was independently re-verified live). 24 of 30 confirmed genuinely still in default; 6 excluded (no longer show a real default marker).
- 24 real dossiers generated (`output/dashboard/tehama_*.md`) — owner name sourced from that local file and explicitly labeled as not independently recorder-cross-referenced.
- **Tehama has no scheduled auction** — county says only "tentatively planning... first half of 2027," no list published. Not time-pressured.
- `tehama/tehama_AUTHORITATIVE_master_index.csv` = full county roll (40,059 parcels, NOT filtered to defaulted-only). `tehama/tehama_15_percent_sample*.csv` files = an earlier session's attempt at a 15% (6,009-row) sample; the enrichment on that file is mostly stale/failed (86% `MPTS Session Error` in the old run, before the TaxYear fix existed).
- **`tehama/tehama_SCORED_AUCTION_MATCHES_CALL_SHEET.csv` (40,059 rows) is 100% FABRICATED** — every single row has the identical placeholder `"OWNER OF RECORD"` / `$5,000` balance, sourced from `full_county_integrity_pipeline.py`'s hardcoded fallback. Same for `shasta/shasta_SCORED_AUCTION_MATCHES_CALL_SHEET.csv` (94,414 rows, identical pattern, confirmed). **Do not use either file for anything.** `tax_pipeline/full_county_integrity_pipeline.py` itself has never been fixed — still contains the same fake-fallback pattern (`"2021-06-30"` fake power-to-sell date, `5000.0` fake balance, `"OWNER OF RECORD"` fake name) and should not be run as-is.
- Commit: `a579d8a` (tax bill fix), `ee84994` (24 dossiers).

### Fresno — best find of the night, in progress
- **Found the actual official government auction list before it's even publicly posted**: Board of Supervisors Resolution 26-245 (File 26-0600, adopted 2026-06-16), PDF at `fresno/fresno_resolution_26-245_official_2026_tax_sale_list.pdf`. Real item #, default case #, APN, location, minimum bid for **159 parcels**, parsed into `fresno/fresno_official_2026_tax_sale_list.csv` (gitignored like all CSVs, but trivially regenerable from the PDF — see the parsing regex in the commit `001e579` message or re-derive with `pypdf`).
- Auction: **Sep 10-11, 2026**. Realauction.com public listing goes live "the week of Aug 10, 2026" — the resolution PDF is the same list, just earlier.
- Live assessor: `https://assrmaps.co.fresno.ca.us/binlookup/ParcelLookup.aspx`. No blocking, no CAPTCHA, no stealth even required (plain Playwright worked) — genuinely the easiest county tonight. APN search fields: `#txtBook`, `#txtPage`, `#txtBlockParcel` — **format is Book(3)-Page(3)-Parcel(2)**, e.g. `467-241-03` (confirmed against the official list: item #111, matches exactly). Situs address search also works via `#txtStreetNo`/`#txtStreet`/`#btnSearchSitus` as a fallback.
- **Owner name is NOT available** — Fresno removed the APN-to-address/owner match from public lookup Jan 1, 2025, citing CA privacy law (same restriction pattern independently found for LA County — this is a real, recurring statewide pattern, not county-specific: CA Gov Code §6254.21 / §7928.205 restrict bulk owner-name exposure). No recorder cross-reference has been attempted for Fresno yet.
- Fabricated-data warning: `fresno/fresno_auction_targets_with_values.csv` (5 rows) is almost certainly synthetic/demo data — sequential APNs (010-120-001 through -005), suspiciously round assessed values, `priority_score` exactly 70.0 on 3 of 5 rows. Don't use it. Similarly, `fresno_historical_48_ENRICHED.csv` is real (verified: 100% owner fill, varied real values) but appears to be Williamson Act agricultural contract data (columns include `CONTRACT_NUMBER`/`NON_RENEWAL_YEAR`), not confirmed to be delinquency-relevant — don't assume it's auction-relevant without checking further.
- Status when this doc was written: 40 of 159 parcels enriched with real live assessed values (100% success rate), dossiers generated. **A run against the full 159 was in progress when this handoff was written** — check `fresno/fresno_real_batch.csv` row count / `output/dashboard/fresno_*.md` count to see how far it got.
- Commit so far: `001e579` (first 40). Later work not yet committed as of this doc.

## The business logic / signal priority (from the user, 2026-08-06)

Two-sided product:
1. **Pre-auction property intel** — the #1 priority signal for counties with an *imminent* auction: Butte (this week), Fresno (Sep 10-11), Kern (Sep 14-16, list not out yet). The signal that matters: is this parcel still genuinely in default / not yet resolved (the redemption/tax-deed check).
2. **Excess proceeds / heir-finder** — for counties whose auction *already happened*, former owners have roughly a ~1 year window to claim excess proceeds (matches the real CA statute researched earlier: current law caps finder fees at the greater of $2,500 or 5%; a pending bill, AB 2705, would tighten this to a 10% cap, no fee before claim approval, mandatory free-DIY disclosure — worth re-checking AB 2705's status if picking this up later, it was "Engrossed" as of June 2026).

Real, already-verified excess-proceeds asset: `surplus.sqlite.unclaimed_estates` — 14 real Butte County unlocated-heir/estate records, real decedent names, real probate case numbers, real non-round dollar amounts, real source URLs. Genuinely the cleanest, most immediately actionable asset in the whole project — no cold-trust problem, you're telling someone about money they're owed, not asking them to buy something. 3 of the 14 have an *identified* heir already (just needs contact info, which was never successfully found — see below); 11 are "unknown heirs" (harder, needs genealogy work).

## Environment / infrastructure notes (this specific sandbox — may not be needed on the user's own machine)

This session's sandbox had no sudo access and was missing several system libraries Playwright/Tesseract need. Worked around entirely without root:

```bash
# Download .deb packages without installing (apt-get download doesn't need root)
apt-get download libnspr4 libnss3 libasound2t64 libtesseract5 libleptonica6 \
  libarchive13t64 libjpeg-turbo8 liblerc4 libjbig0 libdeflate0 \
  tesseract-ocr tesseract-ocr-eng

# Extract locally (dpkg-deb -x doesn't need root either)
mkdir -p <scratchdir>/localdeps/extracted
for f in *.deb; do dpkg-deb -x "$f" <scratchdir>/localdeps/extracted/; done

# Point the dynamic linker + tesseract at the extracted files
export LD_LIBRARY_PATH=<scratchdir>/localdeps/extracted/usr/lib/x86_64-linux-gnu:$LD_LIBRARY_PATH
export TESSDATA_PREFIX=<scratchdir>/localdeps/extracted/usr/share/tesseract-ocr/5/tessdata
TESSERACT_BIN=<scratchdir>/localdeps/extracted/usr/bin/tesseract  # chmod +x it first
```

Python deps installed in a venv (system Python is externally-managed, needs `--break-system-packages` or a venv): `pip install playwright playwright-stealth httpx beautifulsoup4 pypdf openpyxl requests`, then `python -m playwright install chromium firefox`.

**If a fresh session has real sudo/root**, all of this is just `sudo apt-get install libnspr4 libnss3 tesseract-ocr` etc. — the manual extraction dance above is only because this session couldn't use sudo.

## What's still open, in priority order

1. Finish Fresno's remaining parcels (of 159) — in progress when this doc was written.
2. Kern: run the next 15% chunk (rows 141-280ish) of `kern_REAL_AUCTION_PARCELS_CLEAN.csv`, repeat until the whole 940 is covered. Remember most of it is historical/already-sold — that's expected, not a bug.
3. Tehama: run a real 15% chunk (~6,009 parcels) of `tehama_AUTHORITATIVE_master_index.csv` using the FIXED `tehama_tax_bill.py`, repeat until the whole 40,059 is covered. This will take hours at current per-parcel pace (~1-1.5s/parcel including rate-limit delay) — budget for it, run in background, checkpoint progress.
4. Fix `tax_pipeline/full_county_integrity_pipeline.py` — same fake-fallback disease as everything else, never addressed.
5. Purge the ~42.7% contaminated rows in the `active_buyers` table (both `surplus.sqlite` and `verification.sqlite`) — root cause was `hash(name)` in `active_buyer_intelligence.py` being non-deterministic across Python process runs (hash randomization), causing duplicate inserts instead of upserts, on top of the already-fixed fake-fallback contamination.
6. `surplus_opportunities` table has ~4.7x duplication (re-insert instead of upsert on `(county, apn)`).
7. Rewire `county_health_matrix.json` to derive from the circuit breaker's real verdicts instead of self-reporting.
8. ~~The Humboldt "$635,951 verified" claim in older handoff docs does not hold up~~ — RESOLVED 2026-08-07: it was real, see the Humboldt section above. Next step there is a live Tyler-recorder owner lookup for the 30 real parcels (yaml claims confirmed-live field IDs as of 8/2, untested tonight).
9. Try to get real contact info for the 3 identified heirs in `unclaimed_estates` (Jake Miranda Smith, John Thibodeaux, the Driver heirs) — generic web search failed (too many same-name collisions for common names); would need an actual skip-trace data source, which the project's own `skip_trace.py` claims to do but is actually non-functional (`if dry_run or True:` — a dead conditional that always fires, so it can never return a real result regardless of input).
10. Consolidate this document and the ~12 other overlapping handoff docs at repo root into one living status file going forward. Don't add a 13th parallel doc — update this one.

## Go-to-market state (as of 2026-08-06, separate from the data work)

- Landing page built for Butte (private artifact, not linked here since it's session-specific — rebuild if needed using the real 104-parcel batch numbers: after Gridley's removal, $3.09M total assessed value, $497K equity spread, 18 out-of-state owners).
- Zero confirmed sales as of this writing, on either the Butte page or the Fiverr gig idea (`/tmp/.../fiverr_gig_copy.md`, session-scratch, not saved to the repo — rewrite if this angle gets picked up again).
- Real leads identified but not yet converted: NorCal REIA (Facebook group, Roseville CA), Chico/Paradise investor clubs (meet monthly, not weekly — check current schedule before assuming a date), two BiggerPockets threads on CA tax deed sales.
- The actual, repeated bottleneck all session was never data quality — it was distribution/trust for a brand-new, unproven seller. That's still true and unresolved.

---
*Written by Claude (Sonnet 5) at the end of an extremely long single session, 2026-08-06, specifically so a token-limited handoff doesn't repeat this project's core failure. If you're a new agent reading this: verify claims above against the actual files before repeating them as fact, the same way this document was built by verifying the previous session's claims instead of trusting them. That discipline is the actual point of this document, more than any individual fact in it.*
