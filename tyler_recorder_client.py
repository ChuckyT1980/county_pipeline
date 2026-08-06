"""
tyler_recorder_client.py

Shared HTTP client for Tyler Technologies "Self-Service Web" recorder
portals. Confirmed identical HTML/flow shape across three counties so far:

  Tehama  — recordsearch.tehama.gov         (search id DOCSEARCH4S1/S2; S3 =
            document-type + recording-date search, NOT doc numbers)
  Shasta  — recorderselfservice.shastacounty.gov (search id DOCSEARCH344S4/S5)
  Butte   — recorder.buttecounty.net        (search id DOCSEARCH481S1/S2)

All three share:
  - /web/user/disclaimer entry point (session cookie set on GET, no accept-
    click needed on any of the three, confirmed by testing each directly)
  - /web/searchPost/{search_id} POST to submit a search
  - /web/searchResults/{search_id}?page=N GET to page through results
  - identical result HTML: <li class="ss-search-row"> rows, <h1> with a
    bullet-separated doc number / book-page / doc type, and
    <div class="searchResultThreeColumn"> blocks for Recording Date /
    Grantor / Grantee

Per-county differences are config, not code:
  - base_url
  - name_search_id / doc_search_id (the two DOCSEARCH{id}S{n} strings)
  - doc number format transform (Tehama: none: Shasta/Butte: R -> hyphen)
  - whether ajaxrequest/x-requested-with headers are required on POST
    (confirmed required for Tehama and Shasta; CONFIRM for Butte before
    trusting a full run — see note in ajax_headers_required below)

Usage:
    from tyler_recorder_client import TylerRecorderClient, CountyConfig

    BUTTE = CountyConfig(
        county="butte",
        base_url="https://recorder.buttecounty.net",
        name_search_id="DOCSEARCH481S1",
        doc_search_id="DOCSEARCH481S2",
        ajax_headers_required=True,  # CONFIRM via DevTools before trusting
    )

    client = TylerRecorderClient(BUTTE)
    client.submit_doc_search("2024-0030607")
    results, total = client.get_results(search_type="doc")
"""

import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

DOC_NUMBER_SHAPE_RE = re.compile(r"^[\dR\-]+$")


@dataclass
class CountyConfig:
    county: str
    base_url: str
    name_search_id: str          # e.g. "DOCSEARCH4S1" / "DOCSEARCH344S4" / "DOCSEARCH481S1"
    doc_search_id: str           # e.g. "DOCSEARCH4S2" / "DOCSEARCH344S5" / "DOCSEARCH481S2"
    apn_search_id: str = ""      # e.g. Fresno "DOCSEARCH377S5" (empty = APN search unsupported)
    ajax_headers_required: bool = True   # confirmed True for Tehama & Shasta; CONFIRM per county
    doc_number_transform: Optional[str] = None   # "r_to_hyphen" or None
    doc_field_name: str = "field_DocumentNumberID"  # Glenn: "field_DocNumID"


@dataclass
class RecorderResult:
    doc_id: str
    doc_number: str
    doc_type: str
    recording_date: str
    grantors: list[str]
    grantees: list[str]
    book_page: str = ""


def apply_doc_transform(doc_number: str, transform: Optional[str]) -> str:
    """
    CONFIRMED BUG, FIXED 7/13: the original pattern required exactly 6-7
    digits after the R (matching modern doc numbers like 2024R0030607),
    but real Butte data includes legacy pre-2000s doc numbers with shorter
    sequences — confirmed live: 1998R45023 (only 5 digits after R). The
    old pattern silently failed to match on these, passing the string
    through UNCHANGED (still containing "R"), which would break the
    recorder search for every legacy-era document. Loosened to accept any
    digit count after R, same lesson as Tehama's book/page-era doc number
    bug (013042) — don't hardcode a digit-count assumption when older
    records may use a shorter or differently-shaped format.
    """
    if transform == "r_to_hyphen":
        match = re.search(r"^(\d{4})R(\d+)$", doc_number)
        if match:
            year, num = match.groups()
            return f"{year}-{num.zfill(7)}"
        return re.sub(r"(?<=\d{4})R(?=\d+$)", "-", doc_number)
    if transform == "r_to_hyphen_6":
        # Humboldt: recorder indexes R-docs zero-padded to 6 digits
        # (2023R05135 -> 2023-005135, 1998R129 -> 1998-000129).
        # Confirmed live: DOCSEARCH201S7 doc search, modern + legacy.
        match = re.search(r"^(\d{4})R(\d+)$", doc_number)
        if match:
            year, num = match.groups()
            return f"{year}-{num.zfill(6)}"
        return re.sub(r"(?<=\d{4})R(?=\d+$)", "-", doc_number)
    if transform == "r_to_hyphen_raw":
        # Glenn: recorder indexes R-docs with the R replaced by a hyphen,
        # NO zero padding (2022R2373 -> 2022-2373). Confirmed live.
        return re.sub(r"(?<=\d{4})R(?=\d+$)", "-", doc_number)
    if transform == "r_to_strip":
        # Tehama: recorder indexes modern doc numbers with the R removed
        # (2018R007697 -> 2018007697). Confirmed by the existing
        # stage2_recorder_enrich format_doc_number for Tehama.
        return doc_number.replace("R", "")
    return doc_number


class TylerRecorderClient:
    def __init__(self, config: CountyConfig, timeout: float = 15.0, delay_between_requests: float = 0.5):
        self.config = config

        # NOTE 7/13: ajaxrequest/x-requested-with are NOT set globally here
        # anymore. They were originally applied to every request via the
        # client's default headers, but a real browser only ever sends
        # them on actual XHR calls — never on plain page navigations
        # (disclaimer page load, search page load). Sending them on those
        # page GETs too may be why Butte's search POST started returning
        # an empty <title></title> shell instead of real content: the
        # server likely treats a GET carrying x-requested-with as an AJAX
        # fragment request and skips setting up the full view-state the
        # subsequent POST depends on. Headers are now added per-request via
        # self._ajax_headers(), only on the calls that are genuinely AJAX
        # in the real browser (searchPost, searchResults).
        self.client = httpx.Client(
            base_url=config.base_url,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            },
            follow_redirects=True,
        )
        self.delay = delay_between_requests
        self._session_ready = False

    def _ajax_headers(self) -> dict:
        """Headers to add ONLY on genuine AJAX calls (searchPost,
        searchResults) — not on page-navigation GETs. See __init__ note."""
        if self.config.ajax_headers_required:
            return {
                "ajaxrequest": "true",
                "x-requested-with": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }
        return {}

    def _init_session(self):
        """CORRECTED 7/13: originally assumed a plain GET to
        /web/user/disclaimer was universally sufficient (true for Tehama
        and Shasta as tested), but Butte's real flow uses a POST to that
        same URL — confirmed live via DevTools: a background XHR named
        'disclaimer', method POST, fires automatically from the homepage
        on load (jQuery-driven, no visible button or click needed). A GET
        alone returns the page HTML but never flips the server-side
        acceptance state, which is why every subsequent request was
        silently redirecting back to the disclaimer page (confirmed via
        the Final URL diagnostic).

        Doing a GET-then-POST here covers both known cases: Tehama/Shasta
        tolerate the GET and don't need the POST (untested whether the
        POST would break them — worth checking), while Butte needs the
        POST specifically. This POST is treated as a plain navigation, NOT
        an AJAX call, matching the real browser (no ajaxrequest header was
        needed to reproduce this — confirmed by Butte's working manual
        browser flow, which never sends that header on this step either).
        """
        resp = self.client.get("/web/user/disclaimer")
        resp.raise_for_status()
        time.sleep(self.delay)

        resp = self.client.post("/web/user/disclaimer")
        resp.raise_for_status()
        time.sleep(self.delay)

        self._session_ready = True

    def _visit_search_page(self, search_id: str):
        """CONFIRMED MISSING STEP as of 7/13 Butte debugging: the real
        browser flow always GETs /web/search/{search_id} (the actual
        search form page) before any searchPost fires — we replicated the
        POST and the results GET, but never this intermediate page visit.
        This mirrors the same bug already found and fixed on Butte's TAX
        site (a bare GET without visiting the search page first returned
        the generic template). Treated as a plain page navigation — no
        ajax headers here, matching the real browser."""
        resp = self.client.get(f"/web/search/{search_id}")
        resp.raise_for_status()
        time.sleep(self.delay)

    def submit_name_search(self, name: str, contains_mode: str = "Contains Any"):
        """Submits a name search — confirmed field names from Tehama capture.
        CONFIRM field names match for Shasta/Butte before relying on this;
        only doc-number search has been confirmed for Butte so far."""
        if not self._session_ready:
            self._init_session()

        self._visit_search_page(self.config.name_search_id)

        payload = {
            "field_BothNamesID-searchInput": name,
            "field_BothNamesID-containsInput": contains_mode,
            "field_BothNamesID": "",
            "field_RecordingDateID_DOT_StartDate": "",
            "field_RecordingDateID_DOT_EndDate": "",
            "field_UseAdvancedSearch": "",
        }
        resp = self.client.post(
            f"/web/searchPost/{self.config.name_search_id}",
            data=payload,
            headers=self._ajax_headers(),
        )
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def submit_apn_search(self, apn: str):
        """Submits an Assessor Parcel Number search. Confirmed live for
        Fresno (7/31): field_ParcelID takes the RAW parcel number with NO
        dashes (e.g. 09010115, 08018018S) — dashed forms (090-101-15) are
        accepted by the form but return zero results. The document-type
        contains-input field must be present (the real browser sends
        'Contains Any'); it is NOT a plain search on the parcel field
        alone. Full AJAX headers (accept / referer / content-type) were
        required: without them the results GET returns HTTP 500 with a
        server error GUID."""
        if not self._session_ready:
            self._init_session()

        self._visit_search_page(self.config.apn_search_id)

        payload = {
            "field_ParcelID": apn,
            "field_selfservice_documentTypes-containsInput": "Contains Any",
            "field_selfservice_documentTypes": "",
        }
        resp = self.client.post(
            f"/web/searchPost/{self.config.apn_search_id}",
            data=payload,
            headers=self._ajax_headers(),
        )
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def submit_doc_search(self, doc_number: str):
        """Submits a document-number search. Confirmed field name from
        Shasta capture: field_DocumentNumberID. Endpoint/headers/payload
        all confirmed live for Butte via DevTools (2024-0030607 ->
        SAUTTER/HANSON DEED, 1 result) — but that was a real browser flow
        which visited /web/search/{search_id} first. This client never
        replicated that visit until now, which is the likely reason a
        prior test run returned Total results: 0 despite every other
        piece being individually confirmed correct."""
        if not self._session_ready:
            self._init_session()

        self._visit_search_page(self.config.doc_search_id)

        transformed = apply_doc_transform(doc_number, self.config.doc_number_transform)

        # field name differs across Tyler installs: Tehama/Shasta/Butte use
        # field_DocumentNumberID; Glenn uses field_DocNumID. Config carries
        # the discovered name per county.
        payload = {
            self.config.doc_field_name: transformed,
            "field_BookPageID_DOT_Volume": "",
            "field_BookPageID_DOT_Page": "",
        }
        resp = self.client.post(
            f"/web/searchPost/{self.config.doc_search_id}",
            data=payload,
            headers=self._ajax_headers(),
        )
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def get_results(self, page: int = 1, search_type: str = "doc") -> tuple[list[RecorderResult], int]:
        """search_type is 'name', 'doc', or 'apn' — selects which search_id's
        result set to page through, matching whichever submit_*_search you
        called."""
        if not self._session_ready:
            self._init_session()

        if search_type == "apn":
            search_id = self.config.apn_search_id
        else:
            search_id = self.config.doc_search_id if search_type == "doc" else self.config.name_search_id

        resp = self.client.get(
            f"/web/searchResults/{search_id}",
            headers=self._ajax_headers(),
            params={"page": page, "_": int(time.time() * 1000)},
        )
        resp.raise_for_status()
        time.sleep(self.delay)

        return self._parse_results_html(resp.text)

    def _parse_results_html(self, html: str) -> tuple[list[RecorderResult], int]:
        """Confirmed identical structure across Tehama, Shasta, and Butte:
        li.ss-search-row rows, bullet-separated <h1>, searchResultThreeColumn
        blocks. Positional bullet-split (not format-specific regex) handles
        both modern and legacy doc-number formats — see Tehama's 013042 bug."""
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("li.ss-search-row")

        results = []
        for row in rows:
            doc_id = row.get("data-documentid", "")

            header = row.select_one("h1")
            header_text = header.get_text(" ", strip=True) if header else ""

            segments = [s.strip() for s in header_text.split("\u2022") if s.strip()]
            doc_number = segments[0] if segments else ""
            doc_type = segments[-1] if len(segments) > 1 else ""
            book_page = segments[1] if len(segments) > 2 else ""

            # Fresno's rows have no bullet-separated type in the <h1>; the
            # doc-type indicator is the avatar letter (ss-facet-avatar-T).
            if not doc_type:
                avatar = row.select_one("div.ss-facet-avatar")
                if avatar:
                    doc_type = avatar.get_text(strip=True)

            date_el = row.select_one("li.selfServiceSearchResultCollapsed")
            recording_date = date_el.get_text(strip=True) if date_el else ""

            grantors, grantees = [], []
            columns = row.select("div.searchResultThreeColumn")
            for col in columns:
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

            results.append(
                RecorderResult(
                    doc_id=doc_id,
                    doc_number=doc_number,
                    doc_type=doc_type,
                    recording_date=recording_date,
                    grantors=grantors,
                    grantees=grantees,
                    book_page=book_page,
                )
            )

        total_match = re.search(r"for\s+(\d+)\s+Total Results", html)
        total_results = int(total_match.group(1)) if total_match else len(results)

        return results, total_results

    def close(self):
        self.client.close()


# -----------------------------------------------------------------------------
# Confirmed county configs
# -----------------------------------------------------------------------------

TEHAMA = CountyConfig(
    county="tehama",
    base_url="https://recordsearch.tehama.gov",
    name_search_id="DOCSEARCH4S1",
    doc_search_id="DOCSEARCH4S2",
    ajax_headers_required=True,   # confirmed required
    # r_to_strip confirmed live 8/1: the recorder indexes modern doc
    # numbers with the R removed (2026R006490 -> 2026006490, DEED with
    # grantor/grantee names). Legacy pre-2004 numbers (2000R1926129)
    # are NOT indexed this way — they return 0. Matches counties/tehama.yaml.
    doc_number_transform="r_to_strip",
)

SHASTA = CountyConfig(
    county="shasta",
    base_url="https://recorderselfservice.shastacounty.gov",
    name_search_id="DOCSEARCH344S4",
    doc_search_id="DOCSEARCH344S5",
    ajax_headers_required=True,   # confirmed required
    doc_number_transform="r_to_hyphen",
)

BUTTE = CountyConfig(
    county="butte",
    base_url="https://recorder.buttecounty.net",
    name_search_id="DOCSEARCH481S1",
    doc_search_id="DOCSEARCH481S2",
    ajax_headers_required=True,   # confirmed present in DevTools capture
    doc_number_transform="r_to_hyphen",   # confirmed: 2024R0030607 -> 2024-0030607
)

FRESNO = CountyConfig(
    county="fresno",
    base_url="https://fresnocountyca-web.tylerhost.net",
    name_search_id="DOCSEARCH377S1",
    doc_search_id="DOCSEARCH377S2",
    apn_search_id="DOCSEARCH377S5",
    ajax_headers_required=True,   # confirmed required: searchResults 500 without them
    doc_number_transform=None,    # confirmed: 2023-0013662 format needs no transform
)


if __name__ == "__main__":
    # Ground-truth smoke test for Butte, using the confirmed live case.
    client = TylerRecorderClient(BUTTE)
    try:
        client.submit_doc_search("2024R0030607")  # raw R-format as it appears on the tax site
        results, total = client.get_results(search_type="doc")
        print(f"Total results: {total}")
        for r in results:
            print(r.doc_number, r.doc_type, r.recording_date, r.grantors, r.grantees)
    finally:
        client.close()
