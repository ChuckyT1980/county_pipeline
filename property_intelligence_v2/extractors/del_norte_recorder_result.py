"""
property_intelligence_v2/extractors/del_norte_recorder_result.py

Pure parser for Del Norte County's Tyler Self-Service recorder
document-number search-results HTML. Implements the Phase 4D design record
(Phase 4A discovery, Phase 4C live no-persistence lookup, Phase 4D contract
and its revision). See del_norte/del_norte_recorder_tyler.py for the
existing live-query client this module is designed to sit behind - this
file does not call it, import it, or perform any request of its own.

PURE FUNCTION CONTRACT: parse_recorder_results() takes only in-memory input
(already-decoded HTML text plus the document number that was queried) and
returns only an in-memory typed result. No sqlite3 connection, no
filesystem access, no network access, no artifact_root, no call into
legacy_evidence_importer or any importer/pipeline module, and no fetch of
any detail link found on the page - anywhere in this file.

## Warning type independence (approved Phase 4D decision)

RecorderExtractionWarning below is a LOCAL, separately-defined dataclass -
not an import of del_norte_asrprint.py's ExtractionWarning, despite having
an identical field shape. Same reasoning as that module's own separately
defined ObservationFieldInput: keeps this module's zero-dependency-on-any-
sibling-extractor guarantee mechanically obvious rather than merely
documented. No shared warning module is introduced here.

## Data preservation, not normalization

This module never normalizes, deduplicates, infers, reconciles, or
persists a value. Every extracted party name, however many times it
repeats across duplicate Grantor/Grantee blocks, is preserved in exact
source order - see "Duplicate party sections" below.

## Presence/value states (book/page, APN)

  present=False, raw_or_none=None   -> absent: no such column exists on the page
  present=True,  raw_or_none=None   -> present but blank: column exists, no text
  present=True,  raw_or_none="..."  -> populated

As of the Phase 4C live lookup, this platform's document-number results
never included a Book/Page or APN column at all (both always
present=False). These two fields exist so a future platform change is
captured passively, without a code change - not because either has ever
been observed populated.

## Duplicate party sections - merge, never discard

If a result row contains more than one Grantor (or Grantee) block, every
name from every block is concatenated into `grantors`/`grantees` in the
exact order encountered, including exact repeats. Nothing is deduplicated
and no block is treated as more authoritative than another - each block is
independent evidence of what the recorder's index actually displayed.
DUPLICATE_PARTY_SECTION is emitted whenever more than one block of the
same party type is found on a row. This deliberately differs from
del_norte_asrprint.py's duplicate-*label* handling (first value kept,
conflicting duplicate discarded): a duplicate assessor label is two
conflicting values for one fact, but two Grantor blocks are not competing
values for the same fact - merging without loss is correct here.

## Success semantics - zero/multiple results, mismatch

Zero-result and multiple-result responses are both
RecorderResultsExtractionSuccess with a page-level warning, never a
failure: this parser's job is to faithfully describe what came back, not
to enforce "exactly one result was expected". A document-number mismatch
on a row is a row-level warning, never a failure, for the same reason.

ANY FUTURE CALLER (live-query client, importer, persistence layer) MUST
require exactly one row with no DOCUMENT_NUMBER_MISMATCH warning before
treating a lookup as verified or persisting anything from it. This module
enforces none of that - see del_norte_asrprint_pipeline.py for the
analogous separation already built on the assessor side.

## Detail links are opaque locators, permanently

detail_link_path stores whatever raw href text is found on a result row's
detail link, verbatim. Expected relative paths (matching the pattern this
platform is known to use, "/web/document/...") are stored with no warning.
Any other shape (absolute URL, unexpected path, or anything not matching
that pattern) is still stored - never discarded - plus
UNEXPECTED_DETAIL_LINK_FORM. This is a PERMANENT rule, not scoped to any
one phase: no parser, live-query client, importer, or any future module in
this repository may fetch a detail_link_path without its own separately
authorized image/document-retrieval phase.

## Permanent semantic rule - not an ownership/title determination

grantors/grantees (and any future party-type field this module might one
day add) must never be named owner/current_owner, and must never by
themselves be treated as establishing title, ownership, lien priority, or
legal status anywhere this data is later used. A recorder index entry is
evidence of what the index displays, not a legal conclusion. This is an
architectural rule for this data's entire lifecycle, not a limitation of
this module alone.

## Zero-results detection is a documented heuristic, not confirmed live

No genuine empty-result response was captured during the Phase 4C live
lookup (that lookup returned exactly one real match). The zero-results
text patterns this module recognizes ("no results", "0 results", "no
records found" - case-insensitive) are a best-effort heuristic based on
common Tyler Self-Service UI conventions, not independently confirmed
against a live empty response from this specific county's instance. If a
real zero-result page's actual wording differs, a caller might see
FAILURE(schema_mismatch) instead of SUCCESS(rows=(), warnings=[ZERO_RESULTS])
for an empty result - flagged here rather than silently assumed correct.

## Page-shape recognition

A page is treated as a genuine (if empty) results response, rather than
an unrecognized shape, if either:
  (a) at least one <li class="ss-search-row"> element is found, or
  (b) no such element is found, but the page text contains one of the
      zero-results heuristic patterns above.
Neither -> RecorderResultsExtractionFailure(classification="schema_mismatch",
next_action="human_review") - e.g. a disclaimer/login page landing where
results were expected, or genuinely unrecognizable markup.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Union

# ── Types ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RecorderExtractionWarning:
    """Local to this module - see the module docstring's "Warning type
    independence" section. Not imported from, and not imported by, any
    sibling extractor."""
    code: str
    message: str
    field_name_or_none: str | None
    raw_label_or_none: str | None


@dataclass(frozen=True)
class RecorderResultsExtractionInput:
    """Built by a future caller (a live-query client, or a test directly).
    This module never fetches raw_html itself."""
    queried_document_number_transformed: str
    raw_html: str
    search_id: str


@dataclass(frozen=True)
class RecorderResultRow:
    document_number: str
    document_number_matches_query: bool
    recording_date_raw: str | None
    instrument_type_raw: str | None
    grantors: tuple[str, ...]
    grantees: tuple[str, ...]
    detail_link_path: str | None
    book_page_present: bool
    book_page_raw_or_none: str | None
    apn_present: bool
    apn_raw_or_none: str | None
    warnings: tuple[RecorderExtractionWarning, ...]


@dataclass(frozen=True)
class RecorderResultsExtractionSuccess:
    rows: tuple[RecorderResultRow, ...]
    warnings: tuple[RecorderExtractionWarning, ...]


@dataclass(frozen=True)
class RecorderResultsExtractionFailure:
    classification: str
    next_action: str
    message: str
    warnings: tuple[RecorderExtractionWarning, ...] = ()


RecorderResultsExtractionResult = Union[RecorderResultsExtractionSuccess, RecorderResultsExtractionFailure]


# ── Constants ────────────────────────────────────────────────────────────

_ZERO_RESULTS_PATTERN = re.compile(r"no results|0 results|no records found", re.IGNORECASE)
_EXPECTED_DETAIL_LINK_PATTERN = re.compile(r"^/web/document/")
_BULLET = "•"

_VOID_TAGS = frozenset({
    "br", "img", "input", "hr", "meta", "link", "area", "base", "col", "embed", "source", "track", "wbr",
})


# ── Minimal stdlib-only tree builder (no bs4 dependency - matches this
# repository's existing extractor convention: del_norte_asrprint.py also
# uses html.parser directly, not a third-party HTML library) ──────────────


class _Node:
    __slots__ = ("tag", "attrs", "children", "text_parts")

    def __init__(self, tag: str, attrs: dict[str, str | None]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.children: list[_Node] = []
        self.text_parts: list[str] = []


class _TreeBuilder(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {})
        self._stack: list[_Node] = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = _Node(tag, dict(attrs))
        self._stack[-1].children.append(node)
        if tag not in _VOID_TAGS:
            self._stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack[-1].children.append(_Node(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self._stack) - 1, 0, -1):
            if self._stack[i].tag == tag:
                del self._stack[i:]
                break

    def handle_data(self, data: str) -> None:
        if self._stack:
            self._stack[-1].text_parts.append(data)


def _get_text(node: _Node) -> str:
    parts: list[str] = []

    def walk(n: _Node) -> None:
        parts.extend(n.text_parts)
        for c in n.children:
            walk(c)

    walk(node)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _has_class(node: _Node, cls: str) -> bool:
    return cls in (node.attrs.get("class") or "").split()


def _find_all(node: _Node, tag: str | None = None, cls: str | None = None) -> list[_Node]:
    out: list[_Node] = []

    def walk(n: _Node) -> None:
        for c in n.children:
            if (tag is None or c.tag == tag) and (cls is None or _has_class(c, cls)):
                out.append(c)
            walk(c)

    walk(node)
    return out


def _find_one(node: _Node, tag: str | None = None, cls: str | None = None) -> _Node | None:
    found = _find_all(node, tag, cls)
    return found[0] if found else None


# ── Row-level extraction ────────────────────────────────────────────────


def _parse_row(row: _Node, queried_document_number_transformed: str) -> RecorderResultRow:
    warnings: list[RecorderExtractionWarning] = []

    header = _find_one(row, tag="h1")
    header_text = _get_text(header) if header else ""
    segments = [seg.strip() for seg in header_text.split(_BULLET) if seg.strip()]
    document_number = segments[0] if segments else ""
    instrument_type_raw = segments[-1] if len(segments) > 1 else None

    document_number_matches_query = document_number == queried_document_number_transformed
    if not document_number_matches_query:
        warnings.append(RecorderExtractionWarning(
            code="DOCUMENT_NUMBER_MISMATCH",
            message="returned document number does not match the queried document number",
            field_name_or_none="document_number",
            raw_label_or_none=None,
        ))

    if instrument_type_raw is None:
        warnings.append(RecorderExtractionWarning(
            code="MISSING_INSTRUMENT_TYPE",
            message="no instrument/document type segment found in the result header",
            field_name_or_none="instrument_type_raw",
            raw_label_or_none=None,
        ))

    recording_date_raw: str | None = None
    grantors: list[str] = []
    grantees: list[str] = []
    book_page_present = False
    book_page_raw_or_none: str | None = None
    apn_present = False
    apn_raw_or_none: str | None = None

    recording_date_blocks = 0
    grantor_blocks = 0
    grantee_blocks = 0

    for col in _find_all(row, tag="div", cls="searchResultThreeColumn"):
        lis = _find_all(col, tag="li")
        if not lis:
            continue
        label = _get_text(lis[0]).lower()
        values = [_get_text(li) for li in lis[1:] if _get_text(li)]
        combined_value = ", ".join(values) if values else None

        if "grantor" in label:
            grantor_blocks += 1
            grantors.extend(values)
        elif "grantee" in label:
            grantee_blocks += 1
            grantees.extend(values)
        elif "date" in label:
            recording_date_blocks += 1
            if recording_date_raw is None:
                recording_date_raw = combined_value
        elif "book" in label or "page" in label:
            book_page_present = True
            if book_page_raw_or_none is None:
                book_page_raw_or_none = combined_value
        elif "apn" in label or "parcel" in label:
            apn_present = True
            if apn_raw_or_none is None:
                apn_raw_or_none = combined_value

    if recording_date_blocks == 0:
        warnings.append(RecorderExtractionWarning(
            code="MISSING_RECORDING_DATE",
            message="no Recording Date column found on this result row",
            field_name_or_none="recording_date_raw",
            raw_label_or_none=None,
        ))

    if grantor_blocks == 0:
        warnings.append(RecorderExtractionWarning(
            code="MISSING_GRANTOR_SECTION",
            message="no Grantor column found on this result row",
            field_name_or_none="grantors",
            raw_label_or_none=None,
        ))
    elif grantor_blocks > 1:
        warnings.append(RecorderExtractionWarning(
            code="DUPLICATE_PARTY_SECTION",
            message=f"{grantor_blocks} Grantor columns found on this result row; all entries preserved in source order",
            field_name_or_none="grantors",
            raw_label_or_none=None,
        ))

    if grantee_blocks == 0:
        warnings.append(RecorderExtractionWarning(
            code="MISSING_GRANTEE_SECTION",
            message="no Grantee column found on this result row",
            field_name_or_none="grantees",
            raw_label_or_none=None,
        ))
    elif grantee_blocks > 1:
        warnings.append(RecorderExtractionWarning(
            code="DUPLICATE_PARTY_SECTION",
            message=f"{grantee_blocks} Grantee columns found on this result row; all entries preserved in source order",
            field_name_or_none="grantees",
            raw_label_or_none=None,
        ))

    detail_link_path: str | None = None
    for a in _find_all(row, tag="a"):
        href = a.attrs.get("href")
        if href and href != "#":
            detail_link_path = href
            break

    if detail_link_path is not None and not _EXPECTED_DETAIL_LINK_PATTERN.match(detail_link_path):
        warnings.append(RecorderExtractionWarning(
            code="UNEXPECTED_DETAIL_LINK_FORM",
            message="detail link does not match the expected relative /web/document/... pattern; retained verbatim, never followed",
            field_name_or_none="detail_link_path",
            raw_label_or_none=None,
        ))

    return RecorderResultRow(
        document_number=document_number,
        document_number_matches_query=document_number_matches_query,
        recording_date_raw=recording_date_raw,
        instrument_type_raw=instrument_type_raw,
        grantors=tuple(grantors),
        grantees=tuple(grantees),
        detail_link_path=detail_link_path,
        book_page_present=book_page_present,
        book_page_raw_or_none=book_page_raw_or_none,
        apn_present=apn_present,
        apn_raw_or_none=apn_raw_or_none,
        warnings=tuple(warnings),
    )


# ── Top-level entry point ───────────────────────────────────────────────


def parse_recorder_results(extraction_input: RecorderResultsExtractionInput) -> RecorderResultsExtractionResult:
    """Pure function - see the module docstring's PURE FUNCTION CONTRACT.
    Never raises for malformed/unrecognized input; always returns a typed
    RecorderResultsExtractionSuccess or RecorderResultsExtractionFailure."""
    try:
        builder = _TreeBuilder()
        builder.feed(extraction_input.raw_html)
    except Exception as exc:  # HTMLParser is lenient but not unbreakable
        return RecorderResultsExtractionFailure(
            classification="schema_mismatch",
            next_action="human_review",
            message=f"search_id={extraction_input.search_id}: HTML could not be parsed: {exc}",
        )

    row_nodes = _find_all(builder.root, tag="li", cls="ss-search-row")

    if not row_nodes:
        if _ZERO_RESULTS_PATTERN.search(extraction_input.raw_html):
            return RecorderResultsExtractionSuccess(
                rows=(),
                warnings=(RecorderExtractionWarning(
                    code="ZERO_RESULTS",
                    message="no result rows found; page matched a recognized zero-results pattern",
                    field_name_or_none=None,
                    raw_label_or_none=None,
                ),),
            )
        return RecorderResultsExtractionFailure(
            classification="schema_mismatch",
            next_action="human_review",
            message=(
                f"search_id={extraction_input.search_id}: no recognizable result rows and no recognized "
                "zero-results pattern found; page shape did not match this parser's expectations"
            ),
        )

    rows = tuple(_parse_row(row, extraction_input.queried_document_number_transformed) for row in row_nodes)

    page_warnings: list[RecorderExtractionWarning] = []
    if len(rows) > 1:
        page_warnings.append(RecorderExtractionWarning(
            code="MULTIPLE_RESULTS_RETURNED",
            message=f"{len(rows)} result rows found for a lookup expecting at most one match",
            field_name_or_none=None,
            raw_label_or_none=None,
        ))

    return RecorderResultsExtractionSuccess(rows=rows, warnings=tuple(page_warnings))
