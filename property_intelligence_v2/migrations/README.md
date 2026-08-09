# migrations/

## Schema migrations (exists now)

`001_initial_schema.sql` is the ONE canonical, versioned SQL schema for
property_intelligence_v2 - the nine Phase 1 tables (`source_registry`
through `exceptions`). There is no separate production schema and test
schema: `property_intelligence_v2/tests/test_schema.py` applies this
exact file to a temporary in-memory SQLite database and proves it
accepts valid rows and rejects invalid ones (dangling foreign keys,
out-of-vocabulary statuses, missing required fields, out-of-range
values).

`apply_schema.py` is the one code path that applies migrations - both
real usage and tests call the same `apply_schema(conn)` function against
the same files in this directory. Future schema changes get their own
numbered file and an entry in `apply_schema.py`'s `MIGRATIONS` list;
existing migration files are never edited in place once applied
anywhere.

`002_integrity_hardening.sql` (proposed, not yet reviewed/accepted) adds,
on top of 001: unconditional SQLite triggers blocking UPDATE/DELETE on
`raw_evidence` and `observations` (real enforcement, not the unenforced
`immutable` flag column 001 shipped with); a `supersedes_observation_id`
column replacing 001's `superseded_by_observation_id` (the new row points
backward at INSERT time, instead of requiring the old row to be mutated
- which the new immutability triggers would otherwise block); a typed,
immutable `observation_identifiers` table replacing 001's untyped
`observations.source_identifier_type`/`source_identifier_value` columns
(removed, not left running alongside the new table - see the migration's
own comments for why); an append-only `evidence_disposition` table plus
`v_evidence_current_disposition` view implementing ACTIVE/QUARANTINED
evidence status without requiring `raw_evidence` itself to be mutable;
and a `canonical_property_state.verification_status` column plus
normalized `canonical_state_support` table gating VERIFIED/
HUMAN_CONFIRMED status on active-evidence-backed support and a confirmed
parcel match. Each test in
`property_intelligence_v2/tests/test_schema.py` that pre-dates 002 is
pinned to `apply_schema(conn, target_version=1)` deliberately, so it
keeps testing 001's shape in isolation regardless of what later
migrations add or remove - `test_schema_hardening.py` is what tests 001
and 002 applied together.

`003_evidence_identity_unique.sql` (Phase 2) adds one UNIQUE index -
`idx_raw_evidence_identity` on `raw_evidence(source_id, content_hash,
source_url_or_identifier)` - the evidence-identity/deduplication key for
the Phase 2 legacy evidence importer. Byte-identical content from the same
source but a different `source_url_or_identifier` is a distinct record,
not a duplicate (see `importers/legacy_evidence_importer.py`'s module
docstring for the full decision and its schema evidence). Applying this
migration is preflighted by `apply_schema.py`'s `_preflight_003()`, which
raises a clear `RuntimeError` naming how many duplicate groups exist if
`raw_evidence` already violates the new constraint - necessary because
SQLite's `RAISE()` only works inside a trigger body, not in a plain script
statement, so 003's own `.sql` file cannot raise a custom message itself.

SQLite now, written to be mechanically portable to PostgreSQL later (see
the portability notes at the top of `001_initial_schema.sql`) - no cloud
database, credentials, or external service involved at this phase.

## Data import

`importers/legacy_evidence_importer.py` (Phase 2) is the controlled
importer -

```
legacy Kern / Butte / Lake / Del Norte evidence file
  -> raw_evidence + evidence_disposition (ACTIVE) + observations
```

Application code, not a numbered schema migration - built on top of the
`idx_raw_evidence_identity` constraint above. It reads legacy evidence
files read-only (restricted to `kern/`, `butte/`, `lake/`, `del_norte/`;
`monitor_runs/`, `output/`, dashboards, and exports are rejected) and
writes only into v2's own store, configured exclusively through the
`PIV2_ARTIFACT_ROOT` environment variable (must be an absolute path
outside the repository) - never back into any legacy county folder,
dossier, monitor, dashboard, export, or output. See the top-level
`property_intelligence_v2/README.md` for the full isolation rule.

Deliberately not yet built, and out of scope for this importer: parsing a
legacy document's actual field values (callers supply already-extracted
observation fields), parcel matching, and canonical-state creation - see
the module's own docstring for the exact write boundary. It has been
tested against synthetic fixtures only (`tests/
test_legacy_evidence_importer.py`, `tests/
test_evidence_identity_migration.py`) and has not been run against real
legacy county data.
