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
numbered file (`002_...sql`) and an entry in `apply_schema.py`'s
`MIGRATIONS` list; existing migration files are never edited in place
once applied anywhere.

SQLite now, written to be mechanically portable to PostgreSQL later (see
the portability notes at the top of `001_initial_schema.sql`) - no cloud
database, credentials, or external service involved at this phase.

## Data import (future work, not started)

Separate from schema migrations above: the controlled importer that will
eventually populate these tables from legacy evidence -

```
legacy Kern / Butte / Lake evidence
  -> raw_evidence records
  -> observations
  -> parcel matches
  -> canonical property state
```

This is application code, not a numbered schema migration, and doesn't
exist yet. It has not been designed, let alone built, and nothing in
Phase 1 runs it against real legacy data. When it is built, it must read
legacy evidence files read-only and write only into v2's own store -
never back into any legacy county folder, dossier, monitor, dashboard,
export, or output. See the top-level `property_intelligence_v2/README.md`
for the full isolation rule.
