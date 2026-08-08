# Session Handoff — 2026-08-06

## What's real and done
- **Butte**: corrected delivery package at `butte/delivery/butte_auction_2026-08-02/` is the authoritative source — 104 active parcels, Gridley Business Trust (APN 022-210-078-000) removed from every file (CSV, individual PDF, combined PDF, XLSX) after confirming it was redeemed 2026-06-29. Landing page updated to match. Committed: `daab7d6`.
- **Root-cause fixes** (prior commit `2c104de`): `report_builder.py`, `predictive_scorer.py`, `active_buyer_intelligence.py` no longer fabricate plausible defaults — missing data renders as unverified/excluded, not guessed.

## What's real but incomplete
- **Kern**: 940 real owner/APN/min-bid rows exist (`kern_REAL_AUCTION_PARCELS_CLEAN.csv`). Assessed value is currently a fake `5× min_bid` formula — needs real assessor data. Official Kern Assessor site and ParcelQuest both return HTTP 403 (active bot-blocking), confirmed directly, consistent with two prior failed automated attempts. `kerndata.com` has real data but is paid — explicitly ruled out (no third-party payment).
- **Tehama**: `tehama_SCORED_AUCTION_MATCHES_CALL_SHEET.csv` (40,059 rows) is **entirely fabricated** — every row has the identical placeholder owner ("OWNER OF RECORD") and balance ($5,000), traced to `full_county_integrity_pipeline.py`'s hardcoded fallbacks. The 6,009-row 15% sample has real `v_delinquent` flags but empty balance fields. Needs a full rebuild, not a patch — worse than previously believed ("14 of 40,059 filled" undersold how bad this file specifically is).

## New, unbuilt architecture worth pursuing
- **LA County has real, free, open, non-blocked access**: an official bulk CSV of the full assessment roll (`data.lacounty.gov`, "Assessor Parcel Data Rolls 2021-Present"), plus a keyless ArcGIS REST API for APN/address. Owner name and mailing address are restricted from bulk/API access under CA Gov Code §7928.205 — this is a real state law, not a technical block, and may apply beyond LA.
- **The correct fix for owner data isn't Google-dorking** (tested tonight on private individuals — unreliable, too many same-name collisions). It's querying the **county recorder's grantor/grantee index directly** — a separate system from the assessor's restricted GIS layer, historically public independent of that law. This is exactly how Butte's real owner data was sourced (`owner_name_source: recorder_chain_grantee`).
- **The real next-generation architecture**: don't trust any single source. Assessor (value, situs, but owner can lag a real sale), Recorder (real-time ownership via deeds, no value), Tax Collector (delinquency/redemption status) — reconcile all three, and treat disagreement between them as the actual signal. This is literally what would have caught Gridley automatically instead of by manual luck.

## Recommended next session priority
1. Confirm whether LA County actually runs a comparable tax-defaulted auction before investing further there.
2. Kern needs either working browser-based bot-evasion (uncertain) or deprioritization in favor of counties without that wall.
3. Tehama needs the 40,059-row scored file rebuilt from real recorder/assessor sources — the existing one should not be used or trusted at all.
