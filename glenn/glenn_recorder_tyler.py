"""
glenn_recorder_tyler.py — real, live-verified Tyler EagleWeb recorder access
for Glenn County, confirmed working 2026-08-08.

Platform: https://glenncountyca-web.tylerhost.net (Tyler Self-Service).

CONFIRMED LIVE, NOT BLOCKED (2026-08-08): a bare GET + POST to
/web/user/disclaimer (empty body, no click/JS/human solve) flips
server-side disclaimer acceptance and reaches the real search form
(DOCSEARCH615S2, fields field_DocNumID / field_selfservice_documentTypes /
field_UseAdvancedSearch — matches counties/glenn.yaml's doc_search_id and
doc_field notes).

IMPORTANT CAVEAT: Glenn's disclaimer page DOES contain a `g-recaptcha`
marker in its raw HTML (unlike Del Norte's, which has none at all) — but
empirically the plain GET+POST bypass still works and reaches the real
search form without ever solving that widget. This is different from
Tehama, where the same GET+POST never sets disclaimerAccepted. Whether
Glenn's recaptcha widget gates some OTHER action (e.g. actually submitting
a search, as opposed to just the disclaimer) was not fully stress-tested
here because no real parcel/document-number source was found to test
against (see module-level note below) — flag this as WORTH RE-CHECKING
before relying on this for a real batch run.

REAL BLOCKER FOUND FOR GLENN (this is why zero dossiers were produced for
this county): the county's own primary source for auction/tax-defaulted
data, countyofglenn.net (Property Tax Auctions page, Tax Sale FAQ PDF,
excess-proceeds claim form PDF), is behind Cloudflare bot-challenge
protection ("Just a moment..." interstitial) that blocked every fetch
attempt (both a direct httpx/curl GET and the coordinator's own WebFetch
tool, both got HTTP 403 or the raw challenge page). Bid4Assets
(bid4assets.com/glenn, bid4assets.com/storefront/GlennMarch18) is also
bot-protected and returned 403 to WebFetch. Web search results reference a
GovEase portal (govease.com/caglenn) and an October 29-31 sale tied to
"Glenn Tax Sale 18" — but the only supporting evidence found dates that
sale to October 2025, not 2026, and no 2026 sale number/date could be
independently confirmed. Per the "verified-or-excluded" rule, this counts
as NOT FOUND, not as evidence the 2026 sale is on the same October dates.

data/counties/glenn/roll.csv (39 APNs) is NOT a tax-defaulted or auction
list — it's a generic situs-seed discovery sample (core/assessor.py's
_pull_mpts(), searching "1 Main"/"2 Main"/"1 Oak"/etc.), unrelated to
delinquency status. Do not treat it as auction inventory.

Net result: recorder infrastructure works for Glenn, but there is currently
no verified real parcel-level source (auction list OR post-auction sales/
excess-proceeds report) to feed it. This module is left in a working,
reusable state for whenever a real source is found.
"""
from __future__ import annotations

import re
import time
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://glenncountyca-web.tylerhost.net"
DOC_SEARCH_ID = "DOCSEARCH615S2"  # per counties/glenn.yaml, confirmed live 2026-08-08
DOC_FIELD = "field_DocNumID"      # per counties/glenn.yaml

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


def _apply_doc_transform(doc_number: str) -> str:
    """Per counties/glenn.yaml: doc_number_transform 'r_to_hyphen_raw',
    confirmed live in a prior session (e.g. 2022R2373 -> 2022-2373). Not
    re-verified against a real document this session (no real doc number
    was available — see module docstring)."""
    return re.sub(r"(?<=\d{4})R(?=\d+$)", "-", doc_number)


def _new_session() -> httpx.Client:
    s = httpx.Client(follow_redirects=True, timeout=25, headers={"User-Agent": UA})
    s.get(f"{BASE_URL}/web/user/disclaimer")
    time.sleep(REQUEST_DELAY_S)
    s.post(f"{BASE_URL}/web/user/disclaimer", data={})
    time.sleep(REQUEST_DELAY_S)
    s.get(f"{BASE_URL}/web/search/{DOC_SEARCH_ID}")
    time.sleep(REQUEST_DELAY_S)
    return s


def search_by_document_number(doc_number: str) -> str:
    """Returns the raw results HTML — parsing not finalized since no real
    doc number was available to validate the row structure against."""
    s = _new_session()
    payload = {
        DOC_FIELD: _apply_doc_transform(doc_number),
        "field_BookPageID_DOT_Volume": "",
        "field_BookPageID_DOT_Page": "",
    }
    s.post(f"{BASE_URL}/web/searchPost/{DOC_SEARCH_ID}", data=payload, headers=AJAX_HEADERS)
    time.sleep(REQUEST_DELAY_S)
    r = s.get(f"{BASE_URL}/web/searchResults/{DOC_SEARCH_ID}", headers=AJAX_HEADERS,
              params={"page": 1, "_": int(time.time() * 1000)})
    return r.text


def get_assessor_record(apn_dash: str) -> Optional[dict]:
    """Real MPTS AsrPrint pull — common1.mptsweb.com/mbap/glenn/asr,
    confirmed live 2026-08-08 with real APNs (not just the base path)."""
    apn12 = re.sub(r"\D", "", apn_dash).zfill(12)
    url = f"https://common1.mptsweb.com/mbap/glenn/asr/AsrPrint/{apn12}"
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
    # Live smoke test of the assessor half only — confirmed real 2026-08-08.
    # (Recorder half is untestable without a real document number; the
    # county's own auction/sales-report source could not be reached — see
    # module docstring.)
    for apn in ["020-350-011-000", "032-142-009-000", "041-281-038-000"]:
        rec = get_assessor_record(apn)
        print(apn, "->", rec)
