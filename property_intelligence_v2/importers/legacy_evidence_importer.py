"""
property_intelligence_v2/importers/legacy_evidence_importer.py

The controlled importer: legacy evidence file (Kern / Butte / Lake / Del
Norte only) -> raw_evidence + evidence_disposition + observations, written
transactionally into property_intelligence_v2's own store. Reads legacy
files read-only; never writes back into any legacy county folder, dossier,
monitor, dashboard, export, or output - see the top-level
property_intelligence_v2/README.md isolation rule.

SCOPE, STATED HONESTLY: this module does not parse or extract fields from
legacy documents. Field extraction (turning a PDF/HTML page into
(field_name, field_value) pairs) is a separate, not-yet-built capability.
Callers supply already-extracted observation fields; this module's job is
narrower: validate the input path against the manifest, validate the
artifact root, hash and content-address-store the file, and persist
records transactionally with the required disposition-before-observations
ordering and identity-uniqueness enforcement. It has been tested against
synthetic TEST_ONLY_/example.invalid fixtures only and has not been run
against real legacy county evidence.

## Artifact-root enforcement (Phase 2.2)

validate_artifact_root() (absolute path required, resolved, rejected if
inside get_repo_root()) is called unconditionally, as the very first thing,
by BOTH import_evidence_record() and run_legacy_import() - not only by
resolve_artifact_root(). Before this, resolve_artifact_root() was the only
place this check existed, and import_evidence_record()/run_legacy_import()
accepted an artifact_root Path directly with no validation of their own -
a caller could construct any Path (including one inside the repository, or
inside a legacy county folder) and pass it straight in, bypassing the
documented outside-repository isolation rule entirely. Both entry points
now enforce it themselves, so no caller - production or test - can reach
an artifact write without going through this check first, regardless of
whether resolve_artifact_root() was ever called.

## Evidence-identity decision (schema-evidenced)

raw_evidence's columns (001_initial_schema.sql) include
source_url_or_identifier as NOT NULL - a locator/provenance field distinct
from source_id (which source_registry row) and content_hash (what the
bytes are). Byte-identical content retrieved from the same source_id but a
DIFFERENT source_url_or_identifier is treated as a DISTINCT evidence
record, not a duplicate: collapsing across source_url_or_identifier would
silently discard which specific document/location a row came from, and
raw_evidence.source_url_or_identifier is a NOT NULL, single-valued column
that cannot represent two locations on one row anyway. The identity /
deduplication key is therefore:

    (source_id, content_hash, source_url_or_identifier)

enforced at the database level by migrations/003_evidence_identity_unique.sql
(idx_raw_evidence_identity). Re-running the importer against the exact same
triple is the only case treated as a duplicate (idempotent re-import,
returned with ImportResult.deduplicated=True) - the DB is what makes this
authoritative, not this module's own pre-check, which is why a concurrent
duplicate insert is still caught (see below).

## Concurrency

The identity key is enforced by idx_raw_evidence_identity (a real UNIQUE
index), not by a single-writer lock/BEGIN IMMEDIATE convention. Two
concurrent importer calls that both see "no existing row" for the same
triple and both proceed to INSERT will not both succeed: the raw_evidence
INSERT uses `ON CONFLICT(source_id, content_hash, source_url_or_identifier)
DO NOTHING`, and import_evidence_record() checks the resulting cursor's
rowcount (0 means the conflict was hit and nothing was inserted; 1 means
this call's row won) rather than parsing sqlite3.IntegrityError's message
text. An earlier version of this function matched on the literal substring
"idx_raw_evidence_identity" appearing in the exception text - verified
directly to be wrong: SQLite reports UNIQUE-constraint failures as
"UNIQUE constraint failed: raw_evidence.source_id, raw_evidence.content_hash,
raw_evidence.source_url_or_identifier" (table.column names), never the
index's own name, so that check could never actually match and the
recovery branch it gated was dead code. rowcount is not a string to parse
- it is exactly what SQLite reports for the statement that just ran. On a
lost race (rowcount == 0), the identity columns are re-read exactly before
trusting this is really a duplicate. This is preferred over relying purely
on BEGIN IMMEDIATE because it is enforced unconditionally by the schema,
not by every caller remembering to open transactions correctly - the same
reasoning migration 002 used to replace an unenforced `immutable` flag
column with real triggers. import_evidence_record() still opens its
per-record write phase with BEGIN IMMEDIATE as defense in depth, but the
UNIQUE index (and the ON CONFLICT clause targeting it) is the actual
guarantee.

## Failure / orphan-artifact audit trail

Three separate transaction/commit boundaries per run, matching
migrations/README.md's attempt -> observe -> classify -> save evidence ->
record outcome -> choose next action lifecycle:

  Phase A (run_legacy_import): INSERT ingestion_runs(status='attempted'),
    committed immediately, on its own - this row must survive even if
    every record below fails and rolls back. ingestion_runs is not one of
    migration 002's immutable tables, so a later UPDATE to it (Phase C) is
    schema-legal.

  Phase B (import_evidence_record, once per record): artifact bytes are
    written to disk OUTSIDE any DB transaction (the filesystem has no
    transactions to join). Then ONE transaction: INSERT raw_evidence,
    INSERT evidence_disposition (disposition-before-observations, ACTIVE),
    INSERT observations (0+). Any failure ROLLS BACK THE WHOLE
    TRANSACTION - no partial raw_evidence/observations rows ever persist.
    If the artifact was already written to disk before the rollback, it is
    left in place as an orphan (not deleted) - Phase C is what records
    that it exists.

  Phase C (run_legacy_import, after all records attempted): ONE more
    transaction - UPDATE ingestion_runs SET status/finished_at/counts, plus
    one INSERT INTO exceptions per failed record, each referencing the
    ingestion_run (related_entity_type='ingestion_run') and naming the
    orphaned artifact path in `notes` if one was written. No raw_evidence
    row is ever created for a failed record; the exceptions row is the
    audit trail that a real attempt happened and what its artifact was.
    The UPDATE, every exceptions INSERT, and the commit are wrapped in one
    try/except: any failure among them calls conn.rollback() and raises
    ImportFinalizationError (never swallowed, never returned as a
    misleading RunResult) - the ingestion_runs row is left exactly at
    Phase A's own already-committed 'attempted' state, not a half-finalized
    mix, and the connection is left with no open transaction.

## Importer boundary (what this module writes, and what it never does)

INSERT-only into: ingestion_runs (plus one UPDATE of its own status/counts
- see Phase C above, this is the one exception to "INSERT-only" and is
scoped to the run row this call itself created), raw_evidence,
evidence_disposition, observations, exceptions.

Never writes: source_registry (read-only lookup via _require_known_source
- the importer never creates or updates a source; an unknown source_id is
a hard failure, not an auto-registration), observation_identifiers,
parcels, parcel_matches, canonical_property_state, canonical_state_support,
reconciliation_feedback. In particular, this module contains no INSERT or
UPDATE against canonical_property_state at all in this phase - it does not
create canonical states (even as UNVERIFIED) because doing so would
require parcel-matching logic that does not exist yet. If a future phase
adds that, the rule stated here still holds: canonical_property_state may
only ever be INSERTed as UNVERIFIED (migration 002's own
trg_canonical_state_no_verified_on_insert already enforces this at the DB
level) and this importer must never UPDATE verification_status - that
transition is a separate, not-yet-designed, human/review-gated process,
never an automated import side effect.
tests/test_legacy_evidence_importer.py proves these boundaries both
behaviorally and by static source-scan of this file.
"""
from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

ARTIFACT_ROOT_ENV_VAR = "PIV2_ARTIFACT_ROOT"

# The only legacy top-level directories this importer may read from.
ALLOWED_MANIFEST_ROOTS = ("kern", "butte", "lake", "del_norte")

# Denied anywhere in the path, even nested under an allowed root - defense
# in depth beyond the top-level allowlist check.
DENIED_PATH_COMPONENTS = ("monitor_runs", "output", "dashboards", "exports", "__pycache__")

# Values this import call would newly introduce as evidence content or
# provenance must never contain this marker - it exists so a real
# production run can never silently persist a test fixture, and so a test
# fixture can never be mistaken for real data. Does NOT cover source_id /
# ingestion_run_id, which are references to pre-existing rows this module
# never creates (validated instead via _require_known_source).
TEST_ONLY_MARKER = "TEST_ONLY_"

CONTENT_TYPE_EXTENSIONS = {
    "text/html": "html",
    "application/pdf": "pdf",
    "application/json": "json",
    "text/plain": "txt",
    "text/csv": "csv",
}


class LegacyEvidenceImporterError(Exception):
    """Base class for every error this module raises deliberately."""


class ImporterConfigError(LegacyEvidenceImporterError):
    """PIV2_ARTIFACT_ROOT is missing, relative, or inside the repository."""


class ImporterInputError(LegacyEvidenceImporterError):
    """The legacy input path is outside the allowed manifest."""


class ImporterIdentityError(LegacyEvidenceImporterError):
    """A value that would be persisted contains the TEST_ONLY_ marker."""


class UnknownSourceError(LegacyEvidenceImporterError):
    """source_id does not already exist in source_registry."""


class ImportFinalizationError(LegacyEvidenceImporterError):
    """Phase C (finalizing an ingestion_runs row's status/counts and writing
    any exceptions rows) failed after Phase A's ingestion_runs row was
    already committed. run_id identifies which ingestion_runs row was left
    at its Phase A ('attempted') state by the rollback."""

    def __init__(self, message: str, *, run_id: str):
        super().__init__(message)
        self.run_id = run_id


class ImportTransactionError(LegacyEvidenceImporterError):
    """Phase B's transaction failed after the artifact (if any) was already written."""

    def __init__(self, message: str, *, artifact_path: Path | None = None):
        super().__init__(message)
        self.artifact_path = artifact_path


def get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def validate_artifact_root(root: str | Path) -> Path:
    """The one shared artifact-root check: requires an absolute path,
    resolves it, and rejects anything inside get_repo_root(). Does not
    create directories or write anything - pure path validation, like
    validate_legacy_input_path().

    This is called both by resolve_artifact_root() (env-var driven) and
    directly, unconditionally, by import_evidence_record() and
    run_legacy_import() themselves - so a caller cannot bypass the
    outside-repository isolation rule by constructing an artifact_root Path
    directly and skipping resolve_artifact_root(). See those functions'
    docstrings and the module's own "## Artifact-root enforcement" section
    above for why this was previously a real gap."""
    root_path = Path(root)
    if not root_path.is_absolute():
        raise ImporterConfigError(f"artifact_root must be an absolute path, got: {root!r}")
    resolved = root_path.resolve()
    repo_root = get_repo_root().resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise ImporterConfigError(
            f"artifact_root must not be inside the repository: {resolved} is under {repo_root}"
        )
    return resolved


def resolve_artifact_root(env: Mapping[str, str] | None = None) -> Path:
    """Read PIV2_ARTIFACT_ROOT from env (defaults to os.environ), then
    delegate to validate_artifact_root() for the absolute-path and
    outside-repository checks. Does not create the directory."""
    env = os.environ if env is None else env
    raw = env.get(ARTIFACT_ROOT_ENV_VAR)
    if not raw:
        raise ImporterConfigError(f"{ARTIFACT_ROOT_ENV_VAR} is not set. Refusing to guess an artifact root.")
    return validate_artifact_root(raw)


def validate_legacy_input_path(path: Path, *, repo_root: Path | None = None) -> Path:
    """Pure path-string validation - does not touch the filesystem, does not
    require the file to exist. repo_root is injectable for tests; defaults to
    the real repository root in production."""
    root = (repo_root or get_repo_root()).resolve()
    resolved = Path(path).resolve()
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        raise ImporterInputError(f"legacy input path is not inside the repository: {resolved}")
    parts = rel.parts
    if not parts or parts[0] not in ALLOWED_MANIFEST_ROOTS:
        raise ImporterInputError(
            f"legacy input path is not under an allowed manifest root {ALLOWED_MANIFEST_ROOTS}: {rel}"
        )
    for part in parts:
        if part in DENIED_PATH_COMPONENTS:
            raise ImporterInputError(f"legacy input path passes through a denied directory ({part!r}): {rel}")
    return resolved


def reject_test_only(**named_values: str) -> None:
    for name, value in named_values.items():
        if value and TEST_ONLY_MARKER in value:
            raise ImporterIdentityError(
                f"refusing to persist a value containing {TEST_ONLY_MARKER!r} in {name!r}: {value!r}"
            )


def _validate_county_component(county: str) -> None:
    if not county or "/" in county or "\\" in county or ".." in county:
        raise ImporterInputError(f"county is not a safe path component: {county!r}")


def _artifact_extension(content_type: str) -> str:
    return CONTENT_TYPE_EXTENSIONS.get(content_type, "bin")


def content_addressed_path(artifact_root: Path, county: str, content_hash: str, content_type: str) -> Path:
    _validate_county_component(county)
    ext = _artifact_extension(content_type)
    return artifact_root / county / content_hash[:2] / f"{content_hash}.{ext}"


def _write_artifact_if_absent(artifact_path: Path, content: bytes) -> bool:
    """Content-addressed write. Returns True if this call wrote the file, False
    if it already existed (idempotent re-import - same hash means same bytes).
    Writes via a temp file + atomic rename, then marks the file read-only as a
    best-effort second guard (the real immutability guarantee is that a given
    content-addressed path is only ever written once)."""
    if artifact_path.exists():
        return False
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = artifact_path.with_name(artifact_path.name + ".tmp")
    tmp_path.write_bytes(content)
    tmp_path.replace(artifact_path)
    try:
        os.chmod(artifact_path, 0o444)
    except OSError:
        pass  # best-effort only; not every filesystem/mount honors this
    return True


def _require_known_source(conn: sqlite3.Connection, source_id: str) -> None:
    row = conn.execute("SELECT 1 FROM source_registry WHERE source_id = ?", (source_id,)).fetchone()
    if row is None:
        raise UnknownSourceError(
            f"source_id {source_id!r} does not exist in source_registry. "
            "This importer never creates or updates source_registry."
        )


@dataclass(frozen=True)
class ObservationFieldInput:
    field_name: str
    field_value: str
    confidence: str  # must be one of observations.confidence's CHECK vocabulary


@dataclass
class ImportResult:
    evidence_id: str
    observation_ids: list[str]
    artifact_path: Path
    artifact_written: bool
    deduplicated: bool


def import_evidence_record(
    conn: sqlite3.Connection,
    *,
    ingestion_run_id: str,
    source_id: str,
    county: str,
    legacy_path: Path,
    source_url_or_identifier: str,
    content_type: str,
    artifact_root: Path,
    observation_fields: tuple[ObservationFieldInput, ...] = (),
    repo_root: Path | None = None,
    now: datetime | None = None,
    _test_only_race_hook: Callable[[], None] | None = None,
) -> ImportResult:
    """Phase B: import exactly one legacy evidence file into raw_evidence +
    evidence_disposition + observations, in one transaction. Raises without
    persisting anything if the input path, a value, or the source is rejected.

    _test_only_race_hook is never passed by production code (run_legacy_import
    never passes it). It exists solely so tests/test_legacy_evidence_importer.py
    can deterministically force a genuine identity-conflict race - a second
    real connection committing the same identity in the gap between this
    call's own pre-check SELECT and its INSERT - instead of relying on real
    thread timing, which would make that regression test flaky."""
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Validated first, before any other check or side effect - see this
    # module's "## Artifact-root enforcement" docstring section.
    artifact_root = validate_artifact_root(artifact_root)

    validated_path = validate_legacy_input_path(legacy_path, repo_root=repo_root)

    reject_test_only(
        county=county,
        source_url_or_identifier=source_url_or_identifier,
        content_type=content_type,
        legacy_path=str(validated_path),
        **{f"observation_field_name[{i}]": f.field_name for i, f in enumerate(observation_fields)},
        **{f"observation_field_value[{i}]": f.field_value for i, f in enumerate(observation_fields)},
    )

    _require_known_source(conn, source_id)

    content = validated_path.read_bytes()
    if TEST_ONLY_MARKER.encode("utf-8") in content:
        raise ImporterIdentityError(
            f"refusing to persist file content containing {TEST_ONLY_MARKER!r}: {validated_path}"
        )

    content_hash = hashlib.sha256(content).hexdigest()
    artifact_path = content_addressed_path(artifact_root, county, content_hash, content_type)

    existing = conn.execute(
        "SELECT evidence_id FROM raw_evidence WHERE source_id = ? AND content_hash = ? AND source_url_or_identifier = ?",
        (source_id, content_hash, source_url_or_identifier),
    ).fetchone()
    if existing is not None:
        artifact_written = _write_artifact_if_absent(artifact_path, content)
        return ImportResult(
            evidence_id=existing[0], observation_ids=[], artifact_path=artifact_path,
            artifact_written=artifact_written, deduplicated=True,
        )

    if _test_only_race_hook is not None:
        _test_only_race_hook()

    artifact_written = _write_artifact_if_absent(artifact_path, content)

    evidence_id = f"EV_{uuid.uuid4().hex}"
    observation_ids = [f"OBS_{uuid.uuid4().hex}" for _ in observation_fields]

    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            "INSERT INTO raw_evidence (evidence_id, ingestion_run_id, source_id, retrieved_at, content_hash, "
            "content_type, source_url_or_identifier, storage_path) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(source_id, content_hash, source_url_or_identifier) DO NOTHING",
            (evidence_id, ingestion_run_id, source_id, now_iso, content_hash, content_type,
             source_url_or_identifier, str(artifact_path)),
        )
        lost_identity_race = cur.rowcount == 0
        if not lost_identity_race:
            conn.execute(
                "INSERT INTO evidence_disposition (disposition_id, evidence_id, disposition, set_at, reason) "
                "VALUES (?,?,?,?,?)",
                (f"DISP_{uuid.uuid4().hex}", evidence_id, "ACTIVE", now_iso, "imported by legacy_evidence_importer"),
            )
            for obs_id, f in zip(observation_ids, observation_fields):
                conn.execute(
                    "INSERT INTO observations (observation_id, evidence_id, observed_at, county, field_name, "
                    "field_value, confidence) VALUES (?,?,?,?,?,?,?)",
                    (obs_id, evidence_id, now_iso, county, f.field_name, f.field_value, f.confidence),
                )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise ImportTransactionError(f"transaction failed: {exc}", artifact_path=artifact_path) from exc

    if lost_identity_race:
        # The raw_evidence INSERT itself affected 0 rows (ON CONFLICT DO
        # NOTHING) - some other transaction already committed a row for this
        # exact (source_id, content_hash, source_url_or_identifier) identity
        # between our pre-check SELECT above and this INSERT. Detected via
        # cursor.rowcount (what SQLite actually reports for the statement
        # that ran), never by matching driver error text - re-read the
        # identity columns exactly before trusting this is really a
        # duplicate. See this module's "## Concurrency" docstring section.
        raced_row = conn.execute(
            "SELECT evidence_id FROM raw_evidence WHERE source_id = ? AND content_hash = ? "
            "AND source_url_or_identifier = ?",
            (source_id, content_hash, source_url_or_identifier),
        ).fetchone()
        if raced_row is None:
            # raw_evidence is immutable (migration 002 blocks DELETE
            # unconditionally), so a row that caused this conflict cannot
            # have vanished - defensive only, not expected to be reachable.
            raise ImportTransactionError(
                "raw_evidence INSERT ... ON CONFLICT DO NOTHING reported no row inserted, "
                "but no existing row matches this identity",
                artifact_path=artifact_path,
            )
        return ImportResult(
            evidence_id=raced_row[0], observation_ids=[], artifact_path=artifact_path,
            artifact_written=artifact_written, deduplicated=True,
        )

    return ImportResult(
        evidence_id=evidence_id, observation_ids=observation_ids, artifact_path=artifact_path,
        artifact_written=artifact_written, deduplicated=False,
    )


@dataclass
class RecordFailure:
    legacy_path: Path
    error: str
    orphan_artifact_path: Path | None = None


@dataclass
class RunResult:
    run_id: str
    status: str
    succeeded: list[ImportResult] = field(default_factory=list)
    failed: list[RecordFailure] = field(default_factory=list)


def run_legacy_import(
    conn: sqlite3.Connection,
    *,
    source_id: str,
    county: str,
    records: list[dict],
    artifact_root: Path,
    repo_root: Path | None = None,
    now: datetime | None = None,
) -> RunResult:
    """Phases A + (per-record B) + C. `records` is a list of dicts with keys
    legacy_path, source_url_or_identifier, content_type, and optionally
    observation_fields (tuple[ObservationFieldInput, ...])."""
    now = now or datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Validated before Phase A creates/commits an ingestion_runs row - see
    # this module's "## Artifact-root enforcement" docstring section. The
    # validated (resolved) Path is what every per-record import_evidence_record()
    # call below receives, not the caller's original, unvalidated value.
    artifact_root = validate_artifact_root(artifact_root)

    _require_known_source(conn, source_id)  # fail fast, before creating a run row at all

    run_id = f"RUN_{uuid.uuid4().hex}"

    # Phase A: its own commit - this row survives regardless of what happens below.
    conn.execute(
        "INSERT INTO ingestion_runs (run_id, source_id, started_at, status) VALUES (?,?,?,?)",
        (run_id, source_id, now_iso, "attempted"),
    )
    conn.commit()

    succeeded: list[ImportResult] = []
    failed: list[RecordFailure] = []

    for record in records:
        try:
            result = import_evidence_record(
                conn,
                ingestion_run_id=run_id,
                source_id=source_id,
                county=county,
                legacy_path=record["legacy_path"],
                source_url_or_identifier=record["source_url_or_identifier"],
                content_type=record["content_type"],
                observation_fields=record.get("observation_fields", ()),
                artifact_root=artifact_root,
                repo_root=repo_root,
                now=now,
            )
            succeeded.append(result)
        except (LegacyEvidenceImporterError, OSError) as exc:
            failed.append(RecordFailure(
                legacy_path=record["legacy_path"],
                error=str(exc),
                orphan_artifact_path=getattr(exc, "artifact_path", None),
            ))

    if not records:
        status = "attempted"
    elif not failed:
        status = "succeeded"
    elif succeeded:
        status = "partial"
    else:
        status = "failed"

    # Phase C: the ingestion_runs UPDATE, every exceptions INSERT, and the
    # final commit are one transaction - any failure among them rolls all of
    # it back, leaving the ingestion_runs row exactly at the state Phase A's
    # own commit left it in (status='attempted', no finished_at/counts), not
    # a half-finalized mix. Phase A's own commit (above) is untouched either
    # way - it already happened in its own transaction before this block.
    try:
        conn.execute(
            "UPDATE ingestion_runs SET status = ?, finished_at = ?, attempted_count = ?, succeeded_count = ?, "
            "failed_count = ? WHERE run_id = ?",
            (status, now_iso, len(records), len(succeeded), len(failed), run_id),
        )
        for rf in failed:
            notes = f"legacy_path={rf.legacy_path} error={rf.error}"
            if rf.orphan_artifact_path is not None:
                notes += f" orphan_artifact_path={rf.orphan_artifact_path}"
            conn.execute(
                "INSERT INTO exceptions (exception_id, occurred_at, stage, related_entity_type, related_entity_id, "
                "classification, severity, next_action, status, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (f"EXC_{uuid.uuid4().hex}", now_iso, "ingestion", "ingestion_run", run_id,
                 "unknown", "medium", "human_review", "open", notes),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise ImportFinalizationError(
            f"Phase C finalization failed for run {run_id}: {exc}", run_id=run_id
        ) from exc

    return RunResult(run_id=run_id, status=status, succeeded=succeeded, failed=failed)
