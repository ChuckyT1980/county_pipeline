# County Pipeline — Health & Function Report

*Generated: 2026-07-22 · read-only audit · scope: full repo excluding `.git`, `__pycache__`, `archive/`, `scratch/`*

---

## Overall verdict (TL;DR)

The **tax_pipeline/** subproject is the live product and it works: 200+ .py files all compile cleanly, integrity-history JSONL is being written up to July 13–14, and Butte/Shasta/Tehama each have recent VERIFIED → ENRICHED → CRM_READY CSVs on disk. However, the repo has **three structural problems worth fixing before onboarding anyone else**:

1. **Missing bootstrap files** — `requirements.txt`, `tax_pipeline/cps1_outcomes.db`, `scheduler_v2.db`, and several intermediate CSVs referenced unconditionally by `dashboard.py`, `stage2_verify.py`, and both `merge_*.py` were deleted from the working tree (per `git status`) and only survive in `archive/`. A fresh checkout cannot run.
2. **Massive dead/legacy surface** — ~120 root-level `.py` files from a June 24–25 "MAR-1 / CFV / CARS / VPR" research framework are untouched since late June and unreferenced by the current `tax_pipeline/` code. They compile fine but bury the ~10 files that actually matter.
3. **Two hardcoded Gemini API keys in the tree** (`tax_pipeline/butte_e2e_test.py`, `tax_pipeline/butte_stage3_test.py`) — see §4.

Everything below is scannable detail.

---

## 1. Structural overview

### (a) Active entry points — root

| File | Size | What it does |
|---|---|---|
| `dashboard.py` | 83 KB | **Streamlit UI** — main product UI. Loads `tax_pipeline/cps1_outcomes.db` + `northern_ca_MASTER_merged.csv`, renders per-county CRM view. |
| `batch_run.py` | 5.7 KB | End-to-end orchestrator. Iterates `(county, book)` tuples via `subprocess -> run_county.py`, checkpoints to `batch_checkpoint.json`, then runs `process_leads.py` + `transfer_detector.py`. |
| `run_county.py` | 3.5 KB | Per-county driver. Chains `tax_pipeline.test_discovery_mpts → stage2_verify → fill_shasta_owners/filter_shasta_leads → stage7_recorder_enrich`. Skips Lassen/Butte (no MPTS). |
| `run_shasta.py` | 2.4 KB | **Legacy** — imports the MAR-1 modules (`canonical`, `signals`, `scoring`, `fwc`, `divergence_auditor`). Reads `data/raw/shasta_live.jsonl`. Not part of the current tax pipeline flow. |
| `county_health_check.py` | 2.4 KB | Reads per-county VERIFIED CSVs and `_partial.parquet`, reports Stage 1 doc-number coverage and Stage 2 owner/doctype hit rates. |
| `run_shasta_stage7.py` | 838 B | One-liner wrapper around `stage7_recorder_enrich`. |
| `combine_exports.py`, `process_leads.py`, `transfer_detector.py`, `find_distress.py`, `find_real_distress.py` | 3–6 KB | Post-processing helpers used by `batch_run.py`'s final stage. |
| `run_controller.py`, `pipeline.py`, `discovery.py` | 10, 1, 10 KB | Legacy MAR-1 orchestration. |
| `run_all.ps1`, `run_butte_full.ps1`, `run_shasta_chunk.ps1`, `Makefile`, `obs.bat` | — | Shell entry points; PowerShell scripts hardcode `C:\Users\chuck\Downloads\county_pipeline`. |

### (b) `tax_pipeline/stage*.py` — the real product

| Stage | File | Function |
|---|---|---|
| 1 | `stage1_discover.py` / `stage1_discover_shasta.py` | MPTS `feeparcel` API prefix enumeration → parcels CSV. Resumable via `_checkpoint.json` + `_partial.csv`. |
| 1 (tax) | `tehama/stage1_tax_verify.py`, `shasta/stage1_tax_verify.py`, `butte/stage1_tax_verify.py` | County-specific tax-delinquency verification runs. |
| 2 | `stage2_verify.py` | Fetches tax detail pages + MBAP `AsrPrint` for owner; scores HOT/WARM/COLD/REVIEW. Persists to `cps1_outcomes.db` (**global de-dup cache — currently missing from tree**). |
| 2 (alt) | `stage2_http.py`, `stage2_recorder_enrich.py`, `stage2_verify_tehama.py` | Variants; `stage2_recorder_enrich.py` at 47 KB is the largest single file after dashboard. |
| 3 | `stage3_adjudicate.py` | Title/vesting adjudication via Google Gemini (`GEMINI_API_KEY`). |
| 4 | `stage4_owner_enrich.py` | Adds owner_name, mailing_address, doc_number, property_type via MBAP AsrPrint + TaxBillv2. Third-party sources (Regrid) explicitly removed. |
| 5 | `stage5_pdf_merge.py` | PDF-based lead merge. |
| 6 | `stage6_pdf_apn_direct.py` | Direct APN-from-PDF extraction. |
| 7 | `stage7_recorder_enrich.py` (21 KB) | Playwright-driven EagleWeb/Tyler recorder lookup per county; expects `<county>_eagleweb_state.json` session file per county. |
| 8 | `stage8_all_counties.py`, `stage8_skip_trace.py` | Cross-county rollup + skip-trace. |
| Other | `integrity_gate.py` (17 KB), `run_pipeline.py`, `run_pipeline_full.py`, `run_ai_intent.py`, `ai_seller_intent.py` | Gate that writes the `*_integrity_history.jsonl` files; AI intent scorer. |

### (c) Connectors

`connectors/` is a tiny surface: `base.py` (BaseConnector + `RawPayload`), `shasta.py`, `tehama.py`, `__init__.py`. Both connectors use `requests` + `bs4` against `common1/2.mptsweb.com`, no Playwright. Butte has **no connector here** — its scraping lives in `butte/butte_tax_api.py` and `tax_pipeline/butte_recorder_adapter.py`.

### (d) Debug / scratch / one-shot scripts

The root has **at least 50** files matching these prefixes: `debug_*` (6), `test_*` (43), `check_*` (5), `probe_*` (4), `scratch_*` (3), `_*.py` (3). `tax_pipeline/` adds another **30+** `check_butte_*`, `test_butte_*`, `debug_*`, `find_auction_*`, `poc_new_recorder_api*` (v1..v4 + final). Almost none are imported by production code — they're diagnostic breadcrumbs from live-debugging county portals. See §8.

### (e) Legacy MAR-1 / research framework (~120 files)

All dated **6/24–6/25/2026**, single-purpose modules with cryptic prefixes: `afr1/2`, `ala1`, `aql1`, `arc1`, `cars2/3`, `ceg1`, `cfv1..6` (43 files), `cgr1`, `cit1`, `cva1`, `ddl1`, `eaf1`, `eer1`, `ere1`, `hdi1`, `iest1`, `ifp1`, `isl1`, `lril1`, `mar1_*` (9), `oni1`, `prc1`, `rbd1`, `sbn`, `sca1`, `scda2`, `sda1/2`, `vpr2/3`. Plus `canonical.py`, `signals.py`, `scoring.py`, `fwc.py`, `divergence_auditor.py`, `completeness.py`, `counterfactual.py`, `explanation.py`, `resolver.py`, `outcome_logger.py`, `telemetry.py`, `fingerprint.py`. Only `run_shasta.py`, `run_controller.py`, and the `mar1/` package still reference these. **Grep confirms `mar1` is imported 32 times but nearly all of those are inter-legacy imports.** Verdict: research substrate, not shipped.

---

## 2. Subdirectory audit

| Dir | State | Notes |
|---|---|---|
| `connectors/` | **Active, minimal** | 4 files, ~9 KB total. See §1(c). |
| `tax_pipeline/` | **Active, huge & messy** | 200+ files, mixes shipped stage*.py with dozens of `check_*`/`test_*`/`poc_*` scripts. Contains recent PDF artifacts (`pdf_jun2006.pdf`…`pdf_sep2024_reoffer.pdf`), auction-target CSVs, `tyler_session_cookies.json`, `butte_eagleweb_state.json` (392 B, 2026-07-19). |
| `scheduler/` | **Complete but likely unused now** | 10 files. `state_store.py` = SQLite (`scheduler_v2.db`) with WAL mode; tables `runs`, `county_state`, `queue_items`, `telemetry`. The DB itself is missing from the tree (only in `archive/`). |
| `butte/` | **Active output tree** | Recent (2026-07-17 → 07-18) enrichment, adjudication, and CRM CSVs; `butte_tax_api.py` (11.9 KB), a small pile of `test_*` from July 17. |
| `shasta/` | **Active output tree** | `shasta_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv` = 5.7 MB, updated 2026-07-13. Has its own `stage1_tax_verify.py`. |
| `tehama/` | **Active output tree** | Same shape as `shasta/`; `tehama_15_percent_sample_VERIFIED_ENRICHED_CRM_READY.csv` = 2.4 MB, 2026-07-13. |
| `crm_schema/` | **Active** | Pydantic models (`models.py` 5.6 KB updated 2026-07-15), `flatten.py`, `enums.py`. Used by `export_engine.py`. |
| `archive/` | **Snapshot dump** | Massive: former outputs (`butte_test_book*.csv` × 20+, `shasta_test_book*.csv` × 20+, `tehama_test_book*.csv` × 25+), `CA_Parcel_Address_Database.csv` (15 MB), the missing DBs, historical HTML captures. Contains the `requirements.txt` copy that was removed from root. |
| `scratch/` | **Dead** | ~90 files, all dated 6/30–7/2. Includes debug PNG/HTML for county portal reverse-engineering. Safe to leave or archive further. |
| `data/` | Skeleton | Empty subdirs `clean/`, `corpus/`, `errors/`, `raw/`, `registry/`, `telemetry/` + `behavior_map.json` (821 B). MAR-1 framework substrate. |
| `logs/` | Nearly empty | 3 JSONL files 6/24; subdirs `cfit1_calib/`, `cfit1_logs/`, `golden_rule_logs/`, `shadow_logs/`. MAR-1 residue. |
| `mar1/` | Legacy package | Subdirs `adapters/`, `core/`, `ob1/`, `test/`. Referenced by `PRODUCTION_RUNBOOK.md` (a MAR-1 runbook, not a current one). |
| `analysis/` | Legacy | 6 files 6/26 (`drift_engine.py`, `evolution_tracker.py`, `query_plane.py`, `sct_engine.py`, `system_health.py`). |
| `cloud_enrichment/` | **Standalone GCP service** | `Dockerfile`, `deploy.ps1`, `app.py` (Flask on port 8080), `cron_job.py`, `migrate_to_firestore.py`. Its own `requirements.txt`. Deployment target = Cloud Run. |
| `presentation/` | Small | `renderer.py` + `templates/` + `output/`. |
| `replays/`, `snapshots/`, `tests/` | Small | Legacy replay caches (dependency_freeze.sqlite × 2), MAR-1 diagnostic snapshots, 2 gold tests. |

---

## 3. Python compile check

Ran `python -m py_compile` against every `.py` under the repo **excluding** `archive/`, `__pycache__/`, `.git/`, `scratch/`.

**Result: ALL PASS.** No syntax errors, no missing-`from` imports at parse time. This includes the ~120 legacy MAR-1 modules.

---

## 4. Config & dependencies

**`.env`** exists (55 bytes) at root — not printed here. Given file size it likely holds a single API key (probably `GEMINI_API_KEY`).

**`requirements.txt`** — **deleted from working tree** (per `git status` shows `D requirements.txt`). Older copy survives at `archive/requirements.txt` (174 B). `SETUP.md` still tells users `pip install -r requirements.txt`. `cloud_enrichment/requirements.txt` is separate and intact (117 B).

**Environment variables read by code:**

| Var | Where |
|---|---|
| `PORT` | `cloud_enrichment/app.py:183` (Flask, default 8080) |
| `GCP_PROJECT_ID` | `cloud_enrichment/cron_job.py:8` |
| `CLOUD_RUN_URL` | `cloud_enrichment/cron_job.py:9` |
| `GEMINI_API_KEY` | `tax_pipeline/ai_seller_intent.py:142`, `tax_pipeline/stage3_adjudicate.py:32` |
| `TRIAGE_CSV`, `TRIAGE_COUNTY`, `TRIAGE_LIMIT` | `local_auto_verifier.py:10,11,258` |

**Hardcoded API keys in tree (should rotate + remove):**
- `tax_pipeline/butte_e2e_test.py:3` — `os.environ['GEMINI_API_KEY'] = 'AIza...'`
- `tax_pipeline/butte_stage3_test.py:3` — same key literal

**Top third-party imports (by file count, stdlib excluded):**

| Package | Files |
|---|---|
| `requests` | 96 |
| `pandas` | 88 |
| `bs4` (beautifulsoup4) | 87 |
| `playwright` | 78 |
| `numpy` | 19 |
| `httpx` | 12 |
| `fitz` (PyMuPDF) | 8 |
| `pdfplumber` | 8 |
| `google` (`google-generativeai` / `google-cloud-*`) | 8 |
| `pydantic` | — (used in `crm_schema/models.py` and `export_engine.py`) |
| `streamlit` | 1 (`dashboard.py`) |
| `flask` | 1 (`cloud_enrichment/app.py`) |

Rebuild `requirements.txt` minimally as: `requests pandas beautifulsoup4 playwright pydantic streamlit numpy httpx pymupdf pdfplumber google-generativeai flask urllib3`.

**Hardcoded `C:\Users\chuck` paths** — 36 hits across `tax_pipeline/` (mostly one-off `check_*`, `analyze_*`, `poc_*`, `fetch_*`, `fix_*`, `verify_*` scripts) and `scratch/` (2 files pointing at `~/Downloads/*.pdf`). Also both `.ps1` runners hardcode the project root. None of these are on the shipped pipeline path (batch_run.py → run_county.py → tax_pipeline stages). SETUP.md line 39 explicitly warns against this pattern.

---

## 5. Function summary

- **`dashboard.py`** — Streamlit app, `st.set_page_config(page_title="Distressed Property Intelligence")`. Custom Inter-font CSS. Reads `tax_pipeline/cps1_outcomes.db` (missing) and per-county master CSVs (`northern_ca_MASTER_merged.csv`, `butte/butte_15_percent_sample_ENRICHED.csv`). Provides recorder-search URL builders (Tehama/Shasta/Butte), owner-name parsing (LLC/TRUST/multi-party heuristics), and a confidence classifier. Entry: `streamlit run dashboard.py`.
- **`batch_run.py`** — Hardcoded 30-entry `RUNS` list (10 Tehama, 10 Shasta, 5 Lassen, 5 Butte). Uses `subprocess.run("python run_county.py …", shell=True)`. Skips completed via `batch_checkpoint.json`. Final stage runs `process_leads.py` then `transfer_detector.py`, then writes `leads_for_sale.csv`.
- **`run_county.py`** — Chains `python -m tax_pipeline.test_discovery_mpts → stage2_verify → (shasta: fill_shasta_owners + filter_shasta_leads) → stage7_recorder_enrich`. Lassen/Butte exit 0 to mark checkpoint done without work.
- **`run_shasta.py`** — Legacy MAR-1 pipeline: reads `data/raw/shasta_live.jsonl`, runs each record through `canonical.init_intelligence_record` in both FR-0 and FR-1 modes, then computes divergence metrics. **Not on the current pipeline path.**
- **`county_health_check.py`** — Reads `<county>/<county>_15_percent_sample_VERIFIED.csv` and `_partial.parquet`. Reports `v_document_number` coverage (Stage 1) and owner_name/doctype hit rates from `owner_vesting` JSON column (Stage 2). No side effects — safe to run.
- **`tax_pipeline/stage1_discover.py`** — Two-phase: (Phase 1) probe books via `feeparcel/<book><page>` at 6 fixed page prefixes to enumerate valid books; (Phase 2) walk every valid book × pages 0..990. Checkpoints per book. Uses `requests.Session` with `Retry(total=10, backoff=2)`.
- **`tax_pipeline/stage2_verify.py`** — GETs `/MBC/<county>/tax/main/<asmt>/<year>/0000` with fallback to MBAP AsrPrint for assessee name. Scores HOT/WARM/COLD/REVIEW. Writes `<county>_audit_*.csv` + `<county>_crm_*.csv` + parquet checkpoint. Uses SQLite `cps1_outcomes.db` as global de-dup cache (**file currently missing from tree**).
- **`tax_pipeline/stage4_owner_enrich.py`** — Pulls owner + mailing address via MBAP AsrPrint + TaxBillv2. Explicitly removed Regrid dependency. Auto-detects county from filename. Detects out-of-state owner via `| ST 12345` regex on mailing address. Adds ~15 columns.
- **`tax_pipeline/stage7_recorder_enrich.py`** — Playwright-driven Tyler EagleWeb search. Handles disclaimer walls, keepalive modals, per-county selectors (`recorder_config.py`). Persists session per county as `<county>_eagleweb_state.json`. Classifies each doc into LIEN / MORTGAGE / DEED / RECONVEYANCE / SATISFACTION / ASSIGNMENT lists.
- **`connectors/tehama.py`** — `TehamaConnector(BaseConnector)`. `fetch_identity` / `fetch_owner` hit `common1.mptsweb.com/MBC/api/search/tehama/0000-CURR/{feeparcel,owner}/{apn11}`. `fetch_snapshot` does JSON asmt+owner then HTML fallback for balance/mailing/owner via `<dt>/<dd>` parsing.
- **`connectors/shasta.py`** — Same pattern against `common2.mptsweb.com`, but the `dt/dd` parsing is heavier (handles "assessment", "roll category", "address", "owner", "mailing", "total balance").
- **`scheduler/state_store.py`** — SQLite (`scheduler_v2.db`, WAL mode). Four tables: `runs`, `county_state`, `queue_items`, `telemetry`. Simple `save_state` / `load_state` for `CountyState`. `scheduler_v2.db` is missing from working tree.
- **`verifier.py`** (19 KB) — Standalone MBC portal verifier with its own `COUNTY_CONFIG` for 6 counties (tehama, eldorado, tulare, kings, amador, mono). Duplicates stage2_verify logic in principle; unclear which is authoritative.
- **`scoring.py`** — `UncertaintyAwareScorer` (base opportunity score × completeness multiplier → A+/A/B/C) + `process_record(record: IntelligenceRecord)` for the MAR-1 record shape. Ranks by distress persistence, financial pressure, equity proxy, absentee, land-simplicity, motivation. Only used by legacy `run_shasta.py`.
- **`export_engine.py`** — Reads a `*_ADJUDICATED.csv` and emits `_CRM_READY.csv`, `_VALIDATION_FAILURES.csv`, and `_MANUAL_REVIEW_QUEUE.csv`. Uses `crm_schema` Pydantic models (`DistressedPropertyProfile`) — this is the current export path.
- **Which `merge_*.py` is canonical?** — **`merge_v2.py`** (10.7 KB, dated 2026-07-04) is the newest and cleanest CSV-only merge, and both it and `merge_master.py` (12.1 KB, same date) unconditionally `open()` a set of CSVs that **do not exist in the current tree** (`crm_ready_leads.csv`, `shasta_assessed_values.csv`, `tax_pipeline/{shasta,tehama}_MASTER_leads_with_liens.csv`, `tehama_all_leads_export.csv`). Both will `FileNotFoundError` immediately. `merge_engine.py` (1.8 KB, 2026-06-30) is a different, older Tehama-only script using `TehamaConnector` on `tehama_tax_default_leads.csv`. **No merge script currently works out of the box.**

---

## 6. Data files

**Root CSVs / JSONL / DB:**

| File | Size | Modified |
|---|---:|---|
| `all_seller_intent.csv` | 5.96 MB | 2026-07-12 14:31 |
| `all_counties_enriched_leads.csv` | 5.92 MB | 2026-07-12 14:31 |
| `shasta_recheck_batch.csv` | 2.09 MB | 2026-07-12 22:14 |
| `shasta_integrity_history.jsonl` | 79 KB | 2026-07-13 02:44 |
| `tehama_integrity_history.jsonl` | 25 KB | 2026-07-13 00:34 |
| `butte_test_75_ENRICHED.csv` | 24 KB | 2026-07-14 |
| `butte_test_75.csv` | 16 KB | 2026-07-14 |
| `butte_integrity_history.jsonl` | 4.8 KB | 2026-07-14 20:23 |
| `all_seller_intent_HIGH.csv` | 3.5 KB | 2026-07-12 |

**Integrity JSONL — sample (last line each):**

- **butte** — `{"event": "check_passed", "record_index": 487, "rows_with_chain": 49, "hit_rate": 0.98, "corrupt_rate": 0.0}` — actively passing at high hit rate.
- **shasta** — `{"event": "check_passed", "record_index": 13650, "total_chain_events": 0, "corrupt_rate": 0.0}` — passing but with zero chain events per window (the schema field `hit_rate` is missing here; Shasta integrity checks are looking only at corrupt-rate).
- **tehama** — `{"event": "check_passed", "record_index": 4250, "total_chain_events": 0, "corrupt_rate": 0.0}` — same pattern as Shasta.

**Databases anywhere in repo:**
| Path | Size |
|---|---:|
| `archive/tax_pipeline/cps1_outcomes.db` | 766 KB |
| `archive/cps1_outcomes.db` | 28 KB |
| `archive/scheduler.db` | 36 KB |
| `archive/scheduler_v2.db` | 32 KB |
| `replays/…/dependency_freeze.sqlite` (×2) | 64 KB each |

**No live DBs** at `tax_pipeline/cps1_outcomes.db` or root `scheduler_v2.db` — code will recreate them fresh on next run (both `stage2_verify.py` and `state_store.py` use `CREATE TABLE IF NOT EXISTS`), losing the archived global-verifications cache.

---

## 7. Deleted-but-still-referenced check

Git shows a large number of `D` files. Cross-referenced against `import`/`open()`:

**Actively referenced by production code:**

| Missing file | Referenced by | Impact |
|---|---|---|
| `tax_pipeline/cps1_outcomes.db` | `tax_pipeline/stage2_verify.py:182`, `dashboard.py:170` | Recreated empty on first run; historical dedup cache lost. Dashboard reads it — will need at least an empty DB. |
| `scheduler_v2.db` | `scheduler/state_store.py:6` (default) | Recreated empty on first run. Scheduler state lost. |
| `northern_ca_MASTER_merged.csv` | `dashboard.py:2,10,24` (default CSV for tehama/shasta/northern_ca) | Dashboard will crash on load unless replaced. |
| `tax_pipeline/eagleweb_state.json` | `refresh_cookie.py:14`, `scratch_url_test.py`, `scratch_search.py`, `test_playwright.py`, `test_toerpe.py`, `test_req_search.py`, `test_templates.py`, `test_templates2.py`, `test_typing.py`, several `scratch/*.py` | Only the debug/scratch scripts break. `stage7_recorder_enrich.py` uses **per-county** `<county>_eagleweb_state.json` — `tax_pipeline/butte_eagleweb_state.json` exists (392 B, 2026-07-19). |
| `tax_pipeline/shasta_MASTER_leads_with_liens.csv`, `tax_pipeline/tehama_MASTER_leads_with_liens.csv`, `crm_ready_leads.csv`, `tehama_all_leads_export.csv`, `shasta_assessed_values.csv` | `merge_master.py`, `merge_v2.py` (unconditional `open()`) | Both merge scripts `FileNotFoundError` immediately. |
| `requirements.txt` | `SETUP.md`, `Makefile` (indirect) | Fresh checkout has no way to know deps. Copy in `archive/`. |

**Deleted but only referenced by tests / dead code (low impact):**
`api_test.json`, `api_test2.json`, `cps1_weights.json`, `endpoint_profile_shasta.json`, `endpoint_profile_tehama.json`, `h6_resilience_report.json`, `hostility_report.json`, `scored_leads.json`, `tehama_seed_prefixes*.json`, `tehama_live_test.json`, `unified_leads_final.json`, `unified_leads_sample.json`, `mpts_details.html`, `mpts_html.html`, `homepage.html`, `test_req4_out.html`, `test_search.html`, `shasta_audit_*`, `shasta_crm_*`, `shasta_discovery_*`, `northern_ca_MASTER_export.csv`, `tax_pipeline/enrich_output.txt`, `tax_pipeline/search_js.txt`, `tax_pipeline/shasta_MASTER_leads*.csv` — all appear only in ephemeral artifacts or MAR-1 tests. Not blocking.

---

## 8. Cleanup recommendations

### Safe to delete outright
- All `debug_*.py` and `debug_*.html`/`.png` at root (12 files) — one-off portal reverse-engineering artifacts, mostly Shasta/Tehama.
- All `probe_*.py` (4 files) — same category.
- `temp.html` (0 bytes).
- `myarchive.zip` (22 B — empty zip).
- `pivot2_output_*.json`, `pivot2_results.txt`, `test_pivot2.py`, `patch_shasta.py`, `patch_tehama.py`, `fix_shasta.py`, `mock_distress.py`, `purge_corrupted_rows.py`, `verify_doc_number_integrity.py` (all 2026-07-12, one-off recovery tools).
- `tehama_disclaimer.html/png`, `tehama_failed.png`, `tehama_results.html`, `butte_search_results.html`, `shasta_after_accept.html`, `shasta_home.html`, `shasta_search_page.html`, other portal snapshots at root.
- The 18 `test_butte_*.py` files at root (2026-07-13) — all portal-diagnostic probes for a Butte session-handshake bug that's since been solved (docs are now in `butte_test_75_ENRICHED.csv`). Keep at most one canonical probe.
- The 5 `poc_new_recorder_api*.py` in `tax_pipeline/` — the `_final` variant supersedes the others.
- The 3 `audit_coverage*.py` in `tax_pipeline/` — `audit_coverage_fixed.py` supersedes.
- Multiple `butte_name_search_diagnostic*.py` (v1..v3) and `find_auction_id*.py` (v1..v3), `find_auction_buyers*.py` (v1..v2), `debug_shasta_tyler*.py` — keep newest, delete iterations.

### Move to `archive/`
- The entire MAR-1 legacy set (~120 files, 6/24–6/25). One-line litmus: if the module has a 2-letter+digit prefix and nothing under `tax_pipeline/` imports it, archive it. This alone would drop the root file count from ~250 to ~50.
- `analysis/`, `mar1/`, `data/` (empty skeleton), `logs/` (6/24 residue), `snapshots/`, `replays/` — all frozen since June. Move once you're sure `run_shasta.py`/`run_controller.py` are truly retired.
- `run_shasta.py`, `run_controller.py`, `pipeline.py`, `discovery.py` — same batch.
- Root MAR-1-era `.json` metadata files if `.gitignore` doesn't already exclude them.

### Keep — active
- `tax_pipeline/stage[1-8]*.py`, `tax_pipeline/config.py`, `tax_pipeline/recorder_config.py`, `tax_pipeline/integrity_gate.py`, `tax_pipeline/ai_seller_intent.py`, `tax_pipeline/butte_tax_api.py`, `tax_pipeline/butte_recorder_adapter.py`, `tax_pipeline/butte_auction_enrich.py`, `tax_pipeline/generate_auction_report.py`, `tax_pipeline/build_*.py`, `tax_pipeline/run_pipeline_full.py`.
- `connectors/`, `crm_schema/`, `scheduler/`, `butte/`, `shasta/`, `tehama/`.
- `dashboard.py`, `batch_run.py`, `run_county.py`, `county_health_check.py`, `combine_exports.py`, `process_leads.py`, `transfer_detector.py`, `export_engine.py`, `local_auto_verifier.py`, `folder_report.py`, `validate_pipeline.py`.
- `cloud_enrichment/` (standalone GCP service — evaluate separately).
- `SETUP.md`, `MISSION.md`, `AI_NOTES.md` (session-handoff dated 2026-07-07 — probably out-of-date now; consider refreshing).

### Fix before onboarding anyone
1. **Rebuild `requirements.txt`** (start from the list in §4).
2. **Remove hardcoded `GEMINI_API_KEY` from `tax_pipeline/butte_e2e_test.py` and `butte_stage3_test.py`**; rotate that key.
3. **Create empty `tax_pipeline/cps1_outcomes.db`** (or restore from `archive/tax_pipeline/cps1_outcomes.db` which has 766 KB of cache), and either restore `northern_ca_MASTER_merged.csv` or update `dashboard.py`'s default. Otherwise `dashboard.py` and `merge_v2.py` won't run.
4. Update `PRODUCTION_RUNBOOK.md` — it documents MAR-1, not the tax pipeline; misleading to any new reader.
5. `README.md` describes a single "Tehama County Distressed Property Data Pack" — replace with an actual project README that mentions Shasta/Butte and the current stage flow.
6. Delete or update `AI_NOTES.md` — dated 2026-07-07, references paths (`/mnt/c/…`) and "Butte blocked" that are no longer true (Butte enrichment CSVs are on disk from 2026-07-14 → 07-18).

---

*End of report.*
