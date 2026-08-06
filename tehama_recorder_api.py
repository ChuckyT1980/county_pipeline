"""
tehama_recorder_api.py

Direct HTTP client for the Tehama County recorder self-service portal,
replacing full-browser Playwright automation for the search+results flow.

Confirmed from DevTools (7/12):
  - Session tracked via JSESSIONID cookie, persists across all 3 steps below.
  - Step 2 (name suggest) and step 4 (results) are plain HTTP endpoints —
    no browser rendering required, httpx/requests can hit them directly.

CONFIRMED 7/13 — Tehama gates fresh sessions behind Google reCAPTCHA:
  A bare GET to /web/user/disclaimer gets a 200 and a JSESSIONID, but never
  gets disclaimerAccepted — because satisfying the reCAPTCHA challenge
  requires executing real JS and passing Google's checkHuman verification,
  which a plain HTTP client cannot do and which this client will NOT
  attempt to automate or bypass — reCAPTCHA is a deliberate anti-bot
  control, not an incidental implementation detail like the other portals'
  disclaimer cookies.

  This means Tehama is structurally different from Shasta/Butte: it needs
  a HUMAN to solve the CAPTCHA once, per session, in a real browser. This
  client is built around that: pass in the JSESSIONID + disclaimerAccepted
  cookie values captured from a real browser after a human has solved the
  challenge, and everything downstream (search, results, parsing) runs
  automated via httpx same as before — no further CAPTCHA interaction
  needed until that session eventually expires.

  To get fresh cookies: visit https://recordsearch.tehama.gov/web/user/disclaimer
  in a real (ideally incognito, to force a fresh challenge) browser, solve
  the CAPTCHA, click Accept, then in DevTools Network tab click any request
  to recordsearch.tehama.gov -> Headers -> Request Headers -> copy the
  full Cookie: line.

  UNKNOWN, worth monitoring in production: how long this session lasts
  before expiring and requiring a fresh human solve. Track this empirically
  — if a batch run starts getting empty results partway through (which the
  IntegrityGate's hit_rate check will catch), that's very likely session
  expiry, not a code bug. At that point a human needs to solve the CAPTCHA
  again and supply fresh cookies via update_session_cookies().
"""

import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://recordsearch.tehama.gov"
DOC_NUMBER_RE = re.compile(r"\d{4}[A-Za-z\-]?\d{6,7}")


@dataclass
class RecorderResult:
    doc_id: str            # internal id, e.g. DOCCLNDO0017379
    doc_number: str        # e.g. 2013006445, or legacy format like 013042
    doc_type: str           # e.g. DEED
    recording_date: str
    grantors: list[str]
    grantees: list[str]
    book_page: str = ""    # e.g. "B: 2725 P: 0534" — only present on legacy-era docs


class TehamaRecorderClient:
    def __init__(
        self,
        jsessionid: str,
        disclaimer_accepted: str = "true",
        timeout: float = 15.0,
        delay_between_requests: float = 0.5,
    ):
        """
        jsessionid and disclaimer_accepted MUST come from a real browser
        session where a human has already solved the reCAPTCHA challenge —
        see module docstring for how to capture them. This client cannot
        establish a session on its own anymore.
        """
        self.client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            },
            follow_redirects=True,
        )
        self.delay = delay_between_requests
        self.update_session_cookies(jsessionid, disclaimer_accepted)

    def update_session_cookies(self, jsessionid: str, disclaimer_accepted: str = "true"):
        """Call this again with a fresh JSESSIONID whenever the current
        session expires (a human will need to re-solve the CAPTCHA in a
        real browser first — this client has no way to detect expiry
        itself beyond getting empty/failed results, which is what the
        IntegrityGate's hit_rate check is for)."""
        self.client.cookies.set("JSESSIONID", jsessionid, domain="recordsearch.tehama.gov")
        self.client.cookies.set("disclaimerAccepted", disclaimer_accepted, domain="recordsearch.tehama.gov")
        self._session_ready = True

    def suggest_names(self, search_text: str, max_values: int = 1000) -> list[str]:
        """Step 2 — confirmed working. Returns the raw suggestion list;
        caller picks the exact name(s) to search on."""
        if not self._session_ready:
            raise RuntimeError(
                "No session cookies set. Construct TehamaRecorderClient with "
                "jsessionid from a real browser session (see module docstring)."
            )

        resp = self.client.post(
            "/web/search/suggest/BothNamesID",
            params={"searchText": search_text, "maxValues": max_values},
        )
        resp.raise_for_status()
        time.sleep(self.delay)

        try:
            data = resp.json()
            return data if isinstance(data, list) else data.get("names", [])
        except ValueError:
            return re.findall(r'"([^"]+)"', resp.text)

    def submit_search(
        self,
        name: str,
        contains_mode: str = "Contains Any",
        exact_name_field: str = "",
        start_date: str = "",
        end_date: str = "",
    ):
        """Step 3 — confirmed 7/12 via DevTools payload capture.

        POSTs to /web/searchPost/DOCSEARCH4S1 to establish server-side
        search state for this session. The suggest/autocomplete step
        (suggest_names) is NOT required — free-text search works directly
        via field_BothNamesID-searchInput, so this can be called standalone.
        """
        if not self._session_ready:
            raise RuntimeError(
                "No session cookies set. Construct TehamaRecorderClient with "
                "jsessionid from a real browser session (see module docstring)."
            )

        payload = {
            "field_BothNamesID-searchInput": name,
            "field_BothNamesID-containsInput": contains_mode,
            "field_BothNamesID": exact_name_field,
            "field_RecordingDateID_DOT_StartDate": start_date,
            "field_RecordingDateID_DOT_EndDate": end_date,
            "field_UseAdvancedSearch": "",
        }

        resp = self.client.post("/web/searchPost/DOCSEARCH4S1", data=payload)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def submit_doc_search(self, doc_number: str):
        """Document number search via DOCSEARCH4S2."""
        if not self._session_ready:
            raise RuntimeError(
                "No session cookies set. Construct TehamaRecorderClient with "
                "jsessionid from a real browser session (see module docstring)."
            )

        payload = {
            "field_DocumentNumberID": doc_number,
        }
        resp = self.client.post("/web/searchPost/DOCSEARCH4S2", data=payload)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def get_results(self, page: int = 1, search_type: str = "name") -> tuple[list[RecorderResult], int]:
        """Fetches paged results for the last submitted search.
        search_type='name' uses DOCSEARCH4S1; search_type='doc' uses DOCSEARCH4S2."""
        if not self._session_ready:
            raise RuntimeError(
                "No session cookies set. Construct TehamaRecorderClient with "
                "jsessionid from a real browser session (see module docstring)."
            )

        search_id = "DOCSEARCH4S1" if search_type == "name" else "DOCSEARCH4S2"
        resp = self.client.get(
            f"/web/searchResults/{search_id}",
            params={"page": page, "_": int(time.time() * 1000)},
        )
        resp.raise_for_status()
        time.sleep(self.delay)

        return self._parse_results_html(resp.text)

    def _parse_results_html(self, html: str) -> tuple[list[RecorderResult], int]:
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("li.ss-search-row")

        results = []
        for row in rows:
            doc_id = row.get("data-documentid", "")

            header = row.select_one("h1")
            header_text = header.get_text(" ", strip=True) if header else ""

            # Positional bullet-split — handles modern and legacy doc number formats
            segments = [s.strip() for s in header_text.split("\u2022") if s.strip()]
            doc_number = segments[0] if segments else ""
            if not doc_number and header_text:
                doc_number = header_text.strip()

            doc_type = segments[-1] if len(segments) > 1 else ""
            book_page = segments[1] if len(segments) > 2 else ""

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


if __name__ == "__main__":
    # Requires a fresh JSESSIONID from a real browser where a human has
    # solved the reCAPTCHA — see module docstring for how to capture it.
    import sys

    if len(sys.argv) < 2:
        print("Usage: python tehama_recorder_api.py <JSESSIONID>")
        print("Get JSESSIONID from a real browser after solving the CAPTCHA at:")
        print("  https://recordsearch.tehama.gov/web/user/disclaimer")
        sys.exit(1)

    jsessionid = sys.argv[1]

    client = TehamaRecorderClient(jsessionid=jsessionid)
    try:
        client.submit_search("miller 1991 revocable living")
        results, total = client.get_results(page=1)
        print(f"Total results: {total}")
        for r in results:
            print(r.doc_number, r.doc_type, r.recording_date, r.grantors, r.grantees)
    finally:
        client.close()
