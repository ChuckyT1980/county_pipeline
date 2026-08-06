"""
Stage 2 Butte Adapter — wraps the new Tyler Self-Service 2024.1.35 portal.

Usage:
    from butte_recorder_adapter import ButteRecorderAdapter
    adapter = ButteRecorderAdapter()
    adapter.start()
    events = adapter.name_search("MORRIS ELIZABETH")
    adapter.close()
    # events is list[RecorderEvent] matching stage2 recorder_chain schema
"""
import re, time, json
from datetime import datetime
from typing import Optional, List
from playwright.sync_api import sync_playwright, Page

# ── Schema ────────────────────────────────────────────────────────────
# Mirrors stage2 RecorderEvent fields without Pydantic dependency

RECORDER_EVENT_FIELDS = [
    "event_id", "doc_type", "role", "recorded_date",
    "doc_number", "grantor", "grantee"
]

ROLE_MAP = {
    "TRANSFER": "TRANSFER",
    "DEBT": "DEBT",
    "LIEN": "LIEN",
    "DEFAULT": "DEFAULT",
    "RELEASE": "RELEASE",
    "OTHER": "OTHER",
}

RELEASE_KEYWORDS = ["RECONVEYANCE", "FULL RECONVEYANCE", "SUBSTITUTION OF TRUSTEE",
                    "SATISFACTION OF JUDGMENT", "RELEASE OF LIEN", "RELEASE OF FEDERAL TAX LIEN",
                    "RESCISSION OF NOTICE OF DEFAULT", "RESCISSION"]
DEFAULT_KEYWORDS = ["NOTICE OF DEFAULT", "NOTICE OF TRUSTEE'S SALE", "NOTICE OF SALE",
                    "NOTICE OF POWER TO SELL"]
LIEN_KEYWORDS = ["FEDERAL TAX LIEN", "STATE TAX LIEN", "ABSTRACT OF JUDGMENT",
                 "MECHANIC'S LIEN", "MECHANICS LIEN", "NOTICE OF DELINQUENT ASSESSMENT",
                 "LIS PENDENS", "JUDGMENT"]
DEBT_KEYWORDS = ["DEED OF TRUST", "MORTGAGE", "ASSIGNMENT OF RENTS", "ASSIGNMENT OF DEED OF TRUST",
                 "MODIFICATION OF DEED OF TRUST", "MODIFICATION OF AGREEMENT"]
TRANSFER_KEYWORDS = ["GRANT DEED", "QUITCLAIM DEED", "WARRANTY DEED", "TRUSTEE'S DEED",
                     "AFFIDAVIT OF DEATH", "AFFIDAVIT AFFECTING TITLE"]
# "DEED" alone is ambiguous (could be transfer or trust deed), handled separately below

def classify_role(doc_type_str: str) -> str:
    dt = doc_type_str.upper()
    if any(k in dt for k in RELEASE_KEYWORDS): return "RELEASE"
    if any(k in dt for k in DEFAULT_KEYWORDS): return "DEFAULT"
    if any(k in dt for k in LIEN_KEYWORDS): return "LIEN"
    if any(k in dt for k in DEBT_KEYWORDS): return "DEBT"
    if any(k in dt for k in TRANSFER_KEYWORDS): return "TRANSFER"
    if dt == "DEED" or dt.startswith("DEED "): return "TRANSFER"
    if "ASSIGNMENT" in dt: return "DEBT"
    return "OTHER"


# ── ADAPTER ───────────────────────────────────────────────────────────

class ButteRecorderAdapter:
    """
    Playwright wrapper for Butte County Tyler Self-Service.
    Usage: with ButteRecorderAdapter() as a: events = a.name_search("MORRIS")
    """

    BASE = "https://recorder.buttecounty.net/web"
    SEARCH_URL = BASE + "/search/DOCSEARCH481S1"
    SEARCH_POST = BASE + "/searchPost/DOCSEARCH481S1"

    def __init__(self, headless=True, timeout=15000):
        self._playwright = None
        self._browser = None
        self._page: Optional[Page] = None
        self._headless = headless
        self._timeout = timeout

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.close()

    def start(self):
        """Launch browser, load search page, accept disclaimer."""
        self._playwright = sync_playwright().__enter__()
        self._browser = self._playwright.chromium.launch(headless=self._headless)
        ctx = self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        self._page = ctx.new_page()
        self._page.set_default_timeout(self._timeout)

        # Load search page
        self._page.goto(self.SEARCH_URL, wait_until="networkidle", timeout=self._timeout)
        self._page.wait_for_timeout(2000)

        # Accept disclaimer if present
        self._accept_disclaimer()

        # Navigate back to search (disclaimer may redirect)
        if "DOCSEARCH481S1" not in self._page.url:
            self._page.goto(self.SEARCH_URL, wait_until="networkidle", timeout=self._timeout)
            self._page.wait_for_timeout(2000)

        # Ping session to keep alive
        self._ping()

    def _accept_disclaimer(self):
        """Accept the Tyler disclaimer page."""
        if "disclaimer" not in self._page.url.lower():
            return
        btn = self._page.query_selector('button:has-text("I Accept")')
        if btn:
            btn.click()
            self._page.wait_for_timeout(3000)
            self._page.wait_for_load_state("networkidle")

    def _ping(self):
        """Session keepalive."""
        try:
            self._page.evaluate(
                '() => fetch("/web/session/pingSession").then(r => r.text())'
            )
        except:
            pass

    def name_search(self, name: str, max_retries=2) -> List[dict]:
        """
        Search Butte recorder by owner name.
        Returns list of dicts matching recorder_chain schema:
          {event_id, doc_type, role, recorded_date, doc_number, grantor, grantee}
        """
        if not self._page:
            raise RuntimeError("Adapter not started. Call start() first.")

        for attempt in range(max_retries):
            try:
                # Navigate to search page
                self._page.goto(self.SEARCH_URL, wait_until="networkidle", timeout=self._timeout)
                self._page.wait_for_timeout(2000)

                # Re-accept disclaimer if it popped up
                self._accept_disclaimer()

                # If redirected away, go back
                if "DOCSEARCH481S1" not in self._page.url:
                    self._page.goto(self.SEARCH_URL, wait_until="networkidle", timeout=self._timeout)
                    self._page.wait_for_timeout(2000)

                # Fill search field
                search_input = self._page.query_selector("#field_BothNamesID")
                if not search_input:
                    raise RuntimeError("Search input #field_BothNamesID not found")

                search_input.click()
                search_input.fill(name)
                self._page.wait_for_timeout(500)

                # Dismiss autocomplete popup
                self._page.keyboard.press("Escape")
                self._page.wait_for_timeout(500)

                # Click search button
                btn = self._page.query_selector(
                    'button:has-text("Search"), input[value*="Search"], #searchButton'
                )
                if btn:
                    btn.click()
                else:
                    # Fall back to form submit
                    self._page.evaluate(
                        '() => document.querySelector("form").requestSubmit()'
                    )

                self._page.wait_for_timeout(5000)
                self._page.wait_for_load_state("networkidle")

                html = self._page.content()
                return self._parse_results(html, name)

            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                self._ping()
                time.sleep(2)
        return []

    def _parse_results(self, html: str, search_name: str) -> List[dict]:
        """Parse searchPost HTML into recorder_chain events.

        New Tyler 2024.1.35 structure:
          li.ss-search-row[data-documentid] with:
            <h1>DOC_NUM ... DOC_TYPE</h1>
            <div class="searchResultThreeColumn">
              <ul> <li>Recording Date</li> <li><b>DATE</b></li> </ul>
            </div>
            <div class="searchResultThreeColumn">
              <ul> <li>Grantor (N)</li> <li><b>NAME1</b></li> <li><b>NAME2</b></li> </ul>
            </div>
            <div class="searchResultThreeColumn">
              <ul> <li>Grantee</li> <li><b>NAME</b></li> </ul>
            </div>
        """
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        events = []

        rows = soup.select("li.ss-search-row")
        if not rows:
            body = soup.get_text()
            if "please log in" in body.lower() or "log in" in body.lower():
                raise RuntimeError("Login required — Tyler session expired or not authenticated")
            return events

        for row in rows:
            doc_id = row.get("data-documentid", "")

            # Parse H1 for doc number + doc type
            h1 = row.find("h1")
            if not h1:
                continue
            h1_text = h1.get_text(strip=True)

            doc_match = re.search(r'(\d{4}-\d{7})', h1_text)
            if not doc_match:
                continue
            doc_number = doc_match.group(1)

            # Doc type is everything after the first ┬á or the doc number
            doc_type = "UNKNOWN"
            for sep in ["\u00a0\u25a0\u00a0", "\u00a0"]:
                if sep in h1_text:
                    doc_type = h1_text.split(sep)[-1].strip()
                    break
            if doc_type == "UNKNOWN":
                # Fallback: text after doc_number
                after_num = h1_text[len(doc_number):].strip()
                if after_num:
                    doc_type = after_num

            # Parse three-column blocks
            grantor_values = []
            grantee_values = []
            recorded_date = ""
            grantor_label = ""
            grantee_label = ""

            for col in row.find_all("div", class_="searchResultThreeColumn"):
                header_li = col.find("li")
                if not header_li:
                    continue
                header = header_li.get_text(strip=True).upper()

                # Values: all <b> inside the column
                values = [b.get_text(strip=True) for b in col.find_all("b") if b.get_text(strip=True)]

                if "RECORDING DATE" in header:
                    if values:
                        raw = values[0].split()[0]  # "08/13/2025 11:35 AM" -> "08/13/2025"
                        try:
                            recorded_date = datetime.strptime(raw, "%m/%d/%Y").isoformat()
                        except:
                            recorded_date = raw
                elif "GRANTOR" in header:
                    grantor_label = header
                    grantor_values = values
                elif "GRANTEE" in header:
                    grantee_label = header
                    grantee_values = values

            # Multi-grantor/grantee: join with "; "
            grantor = "; ".join(grantor_values) if grantor_values else ""
            grantee = "; ".join(grantee_values) if grantee_values else ""

            # Classify role
            role = classify_role(doc_type)

            event = {
                "event_id": doc_id or doc_number,
                "doc_type": doc_type,
                "role": role,
                "recorded_date": recorded_date,
                "doc_number": doc_number,
                "grantor": grantor,
                "grantee": grantee,
            }
            events.append(event)

        return events

    def close(self):
        """Cleanup."""
        try:
            if self._browser:
                self._browser.close()
        except:
            pass
        try:
            if self._playwright:
                self._playwright.__exit__(None, None, None)
        except:
            pass


# ── CLI / DEMO ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "MORRIS ELIZABETH"

    adapter = ButteRecorderAdapter(headless=True)
    try:
        adapter.start()
        events = adapter.name_search(name)
        print(json.dumps(events, indent=2))
        print(f"\nTotal events: {len(events)}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        adapter.close()
