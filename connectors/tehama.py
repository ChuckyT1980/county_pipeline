import requests
import json as _json
from bs4 import BeautifulSoup
from .base import BaseConnector, RawPayload

class TehamaConnector(BaseConnector):
    BASE = "https://common1.mptsweb.com/MBC"

    def _headers(self):
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json,text/html"
        }

    def _api_get(self, endpoint: str) -> dict:
        """Call a JSON API endpoint and return the first row, or empty dict."""
        url = f"{self.BASE}/api/search/tehama/0000-CURR/{endpoint}"
        try:
            r = requests.get(url, headers=self._headers(), timeout=15)
            if r.status_code != 200:
                return {}
            data = r.json()
            if isinstance(data, str):
                data = _json.loads(data)
            rows = data.get("Table", {}).get("Row", [])
            if isinstance(rows, dict):
                rows = [rows]
            return rows[0] if rows else {}
        except Exception:
            return {}

    def fetch_identity(self, apn: str) -> RawPayload:
        apn_norm = self.normalize_apn(apn)
        data = self._api_get(f"feeparcel/{apn_norm[:11]}")
        return RawPayload(apn_raw=apn, data=data, source="feeparcel_api", county=self.county)

    def fetch_owner(self, apn: str) -> RawPayload:
        """Direct Owner API endpoint — returns owner name."""
        apn_norm = self.normalize_apn(apn)
        data = self._api_get(f"owner/{apn_norm[:11]}")
        return RawPayload(apn_raw=apn, data=data, source="owner_api", county=self.county)

    def fetch_snapshot(self, apn: str) -> RawPayload:
        apn_norm = self.normalize_apn(apn)

        # 1. JSON ASMT Endpoint — identity data (no owner, no balance)
        asmt = self._api_get(f"asmt/{apn_norm[:11]}")
        owner = self._api_get(f"owner/{apn_norm[:11]}")

        merged = {**asmt}
        if owner.get("Owner"):
            merged["OwnerName"] = owner["Owner"]

        # 2. HTML Fallback — parse actual fields from the MPTS page
        html_url = f"{self.BASE}/tehama/tax/main/{apn_norm}"
        try:
            r = requests.get(html_url, headers=self._headers(), timeout=15)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                title = soup.title.string if soup.title else ""
                if "maintenance" not in title.lower():
                    merged["_html_available"] = True

                    for dt in soup.find_all("dt"):
                        label = dt.get_text(strip=True).lower()
                        dd = dt.find_next_sibling("dd")
                        if not dd:
                            continue
                        value = dd.get_text(" ", strip=True)
                        if label == "total balance":
                            merged["CurrDue"] = value
                        elif label == "mailing address" and "MailingAddress" not in merged:
                            merged["MailingAddress"] = value
                        elif label == "owner" and "OwnerName" not in merged:
                            merged["OwnerName"] = value
                else:
                    merged["_html_available"] = False
        except Exception:
            merged["_html_available"] = False

        return RawPayload(apn_raw=apn, data=merged, source="snapshot", county=self.county)

