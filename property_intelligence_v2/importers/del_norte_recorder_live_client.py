"""
property_intelligence_v2/importers/del_norte_recorder_live_client.py

Phase 4F: a narrow, single-lookup live-query client for Del Norte County's
Tyler Self-Service recorder document-number search. Implements the Phase 4E
design's client contract. Companion to del_norte_recorder_result.py (the
Phase 4D pure parser, which this module never calls) and
del_norte_recorder_result_pipeline.py (the thin pipeline that calls both).

BOUNDARY CONTRACT: fetch_recorder_document_number_result() performs HTTP
requests and returns an in-memory typed result. No sqlite3 connection, no
filesystem access, no artifact_root, no call into the recorder parser or
any importer/pipeline module, and no fetch of any detail/image link -
anywhere in this file. No temporary or scratch file is ever created; the
document number and every response body stay in local variables and
returned dataclass fields only.

## Standard library only

Uses urllib.request + http.cookiejar for the disclaimer-acceptance cookie
flow - no httpx/requests dependency. This differs from the existing
del_norte_recorder_tyler.py (which uses httpx) and was a deliberate Phase
4F choice: the stdlib fully supports the required GET/POST/cookie flow
(verified directly before writing this file), and avoiding a new dependency
keeps this module runnable in more environments.

## User-Agent convention

Callers must supply an explicit, identifiable user_agent (e.g. the
self-identifying "PropertyIntelligenceResearch/0.1 (contact: local
operator)" string already used and approved for Phase 4B/4C's discovery
work) - this module has no default and never spoofs a browser. This is a
deliberate departure from the existing del_norte_recorder_tyler.py, which
does spoof a browser UA; the two are not reconciled here.

## Request budget and pacing

A normal successful lookup makes exactly 5 requests: GET disclaimer, POST
disclaimer (empty body), GET search form, POST search, GET results. A
hard cap of MAX_REQUESTS is enforced by an internal counter - exceeding it
returns RecorderLiveQueryBlocked("request_budget_exhausted", ...) rather
than making a 6th request. At least MIN_DELAY_SECONDS elapses between
requests (not before the first); the `sleep` parameter is injectable so
tests never actually wait.

## One session per call

opener_factory (if not supplied) builds a fresh urllib opener with a fresh,
empty http.cookiejar.CookieJar() - constructed fresh inside the function
call and never stored on the module or reused across calls. This session
is discarded when the function returns.

## Typed results - never an ordinary control-flow exception for an expected
## condition

- RecorderLiveQuerySuccess(raw_content: bytes, final_url, status_code,
  request_count): raw_content is the exact, undecoded response body bytes
  - never decoded here. Decoding (and its explicit encoding assumption)
  belongs to the pipeline, at the boundary where it builds the parser's
  input - see del_norte_recorder_result_pipeline.py.
- RecorderLiveQueryBlocked(reason, message, request_count): a site
  condition or a self-imposed safety limit stopped the lookup before (or
  instead of) a normal success - CAPTCHA, a real login form, HTTP 429, an
  unexpected redirect (including a bounce back to the disclaimer page
  after acceptance), an unexpected non-200 status, or request-budget
  exhaustion.
- RecorderLiveQueryError(reason, message, request_count): a genuine
  transport-level failure (DNS, connection refused, timeout, or any other
  urllib.error.URLError/OSError) - the HTTP exchange itself could not be
  completed, as distinct from a Blocked condition where a real response
  was received but wasn't a clean success.

Only a genuinely unexpected internal bug would raise past this function's
own boundary; every condition enumerated in the Phase 4F authorization
(CAPTCHA marker, login/password form, 429/rate limit, redirect back to
disclaimer after acceptance, unexpected redirect, transport/HTTP failure,
request-budget exhaustion) is handled and returned as a typed result.
"""
from __future__ import annotations

import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Union

BASE_URL = "https://delnortecountyca-web.tylerhost.net"
ADVANCED_SEARCH_ID = "DOCSEARCH201S8"
DISCLAIMER_PATH = "/web/user/disclaimer"

MAX_REQUESTS = 5
MIN_DELAY_SECONDS = 2.0
REQUEST_TIMEOUT_SECONDS = 20

AJAX_HEADERS = {
    "ajaxrequest": "true",
    "x-requested-with": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

_CAPTCHA_PATTERN = re.compile(r"recaptcha|g-recaptcha|grecaptcha", re.IGNORECASE)
_LOGIN_FORM_PATTERN = re.compile(r'<input[^>]+type=["\']password["\']', re.IGNORECASE)


def apply_doc_transform(doc_number: str) -> str:
    """The documented Del Norte recorder transform, reused verbatim from
    del_norte_recorder_tyler.py's _apply_doc_transform() (same behavior,
    made public here since both this client and the Phase 4F pipeline
    legitimately need it - not reimplemented independently in either)."""
    return doc_number.replace("R", "")


@dataclass(frozen=True)
class RecorderLiveQuerySuccess:
    raw_content: bytes
    final_url: str
    status_code: int
    request_count: int


@dataclass(frozen=True)
class RecorderLiveQueryBlocked:
    reason: str
    message: str
    request_count: int


@dataclass(frozen=True)
class RecorderLiveQueryError:
    reason: str
    message: str
    request_count: int


RecorderLiveQueryResult = Union[RecorderLiveQuerySuccess, RecorderLiveQueryBlocked, RecorderLiveQueryError]


class _RequestBudgetExhaustedError(Exception):
    """Internal control-flow only - never escapes
    fetch_recorder_document_number_result(); converted to a typed
    RecorderLiveQueryBlocked before returning."""


class _BudgetedSession:
    """Wraps one opener (one session) for the lifetime of a single call.
    Enforces MAX_REQUESTS and the inter-request delay centrally, so every
    request made through this session automatically inherits both."""

    def __init__(self, opener, *, sleep: Callable[[float], None], user_agent: str) -> None:
        self._opener = opener
        self._sleep = sleep
        self._user_agent = user_agent
        self.request_count = 0

    def request(self, method: str, url: str, *, data: bytes | None = None,
                extra_headers: dict[str, str] | None = None):
        if self.request_count >= MAX_REQUESTS:
            raise _RequestBudgetExhaustedError()
        if self.request_count > 0:
            self._sleep(MIN_DELAY_SECONDS)
        headers = {"User-Agent": self._user_agent}
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        self.request_count += 1
        return self._opener.open(req, timeout=REQUEST_TIMEOUT_SECONDS)


def _default_opener_factory():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _response_status(resp) -> int:
    return getattr(resp, "status", None) if getattr(resp, "status", None) is not None else resp.getcode()


def _response_final_url(resp) -> str:
    return resp.geturl()


def _decode_for_pattern_check(raw_bytes: bytes) -> str:
    """Decoding used ONLY for this module's own internal CAPTCHA/login-form
    text-pattern checks - never for the bytes returned on
    RecorderLiveQuerySuccess.raw_content, which are always the untouched
    original bytes."""
    return raw_bytes.decode("utf-8", errors="replace")


def _build_search_payload(transformed_document_number: str) -> bytes:
    payload = {
        "field_DocumentNumberID": transformed_document_number,
        "field_BookPageID_DOT_Volume": "",
        "field_BookPageID_DOT_Page": "",
        "field_RecordingDateID_DOT_StartDate": "",
        "field_RecordingDateID_DOT_EndDate": "",
        "field_BothNamesID-searchInput": "",
        "field_BothNamesID-containsInput": "Contains Any",
        "field_BothNamesID": "",
        "field_GrantorID-searchInput": "",
        "field_GrantorID-containsInput": "Contains Any",
        "field_GrantorID": "",
        "field_GranteeID-searchInput": "",
        "field_GranteeID-containsInput": "Contains Any",
        "field_GranteeID": "",
    }
    return urllib.parse.urlencode(payload).encode("utf-8")


def _check_redirect(final_url: str, expected_path: str, request_count: int) -> RecorderLiveQueryBlocked | None:
    if DISCLAIMER_PATH in final_url and expected_path != DISCLAIMER_PATH:
        return RecorderLiveQueryBlocked(
            "redirected_to_disclaimer_after_acceptance",
            f"expected a response for {expected_path} but was redirected back to the disclaimer page",
            request_count,
        )
    if expected_path not in final_url:
        return RecorderLiveQueryBlocked(
            "unexpected_redirect",
            f"expected a response for {expected_path} but the final URL was {final_url}",
            request_count,
        )
    return None


def fetch_recorder_document_number_result(
    document_number_assessor_form: str,
    *,
    user_agent: str,
    opener_factory: Callable[[], object] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
) -> RecorderLiveQueryResult:
    """Perform exactly one document-number lookup: disclaimer GET,
    disclaimer-acceptance POST, search-form GET, search POST, results GET -
    at most 5 requests total. Returns a typed success/blocked/error result;
    never raises for any of the conditions enumerated in this module's
    docstring. See the module docstring for the full contract."""
    opener = (opener_factory or _default_opener_factory)()
    session = _BudgetedSession(opener, sleep=sleep, user_agent=user_agent)
    transformed = apply_doc_transform(document_number_assessor_form)

    # Step 1: GET disclaimer.
    try:
        resp = session.request("GET", f"{BASE_URL}{DISCLAIMER_PATH}")
    except _RequestBudgetExhaustedError:
        return RecorderLiveQueryBlocked("request_budget_exhausted", "request budget exhausted before disclaimer GET", session.request_count)
    except (urllib.error.URLError, OSError) as exc:
        return RecorderLiveQueryError("transport_failure", str(exc), session.request_count)

    body_bytes = resp.read()
    text = _decode_for_pattern_check(body_bytes)
    if _CAPTCHA_PATTERN.search(text):
        return RecorderLiveQueryBlocked("captcha_detected", "CAPTCHA marker found on the disclaimer page", session.request_count)
    if _LOGIN_FORM_PATTERN.search(text):
        return RecorderLiveQueryBlocked("login_wall_detected", "a password-type input was found on the disclaimer page", session.request_count)

    # Step 2: POST disclaimer acceptance, empty body, no search criteria.
    try:
        resp = session.request("POST", f"{BASE_URL}{DISCLAIMER_PATH}", data=b"")
    except _RequestBudgetExhaustedError:
        return RecorderLiveQueryBlocked("request_budget_exhausted", "request budget exhausted before disclaimer POST", session.request_count)
    except (urllib.error.URLError, OSError) as exc:
        return RecorderLiveQueryError("transport_failure", str(exc), session.request_count)
    if _response_status(resp) == 429:
        return RecorderLiveQueryBlocked("rate_limited", "HTTP 429 on disclaimer-acceptance POST", session.request_count)

    # Step 3: GET the advanced search form (primes server-side view-state).
    try:
        resp = session.request("GET", f"{BASE_URL}/web/search/{ADVANCED_SEARCH_ID}")
    except _RequestBudgetExhaustedError:
        return RecorderLiveQueryBlocked("request_budget_exhausted", "request budget exhausted before search-form GET", session.request_count)
    except (urllib.error.URLError, OSError) as exc:
        return RecorderLiveQueryError("transport_failure", str(exc), session.request_count)
    status = _response_status(resp)
    if status == 429:
        return RecorderLiveQueryBlocked("rate_limited", "HTTP 429 on search-form GET", session.request_count)
    final_url = _response_final_url(resp)
    blocked = _check_redirect(final_url, f"/web/search/{ADVANCED_SEARCH_ID}", session.request_count)
    if blocked is not None:
        return blocked
    body_bytes = resp.read()
    text = _decode_for_pattern_check(body_bytes)
    if _CAPTCHA_PATTERN.search(text):
        return RecorderLiveQueryBlocked("captcha_detected", "CAPTCHA marker found on the search-form page", session.request_count)

    # Step 4: POST exactly one document-number search.
    payload = _build_search_payload(transformed)
    search_headers = dict(AJAX_HEADERS)
    search_headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        resp = session.request(
            "POST", f"{BASE_URL}/web/searchPost/{ADVANCED_SEARCH_ID}",
            data=payload, extra_headers=search_headers,
        )
    except _RequestBudgetExhaustedError:
        return RecorderLiveQueryBlocked("request_budget_exhausted", "request budget exhausted before search POST", session.request_count)
    except (urllib.error.URLError, OSError) as exc:
        return RecorderLiveQueryError("transport_failure", str(exc), session.request_count)
    if _response_status(resp) == 429:
        return RecorderLiveQueryBlocked("rate_limited", "HTTP 429 on search POST", session.request_count)

    # Step 5: GET the search results.
    results_url = f"{BASE_URL}/web/searchResults/{ADVANCED_SEARCH_ID}?page=1&_={int(now() * 1000)}"
    try:
        resp = session.request("GET", results_url, extra_headers=AJAX_HEADERS)
    except _RequestBudgetExhaustedError:
        return RecorderLiveQueryBlocked("request_budget_exhausted", "request budget exhausted before results GET", session.request_count)
    except (urllib.error.URLError, OSError) as exc:
        return RecorderLiveQueryError("transport_failure", str(exc), session.request_count)

    status = _response_status(resp)
    if status == 429:
        return RecorderLiveQueryBlocked("rate_limited", "HTTP 429 on results GET", session.request_count)
    final_url = _response_final_url(resp)
    blocked = _check_redirect(final_url, f"/web/searchResults/{ADVANCED_SEARCH_ID}", session.request_count)
    if blocked is not None:
        return blocked
    body_bytes = resp.read()
    text = _decode_for_pattern_check(body_bytes)
    if _CAPTCHA_PATTERN.search(text):
        return RecorderLiveQueryBlocked("captcha_detected", "CAPTCHA marker found on the results page", session.request_count)
    if status != 200:
        return RecorderLiveQueryBlocked("unexpected_status_code", f"unexpected HTTP status {status} on results GET", session.request_count)

    return RecorderLiveQuerySuccess(
        raw_content=body_bytes,
        final_url=final_url,
        status_code=status,
        request_count=session.request_count,
    )
