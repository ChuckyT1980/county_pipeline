# Backfill Spec — Owner Names / Estate Flags / Addresses (runs BEFORE sales-equity)

**For:** implementer (GLM 5.2 or dev).
**Why this exists:** the last sales/equity run returned `excess_proceeds_candidates: 0` and got a green check. That's wrong — it ran against a stale file where 12 parcels are still nameless and unflagged, so the estate-routing logic had nothing to route on. This step supplies the missing upstream data. **It must run before the sales/equity pass, not after.**
**Data file:** `butte_backfill_12.csv` (ships with this spec — the exact values to merge).
**Scope this run:** the current 105 only. Do NOT expand to 303 in this step (that's the next, separate task).

---

## 0. Source-of-truth rule (read first — this is the actual bug)

The last run drifted because two files hold parcel data and the scorer read the wrong one.

- **`butte_auction_intel_2026-07-31.csv` (71-field master) is the single source of truth.** Backfill lands here.
- **`butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv` is a derived projection.** It must be **regenerated from the master**, never hand-edited.

If the call sheet is currently produced by an independent path (not regenerated from the master), **fix that** — make it a projection of the master. Otherwise every enrichment will keep drifting out of the file the scorer reads, and this exact bug recurs. Acceptance criterion 8 below checks for this.

---

## 1. What to merge

Join `butte_backfill_12.csv` to the master on `apn`. For each of the 12 parcels, write:

| Target column (master) | From backfill file | Notes |
|---|---|---|
| `verified_current_owner_name` | `verified_current_owner_name` | was blank on these 12 |
| `owner_name_source` | `owner_name_source` | real provenance — all 12 trace to the county 5-4-26 list; most cross-verified against the 2023-24 list and/or recorder power-to-sell |
| `owner_name_confidence` | `owner_name_confidence` | do not leave at the old default |
| `ownership_flags` (append) | `owner_class`, `estate_or_deceased` | append `estate` / `trust_involved` where set; don't overwrite existing flags |
| `excess_proceeds_candidate` | `excess_proceeds_candidate` | **5 true** (the estates) — this is the number the last run got wrong |
| `situs_address` | `situs_address` | only where non-empty (3 recovered from the list) — do NOT blank an existing situs |
| `situs_address_source` | `situs_source` | tag provenance |
| `needs_review` | `needs_review` | flags the 2 GIS-required + the McDonnell entity-review case |

Merge rules: match on `apn`; update only the 12 rows; **never coerce a blank to 0**; append to flag columns rather than overwrite; leave all other parcels untouched.

---

## 2. The three sub-cases the data encodes (don't flatten them)

**Estates → excess-proceeds inventory (5 parcels).** Bates, Stutrud, Illman, Svensson, Baron carry `estate_or_deceased = true` and `excess_proceeds_candidate = true`. These are deceased-owner parcels: heirs, probate, and surplus if they sell. This is the flag whose absence made the last run report 0 candidates. After this backfill, the sales/equity pass will find 5 and route them to the estate track. Svensson additionally has 10 named co-heirs — keep the full owner string.

**Addresses recovered from the county list (3 parcels).** McDonnell → Lot 11 Azalea Lane; Jackman → Sec 12 T20N R5E (a legal description, not a street — valid locator); Baron → Grubbs Rd. Write these to `situs_address` with `situs_source = butte_5426_list`.

**Genuinely address-less land (2 parcels).** Tatum and Weldon: the county's own list says NOT DESIGNATED — there is no street or legal description on record. `situs_source = gis_centroid_required`, `needs_review = true`. Do NOT fabricate an address. These get a GIS parcel-centroid + acreage in a later GIS step; for now they carry the flag so they're not mistaken for missing data.

**One review case:** McDonnell (062-300-007) reads "DONALD C REV & MISSIONARY APOSTOLATE" — likely a clergy/religious-entity ownership, not a decedent estate. Flagged `entity_religious_review`, `excess_proceeds_candidate = false`, `needs_review = true`. Do not auto-flag it as an estate; leave the determination to verification.

---

## 3. Run order (the fix is sequencing)

1. **This backfill** → master CSV (12 rows updated).
2. **Regenerate** the call sheet (and dossiers) from the master.
3. **Then** run the sales/equity pass (the existing `enrich_sales_equity.py`) against the regenerated data.
4. Re-audit.

Running sales/equity before steps 1–2 reproduces the `0 candidates` bug.

---

## 4. Two corrections to fold into the sales/equity RE-RUN

While re-running, fix two things the last audit masked:

**(a) The equity-band labels are overstated.** Bands (`thin/moderate/high`) are defined as percentages of a market-to-proxy gap, but there is **no `market_estimate` source built** — so those bands are actually tenure-derived. Print two breakdowns to prove it:
- `equity_confidence` counts — expect ~93 `tenure_proxy`, 12 `unknown`, and **0 `measured`**. If anything shows `measured`, someone fed in a market estimate that doesn't exist (likely the assessed value — the forbidden `assessed − assessed` inversion). Investigate before shipping.
- `market_estimate_source` counts — expect ~all `none`.
Until a real market estimate exists, surface these as tenure-confidence, not as measured "%equity" — a buyer reads ">50% equity" as a dollar claim you can't yet back.

**(b) Spot-check 3 "high" parcels** — print `market_estimate`, `sale_price_proxy_assessor`, and the computed gap, so a human can confirm "high" means a real gap and not just "held a long time."

---

## 5. Acceptance criteria (corrected from last run)

1. All 12 target parcels have a non-blank `verified_current_owner_name` with a real `owner_name_source`.
2. **`excess_proceeds_candidate = true` count is 5** (Bates, Stutrud, Illman, Svensson, Baron) — NOT 0. This is the criterion the last run failed while reporting success.
3. `UNKNOWN_ROUTE` parcels that are estates now also carry `excess_proceeds_candidate = true` — the two no longer contradict.
4. 3 parcels gain a `situs_address` from the list; 2 (Tatum, Weldon) carry `gis_centroid_required` and are NOT given a fabricated address.
5. No blank coerced to 0 anywhere; `unknown`/empty preserved.
6. Call sheet is a regenerated projection of the master (diff them: the 12 rows match).
7. Sales/equity re-run prints the `equity_confidence` and `market_estimate_source` breakdowns from §4; `measured` count is 0 (or explained).
8. `score_version` bumped; per-feature contributions present.

---

## 6. Next step (not this run)

Once the 105 backfill is clean and the 5 candidates surface correctly, expand the roster to the **303 active parcels** from the 5-4-26 county list (through the live-verify pass), then re-run backfill + sales/equity on the full set. Keep this backfill's source-of-truth and no-coercion rules for that expansion.
