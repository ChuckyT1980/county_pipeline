"""
property_intelligence_v2/importers/run_del_norte_asrprint_batch.py

Phase 3E: the batch orchestrator identified as a gap during Phase 3D
planning. import_asrprint_file() (Phase 3B) requires a caller-provided
ingestion_run_id and does not create or finalize a run; run_legacy_import()
(the generic Phase 2 orchestrator) expects pre-computed observation_fields
per record, not legacy file paths to parse. This module fills exactly that
gap for the Del Norte AsrPrint pipeline specifically - it does not touch,
generalize, or replace either of those.

## Design notes (deviations from the literal Phase 3E task wording, made
## transparently during design and preserved here)

- Per-record Phase B calls import_asrprint_file() exactly once. It does
  NOT call parse_asrprint() separately first - import_asrprint_file()
  already validates the path, reads only the validated path, parses, and
  either returns PipelineSkipped (parser failure - no artifact, no
  raw_evidence, import_evidence_record() never reached) or proceeds to a
  real import. Parsing the same file twice would be wasteful and would
  risk inconsistency between two separate reads of the same file.
- No `county` parameter exists here (or in run_del_norte_asrprint_batch()'s
  signature) because import_asrprint_file() itself hardcodes
  county="Del Norte" - accepting a parameter that could never reach
  anything would be misleading API design.

## Phase A (mandatory preflight, in this exact order, before any
## ingestion_runs row exists)

1. artifact_root is validated via the committed validate_artifact_root() -
   FIRST, before the source lookup. An invalid/relative/in-repo root
   raises ImporterConfigError immediately; zero ingestion_runs rows are
   ever created for this failure.
2. source_id is verified to already exist in source_registry. An unknown
   source raises UnknownSourceError immediately; zero ingestion_runs rows
   are created. This module never creates or updates source_registry.
3. Only then: one ingestion_runs row (status='attempted') is inserted and
   committed on its own, before any record is touched.

## Phase B (per record)

import_asrprint_file() is called once per record, using the shared run_id
and the already-validated artifact_root:
  - PipelineSkipped (parser failure) -> BatchParserSkip. No importer call
    happened for this record at all.
  - LegacyEvidenceImporterError or OSError raised -> BatchImporterFailure.
    (OSError is caught alongside LegacyEvidenceImporterError because
    import_asrprint_file()'s own .read_text() can raise IsADirectoryError/
    PermissionError/disk-full errors that are not LegacyEvidenceImporterError
    subclasses - the same reasoning run_legacy_import() already uses.)
  - ImportResult returned (deduplicated=True or False) -> counted as
    succeeded either way. A deduplicated import means the evidence is
    correctly represented in the system already; treating it as a failure
    would penalize the exact safe-re-run property Phase 2 was built to
    guarantee. The `deduplicated` flag stays visible on the ImportResult
    itself for any caller that needs to distinguish "new this run" from
    "already existed."

This module never inserts into observation_identifiers, parcels,
parcel_matches, canonical_property_state, or any normalized-value column -
the same boundary the committed importer and Phase 3B extractor already
hold, simply never crossed here either. It never inserts an exceptions row
for a mere warning on an otherwise-successful import - only for records
that end up in parser_skips or importer_failures.

## Phase C

One transaction: UPDATE ingestion_runs (final status/counts) plus one
exceptions row per parser skip and per importer failure, then commit. Any
failure in this block calls conn.rollback() and raises
ImportFinalizationError(run_id=...) - imported and reused as-is from
legacy_evidence_importer.py, not reimplemented - and BatchRunResult is
never returned in that case. This is the identical atomicity guarantee
run_legacy_import()'s own Phase C already has.

## Exception mapping (no new classification/severity/next_action/status
## values - only the vocabulary already in the committed exceptions CHECK
## constraints)

  Parser skip (any AsrPrintExtractionFailure)
    classification = the skip's own classification (currently always
      'schema_mismatch', copied dynamically rather than hardcoded, so this
      stays correct if the parser's own failure taxonomy ever changes)
    severity = 'medium'
    next_action = the skip's own next_action (currently always
      'human_review', copied dynamically for the same reason)
    status = 'open'

  Importer failure (ImporterInputError / bare OSError / ImportTransactionError
  / ImporterIdentityError / any other LegacyEvidenceImporterError)
    classification = 'unknown'
    severity = 'medium' for ImporterIdentityError, 'high' for everything else
    next_action = 'human_review'
    status = 'open'
    orphan_artifact_path is included in `notes` when the underlying
    exception carries one (ImportTransactionError only - the artifact was
    already written to disk before the transaction that then rolled back)

  UnknownSourceError (Phase A preflight): no exceptions row at all - the
    batch never starts, nothing exists to log against.
  Duplicate identity: no exceptions row - a success, not a failure.
  Phase C failure: no exceptions row - nothing left to insert into;
    communicated only via the raised ImportFinalizationError.

`notes` is built only from: legacy_path (a repo-relative string - the same
locator convention raw_evidence.source_url_or_identifier itself already
uses, not a new exposure), the exception's type name, its own generic
message, and orphan_artifact_path when present. It never includes any
parsed field_name/field_value content - structurally impossible, since
neither BatchParserSkip nor BatchImporterFailure ever carries parsed field
data at all.
"""
from __future__ import annotations

import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legacy_evidence_importer import (  # noqa: E402
    ImportFinalizationError,
    ImportResult,
    LegacyEvidenceImporterError,
    UnknownSourceError,
    validate_artifact_root,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extractors"))
from del_norte_asrprint_pipeline import (  # noqa: E402
    PipelineSkipped,
    import_asrprint_file,
)


@dataclass(frozen=True)
class BatchParserSkip:
    """A record where the parser (invoked internally by import_asrprint_file())
    returned AsrPrintExtractionFailure. No artifact, no raw_evidence -
    import_evidence_record() was never reached for this record."""
    legacy_path: Path
    classification: str
    next_action: str
    message: str


@dataclass(frozen=True)
class BatchImporterFailure:
    """A record where import_asrprint_file() itself raised - path
    validation, an unexpected unknown-source condition, TEST_ONLY_
    rejection, an artifact-write OSError, or a rolled-back DB transaction."""
    legacy_path: Path
    error_type: str
    message: str
    orphan_artifact_path: Path | None = None


@dataclass(frozen=True)
class BatchRunResult:
    run_id: str
    status: str
    succeeded: tuple[ImportResult, ...] = field(default_factory=tuple)
    parser_skips: tuple[BatchParserSkip, ...] = field(default_factory=tuple)
    importer_failures: tuple[BatchImporterFailure, ...] = field(default_factory=tuple)


def _require_known_source(conn: sqlite3.Connection, source_id: str) -> None:
    """Deliberately duplicated, minimal (one-line) check rather than
    importing legacy_evidence_importer's own underscore-prefixed private
    helper of the same name - reaching into another module's "private" name
    is a worse code smell than a two-line duplicate of a trivial read-only
    SELECT. Unlike artifact-root validation (substantial, error-prone logic
    that warranted real extraction in an earlier phase), this check is
    trivial enough that duplication carries negligible risk."""
    row = conn.execute("SELECT 1 FROM source_registry WHERE source_id = ?", (source_id,)).fetchone()
    if row is None:
        raise UnknownSourceError(
            f"source_id {source_id!r} does not exist in source_registry. "
            "This orchestrator never creates or updates source_registry."
        )


def run_del_norte_asrprint_batch(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    records: Sequence[Path],
    artifact_root: Path,
    repo_root: Path | None = None,
    now: datetime | None = None,
) -> BatchRunResult:
    """Phase A (artifact-root + source preflight, one committed
    ingestion_runs row) -> per-record Phase B (import_asrprint_file() once
    per record) -> Phase C (one atomic status/count update + exceptions
    insert). See the module docstring for the full contract."""
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Phase A preflight, part 1: artifact_root validated FIRST - before the
    # source lookup, before any ingestion_runs row exists.
    artifact_root = validate_artifact_root(artifact_root)

    # Phase A preflight, part 2: source must already exist.
    _require_known_source(conn, source_id)

    # Phase A: one committed ingestion_runs row.
    run_id = f"RUN_{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        (run_id, source_id, now_iso, "attempted"),
    )
    conn.commit()

    succeeded: list[ImportResult] = []
    parser_skips: list[BatchParserSkip] = []
    importer_failures: list[BatchImporterFailure] = []

    # Phase B: import_asrprint_file() exactly once per record.
    for legacy_path in records:
        try:
            result = import_asrprint_file(
                conn,
                ingestion_run_id=run_id,
                source_id=source_id,
                legacy_path=legacy_path,
                artifact_root=artifact_root,
                repo_root=repo_root,
                now=now,
            )
        except (LegacyEvidenceImporterError, OSError) as exc:
            importer_failures.append(BatchImporterFailure(
                legacy_path=legacy_path,
                error_type=type(exc).__name__,
                message=str(exc),
                orphan_artifact_path=getattr(exc, "artifact_path", None),
            ))
            continue

        if isinstance(result, PipelineSkipped):
            parser_skips.append(BatchParserSkip(
                legacy_path=legacy_path,
                classification=result.failure.classification,
                next_action=result.failure.next_action,
                message=result.failure.message,
            ))
            continue

        succeeded.append(result)  # deduplicated imports count as success - see module docstring

    if not records:
        status = "attempted"
    elif not parser_skips and not importer_failures:
        status = "succeeded"
    elif succeeded:
        status = "partial"
    else:
        status = "failed"

    # Phase C: one atomic transaction. Any failure rolls back the whole
    # block and raises ImportFinalizationError - BatchRunResult is never
    # returned in that case.
    try:
        conn.execute(
            "UPDATE ingestion_runs SET status = ?, finished_at = ?, attempted_count = ?, succeeded_count = ?, "
            "failed_count = ? WHERE run_id = ?",
            (status, now_iso, len(records), len(succeeded), len(parser_skips) + len(importer_failures), run_id),
        )
        for skip in parser_skips:
            notes = f"legacy_path={skip.legacy_path} error_type=AsrPrintExtractionFailure message={skip.message}"
            conn.execute(
                "INSERT INTO exceptions (exception_id, occurred_at, stage, related_entity_type, related_entity_id, "
                "classification, severity, next_action, status, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"EXC_{uuid.uuid4().hex}", now_iso, "ingestion", "ingestion_run", run_id,
                 skip.classification, "medium", skip.next_action, "open", notes),
            )
        for imp_failure in importer_failures:
            severity = "medium" if imp_failure.error_type == "ImporterIdentityError" else "high"
            notes = f"legacy_path={imp_failure.legacy_path} error_type={imp_failure.error_type} message={imp_failure.message}"
            if imp_failure.orphan_artifact_path is not None:
                notes += f" orphan_artifact_path={imp_failure.orphan_artifact_path}"
            conn.execute(
                "INSERT INTO exceptions (exception_id, occurred_at, stage, related_entity_type, related_entity_id, "
                "classification, severity, next_action, status, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"EXC_{uuid.uuid4().hex}", now_iso, "ingestion", "ingestion_run", run_id,
                 "unknown", severity, "human_review", "open", notes),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise ImportFinalizationError(
            f"Phase C finalization failed for run {run_id}: {exc}", run_id=run_id
        ) from exc

    return BatchRunResult(
        run_id=run_id,
        status=status,
        succeeded=tuple(succeeded),
        parser_skips=tuple(parser_skips),
        importer_failures=tuple(importer_failures),
    )
