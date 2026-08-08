# DOSSIER_QA Report — Post-Remediation Rerun

**Run date**: 2026-08-08
**Scope**: Kern (245), Butte (104), Lake (16) — all regenerated this remediation pass. Del Norte (9 excess-proceeds) unaffected, not in scope for this rerun. Riverside/San Diego/Kings/Glenn: 0 dossiers, not applicable.

**Overall verdict: PASS.** All three findings from the original QA pass are confirmed remediated, exhaustively (not sampled) across every existing record.

---

## Kern identifier-integrity result across all 245 records

**PASS, 245/245.** Exhaustive scan: 0 dossiers retain the old mislabeled `**APN**:` line; 0 are missing the new `**Assessor APN**:` field. Every dossier now shows:
- `**Source Identifier**`: the raw ATN, explicitly labeled `(ATN (Assessment/Tax Number, Kern tax-roll identifier))`
- `**Assessor APN**`: derived from the ATN's own first 3 segments (`property_model.py:atn_to_assessor_parcel_number`)
- `**Assessor APN Verification Status**`: `NOT_VERIFIED` in every case — honestly states the derivation was cross-checked against a second column from the *same* source list, not independently confirmed by reading the assessor's own displayed APN field (which `kern_real_pull.py`'s parser never captured). No record was silently upgraded to "confirmed."

## Kern lifecycle-language result across all 245 records

**PASS, 245/245.** 0 dossiers contain "GOING TO AUCTION." Every dossier now states: *"Tax-default / Power-to-Sell public-record indicator; parcel-specific auction status not verified (county auction window confirmed 2026-09-14 to 2026-09-16, but this parcel's presence on the current, official parcel-level auction list has not been independently confirmed)."* The real, confirmed county-wide auction date is preserved; the false implication of parcel-specific list confirmation is removed.

## Buyer-facing auction-confirmation language without official parcel-specific evidence

**None found**, across Kern, Butte, or Lake. Butte and Lake's own signals were already accurate (Butte: real, occurred, confirmed 104-parcel batch; Lake: explicit "No scheduled auction" or "still tax-defaulted, recorder-confirmed" language, never a specific future auction claim).

## Buyer-facing lien/title/risk terminology implying an actual lien or title review

**None found**, across all three counties. `grep` for "Lien Risk Tier" across `output/dashboard/{kern,butte,lake}_*.md`: 0 occurrences. Every dossier now shows `**Equity / Assessed-Value Indicator**` with the inline disclaimer *"derived from available valuation and recorded amount data only. It is not a title search, lien-priority analysis, encumbrance review, or legal conclusion"* — confirmed present in all 365 dossiers (245+104+16).

## Butte redemption-filter test result and post-fix monitor result

- **Regression test**: `tests/test_butte_redemption_filter.py` — **2/2 passed.** `test_is_redeemed_unit` (direct unit checks of the extracted `is_redeemed()` function) and `test_redeemed_parcel_never_regenerated_end_to_end` (a real, temp-directory, end-to-end run through the actual `regen_butte_dossiers.main()` + `report_builder.build_property_intelligence_dossier()` with a redeemed-parcel fixture matching the real Gridley case — proven to fail before the fix, pass after).
- **Post-fix monitor rerun**: `regen_butte_dossiers.py` executed for real. **Prior count: 104. Revised count: 104. Records removed: 0 net change this rerun** (Gridley was already correctly excluded by the fix applied in the prior BUTTE_MONITOR pass, commit `e5e1aa6` — this rerun's only content change was picking up the new Equity/Assessed-Value Indicator template). Full correction history for Gridley (022-210-078-000) preserved in `remediation/remediation_log.csv`.
- **Honest verification-scope statement**: Butte's 104 dossiers are confirmed **redemption-filter-clean and correctly relabeled**, verified by full regeneration from the real, unmodified source CSVs. They are **not** claimed to be fully current in every other respect — only an 8-parcel live HTTP sample was checked against the assessor this session (`monitor_runs/butte_live_sample_check.log`), not a full 104-parcel live re-verification of value/status/ownership drift since original enrichment.

## Lake and Butte shared lien-risk terminology result

**PASS, both counties, exhaustive.** Butte: 0/104 retain the old label, 104/104 show the new one with disclaimer. Lake: 0/16 retain the old label, 16/16 show the new one with disclaimer. Lake's 16 dossiers were regenerated via `lake/lake_generate_dossiers.py` against its existing, already-verified local classification data (`lake_still_defaulted_full.csv`) — no new live fetching performed or required.

---

## Release decision per county

| County | Release Decision |
|---|---|
| **Kern** | **READY_WITH_LIMITATIONS** — identifier and lifecycle-language defects fully remediated and verified exhaustively. Limitation: `assessor_apn` is a sound derivation, cross-checked, but explicitly NOT independently confirmed against a live assessor read (full CAPTCHA-solving re-verification remains blocked — tesseract/playwright not installed, no new dependencies authorized this ticket). Buyer-facing text is now honest about this; no content is release-blocking. |
| **Butte** | **VERIFIED_READY** — redemption filter confirmed wired to the production path, proven by a real regression test (2/2 passing) and a real end-to-end rerun (104 dossiers, Gridley correctly and permanently excluded). Shared lien-risk relabeling applied and verified. Verification scope for non-redemption drift (value/status changes since original enrichment) remains sample-based (8/104 live-checked) — stated honestly, not release-blocking. |
| **Lake** | **VERIFIED_READY** — lien-risk terminology remediated and verified (16/16). No identifier or lifecycle-wording defects were ever found here; the county's own recorder-based lien-lifecycle classifier (built by COUNTY_PROCESSOR_B) already independently spot-checked. |
| **Del Norte** | **VERIFIED_READY** (excess-proceeds intelligence) — unaffected by this remediation pass; retains its prior verified status with eligibility/availability limitations already stated in every dossier's Claimant Eligibility Note. |
| **Glenn** | **BLOCKED** — unchanged, real Cloudflare access constraint. |
| **Kings** | **BLOCKED** — unchanged, real structural recorder-feature gap; Nova Scotia contamination quarantine unchanged. |
| **Riverside** | **BLOCKED** — unchanged, real reproducible DBMS service outage. |
| **San Diego** | **NO_ACTIVE_CYCLE** — unchanged; legal restriction + Akamai block + closed auction cycle, per the county_exception_ledger.csv row already documenting all three. |

**Nothing in this repository is currently unsafe for buyer-facing release on the specific grounds audited by this QA pass** (identifier integrity, auction-confirmation wording, lien/title terminology). The only remaining caveat is Kern's `assessor_apn` verification level (NOT_VERIFIED, honestly labeled) and the sample-based (not exhaustive) live drift-check scope for Kern and Butte — both are disclosed in-product, not concealed, and neither was found to actually be wrong in any spot check performed this session.
