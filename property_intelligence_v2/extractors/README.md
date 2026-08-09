# extractors/

Phase 3B: the first document-specific extraction target, chosen by the
Phase 3A read-only discovery pass - Del Norte County's assessor "AsrPrint"
HTML page (`del_norte/raw_evidence/delnorte_asrprint_*.html`).

- `del_norte_asrprint.py` - the pure parser. `parse_asrprint()` takes
  already-decoded HTML text and returns a typed `AsrPrintExtractionSuccess`
  or `AsrPrintExtractionFailure`. No `sqlite3` connection, no filesystem
  access, no network access, no `artifact_root`, and no import of
  `legacy_evidence_importer` anywhere in the file - verified by the file
  containing no such import, not just documented as a rule.
- `del_norte_asrprint_pipeline.py` - the only module here that imports the
  committed Phase 2 importer. A thin driver: validate `legacy_path` first,
  parse the validated path, and only call `import_evidence_record()` on a
  successful parse.

## Confidence value

Every extracted field uses `confidence='carried_forward'` (`CONFIDENCE_VALUE`
in `del_norte_asrprint.py`) - **not** `'confirmed'`. Corrected after an
audit caught the original choice as wrong; the reasoning below is the
corrected version, not the original one.

`property_intelligence_v2/contracts/entities.py`'s `ConfidenceLevel` enum
documents the full existing vocabulary:

- `'confirmed'` - *"directly read from a live official source this run"*.
  **Reserved for data actually fetched from the live official source
  during the current ingestion run.** This pipeline imports archived local
  HTML evidence (`del_norte/raw_evidence/delnorte_asrprint_*.html`) - it
  does not fetch or re-verify a live source at any point. `'confirmed'`
  does not apply here, however authoritative the original capture was.
- `'carried_forward'` - *"seen on a prior run, not re-verified this run"*.
  **This is what archived legacy captures are.** The value was established
  as true at an earlier point (the original capture, whenever and however
  it happened); this run does not re-verify it against the live source.
  Of the four existing values, this is the closest match for authoritative
  archived evidence that is not live-re-verified during the current
  ingestion - acknowledged as an imperfect fit to the literal phrasing
  ("seen on a *prior run*" evidently pictures an observation that already
  existed and is being repeated, not a first-time import of an archived
  file), but the closest available without inventing a new value.
- `'source_list_only'` - *"present on a source list, never independently
  verified"*. Does not apply - an AsrPrint page is a full primary
  per-parcel document, not a bulk list entry.
- `'unconfirmed'` - *"present but contradicted, or not yet checked"*. Does
  not apply - nothing extracted here is contradicted, and every value was
  in fact checked (correctly parsed from a genuine document).

No new vocabulary value was added and no migration was made.

## Boundary resolutions carried over from the approved Phase 3B contract

1. **`observation_identifiers`**: the committed importer never writes this
   table. APN, assessment number, and current document number are
   extracted as `IdentifierCandidate` values on the parser's result -
   in-memory only. Nothing in this directory persists them.
2. **Raw vs. normalized**: `observations` has one `field_value` column.
   Every `ObservationFieldInput` produced here carries the raw, as-printed
   value only. No `_raw`/`_normalized` field-name pairs exist. Internal
   normalization attempts (identifier candidates; a numeric sanity check on
   dollar/lot-size fields) either feed
   `IdentifierCandidate.value_normalized_or_none` or a
   `VALUE_DID_NOT_NORMALIZE` warning - never a second observation field.
3. **Warnings**: the committed importer's `run_legacy_import()` writes
   `exceptions` rows only for records in its own `failed` list - never for
   a successful import. Unrecognized labels, missing optional fields,
   conflicting duplicate labels, and failed internal normalization all
   become `ExtractionWarning` values on the parser's result - in-memory
   only, never an `exceptions` row.
4. **Source locator**: the page's own embedded "BACK" link
   (`assessor_portal_related_link`) is extracted as ordinary page content,
   not as capture provenance - no network request that produced any given
   file was independently confirmed. `source_url_or_identifier` is always
   the legacy file's own path relative to the repository root instead (see
   `del_norte_asrprint_pipeline.py`'s `_repo_relative_source_locator()`).
5. **Required field / failure semantics**: Assessor Parcel Number(APN) is
   the sole required field. Its absence, or an unrecognized page/table
   shape, returns a typed `AsrPrintExtractionFailure` - the pipeline driver
   never calls `import_evidence_record()` in that case, so no
   `raw_evidence` row, artifact file, `evidence_disposition` row, or
   `observations` row is ever created for that record.

## Path-validation ordering (corrected)

An earlier version of `del_norte_asrprint_pipeline.py` read and
HTML-parsed `legacy_path`'s content before any manifest check ran -
`validate_legacy_input_path()` was only reached inside
`import_evidence_record()`, and only on a successful parse, meaning an
invalid path (outside `kern/butte/lake/del_norte`, or under a denied
component like `monitor_runs/`/`output/`) would still be opened and parsed
before being rejected. Fixed: `import_asrprint_file()` now calls
`legacy_evidence_importer.validate_legacy_input_path()` as the very first
thing it does - before any read, before the parser, before
`source_url_or_identifier`, before any database or artifact action. The
same allowlist/denylist logic is used (imported directly, not
reimplemented), and only the validated, resolved path it returns is ever
read or persisted.

## Future integration phases required (none authorized or built here)

- **Identifier persistence** - a new phase extending
  `legacy_evidence_importer.py` (or a sibling module) with an INSERT path
  into `observation_identifiers`.
- **Normalized-value persistence** - an explicit decision on where
  normalized values would live (a new migration adding columns to
  `observations`, or routing through `observation_identifiers`'s existing
  normalized column once identifier persistence exists) - not decided here.
- **Warning-to-`exceptions` persistence** - extending
  `run_legacy_import()`'s Phase C (or a new phase) to insert `exceptions`
  rows for warnings attached to successful records, which changes the
  committed importer's current semantics and needs its own authorization
  and tests.

## Tests

`tests/test_del_norte_asrprint_extractor.py` tests the parser alone, with
fully synthetic inline HTML fixtures - no database, no importer call.
`tests/test_del_norte_asrprint_pipeline.py` tests the driver against a
temporary in-memory SQLite database and a temporary external artifact
root - never `del_norte/`'s real files, never the real repository.

## Recorder pipeline (Phase 4F) - `del_norte_recorder_result_pipeline.py`

A second, separate thin pipeline for Del Norte's Tyler Self-Service
recorder document-number search, distinct from the AsrPrint assessor
pipeline above. Sits between `del_norte_recorder_live_client.py`
(`importers/`, the HTTP layer) and `del_norte_recorder_result.py` (the
Phase 4D pure parser, unchanged by this phase).

- **One-result gate**: calls `import_evidence_record()` only when the live
  client succeeds, the parser returns success, exactly one row was parsed,
  and that row's document number matches the query. Any other outcome
  returns `RecorderPipelineNotImported` - no artifact, no database write.
- **Byte-for-byte evidence**: the persisted `raw_content` is always the
  live client's own response bytes, unmodified - never a re-encoded copy of
  the string decoded separately for the parser.
- **Confidence**: `'confirmed'`, not `'carried_forward'` - this data is
  read from a live source during the current run, unlike AsrPrint's
  archived-file evidence.
- **Party ordering**: `recorder_grantor_name_1..N` /
  `recorder_grantee_name_1..N` (1-indexed) preserve the parser's exact
  source order and repeats - no deduplication.
- **APN/book-page**: persisted only when the parser reports the field both
  present and non-blank.
- **Permanent rules inherited unchanged from Phase 4D**: `detail_link_path`
  is stored as opaque text only, never fetched by this or any module
  without its own separate authorization; party fields are never named
  `owner`/`current_owner`; no title/lien/legal-status conclusion is ever
  drawn here.
- **Run lifecycle**: takes `ingestion_run_id` as a caller-supplied
  parameter and never creates/finalizes a run or writes `exceptions` -
  deferred to a future batch orchestrator, mirroring the AsrPrint pipeline.
- **Tests**: `tests/test_del_norte_recorder_live_client.py` (client, fully
  mocked transport, no real HTTP) and
  `tests/test_del_norte_recorder_result_pipeline.py` (pipeline, synthetic
  HTML + temporary in-memory database + temporary external artifact root).
