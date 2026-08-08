# DOSSIER_QA Report

**Run date**: 2026-08-08
**Scope**: All existing pre-auction property-intelligence dossiers (Butte 104, Kern 245, Lake 16) and excess-proceeds dossiers where relevant to identifier integrity (Del Norte 9). Riverside/San Diego/Kings/Glenn produced zero dossiers - not applicable to dossier-content checks.

**Overall verdict: REQUIRES REMEDIATION.** Two confirmed, universal, high-severity findings in Kern's current 245 dossiers; one latent (not yet triggered) defect in shared code; everything else checked passes.

---

## 1. Identifier integrity

| Check | Result |
|---|---|
| ATN and APN not conflated | **FAIL - Kern, 245/245 (100%)**. Every existing Kern dossier's `**APN**:` field actually contains the ATN (5-segment format, e.g. `017-490-06-00-3`), not the assessor's real, shorter parcel number (`017-490-06`). Confirmed by exhaustive scan, not sampling. Root cause identified and modeled in `property_model.py` (commit `fa2c300`) and 10 real records correctly converted in `docs/kern_butte_migration_test.md` - but the 245 live dossiers themselves have NOT been regenerated with the fix yet. |
| Tax-default/Power-to-Sell identifier not presented as assessor parcel number without independent verification | PASS for Butte/Lake/Del Norte (single, consistent APN sourcing, no dual-identifier confusion found). Kern's failure above is the identifier-TYPE conflation, not this specific check. |
| When both ATN and APN are known, stored/displayed as distinct fields with source attribution | **FAIL for live dossier output** (only one field exists, mislabeled). PASS for the `property_model.py` foundation (correctly separates them, real source attribution on each). |

**Remediation required**: regenerate Kern's 245 dossiers through `property_model.py`'s corrected identifier derivation, or at minimum relabel the existing field and add the real assessor_parcel_number alongside it. Not performed this run - this is buyer-facing output; recommend explicit approval before a 245-file regeneration given how much weight exact wording has carried this session.

---

## 2. Lifecycle classification

| Check | Result |
|---|---|
| "Listed" / "tax-defaulted" / "pre-auction" / "auction scheduled" / "auction confirmed" / "sold" / "redeemed" / "excess proceeds available" kept as separate states | PASS for Butte (post-auction, correctly shows a different signal, no "going to auction" claim), Lake (explicitly "No scheduled auction — monitor for a future sale date" where true, "still tax-defaulted" only where recorder-confirmed), Del Norte (excess-proceeds dossiers correctly state ACTIVE_CANDIDATE via the state machine, not conflated with auction status). |
| No record labeled "auction confirmed" without evidence from an official auction source | **FAIL - Kern, 245/245 (100%)**. Every dossier states `PRIORITY SIGNAL: GOING TO AUCTION in 37 days (2026-09-14 - 2026-09-16)`. The auction DATE is real and confirmed (county public notice). What is NOT confirmed is that this SPECIFIC parcel will be on that sale's list - the live, current parcel-level list has not been published yet (per `county-name-assessor-data-access-58.csv`: "Real current list NOT yet published (expected ~Aug 15-17)"). The underlying data source (`kern_REAL_AUCTION_PARCELS_CLEAN.csv`) is explicitly documented as a historical snapshot. Stating a specific parcel is "GOING TO AUCTION" overclaims parcel-level confirmation that doesn't yet exist. |
| Lake lifecycle classifications preserve evidence for sold/redeemed/stale/active/unknown | **PASS, independently re-verified**. Spot-checked APN `005-012-300-000`'s cited lien document (`2025007922`) directly against `lake/lake_lien_classification_ALL.json` before the original merge - matches exactly. The one parcel with a genuine assessor/recorder discrepancy (`032-042-330-000`) was correctly excluded rather than shipped, with its own exception log entry. |

**Remediation required**: Kern's "GOING TO AUCTION in N days" wording needs to change to something honest about the date-vs-parcel-listing distinction (e.g. "County auction confirmed for [date]; this parcel's inclusion on the final list is not yet published") until the real Sept 2026 list is out and each parcel can be individually cross-checked against it.

---

## 3. Source / evidence integrity

| Check | Result |
|---|---|
| No estimated value labeled a minimum bid unless from an official auction source | **Latent defect found, NOT currently triggered.** `report_builder.py:154` silently falls back to `assessed_value * 0.25` when no real min_bid is available, displayed under the identical "Minimum Starting Bid" label with no distinguishing disclosure - a real violation of this rule if it ever fires. Checked all 374 current property-intel dossiers (Kern 245, Butte 104, Lake 16, Del Norte n/a): **0/374 currently use this fallback** - every existing dossier has a real, source-provided min_bid value. Flagged as a real code-level risk for future counties, not a current data-integrity breach. |
| No lien-risk conclusion labeled LOW without lien/deed/recorder/title review | **FAIL - all counties, by design of the current scoring code.** `predictive_scorer.py`'s `lien_risk` field (`HIGH`/`MEDIUM`/`LOW`/`UNKNOWN`) is computed purely from `equity_ratio` (assessed value vs. min bid) - a financial heuristic, not an actual review of recorded liens, deeds, judgments, or title. 45 of 245 Kern dossiers currently display `Lien Risk Tier: LOW`, and this same computed field is used identically across Butte and Lake. The label implies a real lien review was performed; it was not. |
| Missing source fields surfaced as explicit gaps, not silently filled/implied | **PASS, universal.** 245/245 Kern, 104/104 Butte, 16/16 Lake, 9/9 Del Norte all carry an explicit `Data Gap Audit` / `Verification Receipt` field naming exactly what's missing (e.g. `Missing: doc_count, transfer_tax, buyer_match`). |
| Every correction retains evidence and a traceable reason | **PASS.** Verified directly: Del Norte APN `029-270-053-000`'s dossier explicitly documents correcting a stale source-list name ("HOUTS DORA DAVIS") against a more recent real recorded transfer ("COLOTI RENE"), with the actual document evidence cited. |

**Remediation required**: rename `Lien Risk Tier` (and/or its underlying label) to something that doesn't imply a completed lien/title review - e.g. "Equity-Based Risk Proxy" - across the shared template, since this affects every property-intel county, not just one. The 25%-fallback minimum-bid risk should get an explicit label distinguishing "official minimum bid" from "estimated (25% of assessed value)" before any future county without real bid data is processed.

---

## 4. County-access constraints

| Check | Result |
|---|---|
| County-level access failures represented as access constraints, not negative inventory results | **Mostly PASS, one gap found.** Glenn, Riverside, San Diego's `Status` column text in `county-name-assessor-data-access-58.csv` all explain the real reason (Cloudflare, DBMS outage, Akamai+legal restriction+closed cycle respectively). **Kings' Status cell is just the bare word `Red`** with no explanatory text in that column (the real reason lives only in the separate `Complications`/exception-log entry) - a reader scanning the Status column alone could misread this as "no properties exist" rather than "recorder has no online deed-search feature." Fixed in the new county status matrix (Section 7 requirement) by giving every blocked county an explicit, self-contained reason in the same cell. |

---

## 5. Contamination checks

| Check | Result |
|---|---|
| No mismatched/out-of-jurisdiction evidence in a county folder without explicit exception/quarantine | **One real instance found and resolved.** `kings/kings_tax_sale_notice.pdf` was confirmed (via direct PDF text extraction) to be a Nova Scotia, Canada municipal tax-sale notice (`countyofkings.ca`, "Municipality of the County of Kings," Coldbrook Village Park Drive) - not Kings County, California. It was NOT relied upon for the actual Kings-blocked conclusion (which rests on direct Tyler EagleWeb menu-tree testing, independently re-verified). Renamed to `kings/CONTAMINATED_NOT_CALIFORNIA_KingsCountyNovaScotia_tax_sale_notice.pdf` to flag it and prevent future confusion; audit trail preserved, file not deleted. Formal exception record added in Section 6 of this dispatch (see `county_exception_ledger.csv`). |

---

## Summary verdict

| Category | Verdict |
|---|---|
| Identifier integrity | FAIL (Kern, 245/245) |
| Lifecycle classification | FAIL (Kern auction-confirmation wording, 245/245); PASS elsewhere |
| Source/evidence integrity | FAIL (lien-risk labeling, all counties); latent-only (min-bid fallback) |
| County-access constraints | PASS with one matrix-formatting gap (Kings), fixed in Section 7 |
| Contamination checks | PASS (one instance found, already resolved and documented) |

**Nothing here means the underlying verified data is wrong** - the real assessor/recorder cross-matches, document numbers, and dollar amounts checked out in every spot audit performed this session. The failures are all in **labeling/wording**, exactly the category this pipeline has treated as seriously as the underlying data all session. None of the three failing checks were caught by a prior review; all three are being surfaced for the first time in this QA pass.
