"""
del_norte_recorder_tyler.py — real, live-verified Tyler EagleWeb recorder
access for Del Norte County, confirmed working 2026-08-08.

Platform: https://delnortecountyca-web.tylerhost.net (Tyler Self-Service,
version 2022.4.3 per the site's JS asset query strings).

CONFIRMED LIVE, NO CAPTCHA WALL (2026-08-08): a bare GET + POST to
/web/user/disclaimer (empty body — no click/JS/human solve required) is
enough to flip server-side disclaimer acceptance and reach the real search
forms. No grecaptcha/g-recaptcha marker was even present on Del Norte's
disclaimer page (confirmed by scanning the raw HTML for recaptcha strings).
This is meaningfully different from Tehama, where the same GET+POST flow
never sets disclaimerAccepted because a real Google reCAPTCHA challenge
gates it — Del Norte has no such wall.

Discovery: onboard_county.py's yaml (counties/del_norte.yaml) had only ONE
search id (DOCSEARCH201S11) on file, described there as usable for BOTH
name and doc-number search. Live testing found that ID is actually scoped
to a narrow "Registration Search" index (near-empty results for real
grantor/grantee/doc-number queries that are known-good from other sources).
Probing DOCSEARCH201S1 through S15 directly (GET /web/search/{id}, no auth
beyond the disclaimer cookie) found DOCSEARCH201S8 is the real Official
Records / Advanced Search form — it has field_GrantorID, field_GranteeID,
field_DocumentNumberID, field_BookPageID, and field_RecordingDateID_DOT_*.
That is the one that returns real results. counties/del_norte.yaml has NOT
been edited (out of scope for this agent) — flagging this here for whoever
next builds against it.

Document number index format: assessor AsrPrint shows e.g. "2026R1355";
the recorder's internal index strips the "R" -> "20261355". Confirmed by
cross-matching all 11 real May 2026 tax-deed document numbers.

Flow (mirrors tehama_recorder_tyler.py's Tyler wire pattern):
  1. GET  /web/user/disclaimer
  2. POST /web/user/disclaimer  (empty body)
  3. GET  /web/search/DOCSEARCH201S8   (primes server-side view-state)
  4. POST /web/searchPost/DOCSEARCH201S8  (AJAX headers required)
  5. GET  /web/searchResults/DOCSEARCH201S8?page=N&_=ts  (AJAX headers required)

Every call in this module is a plain httpx request — no browser, no
stealth patching, no CAPTCHA solve of any kind needed for this county.
"""
from __future__ import annotations

import re
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://delnortecountyca-web.tylerhost.net"
ADVANCED_SEARCH_ID = "DOCSEARCH201S8"  # Grantor/Grantee/DocNumber/BookPage — the real one
REGISTRATION_SEARCH_ID = "DOCSEARCH201S11"  # per yaml; confirmed near-empty in practice, kept for reference

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
AJAX_HEADERS = {
    "ajaxrequest": "true",
    "x-requested-with": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}
REQUEST_DELAY_S = 0.3


def _new_session() -> httpx.Client:
    s = httpx.Client(follow_redirects=True, timeout=25, headers={"User-Agent": UA})
    s.get(f"{BASE_URL}/web/user/disclaimer")
    time.sleep(REQUEST_DELAY_S)
    s.post(f"{BASE_URL}/web/user/disclaimer", data={})
    time.sleep(REQUEST_DELAY_S)
    s.get(f"{BASE_URL}/web/search/{ADVANCED_SEARCH_ID}")
    time.sleep(REQUEST_DELAY_S)
    return s


def _apply_doc_transform(doc_number: str) -> str:
    """Assessor shows e.g. '2026R1355'; recorder index wants '20261355'."""
    return doc_number.replace("R", "")


def _parse_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for row in soup.select("li.ss-search-row"):
        header = row.select_one("h1")
        header_text = header.get_text(" ", strip=True) if header else ""
        segs = [x.strip() for x in header_text.split("•") if x.strip()]
        doc_number = segs[0] if segs else ""
        doc_type = segs[-1] if len(segs) > 1 else ""
        grantors, grantees = [], []
        for col in row.select("div.searchResultThreeColumn"):
            label_el = col.select_one("li:first-child")
            label = label_el.get_text(strip=True).lower() if label_el else ""
            names = [li.get_text(strip=True) for li in col.select("li")[1:] if li.get_text(strip=True)]
            if "grantor" in label:
                grantors = names
            elif "grantee" in label:
                grantees = names
        date_el = row.select_one("li.selfServiceSearchResultCollapsed")
        rows.append({
            "doc_number": doc_number,
            "doc_type": doc_type,
            "recording_date": date_el.get_text(strip=True) if date_el else "",
            "grantors": grantors,
            "grantees": grantees,
        })
    return rows


def search_by_document_number(doc_number: str) -> list[dict]:
    """Real doc-number search. doc_number should be in assessor form
    (e.g. '2026R1355') — the R-strip transform is applied here."""
    s = _new_session()
    payload = {
        "field_DocumentNumberID": _apply_doc_transform(doc_number),
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
    s.post(f"{BASE_URL}/web/searchPost/{ADVANCED_SEARCH_ID}", data=payload, headers=AJAX_HEADERS)
    time.sleep(REQUEST_DELAY_S)
    r = s.get(f"{BASE_URL}/web/searchResults/{ADVANCED_SEARCH_ID}", headers=AJAX_HEADERS,
              params={"page": 1, "_": int(time.time() * 1000)})
    return _parse_rows(r.text)


def search_by_recording_date(start_mmddyyyy: str, end_mmddyyyy: str) -> list[dict]:
    """Real date-range search — this is how the 2026-05-15 auction's 11 real
    tax deeds (recorded 2026-05-27) were confirmed for this agent's report."""
    s = _new_session()
    payload = {
        "field_DocumentNumberID": "",
        "field_BookPageID_DOT_Volume": "",
        "field_BookPageID_DOT_Page": "",
        "field_RecordingDateID_DOT_StartDate": start_mmddyyyy,
        "field_RecordingDateID_DOT_EndDate": end_mmddyyyy,
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
    s.post(f"{BASE_URL}/web/searchPost/{ADVANCED_SEARCH_ID}", data=payload, headers=AJAX_HEADERS)
    time.sleep(REQUEST_DELAY_S)
    r = s.get(f"{BASE_URL}/web/searchResults/{ADVANCED_SEARCH_ID}", headers=AJAX_HEADERS,
              params={"page": 1, "_": int(time.time() * 1000)})
    return _parse_rows(r.text)


def get_assessor_record(apn_dash: str) -> Optional[dict]:
    """Real MPTS AsrPrint pull — common1.mptsweb.com/mbap/delnorte/asr,
    confirmed live 2026-08-08 with real APNs (not just the base path)."""
    apn12 = re.sub(r"\D", "", apn_dash).zfill(12)
    url = f"https://common1.mptsweb.com/mbap/delnorte/asr/AsrPrint/{apn12}"
    r = httpx.get(url, headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
    if r.status_code != 200:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    text = re.sub(r"\|+", "|", soup.get_text("|", strip=True))
    parts = text.split("|")
    labels = [
        "Current Document Number", "Current Document  Date", "SitusAddr",
        "Property Type", "Asmt Status", "Net Assessed Value",
    ]
    data = {"apn_dash": apn_dash, "apn12": apn12, "source_url": url}
    for i, p in enumerate(parts):
        if p in labels and i + 1 < len(parts):
            data[p] = parts[i + 1]
    return data


if __name__ == "__main__":
    # Live smoke test — confirmed real 2026-08-08.
    recs = search_by_recording_date("05/27/2026", "05/27/2026")
    print(f"{len(recs)} real recorded documents found for 2026-05-27:")
    for r in recs:
        print(f"  {r['doc_number']} | {r['doc_type']} | grantor={r['grantors']} | grantee={r['grantees']}")
