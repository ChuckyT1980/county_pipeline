"""
Synthetic Unit Test Suite for San Joaquin ArcGIS Adapter Validation Logic
Run Label: CA_SJC_ARCGIS_FINAL_STATIC_REMEDIATION_2026_WAVE_01

CONSTRAINTS:
- Uses standard library `unittest` and `ast` only.
- In-memory mock fixtures only. Zero network, disk I/O, or database calls.
- Full AST alias tracking and coordinate hardening verification.
"""

import ast
from typing import Any, Dict, List, Set
import unittest

from san_joaquin.sjc_arcgis_test_validator import (
    DISALLOWED_FIELD_PRESENT,
    DO_NOT_USE_PARCEL_ASSERTION,
    EVIDENCE_INSUFFICIENT,
    EXACT_MATCH_PENDING_EVIDENCE,
    GEOMETRY_MISSING,
    IDENTIFIER_AMBIGUOUS,
    IDENTIFIER_MISMATCH,
    IDENTIFIER_NOT_FOUND,
    MALFORMED_RESPONSE,
    METADATA_CHANGED,
    PENDING_PARCEL_EVIDENCE,
    TEST_FIXTURE_APN_ALLOWLIST,
    build_test_only_request_contract,
    normalize_test_apn,
    validate_mock_feature_response,
    validate_mock_metadata,
)

# Synthetic non-geographic polygon fixture (closed 4-vertex ring)
SYNTHETIC_TEST_GEOMETRY = [[[0.0, 0.0], [0.0, 1.0], [1.0, 1.0], [0.0, 0.0]]]

# AST Analyzer Configuration
BANNED_IMPORT_ROOTS: Set[str] = {
    "requests",
    "urllib",
    "http",
    "httpx",
    "aiohttp",
    "socket",
    "websocket",
    "subprocess",
    "pathlib",
    "shutil",
    "sqlite3",
    "sqlalchemy",
    "psycopg2",
    "pymongo",
    "selenium",
    "playwright",
    "scrapy",
}

BANNED_CALL_NAMES: Set[str] = {
    "open",
    "urlopen",
    "Request",
    "connect",
    "system",
    "popen",
    "exec",
    "eval",
    "execute",
    "executemany",
    "commit",
    "rollback",
    "spawn",
}


def audit_source_text(source_text: str) -> List[str]:
    """Parses a Python source string and detects banned imports, aliases, and call nodes."""
    violations: List[str] = []
    try:
        tree = ast.parse(source_text)
    except SyntaxError as err:
        return [f"Syntax error: {err}"]

    banned_module_aliases: Set[str] = set()
    banned_symbol_aliases: Set[str] = set()

    def _get_call_chain(func_node: ast.AST):
        if isinstance(func_node, ast.Name):
            return func_node.id
        if isinstance(func_node, ast.Attribute):
            base = _get_call_chain(func_node.value)
            if base:
                return f"{base}.{func_node.attr}"
            return func_node.attr
        return None

    # Pass 1: Collect banned imports and alias bindings
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in BANNED_IMPORT_ROOTS:
                    bound_name = alias.asname or alias.name.split(".")[0]
                    banned_module_aliases.add(bound_name)
                    violations.append(f"Banned import '{alias.name}'")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in BANNED_IMPORT_ROOTS:
                    for alias in node.names:
                        bound_name = alias.asname or alias.name
                        banned_symbol_aliases.add(bound_name)
                        violations.append(
                            f"Banned from-import '{node.module}.{alias.name}'"
                        )
                else:
                    for alias in node.names:
                        if alias.name in BANNED_CALL_NAMES:
                            bound_name = alias.asname or alias.name
                            banned_symbol_aliases.add(bound_name)
                            violations.append(
                                f"Banned from-import call symbol '{alias.name}'"
                            )

    # Pass 2: Detect banned calls and calls via module/symbol aliases
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_chain = _get_call_chain(node.func)
            if call_chain:
                root = call_chain.split(".")[0]
                leaf = call_chain.split(".")[-1]
                if leaf in BANNED_CALL_NAMES:
                    violations.append(f"Banned call '{leaf}'")
                elif root in banned_module_aliases:
                    violations.append(
                        f"Banned call on module alias '{call_chain}'"
                    )
                elif call_chain in banned_symbol_aliases:
                    violations.append(
                        f"Banned call on symbol alias '{call_chain}'"
                    )

    return violations


# Literal AST Test Fixtures
SAFE_VALIDATION_SOURCE_FIXTURE = """
from dataclasses import dataclass
import math
import re
from types import MappingProxyType
from typing import Any, Mapping

def safe_calc(apn: str) -> str:
    return apn.replace("-", "")
"""

SAFE_TEST_SOURCE_FIXTURE = """
import unittest
from typing import Dict, Any

class SafeMockTest(unittest.TestCase):
    def test_pure_logic(self):
        self.assertEqual(1 + 1, 2)
"""

UNSAFE_IMPORT_SOURCE_FIXTURE = """
import requests
from urllib.request import urlopen
import sqlite3 as db
"""

UNSAFE_CALL_SOURCE_FIXTURE = """
def bad_func():
    f = open('data.txt', 'r')
    res = urlopen('http://example.com')
    db.connect()
"""

UNSAFE_MODULE_ALIAS_SOURCE_FIXTURE = """
import requests as req
def fetch_data():
    return req.get("http://example.com")
"""

UNSAFE_CALL_ALIAS_SOURCE_FIXTURE = """
from urllib.request import urlopen as fetch
def run_fetch():
    return fetch("http://example.com")
"""

UNSAFE_DOTTED_IMPORT_SOURCE_FIXTURE = """
import requests.sessions

def build():
    return requests.sessions.Session()
"""


class TestSanJoaquinArcGISAdapterRemediated(unittest.TestCase):
    """Comprehensive unit test suite for fully remediated adapter contracts."""

    def setUp(self) -> None:
        self.apn_valid_1 = "999000111222"
        self.apn_valid_2 = "111222333444"

        self.valid_metadata: Dict[str, Any] = {
            "name": "Tax Parcels",
            "type": "Feature Layer",
            "geometryType": "esriGeometryPolygon",
            "fields": [
                {"name": "APN", "type": "esriFieldTypeString", "length": 12},
                {"name": "OBJECTID", "type": "esriFieldTypeOID"},
            ],
        }

    def test_01_full_fixture_apn_accepted(self) -> None:
        """Test 1: Valid 12-digit fixture APN accepted directly."""
        result = normalize_test_apn(self.apn_valid_1)
        self.assertEqual(result, self.apn_valid_1)

    def test_02_hyphen_normalization_succeeds(self) -> None:
        """Test 2: Hyphenated fixture APN normalizes cleanly by removing hyphens only."""
        hyphenated = "999-000-111-222"
        result = normalize_test_apn(hyphenated)
        self.assertEqual(result, self.apn_valid_1)
        self.assertEqual(len(result), 12)

    def test_03_invalid_identifiers_rejected_preflight(self) -> None:
        """Test 3: Prefix, invalid length, non-numeric, dotted, spaced, and unallowlisted reject."""
        invalid_cases = [
            "99900011",
            "99900011122",
            "9990001112223",
            "99900011122A",
            "999.000.111.222",
            " 999000111222 ",
            "222-333-444-555",
            None,
            123456789012,
        ]
        for case in invalid_cases:
            with self.subTest(case=case):
                with self.assertRaises(ValueError):
                    normalize_test_apn(case)

    def test_04_metadata_drift_cases(self) -> None:
        """Test 4: Schema alterations return METADATA_CHANGED."""
        meta_name_drift = dict(self.valid_metadata, name="Tax Parcels Historic")
        valid_a, state_a = validate_mock_metadata(meta_name_drift)
        self.assertFalse(valid_a)
        self.assertEqual(state_a, METADATA_CHANGED)

        meta_missing_apn = dict(
            self.valid_metadata,
            fields=[{"name": "OBJECTID", "type": "esriFieldTypeOID"}],
        )
        valid_b, state_b = validate_mock_metadata(meta_missing_apn)
        self.assertFalse(valid_b)
        self.assertEqual(state_b, METADATA_CHANGED)

        meta_wrong_len = dict(
            self.valid_metadata,
            fields=[{"name": "APN", "type": "esriFieldTypeString", "length": 8}],
        )
        valid_c, state_c = validate_mock_metadata(meta_wrong_len)
        self.assertFalse(valid_c)
        self.assertEqual(state_c, METADATA_CHANGED)

        meta_geom_drift = dict(
            self.valid_metadata,
            geometryType="esriGeometryPoint",
        )
        valid_d, state_d = validate_mock_metadata(meta_geom_drift)
        self.assertFalse(valid_d)
        self.assertEqual(state_d, METADATA_CHANGED)

    def test_05_request_contract_exactness_and_immutability(self) -> None:
        """Test 5: Request contract has exact 5 keys and is immutable (raises TypeError on assignment)."""
        contract = build_test_only_request_contract(self.apn_valid_1)
        self.assertEqual(
            set(contract.keys()),
            {"where", "outFields", "returnGeometry", "resultRecordCount", "f"},
        )
        self.assertEqual(contract["where"], f"APN = '{self.apn_valid_1}'")
        self.assertEqual(contract["outFields"], "APN")
        self.assertTrue(contract["returnGeometry"])
        self.assertEqual(contract["resultRecordCount"], 1)
        self.assertEqual(contract["f"], "json")

        # Verify immutability
        with self.assertRaises(TypeError):
            contract["outFields"] = "*"

        with self.assertRaises(TypeError):
            contract["injected_key"] = "unsafe_val"

    def test_06_request_contract_rejections(self) -> None:
        """Test 6: Request builder rejects test_mode=False and unallowlisted APNs."""
        with self.assertRaises(ValueError):
            build_test_only_request_contract(self.apn_valid_1, test_mode=False)

        with self.assertRaises(ValueError):
            build_test_only_request_contract("222-333-444-555")

    def test_07_response_validator_expected_input_gating(self) -> None:
        """Test 7: Response validator validates expected_apn before checking payload."""
        with self.assertRaises(ValueError):
            validate_mock_feature_response("99900011", {"features": []})

        with self.assertRaises(ValueError):
            validate_mock_feature_response("222-333-444-555", {"features": []})

        hyphenated_expected = "999-000-111-222"
        payload = {
            "features": [{
                "attributes": {"APN": self.apn_valid_1},
                "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
            }]
        }
        res = validate_mock_feature_response(hyphenated_expected, payload)
        self.assertTrue(res.success)
        self.assertEqual(res.status_code, EXACT_MATCH_PENDING_EVIDENCE)
        self.assertEqual(res.apn, self.apn_valid_1)

    def test_08_empty_features_returns_not_found(self) -> None:
        """Test 8: Empty feature array returns IDENTIFIER_NOT_FOUND and geometry is None."""
        payload = {"features": []}
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, IDENTIFIER_NOT_FOUND)
        self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
        self.assertIsNone(res.geometry)

    def test_09_one_feature_prefix_returns_mismatch(self) -> None:
        """Test 9: Single feature returning 8-digit prefix returns IDENTIFIER_MISMATCH."""
        payload = {
            "features": [{
                "attributes": {"APN": "99900011"},
                "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
            }]
        }
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, IDENTIFIER_MISMATCH)
        self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
        self.assertIsNone(res.geometry)

    def test_10_one_feature_different_12_digit_returns_mismatch(self) -> None:
        """Test 10: Single feature returning different 12-digit APN returns IDENTIFIER_MISMATCH."""
        payload = {
            "features": [{
                "attributes": {"APN": self.apn_valid_2},
                "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
            }]
        }
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, IDENTIFIER_MISMATCH)
        self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
        self.assertIsNone(res.geometry)

    def test_11_two_features_returns_ambiguous(self) -> None:
        """Test 11: Multiple features return IDENTIFIER_AMBIGUOUS and geometry is None."""
        payload = {
            "features": [
                {
                    "attributes": {"APN": self.apn_valid_1},
                    "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
                },
                {
                    "attributes": {"APN": self.apn_valid_1},
                    "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
                },
            ]
        }
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, IDENTIFIER_AMBIGUOUS)
        self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
        self.assertIsNone(res.geometry)

    def test_12_extra_attribute_returns_disallowed_field(self) -> None:
        """Test 12: Extra attribute beyond APN returns DISALLOWED_FIELD_PRESENT."""
        payload = {
            "features": [{
                "attributes": {"APN": self.apn_valid_1, "OBJECTID": 101},
                "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
            }]
        }
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, DISALLOWED_FIELD_PRESENT)
        self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
        self.assertIsNone(res.geometry)

    def test_13_missing_geometry_returns_missing(self) -> None:
        """Test 13: Missing geometry dictionary returns GEOMETRY_MISSING."""
        payload = {"features": [{"attributes": {"APN": self.apn_valid_1}}]}
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertFalse(res.success)
        self.assertEqual(res.status_code, GEOMETRY_MISSING)
        self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
        self.assertIsNone(res.geometry)

    def test_14_coordinate_numeric_hardening(self) -> None:
        """Test 14: Boolean, NaN, and Infinite coordinates return EVIDENCE_INSUFFICIENT."""
        hardened_cases = [
            [[[True, 0.0], [0.0, 1.0], [1.0, 1.0], [True, 0.0]]],
            [[[0.0, float("nan")], [0.0, 1.0], [1.0, 1.0], [0.0, float("nan")]]],
            [[[0.0, float("inf")], [0.0, 1.0], [1.0, 1.0], [0.0, float("inf")]]],
            [[[0.0, float("-inf")], [0.0, 1.0], [1.0, 1.0], [0.0, float("-inf")]]],
        ]
        for ring in hardened_cases:
            with self.subTest(ring=ring):
                payload = {
                    "features": [{
                        "attributes": {"APN": self.apn_valid_1},
                        "geometry": {"rings": ring},
                    }]
                }
                res = validate_mock_feature_response(self.apn_valid_1, payload)
                self.assertFalse(res.success)
                self.assertEqual(res.status_code, EVIDENCE_INSUFFICIENT)
                self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
                self.assertIsNone(res.geometry)

    def test_15_malformed_response_envelopes(self) -> None:
        """Test 15: Non-dict payload, error object, missing/non-list features, missing attributes return MALFORMED_RESPONSE."""
        malformed_cases = [
            "not a dictionary",
            12345,
            {"error": {"code": 400, "message": "Bad Request"}},
            {"other_key": []},
            {"features": "not a list"},
            {"features": ["not a dictionary feature"]},
            {"features": [{"attributes": None, "geometry": {}}]},
            {"features": [{"geometry": {}}]},
            {"features": [{"attributes": {"APN": self.apn_valid_1}, "geometry": {"rings": []}}]},
            {"features": [{"attributes": {"APN": self.apn_valid_1}, "geometry": {"rings": [[[0.0, 0.0], [1.0, 1.0], [0.0, 0.0]]]}}]},
        ]
        for case in malformed_cases:
            with self.subTest(case=case):
                res = validate_mock_feature_response(self.apn_valid_1, case)
                self.assertFalse(res.success)
                self.assertEqual(res.validation_decision, DO_NOT_USE_PARCEL_ASSERTION)
                self.assertIsNone(res.geometry)

    def test_16_exact_valid_match_success(self) -> None:
        """Test 16: Exact match returns EXACT_MATCH_PENDING_EVIDENCE and retains geometry."""
        payload = {
            "features": [{
                "attributes": {"APN": self.apn_valid_1},
                "geometry": {"rings": SYNTHETIC_TEST_GEOMETRY},
            }]
        }
        res = validate_mock_feature_response(self.apn_valid_1, payload)
        self.assertTrue(res.success)
        self.assertEqual(res.status_code, EXACT_MATCH_PENDING_EVIDENCE)
        self.assertEqual(res.validation_decision, PENDING_PARCEL_EVIDENCE)
        self.assertEqual(res.apn, self.apn_valid_1)
        self.assertEqual(res.geometry, SYNTHETIC_TEST_GEOMETRY)

    def test_17_ast_isolation_safe_fixtures_pass(self) -> None:
        """Test 17: AST analyzer produces zero violations on literal safe source strings."""
        violations_val = audit_source_text(SAFE_VALIDATION_SOURCE_FIXTURE)
        self.assertEqual(violations_val, [])

        violations_test = audit_source_text(SAFE_TEST_SOURCE_FIXTURE)
        self.assertEqual(violations_test, [])

    def test_18_ast_isolation_unsafe_imports_and_calls_detected(self) -> None:
        """Test 18: AST analyzer flags prohibited module imports and direct runtime calls."""
        violations_imp = audit_source_text(UNSAFE_IMPORT_SOURCE_FIXTURE)
        self.assertGreater(len(violations_imp), 0)
        violation_str_imp = " ".join(violations_imp)
        self.assertIn("requests", violation_str_imp)
        self.assertIn("urllib.request", violation_str_imp)
        self.assertIn("sqlite3", violation_str_imp)

        violations_call = audit_source_text(UNSAFE_CALL_SOURCE_FIXTURE)
        self.assertGreater(len(violations_call), 0)
        violation_str_call = " ".join(violations_call)
        self.assertIn("open", violation_str_call)
        self.assertIn("urlopen", violation_str_call)
        self.assertIn("connect", violation_str_call)

    def test_19_ast_isolation_aliases_detected(self) -> None:
        """Test 19: AST analyzer tracks module and symbol aliases and flags calls made through them."""
        violations_mod_alias = audit_source_text(UNSAFE_MODULE_ALIAS_SOURCE_FIXTURE)
        self.assertGreater(len(violations_mod_alias), 0)
        v_str_mod = " ".join(violations_mod_alias)
        self.assertIn("req.get", v_str_mod)

        violations_call_alias = audit_source_text(UNSAFE_CALL_ALIAS_SOURCE_FIXTURE)
        self.assertGreater(len(violations_call_alias), 0)
        v_str_call = " ".join(violations_call_alias)
        self.assertIn("fetch", v_str_call)

        violations_dotted = audit_source_text(UNSAFE_DOTTED_IMPORT_SOURCE_FIXTURE)
        self.assertGreater(len(violations_dotted), 0)
        v_str_dotted = " ".join(violations_dotted)
        self.assertIn("requests.sessions.Session", v_str_dotted)


if __name__ == '__main__':
    unittest.main()
