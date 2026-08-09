"""
property_intelligence_v2/extractors/del_norte_recorder_result_pipeline.py

Phase 4F: the thin pipeline that connects the live-query client
(del_norte_recorder_live_client.py), the pure recorder-result parser
(del_norte_recorder_result.py, Phase 4D), and the committed importer's new
raw_content route (legacy_evidence_importer.import_evidence_record(),
extended for Phase 4F/Option A) - for exactly one document-number lookup.

## The one-result gate (Phase 4E design, implemented exactly)

import_recorder_document_number_result() only calls import_evidence_record()
after ALL of the following hold:
  1. the live client returned a plain RecorderLiveQuerySuccess (not
     RecorderLiveQueryBlocked/RecorderLiveQueryError);
  2. parse_recorder_results() returned RecorderResultsExtractionSuccess
     (not RecorderResultsExtractionFailure);
  3. exactly one row was parsed;
  4. that row's document_number_matches_query is True.
On ANY other outcome, this function returns a typed RecorderPipelineNotImported
describing why - no artifact, no database write, nothing persisted. This
mirrors del_norte_asrprint_pipeline.py's PipelineSkipped pattern exactly.

## Byte-for-byte evidence preservation

The bytes persisted through import_evidence_record()'s raw_content= are
exactly RecorderLiveQuerySuccess.raw_content, untouched - never a
re-encoded copy of a decoded string. Decoding only happens on a SEPARATE
copy, used solely to build the parser's RecorderResultsExtractionInput
(which takes raw_html: str), using an explicit UTF-8 decode with
errors="replace" - this is this module's own stated encoding assumption at
the client/parser boundary; the parser itself makes no encoding assumption
of its own since it only ever sees already-decoded text.

## Run-lifecycle boundary

This pipeline takes ingestion_run_id as a caller-supplied parameter and
does not create, update, or finalize any ingestion_runs row itself, and
never writes an exceptions row - exactly like del_norte_asrprint_pipeline.py.
Run-lifecycle management is deferred to a future batch orchestrator, not
built in this phase.

## Boundaries preserved (unchanged from the Phase 4D/4E design)

Never writes observation_identifiers, parcels, parcel_matches, or
canonical_property_state. Never writes an exceptions row for a nonfatal
parser warning (e.g. UNEXPECTED_DETAIL_LINK_FORM) attached to an otherwise
gate-passing row - the same "warnings on a success never become an
exceptions row" rule already established for the assessor pipeline. Never
fetches detail_link_path - it is persisted as opaque text only, if present.
Never persists an APN/book-page observation unless the parser reports it
both present AND non-blank (raw_or_none is not None).

## Confidence

Every persisted observation uses confidence='confirmed' - this data was, by
construction of the one-result gate, directly read from a live official
source during this run, which is the exact documented definition of
ConfidenceLevel.confirmed (unlike the archived-file AsrPrint pipeline,
which correctly uses 'carried_forward' instead - see extractors/README.md).

## Party-name ordering

grantor_name_1..N / grantee_name_1..N (1-indexed) preserve the parser's own
exact source order, including exact repeats across duplicate blocks -
nothing here re-orders, deduplicates, or drops an entry the parser already
preserved.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))
from del_norte_recorder_result import (  # noqa: E402
    RecorderResultsExtractionFailure,
    RecorderResultsExtractionInput,
    RecorderResultsExtractionSuccess,
    parse_recorder_results,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importers"))
from del_norte_recorder_live_client import (  # noqa: E402
    RecorderLiveQueryBlocked,
    RecorderLiveQueryError,
    RecorderLiveQuerySuccess,
    apply_doc_transform,
    fetch_recorder_document_number_result,
)
from legacy_evidence_importer import (  # noqa: E402
    ImportResult,
    ObservationFieldInput,
    import_evidence_record,
)

SEARCH_ID = "DOCSEARCH201S8"
COUNTY = "Del Norte"
CONFIDENCE_VALUE = "confirmed"
CONTENT_TYPE = "text/html"


@dataclass(frozen=True)
class RecorderPipelineNotImported:
    """A record that did not pass the one-result gate. No artifact, no
    database write - import_evidence_record() was never reached."""
    reason: str
    message: str


def _source_url_or_identifier(transformed_document_number: str) -> str:
    return f"recorder:{SEARCH_ID}:document_number={transformed_document_number}"


def import_recorder_document_number_result(
    conn,
    *,
    ingestion_run_id: str,
    source_id: str,
    document_number_assessor_form: str,
    artifact_root: Path,
    user_agent: str,
    repo_root: Path | None = None,
    now: datetime | None = None,
    opener_factory: Callable[[], object] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Union[ImportResult, RecorderPipelineNotImported]:
    """Fetch (live client) -> parse (Phase 4D parser) -> gate -> import
    (unchanged raw_content route on the committed importer). See the module
    docstring for the full contract."""
    now = now or datetime.now(timezone.utc)
    transformed = apply_doc_transform(document_number_assessor_form)

    client_kwargs = {}
    if opener_factory is not None:
        client_kwargs["opener_factory"] = opener_factory
    if sleep is not None:
        client_kwargs["sleep"] = sleep

    live_result = fetch_recorder_document_number_result(
        document_number_assessor_form, user_agent=user_agent, **client_kwargs
    )

    if isinstance(live_result, RecorderLiveQueryBlocked):
        return RecorderPipelineNotImported(
            reason=f"client_blocked:{live_result.reason}", message=live_result.message,
        )
    if isinstance(live_result, RecorderLiveQueryError):
        return RecorderPipelineNotImported(
            reason=f"client_error:{live_result.reason}", message=live_result.message,
        )
    assert isinstance(live_result, RecorderLiveQuerySuccess)

    # Decoding happens only here, on a separate copy, for the parser's
    # benefit - the bytes persisted below (if the gate passes) are always
    # live_result.raw_content itself, never re-derived from this string.
    decoded_html = live_result.raw_content.decode("utf-8", errors="replace")

    parsed = parse_recorder_results(RecorderResultsExtractionInput(
        queried_document_number_transformed=transformed,
        raw_html=decoded_html,
        search_id=SEARCH_ID,
    ))

    if isinstance(parsed, RecorderResultsExtractionFailure):
        return RecorderPipelineNotImported(reason="parser_failure", message=parsed.message)
    assert isinstance(parsed, RecorderResultsExtractionSuccess)

    if len(parsed.rows) == 0:
        return RecorderPipelineNotImported(
            reason="zero_results", message="the live query returned zero results",
        )
    if len(parsed.rows) > 1:
        return RecorderPipelineNotImported(
            reason="multiple_results",
            message=f"the live query returned {len(parsed.rows)} results, expected exactly one",
        )

    row = parsed.rows[0]
    if not row.document_number_matches_query:
        return RecorderPipelineNotImported(
            reason="document_number_mismatch",
            message="the returned document number did not match the queried document number",
        )

    # One-result gate passed - build observations and persist via the
    # unchanged (Phase 4F/Option A extended) committed importer.
    observation_fields: list[ObservationFieldInput] = [
        ObservationFieldInput(field_name="recorder_document_number", field_value=row.document_number, confidence=CONFIDENCE_VALUE),
    ]
    if row.recording_date_raw:
        observation_fields.append(ObservationFieldInput(
            field_name="recorder_recording_date", field_value=row.recording_date_raw, confidence=CONFIDENCE_VALUE,
        ))
    if row.instrument_type_raw:
        observation_fields.append(ObservationFieldInput(
            field_name="recorder_instrument_type", field_value=row.instrument_type_raw, confidence=CONFIDENCE_VALUE,
        ))
    for i, grantor in enumerate(row.grantors, start=1):
        observation_fields.append(ObservationFieldInput(
            field_name=f"recorder_grantor_name_{i}", field_value=grantor, confidence=CONFIDENCE_VALUE,
        ))
    for i, grantee in enumerate(row.grantees, start=1):
        observation_fields.append(ObservationFieldInput(
            field_name=f"recorder_grantee_name_{i}", field_value=grantee, confidence=CONFIDENCE_VALUE,
        ))
    if row.detail_link_path:
        observation_fields.append(ObservationFieldInput(
            field_name="recorder_detail_link_path", field_value=row.detail_link_path, confidence=CONFIDENCE_VALUE,
        ))
    if row.apn_present and row.apn_raw_or_none:
        observation_fields.append(ObservationFieldInput(
            field_name="recorder_apn", field_value=row.apn_raw_or_none, confidence=CONFIDENCE_VALUE,
        ))
    if row.book_page_present and row.book_page_raw_or_none:
        observation_fields.append(ObservationFieldInput(
            field_name="recorder_book_page", field_value=row.book_page_raw_or_none, confidence=CONFIDENCE_VALUE,
        ))

    return import_evidence_record(
        conn,
        ingestion_run_id=ingestion_run_id,
        source_id=source_id,
        county=COUNTY,
        raw_content=live_result.raw_content,
        source_url_or_identifier=_source_url_or_identifier(transformed),
        content_type=CONTENT_TYPE,
        artifact_root=artifact_root,
        observation_fields=tuple(observation_fields),
        repo_root=repo_root,
        now=now,
    )
