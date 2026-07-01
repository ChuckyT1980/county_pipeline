import requests
from bs4 import BeautifulSoup
from .base import BaseConnector, RawPayload


class ShastaConnector(BaseConnector):
    BASE = "https://common2.mptsweb.com/MBC"

    def _headers(self):
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json,text/html"
        }

    def fetch_identity(self, apn: str) -> RawPayload:
        apn_norm = self.normalize_apn(apn)
        url = f"{self.BASE}/api/search/shasta/0000-CURR/feeparcel/{apn_norm[:11]}"
        r = requests.get(url, headers=self._headers(), timeout=15)
        raw_data = {}
        if r.status_code == 200:
            try:
                data = r.json()
                rows = data.get("Table", {}).get("Row", [])
                if isinstance(rows, dict):
                    rows = [rows]
                raw_data = rows[0] if rows else {}
            except Exception:
                pass
        return RawPayload(apn_raw=apn, data=raw_data, source="feeparcel_api", county=self.county)

    def fetch_snapshot(self, apn: str) -> RawPayload:
        apn_norm = self.normalize_apn(apn)

        # 1. JSON ASMT Endpoint
        api_url = f"{self.BASE}/api/search/shasta/0000-CURR/asmt/{apn_norm[:11]}"
        r = requests.get(api_url, headers=self._headers(), timeout=15)
        if r.status_code == 200:
            try:
                data = r.json()
                rows = data.get("Table", {}).get("Row", [])
                if isinstance(rows, dict):
                    rows = [rows]
                raw_data = rows[0] if rows else {}
                if raw_data:
                    return RawPayload(apn_raw=apn, data=raw_data, source="asmt_api", county=self.county)
            except Exception:
                pass

        # 2. HTML Fallback — same page structure as Tehama (same MPTS platform)
        html_url = f"{self.BASE}/shasta/tax/main/{apn_norm}"
        r = requests.get(html_url, headers=self._headers(), timeout=15)
        raw_data = {}
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")

            asmt_div = soup.find("div", string=lambda t: t and "ASMT" in t)
            if asmt_div:
                sibling = asmt_div.find_next_sibling("div")
                if sibling:
                    raw_data["Asmt"] = sibling.get_text(strip=True)

            for dt in soup.find_all("dt"):
                label = dt.get_text(strip=True).lower()
                dd = dt.find_next_sibling("dd")
                if not dd:
                    continue
                value = dd.get_text(" ", strip=True)
                if label == "assessment":
                    raw_data.setdefault("Asmt", value)
                elif label == "roll category":
                    raw_data["RollCategory"] = value
                elif label == "address":
                    if "Situs1" not in raw_data:
                        raw_data["Situs1"] = value
                    elif "Situs2" not in raw_data:
                        raw_data["Situs2"] = value
                        raw_data["Situs1"] = f"{raw_data['Situs1']}, {value}"

            owner_tag = soup.find("dd", id="ownerName")
            if not owner_tag:
                for dt in soup.find_all("dt"):
                    if "owner" in dt.get_text(strip=True).lower():
                        dd = dt.find_next_sibling("dd")
                        if dd:
                            raw_data["OwnerName"] = dd.get_text(strip=True)
                            break
            else:
                raw_data["OwnerName"] = owner_tag.get_text(strip=True)

            for dt in soup.find_all("dt"):
                if "mailing" in dt.get_text(strip=True).lower():
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        raw_data["MailingAddress"] = dd.get_text(" ", strip=True)
                    break

            for dt in soup.find_all("dt"):
                if "total balance" in dt.get_text(strip=True).lower():
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        raw_data["CurrDue"] = dd.get_text(strip=True)
                    break

        return RawPayload(apn_raw=apn, data=raw_data, source="html_fallback", county=self.county)
