"""
Pure In-Memory Validation Module for San Joaquin ArcGIS MapServer Adapter
Run Label: CA_SJC_ARCGIS_FINAL_STATIC_REMEDIATION_2026_WAVE_01

CONSTRAINTS:
- Pure in-memory computation only.
- Zero network, filesystem, subprocess, or database calls.
- No URLs, endpoint strings, or real-world APN records.
- Request contract is an immutable MappingProxyType.
"""

from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Any, List, Mapping, Optional, Set, Tuple

# Closed Failure State Enums
METADATA_CHANGED = "METADATA_CHANGED"
SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
RATE_LIMITED = "RATE_LIMITED"
QUERY_NOT_APPROVED = "QUERY_NOT_APPROVED"
MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
IDENTIFIER_NOT_FOUND = "IDENTIFIER_NOT_FOUND"
IDENTIFIER_MISMATCH = "IDENTIFIER_MISMATCH"
IDENTIFIER_AMBIGUOUS = "IDENTIFIER_AMBIGUOUS"
GEOMETRY_MISSING = "GEOMETRY_MISSING"
DISALLOWED_FIELD_PRESENT = "DISALLOWED_FIELD_PRESENT"
EVIDENCE_INSUFFICIENT = "EVIDENCE_INSUFFICIENT"

# Decision State Enums
DO_NOT_USE_PARCEL_ASSERTION = "DO_NOT_USE_PARCEL_ASSERTION"
PENDING_PARCEL_EVIDENCE = "PENDING_PARCEL_EVIDENCE"
EXACT_MATCH_PENDING_EVIDENCE = "EXACT_MATCH_PENDING_EVIDENCE"

# Approved Synthetic Test-Fixture APN Allowlist
TEST_FIXTURE_APN_ALLOWLIST: Set[str] = {
    "999000111222",
    "111222333444",
}

APN_REGEX = re.compile(r"^[0-9]{12}$")


@dataclass(frozen=True)
class ValidationResult:
    """Immutable result container for mock feature validation."""
    success: bool
    status_code: str
    validation_decision: str
    apn: Optional[str] = None
    geometry: Optional[List[List[List[float]]]] = None
    error_message: Optional[str] = None


def normalize_test_apn(
    raw_apn: Any,
    test_fixture_allowlist: Set[str] = TEST_FIXTURE_APN_ALLOWLIST,
) -> str:
    """
    Validates and normalizes raw test APN strings.

    Rules:
    - Input must be a non-empty string.
    - Normalization removes hyphens only.
    - Rejects spaces, dots, slashes, letters, symbols, nulls, and non-strings.
    - Normalized string must strictly match ^[0-9]{12}$.
    - Normalized string must exist in test_fixture_allowlist.
    """
    if not isinstance(raw_apn, str):
        raise ValueError("APN must be a string")

    if any(char in raw_apn for char in [" ", ".", "/", "\\", "\t", "\n"]):
        raise ValueError("APN contains unauthorized whitespace or punctuation")

    normalized = raw_apn.replace("-", "")

    if not APN_REGEX.match(normalized):
        raise ValueError(f"APN '{normalized}' is not a valid 12-digit numeric string")

    if normalized not in test_fixture_allowlist:
        raise ValueError(
            f"APN '{normalized}' is not present in TEST_FIXTURE_APN_ALLOWLIST"
        )

    return normalized


def validate_mock_metadata(metadata: Any) -> Tuple[bool, str]:
    """Validates mock layer metadata dictionary without I/O."""
    if not isinstance(metadata, dict):
        return False, METADATA_CHANGED

    if metadata.get("name") != "Tax Parcels":
        return False, METADATA_CHANGED

    if metadata.get("type") != "Feature Layer":
        return False, METADATA_CHANGED

    if metadata.get("geometryType") != "esriGeometryPolygon":
        return False, METADATA_CHANGED

    fields = metadata.get("fields")
    if not isinstance(fields, list):
        return False, METADATA_CHANGED

    apn_field = None
    for field in fields:
        if isinstance(field, dict) and field.get("name") == "APN":
            apn_field = field
            break

    if apn_field is None:
        return False, METADATA_CHANGED

    if apn_field.get("type") != "esriFieldTypeString":
        return False, METADATA_CHANGED

    if apn_field.get("length") != 12:
        return False, METADATA_CHANGED

    return True, "METADATA_VALID"


def build_test_only_request_contract(
    apn: str,
    test_mode: bool = True,
) -> Mapping[str, Any]:
    """Constructs exact, immutable 5-key query parameter MappingProxyType."""
    if not test_mode:
        raise ValueError("Production request generation is prohibited")

    normalized_apn = normalize_test_apn(apn)

    return MappingProxyType({
        "where": f"APN = '{normalized_apn}'",
        "outFields": "APN",
        "returnGeometry": True,
        "resultRecordCount": 1,
        "f": "json",
    })


def _is_valid_coordinate(val: Any) -> bool:
    """Validates that a coordinate value is a finite number (rejects bool, NaN, Inf)."""
    if isinstance(val, bool):
        return False
    if not isinstance(val, (int, float)):
        return False
    if math.isnan(val) or math.isinf(val):
        return False
    return True


def validate_mock_feature_response(
    expected_apn: Any,
    payload: Any,
) -> ValidationResult:
    """Evaluates mock feature payload in strict fail-closed order of operations."""
    normalized_expected_apn = normalize_test_apn(expected_apn)

    if not isinstance(payload, dict):
        return ValidationResult(
            success=False,
            status_code=MALFORMED_RESPONSE,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Payload is not a dictionary",
        )

    if "error" in payload:
        return ValidationResult(
            success=False,
            status_code=MALFORMED_RESPONSE,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Payload contains error object",
        )

    features = payload.get("features")
    if not isinstance(features, list):
        return ValidationResult(
            success=False,
            status_code=MALFORMED_RESPONSE,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Features field is missing or not a list",
        )

    if len(features) == 0:
        return ValidationResult(
            success=False,
            status_code=IDENTIFIER_NOT_FOUND,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Zero features returned in envelope",
        )

    if len(features) >= 2:
        return ValidationResult(
            success=False,
            status_code=IDENTIFIER_AMBIGUOUS,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message=f"Multiple ({len(features)}) features returned in envelope",
        )

    feature = features[0]
    if not isinstance(feature, dict):
        return ValidationResult(
            success=False,
            status_code=MALFORMED_RESPONSE,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Feature entry is not a dictionary",
        )

    attributes = feature.get("attributes")
    if not isinstance(attributes, dict):
        return ValidationResult(
            success=False,
            status_code=MALFORMED_RESPONSE,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Attributes is missing or not a dictionary",
        )

    if set(attributes.keys()) != {"APN"}:
        return ValidationResult(
            success=False,
            status_code=DISALLOWED_FIELD_PRESENT,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message=f"Non-allowlisted attributes present: {set(attributes.keys())}",
        )

    returned_apn = attributes.get("APN")
    if returned_apn != normalized_expected_apn:
        return ValidationResult(
            success=False,
            status_code=IDENTIFIER_MISMATCH,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message=f"Returned APN '{returned_apn}' does not match expected '{normalized_expected_apn}'",
        )

    geometry = feature.get("geometry")
    if not isinstance(geometry, dict) or "rings" not in geometry:
        return ValidationResult(
            success=False,
            status_code=GEOMETRY_MISSING,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Geometry dictionary missing or rings absent",
        )

    rings = geometry.get("rings")
    if not isinstance(rings, list) or len(rings) == 0:
        return ValidationResult(
            success=False,
            status_code=GEOMETRY_MISSING,
            validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
            error_message="Geometry rings is empty or not a list",
        )

    for ring in rings:
        if not isinstance(ring, list) or len(ring) < 4:
            return ValidationResult(
                success=False,
                status_code=EVIDENCE_INSUFFICIENT,
                validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
                error_message="Ring has fewer than 4 vertices or is not a list",
            )

        for pt in ring:
            if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                return ValidationResult(
                    success=False,
                    status_code=EVIDENCE_INSUFFICIENT,
                    validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
                    error_message="Coordinate point is not a list/tuple of length >= 2",
                )

            if not _is_valid_coordinate(pt[0]) or not _is_valid_coordinate(pt[1]):
                return ValidationResult(
                    success=False,
                    status_code=EVIDENCE_INSUFFICIENT,
                    validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
                    error_message="Non-numeric, boolean, NaN, or infinite coordinate",
                )

        if ring[0][0] != ring[-1][0] or ring[0][1] != ring[-1][1]:
            return ValidationResult(
                success=False,
                status_code=EVIDENCE_INSUFFICIENT,
                validation_decision=DO_NOT_USE_PARCEL_ASSERTION,
                error_message="Polygon ring is not closed",
            )

    return ValidationResult(
        success=True,
        status_code=EXACT_MATCH_PENDING_EVIDENCE,
        validation_decision=PENDING_PARCEL_EVIDENCE,
        apn=normalized_expected_apn,
        geometry=rings,
    )
