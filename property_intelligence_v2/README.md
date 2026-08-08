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

## Subdirectories

- `contracts/` - interface/schema definitions (the "what a valid input/output looks like" layer) - not yet populated.
- `models/` - canonical domain models (property identity, evidence, observations, lifecycle state) - not yet populated. Distinct from the existing root-level `property_model.py` (Property/PropertyIdentifier/CountySourceConfig) built during the earlier remediation session - that file is legacy-adjacent scaffolding, not part of v2; whether/how it gets superseded or absorbed is a decision for the migration step, not assumed here.
- `validation/` - validation rules and gates (the v2 equivalent of `release_gate.py`/`lead_status.py`'s state-machine discipline, rebuilt on the new models) - not yet populated.
- `tests/` - v2's own test suite, independent of the legacy `tests/` directory at the repo root - not yet populated.
- `docs/` - v2 architecture documentation - not yet populated.
- `migrations/` - the controlled importer, once authorized (see below) - not yet populated.

## Planned importer (future work, not started)

```
legacy Kern / Butte / Lake evidence
  → raw_evidence records
  → observations
  → parcel matches
  → canonical property state
```

This pipeline is explicitly **future work** - nothing in `migrations/` has
been written yet, and no import/migration runs against real legacy data
until separately authorized. When it is built, it reads legacy evidence
files read-only and writes only into v2's own canonical store; it does not
touch the legacy files it reads from.

## Status

Scaffold only, created 2026-08-08. No contracts, models, validation rules,
tests, or migration code exist yet. This commit's only job is to establish
the isolated directory structure and the ground rules above before any
real v2 code is written.
