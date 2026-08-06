# Agent Handoff — Owner Resolution & Pipeline Integration
**Date**: 2026-08-03 21:15 PDT  
**Handed off by**: Primary agent (conversation 4c245989-eac9-437b-a3cb-fbc25f7a7eff)  
**Project root**: `C:\Users\chuck\Downloads\county_pipeline\`

---

## Situation Summary

Chuck is building a NorCal property intelligence pipeline that finds excess-proceeds claimants across all 58 CA counties after tax-deed auctions. The pipeline is real and already working. This session resolved a key blocker and built a new unified tool. Continue from here.

---

## What Was Just Completed

### 1. The Casey Check — SOLVED
**APN `305-073-053-000` is a Humboldt County parcel, NOT Tehama.**
- Owner: **CASEY B A**
- Excess: **$11,481.75**
- Claim deadline: **2027-06-18**
- Deed status: `deed_confirmed_by_block_match`
- Auction winner: LUC KEVIN
- Source: `data/counties/humboldt/excess_proceeds.csv` line 25

This was the missing piece in the Tehama "3 checks" audit. The footing is now:
- McKague check (APN 500-221-032-000): **CLEAN DISCARD** — not in the 30 auction parcels
- Footing: 36 county deeds = 29 matched + 6 no-surplus + 1 pending-Casey resolved
- Casey check: **CLOSED** — CASEY B A, Humboldt, $11,481.75, deadline 2027-06-18

### 2. `owner_resolve.py` — Built and tested
**Location**: `C:\Users\chuck\Downloads\county_pipeline\owner_resolve.py`

Unified single-command owner lookup. Free, no APIs, no payment.

**Resolution cascade**:
1. Local CSV (`data/counties/{county}/excess_proceeds.csv`, `roll.csv`, etc.)
2. MPTS AsrPrint (`common1.mptsweb.com`) — 40+ NorCal counties
3. Tyler EagleWeb APN recorder search (Humboldt, Fresno, Kern)
4. Google Dork enrichment -> `null_name_dork_resolver.py capture` for manual receipt lock-in

**Usage**:
```
python owner_resolve.py 305-073-053-000 humboldt
python owner_resolve.py 004-110-034-000 tehama --json
python owner_resolve.py 500-221-032-000 tehama --dorks
```

**Confirmed working**:
- `305-073-053-000 humboldt` -> Tier 1 HIT -> CASEY B A (confirmed)
- `305-073-054-000 humboldt` -> Tier 1 HIT -> CASEY B A (confirmed)
- `500-221-032-000 tehama` -> Tier 4 DORKS (correct -- APN not in auction list)

---

## Pipeline Architecture (what already exists -- do NOT rebuild)

```
county_pipeline/
+-- owner_resolve.py          <- NEW: unified owner lookup (just built)
+-- run.py                    <- unified CLI runner (assessor + recorder)
+-- contracts.py              <- port/adapter contracts (Pydantic v2, 579 lines)
+-- county_config_loader.py   <- loads counties/*.yaml
+-- mpts_assessor.py          <- MPTS AsrPrint adapter (registered)
+-- arcgis_assessor.py        <- ArcGIS assessor adapter (registered)
+-- tehama_recorder_tyler.py  <- Tyler EagleWeb recorder adapter
+-- tyler_recorder_client.py  <- low-level Tyler HTTP client
+-- null_name_dork_resolver.py<- Google dork enrichment + receipt gate
+-- normalizers.py            <- APN/address/name normalization
+-- raw_store.py              <- raw capture store
+-- http_client.py            <- httpx client builder
+-- multi_transform.py        <- doc-number variant sweep
+-- counties/                 <- 58 county YAML configs
|   +-- humboldt.yaml         <- Tyler recorder: humboldtcountyca-web.tylerhost.net
|   +-- tehama.yaml           <- Tyler recorder: Tyler DOCSEARCH; MPTS common1
|   +-- fresno.yaml           <- Tyler recorder + MPTS
|   +-- ... (all 58 CA counties)
+-- data/
    +-- counties/
        +-- humboldt/
        |   +-- excess_proceeds.csv   <- 31 parcels, 2026 auction, deadline 2027-06-18
        |   +-- roll.csv              <- 3.5MB full roll
        |   +-- state.sqlite          <- pipeline state DB (10.9MB)
        |   +-- bridge_run.out        <- 24,624 parcels processed, ~22,477 docs found
        +-- tehama/
        |   +-- state.sqlite          <- pipeline state
        |   +-- recorder_docs.csv
        +-- fresno/
        |   +-- recorder_docs.csv     <- 53,546 bytes, 8/3/2026
        |   +-- state.sqlite          <- 40MB
        +-- butte/
        |   +-- roll.csv, sold_results.csv, auction_list.csv
        +-- shasta/
            +-- ...
```

---

## Hard Rules (enforced -- never violate)

1. **Never invent data.** Every APN, owner name, address must come from a live verified public source with a `source_url` receipt.
2. Verified owner = name + source from county/court domain with APN present on the landing page.
3. Unverified lead = name from snippet/third-party -> park under `lead_owner_name`, status `LEAD_UNVERIFIED`. Never promote to `verified_owner_name`.
4. `null_name_dork_resolver.py capture` is the ONLY path to locking in a manually-found name.
5. The `excess_proceeds_tehama_2025.csv` in the legacy folder is **synthetic placeholder data** -- never use it for auditing.

---

## Immediate Next Tasks (in priority order)

### TASK 1 -- Humboldt Bridge Run: Finish the remaining ~2,147 parcels
The bridge ran 24,250/24,624 parcels before the server restart. 374 parcels remain.
- Check `data/counties/humboldt/bridge_run.out` for the last processed APN
- Find the bridge runner script (check `loop_run.log`, look for `bridge.py`)
- Restart it with checkpoint resume from APN 24,250 onwards

### TASK 2 -- Wire `owner_resolve.py` into the main pipeline loop
When a parcel has null owner name during any pipeline stage, auto-call `owner_resolve.resolve_owner(apn, county)`.
If Tier 1-3 all miss, emit dork URLs to `data/counties/{county}/null_name_dorks.html`

### TASK 3 -- Humboldt: Run `null_name_dork_resolver.py dorks`
```
python null_name_dork_resolver.py dorks \
  --csv data/counties/humboldt/excess_proceeds.csv \
  --county humboldt \
  --out data/counties/humboldt/null_name_dorks.html
```

### TASK 4 -- Find and fill the Tyler APN search ID for Humboldt
`humboldt.yaml` has `apn_search_id:` blank. Check `tyler_recorder_client.py` for the APN search shape.
If a valid search ID exists, add it to `TYLER_APN_ENDPOINTS["humboldt"]` in `owner_resolve.py`.

### TASK 5 -- Update `MASTER_AGENT_HANDOFF_2026-08-03.md`
Add: Casey check CLOSED, owner_resolve.py built, Humboldt bridge status.

---

## Key File Paths

| File | Purpose |
|---|---|
| `owner_resolve.py` | **NEW** -- unified owner lookup |
| `null_name_dork_resolver.py` | Google dork enrichment + receipt gate |
| `run.py` | Unified CLI runner |
| `contracts.py` | Adapter contracts (read before touching anything) |
| `counties/humboldt.yaml` | Humboldt config |
| `data/counties/humboldt/excess_proceeds.csv` | 31 real parcels, 2026 auction |
| `data/counties/humboldt/bridge_run.out` | Bridge stopped at 24,250/24,624 |
| `MASTER_AGENT_HANDOFF_2026-08-03.md` | Master context doc |

---

## Environment

- Python 3.11, Windows (PowerShell -- use `;` not `&&` to chain commands)
- Dependencies: `httpx`, `beautifulsoup4`, `pydantic`, `yaml`, `pandas`, `openpyxl`
- All deps installed globally -- no venv, just `python`
- No paid APIs. No keys needed for any current task.

---

## Quick Validation

```powershell
# Confirm owner_resolve works before doing anything else
python owner_resolve.py 305-073-053-000 humboldt

# Expected:
#   Owner   : CASEY B A
#   Excess  : $11,481.75
#   Deadline: 2027-06-18
#   Tier    : LOCAL_CSV
#   Status  : VERIFIED_LOCAL_COUNTY_DATA
```
