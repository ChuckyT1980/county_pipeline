# property_intelligence_v2

New canonical architecture for the California property-intelligence system.
Lives inside the existing `county_pipeline` repository - not a separate repo.

## Isolation rule (read this before touching anything outside this folder)

```
Legacy county folders (kern/, butte/, lake/, del_norte/, output/, monitor_runs/,
and every other existing script, dossier, monitor, dashboard, export, or
data file at the repo root) = read-only evidence and research inputs.

property_intelligence_v2/ = new canonical architecture.
```

**Nothing under this folder may move, rename, delete, regenerate, or rewrite
any legacy county folder, evidence file, dossier, monitor, dashboard,
export, or output.** Legacy data stays exactly as-is - real, already-verified
evidence (Kern's document-number recorder cross-matches, Butte's redemption-
filtered dossiers, Lake's lien-lifecycle classifications, Del Norte's
excess-proceeds records, and everything in `monitor_runs/`) that this new
architecture will eventually read from, never write to or restructure in
place.

Any code added here that needs to *read* legacy data (for research,
comparison, or future migration prototyping) must open those files
read-only and must not be wired into any legacy generation path
(`regen_butte_dossiers.py`, `report_builder.py`, `ca_unify_dashboard.py`,
etc.) or vice versa. The two trees stay decoupled until an explicit,
separately-authorized migration step.

## Architecture (Phase 1)

```
Parcel Master
  -> Immutable Source Observations
    -> Reconciliation
      -> Canonical Property State
        -> Reconciliation Feedback
          -> (future) Derived Intelligence
```

A failure is a valid system output, not an absence of one:

```
attempt -> observe -> classify -> save evidence -> record outcome
  -> choose next action -> retry / fallback / quarantine / human_review
```

Nine entities implement this, in pipeline order: `source_registry`,
`ingestion_runs`, `raw_evidence`, `observations`, `parcels`,
`parcel_matches`, `canonical_property_state`, `reconciliation_feedback`,
`exceptions`. Full field-level documentation lives in
`contracts/entities.py`'s docstrings and `migrations/001_initial_schema.sql`'s
comments - both describe the same nine entities and are kept in sync by
hand (see "Two representations, one shape" below).

## Subdirectories

- `contracts/` - `entities.py`: the nine entities as Python dataclasses, plus their supporting enums (statuses, confidence levels, classifications). This is the primary reference for what each entity's fields mean and why.
- `migrations/` - `001_initial_schema.sql`: the ONE canonical, versioned SQL schema (SQLite now, written to port cleanly to PostgreSQL later). `apply_schema.py` is the one code path (used by both real usage and tests) that applies it. No import/migration of legacy data exists yet - see `migrations/README.md`.
- `validation/` - `lifecycle.py`: structural transition validity for the four entities that carry a lifecycle status (does a proposed status change make sense at all) - not scoring, ranking, or decision logic about what SHOULD happen, which is out of scope for Phase 1.
- `tests/` - `test_contracts.py`, `test_schema.py`, `test_lifecycle.py` - v2's own test suite, independent of the legacy `tests/` directory at the repo root. Plain assertions, no pytest dependency, matching the legacy suite's convention. No real or synthetic California data anywhere - every fixture value is an explicit placeholder (`TEST_ONLY_*` prefix in schema tests).
- `models/` - not populated; see `models/README.md` for why.
- `docs/` - not yet populated beyond this README.

## Two representations, one shape

`contracts/entities.py` (Python dataclasses) and
`migrations/001_initial_schema.sql` (SQL DDL) describe the same nine
entities from two angles - dataclasses for in-process use and
type-checking, SQL for persistence and its own independent integrity
enforcement (CHECK constraints, foreign keys, NOT NULL). They are
maintained by hand as two views of one shape, not generated from each
other - `tests/test_contracts.py` and `tests/test_schema.py` each prove
their own side independently.

## Status

Phase 1 data-contract foundation, built 2026-08-08. Contracts, schema,
lifecycle validation, and tests exist; no scraper, county adapter,
monitor, dossier, dashboard, export, scoring model, ML model, or
opportunity ranking has been built, and none is planned until a
separately-authorized later phase. No real or synthetic California
county data has been inserted anywhere in this tree.
