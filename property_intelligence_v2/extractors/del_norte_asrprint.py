"""
property_intelligence_v2/extractors/del_norte_asrprint.py

Pure parser for Del Norte County's assessor "AsrPrint" HTML page
(del_norte/raw_evidence/delnorte_asrprint_*.html). Phase 3B target, per the
Phase 3A discovery pass and the Phase 3B extraction contract it produced.

PURE FUNCTION CONTRACT: parse_asrprint() takes only in-memory input (already
decoded HTML text) and returns only an in-memory typed result. No sqlite3
connection, no filesystem access, no network access, no artifact_root, and
no call into legacy_evidence_importer anywhere in this file. Wiring this
parser's output to the committed importer is del_norte_asrprint_pipeline.py's
job, not this module's.

## Boundary resolutions this module honors (see the approved Phase 3B contract)

1. Identifier candidates (APN, assessment number, current document number)
   are IdentifierCandidate values on the returned result - never written to
   observation_identifiers anywhere in this module, because nothing in this
   module touches a database at all.
2. Every ObservationFieldInput carries a RAW, as-printed value only. No
   "_raw"/"_normalized" field-name pairs are ever produced. Where an
   internal normalization is attempted (identifier candidates; a numeric
   sanity check on dollar/lot-size fields), the result either feeds
   IdentifierCandidate.value_normalized_or_none (in-memory only) or a
   VALUE_DID_NOT_NORMALIZE warning - never a second observation field.
3. Unrecognized labels, missing optional fields, conflicting duplicate
   labels, and failed internal normalization all produce ExtractionWarning
   values on the result - never an exceptions row, because nothing in this
   module writes to a database.
4. The BACK-link href (assessor_portal_related_link) is extracted as
   ordinary page content, not as source_url_or_identifier provenance -
   choosing that value is del_norte_asrprint_pipeline.py's job, using the
   legacy file's own repository-relative path, not this link.
5. Assessor Parcel Number(APN) read from page content is the sole required
   field. Its absence, or an unrecognized page/table shape, returns
   AsrPrintExtractionFailure - a typed value, never a raised exception -
   so a caller can decide not to attempt any import at all without needing
   to catch anything.

## Confidence value

Every field extracted here uses confidence='carried_forward' (see
CONFIDENCE_VALUE below) - NOT 'confirmed'. property_intelligence_v2/
contracts/entities.py's ConfidenceLevel enum documents 'confirmed' as
"directly read from a live official source this run": this parser
processes archived local HTML files (del_norte/raw_evidence/
delnorte_asrprint_*.html), not a live fetch performed during the current
run, so 'confirmed' does not apply, regardless of how authoritative the
archived capture was at the time it was taken. Of the remaining existing
values, 'source_list_only' (a bulk list entry, never independently
verified) and 'unconfirmed' (contradicted or unchecked) both describe a
weaker epistemic state than an AsrPrint page actually has - this is a full
primary document, correctly parsed. 'carried_forward' - "seen on a prior
run, not re-verified this run" - is the closest existing match: the value
was established as true at an earlier point (the original capture), and
this run does not re-verify it against the live source. No new vocabulary
value was added and no migration was made; see extractors/README.md for
the fuller rationale, including the acknowledged imperfection in this fit.

## Label matching

Label text is matched against a fixed set of 22 known labels after
whitespace normalization only (runs of whitespace collapsed to one space,
leading/trailing whitespace stripped) - not case-folded, not fuzzy, not
partial. This is necessary because the real source HTML itself is
inconsistent about internal whitespace (e.g. "Current Document  Date" with
two spaces) - normalizing whitespace is not "inferring" a label, it is
recovering the same text a human reading the rendered page would see.
Nothing here ever maps an unrecognized label onto a known field_name by
similarity; unrecognized labels always become an UNRECOGNIZED_LABEL warning
and are otherwise skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Union

# ── Types the committed importer already defines - reused, not duplicated ──
# Imported lazily by callers that need it (del_norte_asrprint_pipeline.py);
# this module only needs the shape, so it defines its own minimal
# frozen dataclass with the identical field set rather than importing from
# legacy_evidence_importer.py, keeping this module's "no importer import"
# guarantee mechanically obvious rather than merely documented.


@dataclass(frozen=True)
class ObservationFieldInput:
    """Field-for-field identical in shape to
    legacy_evidence_importer.ObservationFieldInput. Kept as a separate
    definition here (not an import) so this module provably has zero
    dependency on the importer module - see the module docstring."""
    field_name: str
    field_value: str
    confidence: str


@dataclass(frozen=True)
class AsrPrintExtractionInput:
    """Built by the caller (del_norte_asrprint_pipeline.py in production;
    a test, directly, in tests). legacy_path is carried through only for
    error messages / traceability - this module never opens it."""
    legacy_path: Path
    raw_html: str
    filename: str


@dataclass(frozen=True)
class IdentifierCandidate:
    """In-memory only. Never written to observation_identifiers by any code
    in this repository as of Phase 3B - see resolution (1) above."""
    identifier_type: str
    value_raw: str
    value_normalized_or_none: str | None
    verification_status: str
    source_field_label: str


@dataclass(frozen=True)
class ExtractionWarning:
    """In-memory only. Never written to `exceptions` by any code in this
    repository as of Phase 3B - see resolution (3) above."""
    code: str
    message: str
    field_name_or_none: str | None
    raw_label_or_none: str | None


@dataclass(frozen=True)
class AsrPrintExtractionSuccess:
    observation_fields: tuple[ObservationFieldInput, ...]
    identifier_candidates: tuple[IdentifierCandidate, ...]
    warnings: tuple[ExtractionWarning, ...] = ()


@dataclass(frozen=True)
class AsrPrintExtractionFailure:
    classification: str
    next_action: str
    message: str
    warnings: tuple[ExtractionWarning, ...] = ()


AsrPrintExtractionResult = Union[AsrPrintExtractionSuccess, AsrPrintExtractionFailure]


# ── The 22 known labeled table fields (exact set - see extractors/README.md) ──
# Label text exactly as it appears on the real source page, after whitespace
# normalization only. "Total land & Improvemnets" is the source's own
# spelling, not a typo introduced here - matched verbatim on purpose.
KNOWN_LABEL_TO_FIELD_NAME: dict[str, str] = {
    "Assessor Parcel Number(APN)": "assessor_parcel_number_apn",
    "Assessment Number": "assessment_number",
    "Tax Rate Area(TRA)": "tax_rate_area",
    "Current Document Number": "current_document_number",
    "Current Document Date": "current_document_date",
    "SitusAddr": "situs_address",
    "Property Type": "property_type",
    "Lot Size(Acres)": "lot_size_acres",
    "Lot Size(SqFt)": "lot_size_sqft",
    "Asmt Description": "assessment_description",
    "Asmt Status": "assessment_status",
    "Land": "roll_value_land",
    "Structural Imprv": "roll_value_structural_improvements",
    "Fixtures Real Property": "roll_value_fixtures_real_property",
    "Growing Imprv.": "roll_value_growing_improvements",
    "Total land & Improvemnets": "roll_value_total_land_and_improvements",
    "Fixtures Personal Property": "roll_value_fixtures_personal_property",
    "Personal Property": "roll_value_personal_property",
    "Manufactured Homes": "roll_value_manufactured_homes",
    "Homeowners Exemption(HOX)": "roll_value_homeowners_exemption",
    "Other Exemptions": "roll_value_other_exemptions",
    "Net Assessed Value": "roll_value_net_assessed_value",
}
assert len(KNOWN_LABEL_TO_FIELD_NAME) == 22

REQUIRED_LABEL = "Assessor Parcel Number(APN)"
REQUIRED_FIELD_NAME = KNOWN_LABEL_TO_FIELD_NAME[REQUIRED_LABEL]

# field_name this optional, separately-extracted link is stored under - not
# one of the 22 above, never counted as a "known table label".
RELATED_LINK_FIELD_NAME = "assessor_portal_related_link"

# The one confidence value this parser ever emits - see the module
# docstring's "## Confidence value" section for why this is
# 'carried_forward', not 'confirmed'. Defined once so every emission site
# uses the identical value and a test can assert against this constant
# directly, rather than repeating (and risking a mismatched) literal string.
CONFIDENCE_VALUE = "carried_forward"

# Identifier candidates are proposed only for these three labels - see
# extractors/README.md for the identifier_type choice on each, including the
# explicitly-flagged [INFERENCE] on "Assessment Number".
_IDENTIFIER_CANDIDATE_LABELS: dict[str, str] = {
    "Assessor Parcel Number(APN)": "ASSESSOR_APN",
    "Assessment Number": "OTHER_SOURCE_IDENTIFIER",
    "Current Document Number": "RECORDER_DOCUMENT_NUMBER",
}

_DOLLAR_PATTERN = re.compile(r"^\$[\d,]+$")


def _normalize_label(text: str) -> str:
    """Whitespace normalization only - see the module docstring's
    "Label matching" section for why this is not fuzzy matching."""
    return " ".join(text.split())


def _normalize_identifier_value(identifier_type: str, raw_value: str) -> str | None:
    """In-memory only (feeds IdentifierCandidate.value_normalized_or_none).
    Digits-only normalization for APN-shaped identifiers; no normalized form
    is proposed yet for RECORDER_DOCUMENT_NUMBER - its format is not yet
    confirmed against the rest of the pipeline (flagged in the Phase 3B
    contract as an open [INFERENCE], not decided here)."""
    if identifier_type in ("ASSESSOR_APN", "OTHER_SOURCE_IDENTIFIER"):
        digits = "".join(ch for ch in raw_value if ch.isdigit())
        return digits or None
    return None


def _numeric_normalization_check(field_name: str, value: str) -> bool:
    """Informational only - never blocks extraction, never rewrites the raw
    value. Returns False to trigger a VALUE_DID_NOT_NORMALIZE warning."""
    if field_name.startswith("roll_value_"):
        return bool(_DOLLAR_PATTERN.match(value))
    if field_name in ("lot_size_acres", "lot_size_sqft"):
        try:
            float(value)
        except ValueError:
            return False
        return True
    return True


class _AsrPrintRowCollector(HTMLParser):
    """Collects (first_td_is_bold, [td_text, ...]) per <tr>, plus the href of
    <a id="Back">, from an AsrPrint page.

    Deliberately ignores <table> boundaries entirely - the real source page
    nests its "Roll Values" <table> inside the "Property Information"
    <table> without closing the outer one first (verified directly against
    a real captured sample during Phase 3A). Since every field-bearing row,
    in either section, uses the identical
    <tr><td class="font-weight-bolder">Label</td><td>Value</td></tr> shape,
    tracking <tr> boundaries only (not <table> nesting) is both simpler and
    robust to that malformed nesting - not a design compromise."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[bool, list[str]]] = []
        self.back_href: str | None = None
        self._in_tr = False
        self._tds: list[dict] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if tag == "a" and attrs_dict.get("id") == "Back" and self.back_href is None:
            href = attrs_dict.get("href")
            if href:
                self.back_href = href
        elif tag == "tr":
            self._in_tr = True
            self._tds = []
        elif tag == "td" and self._in_tr:
            self._tds.append({"class": attrs_dict.get("class") or "", "text": []})

    def handle_endtag(self, tag: str) -> None:
        if tag == "tr" and self._in_tr:
            texts = ["".join(td["text"]).strip() for td in self._tds]
            first_is_bold = bool(self._tds) and "font-weight-bolder" in self._tds[0]["class"].split()
            self.rows.append((first_is_bold, texts))
            self._in_tr = False
            self._tds = []

    def handle_data(self, data: str) -> None:
        if self._tds:
            self._tds[-1]["text"].append(data)


def parse_asrprint(extraction_input: AsrPrintExtractionInput) -> AsrPrintExtractionResult:
    """Pure function - see the module docstring's PURE FUNCTION CONTRACT.
    Never raises for malformed/unrecognized input; always returns a typed
    AsrPrintExtractionSuccess or AsrPrintExtractionFailure."""
    warnings: list[ExtractionWarning] = []

    try:
        collector = _AsrPrintRowCollector()
        collector.feed(extraction_input.raw_html)
    except Exception as exc:  # HTMLParser is lenient but not unbreakable
        return AsrPrintExtractionFailure(
            classification="schema_mismatch",
            next_action="human_review",
            message=f"{extraction_input.filename}: HTML could not be parsed: {exc}",
        )

    seen_values: dict[str, str] = {}
    field_values: dict[str, str] = {}

    for first_is_bold, texts in collector.rows:
        if not first_is_bold or len(texts) != 2:
            continue
        label = _normalize_label(texts[0])
        value = texts[1]
        if not label:
            continue

        if label in seen_values:
            if seen_values[label] != value:
                warnings.append(ExtractionWarning(
                    code="DUPLICATE_LABEL_OBSERVED",
                    message=f"label {label!r} observed more than once with differing values; first value kept",
                    field_name_or_none=KNOWN_LABEL_TO_FIELD_NAME.get(label),
                    raw_label_or_none=label,
                ))
            continue

        seen_values[label] = value

        field_name = KNOWN_LABEL_TO_FIELD_NAME.get(label)
        if field_name is None:
            warnings.append(ExtractionWarning(
                code="UNRECOGNIZED_LABEL",
                message=f"label {label!r} does not match any of the 22 known AsrPrint fields",
                field_name_or_none=None,
                raw_label_or_none=label,
            ))
            continue

        field_values[field_name] = value
        if not _numeric_normalization_check(field_name, value):
            warnings.append(ExtractionWarning(
                code="VALUE_DID_NOT_NORMALIZE",
                message=f"value for {field_name!r} did not match the expected numeric format: {value!r}",
                field_name_or_none=field_name,
                raw_label_or_none=label,
            ))

    apn_value = field_values.get(REQUIRED_FIELD_NAME)
    if not apn_value:
        return AsrPrintExtractionFailure(
            classification="schema_mismatch",
            next_action="human_review",
            message=f"{extraction_input.filename}: required field {REQUIRED_LABEL!r} was not found on the page",
            warnings=tuple(warnings),
        )

    for label, field_name in KNOWN_LABEL_TO_FIELD_NAME.items():
        if field_name == REQUIRED_FIELD_NAME:
            continue
        if field_name not in field_values:
            warnings.append(ExtractionWarning(
                code="OPTIONAL_FIELD_MISSING",
                message=f"optional field {field_name!r} (label {label!r}) was not present on the page",
                field_name_or_none=field_name,
                raw_label_or_none=label,
            ))

    observation_fields = tuple(
        ObservationFieldInput(field_name=field_name, field_value=value, confidence=CONFIDENCE_VALUE)
        for field_name, value in field_values.items()
    )

    if collector.back_href:
        observation_fields = observation_fields + (
            ObservationFieldInput(
                field_name=RELATED_LINK_FIELD_NAME,
                field_value=collector.back_href,
                confidence=CONFIDENCE_VALUE,
            ),
        )

    identifier_candidates: list[IdentifierCandidate] = []
    for label, identifier_type in _IDENTIFIER_CANDIDATE_LABELS.items():
        field_name = KNOWN_LABEL_TO_FIELD_NAME[label]
        raw_value = field_values.get(field_name)
        if raw_value is None:
            continue
        identifier_candidates.append(IdentifierCandidate(
            identifier_type=identifier_type,
            value_raw=raw_value,
            value_normalized_or_none=_normalize_identifier_value(identifier_type, raw_value),
            verification_status="SOURCE_ASSERTED",
            source_field_label=label,
        ))

    return AsrPrintExtractionSuccess(
        observation_fields=observation_fields,
        identifier_candidates=tuple(identifier_candidates),
        warnings=tuple(warnings),
    )
