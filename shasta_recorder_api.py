import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://recorderselfservice.shastacounty.gov"


@dataclass
class RecorderResult:
    doc_id: str
    doc_number: str
    doc_type: str
    recording_date: str
    grantors: list[str]
    grantees: list[str]


class ShastaRecorderClient:
    def __init__(self, timeout: float = 15.0, delay_between_requests: float = 0.5):
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
        self._session_ready = False

    def _init_session(self):
        resp = self.client.get("/web/search/DOCSEARCH344S5")
        resp.raise_for_status()
        time.sleep(self.delay)

        self.client.cookies.set("disclaimerAccepted", "true", domain="recorderselfservice.shastacounty.gov")

        self._session_ready = True

    def submit_search(
        self,
        name: str
    ):
        if not self._session_ready:
            self._init_session()

        payload = {
            "field_BothNamesID": name,
            "field_RecordingDateID_DOT_StartDate": "",
            "field_RecordingDateID_DOT_EndDate": "",
            "field_UseAdvancedSearch": ""
        }

        headers = {
            "ajaxrequest": "true",
            "x-requested-with": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        resp = self.client.post("/web/searchPost/DOCSEARCH344S4", data=payload, headers=headers)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def submit_doc_search(
        self,
        doc_num: str
    ):
        if not self._session_ready:
            self._init_session()

        payload = {
            "field_DocumentNumberID": doc_num,
            "field_BookPageID_DOT_Volume": "",
            "field_BookPageID_DOT_Page": ""
        }

        headers = {
            "ajaxrequest": "true",
            "x-requested-with": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }
        resp = self.client.post("/web/searchPost/DOCSEARCH344S5", data=payload, headers=headers)
        resp.raise_for_status()
        time.sleep(self.delay)
        return resp

    def get_results(self, search_type: str = "DOCSEARCH344S5", page: int = 1) -> tuple[list[RecorderResult], int]:
        if not self._session_ready:
            self._init_session()

        resp = self.client.get(
            f"/web/searchResults/{search_type}",
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
            
            segments = [s.strip() for s in header_text.replace('\ufffd', '\u2022').split('\u2022')]
            if len(segments) >= 2:
                doc_number = segments[0]
                doc_type = segments[-1]
            elif len(segments) == 1:
                doc_number = segments[0]
                doc_type = ""
            else:
                doc_number = ""
                doc_type = ""

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
                )
            )

        total_match = re.search(r"for\s+(\d+)\s+Total Results", html)
        total_results = int(total_match.group(1)) if total_match else len(results)

        return results, total_results

    def close(self):
        self.client.close()

if __name__ == "__main__":
    client = ShastaRecorderClient()
    try:
        print("Testing Shasta name search...")
        client.submit_search("SMITH JOHN")
        results, total = client.get_results(search_type="DOCSEARCH344S4", page=1)
        print(f"Total results: {total}")
        for r in results[:5]:
            print(r.doc_number, r.doc_type, r.recording_date, r.grantors, r.grantees)
            
        print("\\nTesting Shasta doc search...")
        client.submit_doc_search("2018-0007697")
        results, total = client.get_results(page=1)
        print(f"Total results: {total}")
        for r in results:
            print(r.doc_number, r.doc_type, r.recording_date, r.grantors, r.grantees)
    finally:
        client.close()
