"""
Tests for property_intelligence_v2/importers/del_norte_recorder_live_client.py.

No real HTTP request anywhere in this file. Every test injects a fake
opener (mimicking only the .open(request, timeout=...) surface this client
actually uses) and a no-op sleeper - never touches a real socket. Document
numbers and response bodies are fully synthetic (TEST_ONLY_/EXAMPLE_*-style
placeholders are fine here since nothing in this file ever reaches the
committed importer's TEST_ONLY_ rejection gate - these are pure client-layer
tests, no database, no persistence).

Run: python3 property_intelligence_v2/tests/test_del_norte_recorder_live_client.py
"""
import ast
import sys
import urllib.error
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "importers"))

import del_norte_recorder_live_client as client_module  # noqa: E402
from del_norte_recorder_live_client import (  # noqa: E402
    BASE_URL,
    ADVANCED_SEARCH_ID,
    MIN_DELAY_SECONDS,
    RecorderLiveQueryBlocked,
    RecorderLiveQueryError,
    RecorderLiveQuerySuccess,
    _BudgetedSession,
    _RequestBudgetExhaustedError,
    apply_doc_transform,
    fetch_recorder_document_number_result,
)

CLIENT_SOURCE = Path(client_module.__file__).read_text(encoding="utf-8")

UA = "TEST_ONLY_PropertyIntelligenceResearch/0.1 (contact: local operator)"
DOC_NUMBER = "2000R0000"
TRANSFORMED_DOC_NUMBER = apply_doc_transform(DOC_NUMBER)  # "20000000"


class _FakeResponse:
    def __init__(self, body: bytes = b"", status: int = 200, url: str | None = None):
        self._body = body
        self.status = status
        self._url = url

    def read(self) -> bytes:
        return self._body

    def geturl(self) -> str:
        return self._url


class _FakeOpener:
    """Records every request made through it (method, url, data, headers);
    returns/raises the next canned item from a caller-supplied list in
    order. Mimics only the .open(request, timeout=...) surface this client
    actually calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append({
            "method": request.get_method(),
            "url": request.full_url,
            "data": request.data,
            "user_agent": request.get_header("User-agent"),
        })
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _sleeper():
    calls = []

    def sleep(seconds):
        calls.append(seconds)

    sleep.calls = calls
    return sleep


def _counting_factory(opener):
    calls = []

    def factory():
        calls.append(1)
        return opener

    factory.calls = calls
    return factory


DISCLAIMER_URL = f"{BASE_URL}/web/user/disclaimer"
SEARCH_FORM_URL = f"{BASE_URL}/web/search/{ADVANCED_SEARCH_ID}"
RESULTS_URL_PREFIX = f"{BASE_URL}/web/searchResults/{ADVANCED_SEARCH_ID}"


def _happy_path_responses():
    return [
        _FakeResponse(b"<html>disclaimer, clean</html>", 200, DISCLAIMER_URL),
        _FakeResponse(b"", 200, DISCLAIMER_URL),
        _FakeResponse(b"<html>search form, clean</html>", 200, SEARCH_FORM_URL),
        _FakeResponse(b"", 200, f"{BASE_URL}/web/searchPost/{ADVANCED_SEARCH_ID}"),
        _FakeResponse(b"<html>one result row here</html>", 200, f"{RESULTS_URL_PREFIX}?page=1&_=123"),
    ]


def test_full_happy_path_sequence_payload_delays_and_session_reuse():
    opener = _FakeOpener(_happy_path_responses())
    factory = _counting_factory(opener)
    sleep = _sleeper()

    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=factory, sleep=sleep, now=lambda: 0.123,
    )

    assert isinstance(result, RecorderLiveQuerySuccess), result
    assert result.raw_content == b"<html>one result row here</html>"
    assert result.status_code == 200
    assert result.request_count == 5

    assert len(factory.calls) == 1, "opener_factory must be called exactly once per lookup call (one session per call)"

    assert len(opener.calls) == 5
    methods_urls = [(c["method"], c["url"].split("?")[0]) for c in opener.calls]
    assert methods_urls == [
        ("GET", DISCLAIMER_URL),
        ("POST", DISCLAIMER_URL),
        ("GET", SEARCH_FORM_URL),
        ("POST", f"{BASE_URL}/web/searchPost/{ADVANCED_SEARCH_ID}"),
        ("GET", RESULTS_URL_PREFIX),
    ], methods_urls

    assert opener.calls[1]["data"] == b"", "disclaimer acceptance POST must have an empty body, no search criteria"
    search_payload = urllib.parse.parse_qs(opener.calls[3]["data"].decode("utf-8"), keep_blank_values=True)
    assert search_payload["field_DocumentNumberID"] == [TRANSFORMED_DOC_NUMBER]
    assert search_payload["field_GrantorID"] == [""]
    assert search_payload["field_GranteeID"] == [""]

    assert all(c["user_agent"] == UA for c in opener.calls), "every request must carry the caller-supplied identifiable user agent"

    assert sleep.calls == [MIN_DELAY_SECONDS] * 4, "exactly one delay between each pair of the 5 requests, none before the first"
    print("PASS: full happy-path sequence - correct method/URL order, empty disclaimer-POST body, exact document-number search payload, identifiable UA on every request, correct delay count, and single-session reuse (opener_factory called exactly once)")


def test_captcha_marker_on_disclaimer_page_blocks_immediately():
    opener = _FakeOpener([_FakeResponse(b"<html>please solve this grecaptcha challenge</html>", 200, DISCLAIMER_URL)])
    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
    )
    assert isinstance(result, RecorderLiveQueryBlocked), result
    assert result.reason == "captcha_detected"
    assert result.request_count == 1
    assert len(opener.calls) == 1, "no further request should be made once a CAPTCHA marker is found"
    print("PASS: a CAPTCHA marker on the disclaimer page returns RecorderLiveQueryBlocked('captcha_detected', ...) after exactly 1 request")


def test_login_form_on_disclaimer_page_blocks_immediately():
    body = b'<html><form><input type="password" name="pw"></form></html>'
    opener = _FakeOpener([_FakeResponse(body, 200, DISCLAIMER_URL)])
    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
    )
    assert isinstance(result, RecorderLiveQueryBlocked), result
    assert result.reason == "login_wall_detected"
    assert result.request_count == 1
    print("PASS: a real password-type input on the disclaimer page returns RecorderLiveQueryBlocked('login_wall_detected', ...)")


def test_429_on_disclaimer_post_blocks():
    opener = _FakeOpener([
        _FakeResponse(b"<html>disclaimer, clean</html>", 200, DISCLAIMER_URL),
        _FakeResponse(b"", 429, DISCLAIMER_URL),
    ])
    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
    )
    assert isinstance(result, RecorderLiveQueryBlocked), result
    assert result.reason == "rate_limited"
    assert result.request_count == 2
    print("PASS: HTTP 429 on the disclaimer-acceptance POST returns RecorderLiveQueryBlocked('rate_limited', ...)")


def test_redirect_back_to_disclaimer_after_acceptance_blocks():
    opener = _FakeOpener([
        _FakeResponse(b"<html>disclaimer, clean</html>", 200, DISCLAIMER_URL),
        _FakeResponse(b"", 200, DISCLAIMER_URL),
        _FakeResponse(b"<html>still disclaimer</html>", 200, DISCLAIMER_URL),  # bounced back
    ])
    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
    )
    assert isinstance(result, RecorderLiveQueryBlocked), result
    assert result.reason == "redirected_to_disclaimer_after_acceptance"
    assert result.request_count == 3
    print("PASS: a redirect back to the disclaimer page after acceptance returns RecorderLiveQueryBlocked('redirected_to_disclaimer_after_acceptance', ...)")


def test_unexpected_redirect_blocks():
    opener = _FakeOpener([
        _FakeResponse(b"<html>disclaimer, clean</html>", 200, DISCLAIMER_URL),
        _FakeResponse(b"", 200, DISCLAIMER_URL),
        _FakeResponse(b"<html>somewhere else entirely</html>", 200, f"{BASE_URL}/web/some/unrelated/page"),
    ])
    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
    )
    assert isinstance(result, RecorderLiveQueryBlocked), result
    assert result.reason == "unexpected_redirect"
    assert result.request_count == 3
    print("PASS: an unexpected redirect to neither the expected path nor the disclaimer returns RecorderLiveQueryBlocked('unexpected_redirect', ...)")


def test_transport_failure_returns_typed_error():
    opener = _FakeOpener([urllib.error.URLError("TEST_ONLY simulated DNS failure")])
    result = fetch_recorder_document_number_result(
        DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
    )
    assert isinstance(result, RecorderLiveQueryError), result
    assert result.reason == "transport_failure"
    assert result.request_count == 1
    print("PASS: a genuine transport failure (URLError) returns a typed RecorderLiveQueryError, not an uncaught exception")


def test_request_budget_exhaustion_returns_typed_blocked_via_real_flow():
    """Temporarily lowers MAX_REQUESTS so the real 5-step flow itself hits
    the budget mid-sequence, proving the integration behavior (not just the
    isolated _BudgetedSession unit below)."""
    original_max = client_module.MAX_REQUESTS
    client_module.MAX_REQUESTS = 2
    try:
        opener = _FakeOpener([
            _FakeResponse(b"<html>disclaimer, clean</html>", 200, DISCLAIMER_URL),
            _FakeResponse(b"", 200, DISCLAIMER_URL),
        ])
        result = fetch_recorder_document_number_result(
            DOC_NUMBER, user_agent=UA, opener_factory=lambda: opener, sleep=_sleeper(),
        )
        assert isinstance(result, RecorderLiveQueryBlocked), result
        assert result.reason == "request_budget_exhausted"
        assert result.request_count == 2
        assert len(opener.calls) == 2, "no 3rd request should ever be attempted once the budget is exhausted"
    finally:
        client_module.MAX_REQUESTS = original_max
    print("PASS: exhausting the request budget mid-flow returns RecorderLiveQueryBlocked('request_budget_exhausted', ...) without attempting another request")


def test_budgeted_session_raises_internally_past_its_own_cap():
    """Direct unit-level proof of the _BudgetedSession mechanism itself,
    independent of the integration test above."""
    opener = _FakeOpener([_FakeResponse(b"", 200, DISCLAIMER_URL) for _ in range(5)])
    session = _BudgetedSession(opener, sleep=_sleeper(), user_agent=UA)
    for _ in range(5):
        session.request("GET", DISCLAIMER_URL)
    try:
        session.request("GET", DISCLAIMER_URL)
        raise AssertionError("Expected _RequestBudgetExhaustedError")
    except _RequestBudgetExhaustedError:
        pass
    print("PASS: _BudgetedSession itself raises _RequestBudgetExhaustedError on the request past its cap")


def test_document_number_transform_is_the_documented_one_and_is_reused_not_reinvented():
    assert apply_doc_transform("2026R1355") == "20261355"
    assert apply_doc_transform("1234ABCD5678") == "1234ABCD5678"  # no "R" present - no-op
    print("PASS: apply_doc_transform() matches the documented Del Norte recorder transform ('R' stripped, nothing else)")


def test_client_source_has_no_scratch_file_or_persistence_behavior():
    # AST-based, not substring matching - immune to this module's own
    # docstring/comment prose about "no temporary or scratch file", the
    # same technique already established in this repository's extractor
    # purity tests after two prior false-positive substring-scan incidents.
    tree = ast.parse(CLIENT_SOURCE, filename=client_module.__file__)
    imported_modules = set()
    direct_called_names = set()   # bare name calls, e.g. open(...) - the real builtin file-open risk
    method_called_names = set()   # attribute calls, e.g. self._opener.open(...) - NOT file I/O here;
                                   # .open() on the injected transport is the intended dependency-injection
                                   # seam this whole module is built around, so "open" is deliberately
                                   # excluded from THIS set's forbidden check below, unlike direct_called_names.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                direct_called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                method_called_names.add(func.attr)

    forbidden_modules = {"sqlite3", "tempfile"}
    assert not (imported_modules & forbidden_modules), imported_modules & forbidden_modules

    forbidden_direct_calls = {"open"}
    assert not (direct_called_names & forbidden_direct_calls), direct_called_names & forbidden_direct_calls

    forbidden_method_calls = {"write_text", "write_bytes", "mkstemp", "mkdtemp"}
    assert not (method_called_names & forbidden_method_calls), method_called_names & forbidden_method_calls
    print("PASS: del_norte_recorder_live_client.py never imports sqlite3/tempfile, never calls the builtin open(), and never calls write_text()/write_bytes()/mkstemp()/mkdtemp() (checked via AST; the injected transport's own .open() method call is correctly excluded, not a file-I/O risk)")


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
