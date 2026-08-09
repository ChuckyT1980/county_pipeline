"""
property_intelligence_v2/extractors/del_norte_asrprint_pipeline.py

Thin driver wiring the pure del_norte_asrprint parser to the committed
Phase 2 importer (property_intelligence_v2/importers/legacy_evidence_importer.py).
This is the only module in Phase 3B that imports legacy_evidence_importer -
del_norte_asrprint.py itself never does (see that module's own docstring).

What this module does, in order, for import_asrprint_file():
  a) validates legacy_path via legacy_evidence_importer's own
     validate_legacy_input_path() FIRST - before any read, before invoking
     the parser, before constructing source_url_or_identifier, before any
     database or artifact-related action. This is the same manifest
     allowlist/denylist logic import_evidence_record() itself uses
     (imported directly, not reimplemented or weakened), so calling it here
     first is a genuine earlier check, not a duplicate rule. An invalid
     path raises ImporterInputError immediately, from this call, before
     this function does anything else - no file has been opened yet.
     (An earlier version of this module deferred all validation to
     import_evidence_record(), which meant it read and HTML-parsed
     arbitrary file content - including paths outside the manifest
     entirely - before any check ran. Fixed here: validate first.)
  b) reads ONLY the validated, resolved path that call returns (never the
     caller-supplied original legacy_path value) and hands its decoded
     text to the pure parser, del_norte_asrprint.parse_asrprint();
  c) on AsrPrintExtractionFailure, returns PipelineSkipped WITHOUT calling
     import_evidence_record() at all - no raw_evidence row, no artifact
     file, no evidence_disposition row, no observations row is created,
     because the only code path that could create any of them is never
     reached;
  d) on AsrPrintExtractionSuccess, calls import_evidence_record() with raw
     observation fields only (each field_value exactly as printed on the
     source page - see del_norte_asrprint.py's own boundary-resolution
     notes for why no normalized value is ever included here), and with
     the same validated path used throughout - both as legacy_path and as
     the basis for source_url_or_identifier (E below).

What this module never does:
  - insert into observation_identifiers (parser's IdentifierCandidate
    values are available on the AsrPrintExtractionSuccess result for a
    caller to inspect, but this module does not read or persist them);
  - insert into exceptions for a warning on an otherwise-successful import
    (ExtractionWarning values are likewise available but not persisted);
  - reconstruct or claim any live AsrPrint URL - source_url_or_identifier
    is always the legacy file's path relative to the repository root (see
    _repo_relative_source_locator()), never the observed
    assessor_portal_related_link field.

Every capability listed as "never does" above requires its own,
separately-authorized future integration phase - see the approved Phase 3B
contract (delivered in this session prior to implementation) for exactly
which phase each one needs.
"""
from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importers"))
from legacy_evidence_importer import (  # noqa: E402
    ImportResult,
    ObservationFieldInput as ImporterObservationFieldInput,
    get_repo_root,
    import_evidence_record,
    validate_legacy_input_path,
)

from del_norte_asrprint import (  # noqa: E402
    AsrPrintExtractionFailure,
    AsrPrintExtractionInput,
    parse_asrprint,
)

# This pipeline is dedicated to one county - hardcoded here rather than a
# caller-supplied parameter, so a caller cannot accidentally mis-attribute
# a Del Norte AsrPrint capture to a different county.
COUNTY = "Del Norte"

CONTENT_TYPE = "text/html"


@dataclass(frozen=True)
class PipelineSkipped:
    """Returned when the parser failed. import_evidence_record() was never
    called for this record - see the module docstring, point (c)."""
    legacy_path: Path
    failure: AsrPrintExtractionFailure


PipelineResult = ImportResult | PipelineSkipped


def _repo_relative_source_locator(legacy_path: Path, *, repo_root: Path) -> str:
    """The stable, non-inferred source_url_or_identifier value: legacy_path's
    own location relative to the repository root, as a plain string. Never
    a reconstructed live AsrPrint URL - see the module docstring."""
    resolved = legacy_path.resolve()
    rel = resolved.relative_to(repo_root.resolve())
    return str(rel)


def import_asrprint_file(
    conn: sqlite3.Connection,
    *,
    ingestion_run_id: str,
    source_id: str,
    legacy_path: Path,
    artifact_root: Path,
    repo_root: Path | None = None,
    now: datetime | None = None,
) -> PipelineResult:
    """Validate legacy_path first (raises ImporterInputError immediately if
    it's outside the manifest, before anything else happens - see the
    module docstring, point (a)); parse the validated path with the pure
    AsrPrint parser; on success, call the committed importer's
    import_evidence_record() with raw observation fields only; on parser
    failure, call nothing and return PipelineSkipped."""
    effective_repo_root = repo_root or get_repo_root()

    # Validated FIRST - before any read, before the parser, before
    # source_url_or_identifier, before any database or artifact action.
    # Same manifest allowlist/denylist legacy_evidence_importer.py itself
    # uses (imported directly above, not reimplemented or weakened).
    validated_path = validate_legacy_input_path(legacy_path, repo_root=repo_root)

    raw_html = validated_path.read_text(encoding="utf-8", errors="replace")
    result = parse_asrprint(AsrPrintExtractionInput(
        legacy_path=validated_path,
        raw_html=raw_html,
        filename=validated_path.name,
    ))

    if isinstance(result, AsrPrintExtractionFailure):
        return PipelineSkipped(legacy_path=validated_path, failure=result)

    source_url_or_identifier = _repo_relative_source_locator(validated_path, repo_root=effective_repo_root)

    importer_observation_fields = tuple(
        ImporterObservationFieldInput(
            field_name=f.field_name, field_value=f.field_value, confidence=f.confidence,
        )
        for f in result.observation_fields
    )

    return import_evidence_record(
        conn,
        ingestion_run_id=ingestion_run_id,
        source_id=source_id,
        county=COUNTY,
        legacy_path=validated_path,
        source_url_or_identifier=source_url_or_identifier,
        content_type=CONTENT_TYPE,
        artifact_root=artifact_root,
        observation_fields=importer_observation_fields,
        repo_root=repo_root,
        now=now,
    )
