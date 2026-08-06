"""
tehama_recorder_tyler.py — reference RecorderAdapter for Tehama County.

Platform: Tyler Technologies self-service recorder search
    https://recordsearch.tehama.gov/web   (confirmed live; footer reads
    'Tyler Technologies | Version 2024.1.40', reached via /web/user/disclaimer)

Wire details in the PORTAL WIRE DETAILS block below are the live-verified
values from tyler_recorder_client.py. Same portal, same flow. If a Tyler
install has different search IDs / doc-number transform, they live in the
CountyConfig — the rest of this class is portal-shape, not county-shape.

────────────────────────────────────────────────────────────────────────────
Flow (confirmed live 7/13, 8/1 in tyler_recorder_client.py):
  1. GET  /web/user/disclaimer          — sets session cookie
  2. POST /web/user/disclaimer          — flips server-side acceptance
  3. GET  /web/search/{search_id}       — prime the search view-state
  4. POST /web/searchPost/{search_id}   — submit; AJAX headers required
  5. GET  /web/searchResults/{search_id}?page=N&_=ts  — page through
     — AJAX headers required; without them Fresno returns 500.
Results: <li class="ss-search-row"> rows, bullet-separated <h1>, and
<div class="searchResultThreeColumn"> blocks for grantor/grantee.
Every IO call routes through BaseAdapter.capture() so a RawFetch row is
recorded before parsing — no silent fallback, no re-hitting the server.
────────────────────────────────────────────────────────────────────────────

Deps: beautifulsoup4, python-dateutil  (both already in requirements.txt)
Assumes self.http is a cookie-persistent client (httpx.Client with
follow_redirects=True is what tyler_recorder_client.py uses in prod).
"""
from __future__ import annotations

import re
import time
from typing import Optional, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dtparse

from contracts import (
    Captured,
    Event,
    EventType,
    RecorderAdapter,
    SourceType,
    register,
)


def _apply_doc_transform(doc_number: str, transform: Optional[str]) -> str:
    """Mirror of tyler_recorder_client.apply_doc_transform — kept local so
    this adapter is self-contained. Confirmed live per-county transforms:
      r_to_strip     — Tehama: 2026R006490 -> 2026006490
      r_to_hyphen    — Shasta/Butte: 2024R0030607 -> 2024-0030607 (zero-pad to 7)
      r_to_hyphen_raw — Glenn: 2022R2373 -> 2022-2373 (no padding)
      None           — Fresno: 2023-0013662 already in indexed shape
    """
    if not transform:
        return doc_number
    if transform == "r_to_strip":
        return doc_number.replace("R", "")
    if transform == "r_to_hyphen":
        m = re.search(r"^(\d{4})R(\d+)$", doc_number)
        if m:
            year, num = m.groups()
            return f"{year}-{num.zfill(7)}"
        return re.sub(r"(?<=\d{4})R(?=\d+$)", "-", doc_number)
    if transform == "r_to_hyphen_raw":
        return re.sub(r"(?<=\d{4})R(?=\d+$)", "-", doc_number)
    return doc_number


@register(SourceType.RECORDER, "tyler")
class TehamaTylerRecorderAdapter(RecorderAdapter):
    parser_version = "2024.1.40-tehama-1"

    # ================================================================= #
    # PORTAL WIRE DETAILS — live-verified values from tyler_recorder_client.py.
    # County-varying values (base_url, search IDs, doc transform) come from
    # self.config.params; the class-level defaults below are Tehama's.
    # ================================================================= #
    DEFAULT_BASE_URL = "https://recordsearch.tehama.gov"

    # Path templates — same across every Tyler self-service install we've
    # verified (Tehama, Shasta, Butte, Fresno):
    DISCLAIMER_PATH = "/web/user/disclaimer"
    SEARCH_PAGE_PATH_TEMPLATE = "/web/search/{search_id}"
    SEARCH_POST_PATH_TEMPLATE = "/web/searchPost/{search_id}"
    RESULTS_PATH_TEMPLATE = "/web/searchResults/{search_id}"

    # Result HTML selectors — confirmed identical across Tehama, Shasta, Butte:
    RESULTS_ROW_SELECTOR = "li.ss-search-row"
    HEADER_SELECTOR = "h1"
    DATE_SELECTOR = "li.selfServiceSearchResultCollapsed"
    COLUMN_SELECTOR = "div.searchResultThreeColumn"
    BULLET = "•"
    TOTAL_RESULTS_RE = re.compile(r"for\s+(\d+)\s+Total Results")

    # Legitimately-empty indicator (Tyler shows this string when the search
    # ran but matched no records — distinguishes from a broken structure):
    NO_RESULTS_MARKER = "no results"

    # Safety bound on pagination — not a silent truncation, an alarm:
    PAGE_CEILING = 100

    # Politeness gap between requests — same value as the prod client:
    REQUEST_DELAY_S = 0.5

    # AJAX headers required on the two calls that are genuine XHR in a real
    # browser (searchPost + searchResults). NOT required on plain page
    # navigations (disclaimer, search-page prime) — sending them there
    # actively broke Butte per the note in tyler_recorder_client._init_session.
    AJAX_HEADERS = {
        "ajaxrequest": "true",
        "x-requested-with": "XMLHttpRequest",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }

    # POST field names — confirmed field names from live captures (Tehama).
    # These names are the same across every Tyler install we've probed;
    # per-county divergences (e.g., Glenn uses field_DocNumID) live in
    # self.config.params["doc_field_name"] with the class default below.
    DEFAULT_DOC_FIELD = "field_DocumentNumberID"
    F_NAME_INPUT = "field_BothNamesID-searchInput"
    F_NAME_CONTAINS = "field_BothNamesID-containsInput"
    F_NAME_HIDDEN = "field_BothNamesID"
    F_DATE_START = "field_RecordingDateID_DOT_StartDate"
    F_DATE_END = "field_RecordingDateID_DOT_EndDate"
    F_DOC_TYPES = "field_selfservice_documentTypes"
    F_DOC_TYPES_CONTAINS = "field_selfservice_documentTypes-containsInput"
    F_USE_ADVANCED = "field_UseAdvancedSearch"
    F_BOOK_VOLUME = "field_BookPageID_DOT_Volume"
    F_BOOK_PAGE = "field_BookPageID_DOT_Page"
    F_APN = "field_ParcelID"

    # Tehama defaults (overridden per county via self.config.params):
    DEFAULT_NAME_SEARCH_ID = "DOCSEARCH4S1"
    DEFAULT_DOC_SEARCH_ID = "DOCSEARCH4S2"
    DEFAULT_APN_SEARCH_ID = ""             # Tehama has no APN search
    DEFAULT_DOC_TRANSFORM = "r_to_strip"   # confirmed live 8/1
    # ================================================================= #

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._session_ready = False

    # ---- per-county wire values (from CountyConfig.params, with defaults) #
    @property
    def _base_url(self) -> str:
        return self.config.url or self.DEFAULT_BASE_URL

    @property
    def _name_search_id(self) -> str:
        return self.config.params.get("name_search_id") or self.DEFAULT_NAME_SEARCH_ID

    @property
    def _doc_search_id(self) -> str:
        return self.config.params.get("doc_search_id") or self.DEFAULT_DOC_SEARCH_ID

    @property
    def _apn_search_id(self) -> str:
        return self.config.params.get("apn_search_id", self.DEFAULT_APN_SEARCH_ID)

    @property
    def _doc_field_name(self) -> str:
        return self.config.params.get("doc_field_name") or self.DEFAULT_DOC_FIELD

    @property
    def _doc_transform(self) -> Optional[str]:
        return self.config.params.get("doc_number_transform", self.DEFAULT_DOC_TRANSFORM)

    # ---- session / disclaimer handshake ------------------------------ #
    def _ensure_session(self, force: bool = False) -> None:
        """GET then POST /web/user/disclaimer — Butte's real flow requires
        the POST (confirmed live 7/13 via DevTools: a background XHR fires
        automatically on the homepage). Tehama/Shasta tolerate the POST too.
        Not AJAX — no ajax headers here, matching the real browser."""
        if self._session_ready and not force:
            return
        self.capture(urljoin(self._base_url, self.DISCLAIMER_PATH))
        time.sleep(self.REQUEST_DELAY_S)
        self.capture(urljoin(self._base_url, self.DISCLAIMER_PATH), method="POST")
        time.sleep(self.REQUEST_DELAY_S)
        self._session_ready = True

    def _visit_search_page(self, search_id: str) -> None:
        """GET /web/search/{search_id} — primes server-side view-state for
        the subsequent POST. Confirmed required (Butte 7/13 debug): without
        it, searchPost returns the generic template shell with an empty
        <title>. Not AJAX — no ajax headers here."""
        self.capture(urljoin(self._base_url,
                             self.SEARCH_PAGE_PATH_TEMPLATE.format(search_id=search_id)))
        time.sleep(self.REQUEST_DELAY_S)

    # ---- search + pagination ----------------------------------------- #
    def _submit_and_page(self, search_id: str, payload: dict) -> list[Event]:
        self._ensure_session()
        self._visit_search_page(search_id)

        # 1) POST the search — this sets the server-side result set for
        # this search_id but returns a redirect/shell, NOT the rows.
        self.capture(
            urljoin(self._base_url,
                    self.SEARCH_POST_PATH_TEMPLATE.format(search_id=search_id)),
            method="POST",
            data=payload,
            headers=self.AJAX_HEADERS,
        )
        time.sleep(self.REQUEST_DELAY_S)

        # 2) GET the results HTML, page by page.
        events: list[Event] = []
        seen: set[str] = set()
        page = 1
        while True:
            cap = self.capture(
                urljoin(self._base_url,
                        self.RESULTS_PATH_TEMPLATE.format(search_id=search_id)),
                headers=self.AJAX_HEADERS,
                params={"page": page, "_": int(time.time() * 1000)},
            )
            rows, total = self._parse_results(cap)
            added = 0
            for ev in rows:
                key = ev.document_number or (
                    f"{ev.recording_date}|{ev.grantor_raw}|{ev.grantee_raw}"
                )
                if key in seen:
                    continue
                seen.add(key)
                events.append(ev)
                added += 1
            if total is not None and len(events) >= total:
                break
            if added == 0:
                break
            if page >= self.PAGE_CEILING:
                self.gate(False,
                          f"pagination hit PAGE_CEILING={self.PAGE_CEILING} for "
                          f"{search_id} — either raise the ceiling deliberately "
                          f"or narrow the query")
            page += 1
            time.sleep(self.REQUEST_DELAY_S)
        return events

    # ---- parsing (Tyler self-service HTML, confirmed identical across
    #                Tehama / Shasta / Butte) ---------------------------- #
    def _parse_results(self, cap: Captured) -> tuple[list[Event], Optional[int]]:
        soup = BeautifulSoup(cap.text, "html.parser")
        rows = soup.select(self.RESULTS_ROW_SELECTOR)
        total_match = self.TOTAL_RESULTS_RE.search(cap.text)
        total = int(total_match.group(1)) if total_match else None

        if not rows:
            page_text = soup.get_text(" ", strip=True).lower()
            if total == 0 or self.NO_RESULTS_MARKER in page_text:
                return [], total
            # Fail loud instead of silently returning empty — signals a
            # structural break (disclaimer flip lost, portal template changed).
            self.gate(False,
                      "results container found no ss-search-row and no "
                      "'no results' marker — portal structure may have changed")
        events = [self._row_to_event(r, cap) for r in rows]
        return events, total

    def _row_to_event(self, row, cap: Captured) -> Event:
        # <h1> carries doc_number • book_page • doc_type (bullet-separated).
        # Positional split, not regex — handles both modern (2024R006490)
        # and legacy (013042) formats. See tyler_recorder_client note on
        # Tehama's book/page-era 013042 bug.
        header = row.select_one(self.HEADER_SELECTOR)
        header_text = header.get_text(" ", strip=True) if header else ""
        segments = [s.strip() for s in header_text.split(self.BULLET) if s.strip()]
        doc_number = segments[0] if segments else ""
        doc_type_label = segments[-1] if len(segments) > 1 else ""
        book_page = segments[1] if len(segments) > 2 else ""

        # Fresno's rows have no bullet-separated type; doc-type is the
        # avatar letter (ss-facet-avatar-T). Handled here so this adapter
        # keeps working when the same class serves Fresno.
        if not doc_type_label:
            avatar = row.select_one("div.ss-facet-avatar")
            if avatar:
                doc_type_label = avatar.get_text(strip=True)

        date_el = row.select_one(self.DATE_SELECTOR)
        recording_date_raw = date_el.get_text(strip=True) if date_el else ""

        grantors: list[str] = []
        grantees: list[str] = []
        for col in row.select(self.COLUMN_SELECTOR):
            label_el = col.select_one("li:first-child")
            label = label_el.get_text(strip=True).lower() if label_el else ""
            names = [
                li.get_text(strip=True)
                for li in col.select("li")[1:]
                if li.get_text(strip=True)
            ]
            if "grantor" in label:
                grantors = names
            elif "grantee" in label:
                grantees = names

        event_type = self.norm.event_type(doc_type_label) if doc_type_label else EventType.UNKNOWN

        ev = Event(
            county=self.county,
            source_url=cap.raw.source_url,
            source_file=cap.raw.file_path,
            raw_fetch_id=cap.raw.id,
            parser_version=self.parser_version,
            event_type=event_type,
            document_number=doc_number or None,
            grantor_raw="; ".join(grantors) if grantors else None,   # FROM — exit signal
            grantee_raw="; ".join(grantees) if grantees else None,   # TO — acquisition
            recording_date=self._iso_date(recording_date_raw),
        )

        if event_type is EventType.UNKNOWN and doc_type_label:
            ev.gap(f"unmapped_doc_type:{doc_type_label}")
        if not doc_number:
            ev.gap("missing_document_number")
        if book_page:
            ev.gap(f"book_page:{book_page}")
        return ev

    @staticmethod
    def _iso_date(value: str) -> Optional[str]:
        value = (value or "").strip()
        if not value:
            return None
        try:
            return dtparse.parse(value).date().isoformat()
        except (ValueError, OverflowError, TypeError):
            return None

    # ---- ABC surface ------------------------------------------------- #
    def search_by_apn(self, apn: str) -> Sequence[Event]:
        """APN search — supported on Fresno (DOCSEARCH377S5) but not Tehama.
        The apn_search_id from CountyConfig.params gates whether this works.
        If unsupported for this county, raise loudly — never fake results."""
        sid = self._apn_search_id
        self.gate(bool(sid),
                  f"APN search not supported for county={self.county} "
                  f"(no apn_search_id configured)")
        payload = {
            self.F_APN: apn,
            self.F_DOC_TYPES_CONTAINS: "Contains Any",
            self.F_DOC_TYPES: "",
        }
        return self._submit_and_page(sid, payload)

    def search_by_name(self, name: str) -> Sequence[Event]:
        payload = {
            self.F_NAME_INPUT: name,
            self.F_NAME_CONTAINS: "Contains Any",
            self.F_NAME_HIDDEN: "",
            self.F_DATE_START: "",
            self.F_DATE_END: "",
            self.F_USE_ADVANCED: "",
        }
        return self._submit_and_page(self._name_search_id, payload)

    def search_by_date_range(
        self,
        start: str,
        end: str,
        doc_types: Optional[Sequence[EventType]] = None,
    ) -> Sequence[Event]:
        # Tyler self-service does date+doc-type through the name-search page
        # (name field empty) — confirmed via the field composition in
        # onboard_county.discover_search_ids (typedate_search_id detection).
        payload = {
            self.F_NAME_INPUT: "",
            self.F_NAME_CONTAINS: "Contains Any",
            self.F_NAME_HIDDEN: "",
            self.F_DATE_START: start,
            self.F_DATE_END: end,
            self.F_USE_ADVANCED: "",
        }
        if doc_types:
            payload[self.F_DOC_TYPES] = ",".join(dt.value for dt in doc_types)
        return self._submit_and_page(self._name_search_id, payload)

    def search_by_document_number(self, doc_number: str) -> Sequence[Event]:
        # Convenience: doc-number lookup is the single most useful path
        # (used heavily by stage4 enrichment). Not on the ABC — an extra
        # method that power-callers can use if they have the doc number.
        transformed = _apply_doc_transform(doc_number, self._doc_transform)
        payload = {
            self._doc_field_name: transformed,
            self.F_BOOK_VOLUME: "",
            self.F_BOOK_PAGE: "",
        }
        return self._submit_and_page(self._doc_search_id, payload)
