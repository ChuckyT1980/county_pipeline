# Excess-Proceeds Inventory — Release Report

**Run date**: 2026-08-08
**State machine version**: 1.1.0
**Release tag**: `state-machine-v1.1.0`

This report exists to answer one question before any lead is marketed or
sold: *does every ACTIVE_CANDIDATE record actually trace, unbroken, from
a real county source document to the dashboard feed?* It documents a
cycle-level reconciliation, a manual 3-record audit, the automated
release-gate results, and — separately — the records that are explicitly
excluded and why.

---

## 1. Madera Reconciliation

Madera has **three** distinct sale cycles. Two are verified and active.
One is neither, and must not be confused with the other two just because
all three involve the word "Madera" and dates near each other.

| Sale Cycle | `sale_cycle_id` | Status | Source Artifact | Auction / Sale Date | Deed Recorded | Claim Deadline | Deadline Evidence |
|---|---|---|---|---|---|---|---|
| 2025 May original sale | `madera_2025-05_sale` | **EXCLUDED / UNVERIFIED** | *Not downloaded.* Seen listed as "2025 FINALIZED EXCESS PROCEEDS - MAY 2025" on the county page, never fetched or read. | Unknown | Unknown | Unknown | **None** — never verified. Previously *assumed* likely-expired based on typical 1-year timing; that assumption was never checked against the real document. Zero records extracted from this cycle. |
| 2025 August Re-Offer | `madera_2025-08-08_reoffer` | **ACTIVE_CANDIDATE** | `sha256:7d17a723...` (`madera_2025_august_reoffer_excess_proceeds.pdf`) | Aug 8, 2025 | Aug 27, 2025 | **2026-08-27** | Stated directly in the document: *"Excess Proceeds Claim forms are due: August 27, 2026."* 19 days remaining as of run date. |
| 2026 May sale | `madera_2026-05-11_to_05-14_sale` | **ACTIVE_CANDIDATE** | `sha256:56cea126...` (`madera_2026_finalized_excess_proceeds.pdf`) | May 11–14, 2026 | Jun 8, 2026 | **2027-06-08** | Stated directly in the document: *"Excess Proceeds Claim forms are due: June 8, 2027."* |

**The reconciliation, made explicit:**

```
Madera 2025-05 sale cycle   → EXCLUDED / UNVERIFIED   (never downloaded — 0 records)
Madera 2025-08 Re-Offer     → ACTIVE_CANDIDATE          (verified artifact + deadline — 6 records, deadline 2026-08-27)
Madera 2026-05 sale cycle   → ACTIVE_CANDIDATE          (verified artifact + deadline — 19 records, deadline 2027-06-08)
```

The 25 Madera `ACTIVE_CANDIDATE` records in the lead registry belong
**exclusively** to the two verified cycles (6 + 19 = 25). The excluded
May 2025 cycle contributed **zero** records to that count — it was never
extracted, and `release_gate.py` check 6 confirms `madera_2025-05_sale`
does not appear in any dossier, feed entry, lead row, or buyer export.
The "deadlines from 2026-08-27 through 2027-06-08" range spans the two
*verified* cycles only, and each Madera row in the registry carries its
own `sale_cycle_id` — they are never merged into one undifferentiated
Madera bucket.

---

## 2. Human Spot Audit (3 records)

Manually traced, source document to dashboard feed, before this release.

### 2a. Nearest deadline — Madera, `029-270-053-000`

| Step | Value |
|---|---|
| Official source document | `madera/madera_2025_august_reoffer_excess_proceeds.pdf` (sha256 `7d17a723...`) |
| Source page / row | Item No. 11: `029-270-053-000 MILLER CAROLYN 96,235.49` |
| APN | `029-270-053-000` ✓ matches |
| Amount | `$96,235.49` ✓ matches |
| Sale cycle | `madera_2025-08-08_reoffer` (Aug 8 2025 auction, Aug 27 2025 deed) ✓ correct cycle |
| Deadline | Document states "Excess Proceeds Claim forms are due: August 27, 2026" → `2026-08-27` ✓ matches |
| Dossier state | `output/dashboard/madera_029270053000_excess_claim.md` — `Status: ACTIVE_CANDIDATE`, all fields match the source row exactly |
| Dashboard-feed entry | `apn: "029-270-053-000"`, `owner: "MILLER CAROLYN"`, `excess_amount: 96235.49`, `claim_deadline: "2026-08-27"`, `lead_status: "active_candidate"` ✓ matches |

**Result: traces cleanly, end to end.**

### 2b. Long-deadline record — Madera, `001-052-010-000`

| Step | Value |
|---|---|
| Official source document | `madera/madera_2026_finalized_excess_proceeds.pdf` (sha256 `56cea126...`) |
| Source page / row | Item No. 1: `001-052-010-000 GOWIN DAVID ROY SR TRUSTEE 146,266.34` |
| APN | `001-052-010-000` ✓ matches |
| Amount | `$146,266.34` ✓ matches |
| Sale cycle | `madera_2026-05-11_to_05-14_sale` (May 11–14 2026 auction, Jun 8 2026 deed) ✓ correct cycle — distinct from 2a's cycle |
| Deadline | Document states "Excess Proceeds Claim forms are due: June 8, 2027" → `2027-06-08` ✓ matches |
| Dossier state | `output/dashboard/madera_001052010000_excess_claim.md` — `Status: ACTIVE_CANDIDATE`, includes an explicit note that "TRUSTEE" in the name may mean the real claimant is an heir/successor, not the printed name |
| Dashboard-feed entry | `apn: "001-052-010-000"`, `owner: "GOWIN DAVID ROY SR TRUSTEE"`, `excess_amount: 146266.34`, `claim_deadline: "2027-06-08"` ✓ matches |

**Result: traces cleanly, end to end. Confirms the two Madera cycles are genuinely distinct — different source PDFs, different item numbers, different auction dates, different deed-recording dates, different deadlines.**

### 2c. San Joaquin — `027-134-130-000` (chosen specifically to re-test the fixed county-parsing bug)

| Step | Value |
|---|---|
| Official source document | `san_joaquin/san_joaquin_excess_proceeds_march2026.pdf` (sha256 `cb1f60fc...`) |
| Source page / row | Item 2: `027-134-130-000  DEF-200-000-183  LODUCA, SHANNON TR  2101 CABRILLO CI, LODI  $32,916.66  $427,500.00  $394,583.34` |
| APN | `027-134-130-000` ✓ matches |
| Amount | `$394,583.34` (excess proceeds column, purchase price minus redemption amount) ✓ matches |
| Sale cycle | `san_joaquin_2026-03-11_to_03-12_sale` ✓ correct — **and correctly labeled "San Joaquin," not "San"** |
| Deadline | Not individually stated for this parcel; approximated as sale date + 365 days → `2027-03-12`, explicitly marked APPROXIMATE in the dossier |
| Dossier state | `output/dashboard/san_joaquin_027134130000_excess_claim.md` — `Status: ACTIVE_CANDIDATE`, situs `2101 CABRILLO CI, LODI` and doc number `DEF-200-000-183` both match |
| Dashboard-feed entry | `apn: "027-134-130-000"`, `owner: "LODUCA, SHANNON TR"`, `excess_amount: 394583.34` ✓ matches |
| Lead registry row | `county: "San Joaquin"` (not "San") ✓ the earlier filename-splitting bug (`san_joaquin_...` → `"san"`) is confirmed fixed |

**Result: traces cleanly, end to end. The county-name bug fix holds under direct audit — this county's 3 leads are no longer silently orphaned into an `UNKNOWN-CYCLE` bucket.**

**All three spot-audited records trace correctly from raw county artifact to dashboard output. The release process is credible for this batch.**

---

## 3. Excluded Cycles and Why They Are Not Marketed

Three sale cycles are excluded from `ACTIVE_CANDIDATE` inventory as of
this release. None of their records appear in any dossier, the dashboard
feed, the active lead count, or any buyer export — enforced by
`release_gate.py` check 6, not just asserted here.

| Cycle | `sale_cycle_id` | Why excluded | Records affected |
|---|---|---|---|
| Madera, May 2025 sale | `madera_2025-05_sale` | Source document never downloaded or read — an "unverified" exclusion, not a "confirmed bad" one. Previously, incorrectly, assumed likely-expired without checking. | 0 (never extracted) |
| Nevada, Nov 2024 sale | `nevada_2024-11-07_sale` | **EXPIRED.** Real, verified deadline (Nov 27, 2025) has passed. This is the resolved incident that motivated the whole `lead_status.py` state machine: the "Dec 2026" figure originally reported for Nevada belonged to a *different*, later Nevada cycle, not this one. | 0 (0 records ever extracted from this specific cycle; the real Dec 2026 figure is correctly attributed to `nevada_2025-11-13_sale_and_2026-01-28_reoffer`, which IS active) |
| Sonoma, Nov 2025 auction | `sonoma_2025-11-07_to_11-10_auction` | **Demoted at this release gate.** Real minimum-bid and sale-price data were read from the county's own results table, but the results page itself was never saved/hashed as an artifact — only the extracted rows exist. Per the state machine, `SOURCE_VERIFIED` requires an actual preserved, hashable artifact, not just a citation string. Demoted from `ACTIVE_CANDIDATE` to `UNKNOWN`. | 18 (demoted, not discarded — real data retained in the lead registry and dossiers, just excluded from active/marketed inventory pending re-scrape) |

**Net effect on this release**: 130 dossiers evaluated → **112 ACTIVE_CANDIDATE**, **18 UNKNOWN** (Sonoma, pending artifact re-capture), **0 EXPIRED** (Nevada's expired cycle correctly contributed zero records rather than a nonzero-then-filtered count).

To re-activate Sonoma: re-fetch and hash the county's live auction-results page, update `county-sale-cycle-registry.csv`'s Sonoma row with the real `sha256:` artifact ID, and re-run `sonoma/sonoma_excess_enrich.py` + `build_lead_registry.py`. To resolve Madera's May 2025 gap: download and read the actual "2025 FINALIZED EXCESS PROCEEDS - MAY 2025" document before asserting anything about it either way.

---

## 4. Automated Release Gate (`release_gate.py`)

Run against 112 `ACTIVE_CANDIDATE` rows and 11 sale-cycle registry rows:

| # | Assertion | Result |
|---|---|---|
| 1 | Every ACTIVE_CANDIDATE has a nonempty `sale_cycle_id` | PASS (0 failures) |
| 2 | Every ACTIVE_CANDIDATE has a real source artifact hash (`sha256:<64 hex>`, not a placeholder) | PASS (0 failures) — this check is what caught and demoted Sonoma |
| 3 | Every ACTIVE_CANDIDATE has a future, re-parsed claim deadline | PASS (0 failures) |
| 4 | Every ACTIVE_CANDIDATE's `sale_cycle_id` resolves to the correct, active county cycle in the registry | PASS (0 failures) |
| 5 | No `WIRING-TEST` / test-fixture identifier appears in `dashboard_feed.json` | PASS (0 failures) |
| 6 | No excluded cycle (`madera_2025-05_sale`, `nevada_2024-11-07_sale`, `sonoma_2025-11-07_to_11-10_auction`) appears in any dossier, feed entry, lead row, or buyer export | PASS (0 failures) |

**Overall: PASS — safe to release.**

Raw result: `release/release_gate_result.json`. Re-run any time with
`python3 release_gate.py` — it exits nonzero on any failure, so it can be
wired into CI or a pre-outreach checklist directly.

---

## 5. Regression Test Suite (`tests/test_lead_status.py`)

10/10 tests passing at release time, including the 5 specifically
required for this release:

1. Past deadline → always `EXPIRED` (`test_past_deadline_is_always_expired_never_active`)
2. Missing/unparseable deadline → always `DEADLINE_UNVERIFIABLE` (maps to `UNKNOWN`) (`test_missing_deadline_never_reaches_active`, `test_unparseable_deadline_never_reaches_active`)
3. Future verified deadline → can produce `ACTIVE_CANDIDATE` (`test_future_deadline_with_amount_reaches_active_via_possible`, `test_future_deadline_without_amount_reaches_active_via_unconfirmed`)
4. County-level expired sale cycle prevents every linked dossier from becoming `ACTIVE_CANDIDATE` (`test_expired_sale_cycle_forces_expired_regardless_of_own_deadline`)
5. No lead status can be manually set outside the state machine (`test_no_status_can_be_set_outside_the_state_machine`)

---

## 6. Product Wording

`ACTIVE_CANDIDATE` remains the only term used for public/internal
inventory. No record is labeled `CLAIMABLE` anywhere in the templates,
registries, or this report — every dossier's Claimant Eligibility Note
states explicitly that claimant identity and priority require separate
verification before outreach (R&T Code §4675 priority order).
