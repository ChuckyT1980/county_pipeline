# AI Session Handoff — Logic Flow Systems
**Date:** 2026-08-02 (afternoon)
**Owner:** Chuck Terrell | mrt@logicflowsystems.io
**Workspace:** `C:\Users\chuck\Downloads\county_pipeline\`
**Prior handoff:** `AI_SESSION_HANDOFF_2026-07-31.md` (still valid for business/strategy context)

---

## What This Session Actually Built

Chuck's ongoing vision: **unify all 58 CA counties under one system, pull data on demand, leave everything like we were not there.** GLM had earlier drafted `contracts.py` (canonical schema + adapter ABCs + registry) and a `tehama_recorder_tyler.py` stub with GLM's *guessed* Tyler Eagle wire details. This session made that architecture real for one county × one vendor: **Tehama recorder end-to-end through the unified contract, verified against live production data.**

### Files shipped or rewritten this session
| File | Status | What it is |
|---|---|---|
| `contracts.py` | verified | canonical models (Property, Owner, Event, ExcessProceeds…), 6 adapter ABCs, `@register` decorator, `build_adapters_for_county()` |
| `tehama_recorder_tyler.py` | **REWRITTEN** | placeholder wire details replaced with the live-verified values from `tyler_recorder_client.py`. Registered under `(SourceType.RECORDER, "tyler")` |
| `normalizers.py` | **NEW** | `DefaultNormalizers` — event_type map (18 real Tyler labels), APN normalization, owner+entity classification (LLC/TRUST/CORP/GOV/PERSON), address flags (out_of_state) |
| `raw_store.py` | **NEW** | `FileRawStore` — sha256-sharded content-addressed bytes at `data/raw/{county}/{source}/{hash[:2]}/{hash[2:]}.bin`, JSONL index at `data/raw_index.jsonl`, deduplicating |
| `http_client.py` | **NEW** | `build_http_client()` — cookie-persistent httpx.Client with real-browser UA |
| `multi_transform.py` | **NEW** | `generate_doc_variants` (capped at 4) + `search_document_with_variants()`. Session-recovery on IntegrityError. Handles Tehama's format zoo: `2011R0001795 → 2011001795`, etc. |
| `smoke_tehama_live.py` | **NEW** | 1-request wire proof against live Tehama. Runs green (`grant_deed` on doc 2026R006490, grantor VOTH → grantee MATTHEWS) |
| `pull_tehama_recorder_batch.py` | **NEW** | Production batch puller with `--resume`, `--limit 0` = all, per-parcel flush, rolling progress every 25 |

### Data produced
- `data/tehama/unified_pull_2026-08-02.jsonl` — **835 canonical records** (55 hits, 778 no_hit, 2 error) from the interrupted full sweep
- `data/raw/tehama/recorder/…` — raw HTML for every request, deduped by sha256
- `data/raw_index.jsonl` — searchable index of every fetch

---

## The Sweep Bug (Read This Before Resuming)

**What happened:** kicked off a full 2,019-parcel Tehama sweep with `--limit 0 --resume`. Progress collapsed hard mid-run. Batch-of-50 pattern from the jsonl:

```
batch  0 (parcels 1–50):   36/50 hits (72%)   ← healthy
batch  1–11 (51–600):      0/50 each          ← session wedged, ZERO hits
batch 12 (601–650):        4/50               ← partial recovery
batch 13 (651–700):        15/50              ← session actually working
batch 14–16 (701–835):     0/50 again         ← re-wedged
```

Overall: **55 hits / 835 processed = 6.5% hit rate**, vs. **the top-10 sample earlier this session at 80%**. This is not a data-quality drop — it's the portal wedging our session and every subsequent search returning the disclaimer redirect (which trips the "results container found no ss-search-row" integrity gate).

**Root cause suspects (in order of likelihood):**
1. **Rate-limit / throttle by IP.** The 0.5s inter-request delay + up to 4 variants per parcel = burst of ~2 requests/sec sustained. Tehama's Tyler install may throttle at ~50 parcels in / few minutes.
2. **Session cookie lifetime.** Disclaimer cookie may expire after N minutes or M requests; `_session_ready` doesn't refresh proactively.
3. **`_session_ready = False` on IntegrityError is not enough.** The next call re-runs the disclaimer handshake but that alone may not clear whatever throttle state the server holds.

**What I DID NOT try (next-session's fastest wins, in priority order):**
1. **Add proactive session refresh every N parcels** (e.g., every 20) — cheap, likely resolves it.
2. **Increase inter-parcel delay to 2–3s** — cuts throughput in half but restores hit rate.
3. **Chunk in batches of 40, sleep 5 minutes between chunks** — matches the observed throttle boundary.
4. **Rotate through multiple IP paths** — proxy layer. Bigger project.
5. **Contact Tehama and ask for bulk-data access** — the correct long-term move. CPRA §408.3 covers assessor data; recorder is separate but similar precedent.

The sweep IS resumable. Rerun with `python pull_tehama_recorder_batch.py --limit 0 --resume` and it skips the 835 already in the jsonl. Fix the wedging first or you'll just add more no_hit rows.

---

## Unified Pipeline: What Works, What Doesn't

### Works (verified live 2026-08-02)
- `contracts.py` architecture — registry populates, `build_adapters_for_county()` assembles
- Tehama Tyler recorder adapter — real wire, real grantor+grantee capture, event_type mapping, gap tracking
- Raw capture — every fetch persisted with sha256, content-addressed dedupe
- Multi-transform helper — 4-variant sweep with session recovery. Caught a **v1-missed WELLS FARGO/WACHOVIA → JOHNSON deed chain** on parcel `004-110-034-000` (variant `2011001795`)
- Comparison harness — every unified event tagged `match`, `differ`, `unified_only`, `v1_only`, `both_empty`

### Doesn't exist yet (in unified-contract terms)
- **MPTS assessor adapter** — biggest coverage lever. MPTS is the assessor backend for ~40 CA counties (Butte, Shasta, Tehama, and most rurals). Same shape everywhere. One adapter class + a `@register(SourceType.ASSESSOR, "mpts")` decorator. Ground truth: `tax_pipeline/stage4_owner_enrich.py::fetch_asr_print` — port that into an `AssessorAdapter` subclass.
- **YAML → CountyConfig loader** — `counties/*.yaml` files exist for all 58 counties but their schema doesn't yet map to `contracts.CountyConfig`. Need a small `load_county(name) -> CountyConfig` function so `python run.py --county tehama --doc X` works from config.
- **Other Tyler counties (Shasta, Butte, Fresno, Glenn)** — the adapter is already generic enough (reads search IDs + doc transform from `SourceConfig.params`). They need a config entry each and one CountyConfig loader test.
- **GovEase auction adapter** — schedule + results. No draft yet.
- **ArcGIS GIS adapter** — parcel geometry. Nearly universal across CA counties.
- **CA SOS entity adapter** — LLC/corp lookups. Statewide, one implementation.
- **Tax collector adapter** — MPTS again, different endpoint (Bill Search vs. Fee Parcel Search).

---

## Priority Order For Next Session

**IF the plan is to keep sweeping Tehama:**
1. Fix the session-wedge (proactive refresh every 20 parcels + inter-parcel delay 2s). Resume the sweep. Full run should complete in ~2 hours clean.

**IF the plan is to widen coverage first:**
1. Write the MPTS assessor adapter. Reuses `tax_pipeline/stage4_owner_enrich::fetch_asr_print` logic behind the ABC. Unlocks Butte + Shasta + Tehama + ~37 other counties' assessor data through the unified pipeline in one file.
2. Write the YAML→CountyConfig loader.
3. Write a runner script (`run.py --county X --source recorder --apn Y`).
4. Repeat sweep pattern for each new county.

**Chuck's stated preference:** "unify all counties under our system so we can pull data when we want to and leave everything like we were not there." That maps most cleanly to the widen-coverage plan — MPTS assessor first is the single highest-leverage next step.

---

## Parked From Earlier In This Conversation (Non-Code, Needs Chuck)

1. **Kern CPRA email** — draft is in `CPRA_ASSESSOR_ROLL_REQUEST_PACKAGE.md`. Send to `assessor@co.kern.ca.us`, BCC yourself. 30-second task. Kern auction Sept 14–16, county has 10 days to respond, every day matters.
2. **Butte / Jeff delivery confirmation** — you needed to confirm the July 29 delivery landed.
3. **Butte 2026 excess proceeds mailer** — 433 real leads in `excess_proceeds/archive/excess_proceeds_butte_2026.csv`, 320 days to escheat, mailing addresses are placeholders (`"Address on Tax Roll"`) — need real address resolution + letter template + PDF batch. No mailer script exists.
4. **Gemini API key rotation** — still hardcoded in `tax_pipeline/butte_e2e_test.py:3` and `butte_stage3_test.py:3`.
5. **Fresno 2025 excess** — dead lead (50 records, all past 1-year §4675 window). Correctly archived. Only mention if someone asks why the outreach list is empty.
6. **Tehama 2025 excess** — never had real auction data. Old 40k-row file was fabricated placeholder, correctly archived. Real Tehama historical sales data would need to be pulled from the county before excess can be computed.

---

## Key Facts For The Next AI

- **Chuck's business email is `mrt@logicflowsystems.io`** (NOT `chuck@`, NOT `.com`).
- **Chuck is a solo founder on a tight cash timeline.** He can handle real information including bad news; he cannot handle false certainty followed by pivots. When a next step is obvious, execute — do not present a menu. When you don't know, say so plainly. When you hit friction (a 403, an empty results page, missing data), try three alternatives before reporting the constraint.
- **This session's mistake pattern to avoid:** I ran a 2,019-parcel sweep in background without first proving the polling behavior would hold under sustained volume. The top-10 sample was clean, so I assumed 2,019 would be. Wrong. Next time: run 100 first, watch the batch-of-50 hit rate, decide whether to continue.
- **Handoff protocol note:** Chuck's memory folder for this workspace is at `C:\Users\chuck\.claude\projects\C--Users-chuck-Downloads-county-pipeline\memory\` — read `MEMORY.md` there for user-identity + behavior-rules memories before you do anything else.

---

## Files Reference (Quick Nav)

```
county_pipeline/
├── AI_SESSION_HANDOFF_2026-08-02.md         ← THIS FILE
├── AI_SESSION_HANDOFF_2026-07-31.md         ← prior session (business context)
├── MASTER_HANDOFF.md                        ← original business overview
│
├── contracts.py                             ← unified contract (schema + ABCs)
├── tehama_recorder_tyler.py                 ← Tyler recorder adapter (registered)
├── normalizers.py                           ← event_type / apn / owner / address
├── raw_store.py                             ← sha256-sharded raw capture
├── http_client.py                           ← cookie-persistent httpx wrapper
├── multi_transform.py                       ← doc-variant sweep w/ session recovery
├── smoke_tehama_live.py                     ← 1-request wire proof
├── pull_tehama_recorder_batch.py            ← production batch puller
│
├── tyler_recorder_client.py                 ← LEGACY: source of truth for wire details
├── tax_pipeline/stage4_owner_enrich.py      ← LEGACY: source for MPTS assessor logic
├── enrich_tehama_owners_v2.py               ← LEGACY: source for multi-transform logic
│
├── data/
│   ├── raw_index.jsonl                      ← fetch index (~840 entries now)
│   ├── raw/tehama/recorder/...              ← content-addressed HTML
│   └── tehama/
│       ├── tehama_owner_enriched.csv        ← v1 output (2164 rows, 2019 with doc)
│       └── unified_pull_2026-08-02.jsonl    ← this session's canonical output (835 rows)
│
├── counties/*.yaml                          ← 58 county configs (many stub-only)
├── CPRA_ASSESSOR_ROLL_REQUEST_PACKAGE.md    ← Kern email template (unsent)
└── excess_proceeds/archive/                 ← Butte 2026 leads, Tehama fabricated, etc.
```

*Session: 2026-08-02, approximately 4 hours of work.*
