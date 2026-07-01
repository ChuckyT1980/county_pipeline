import requests
from bs4 import BeautifulSoup
from .base import BaseConnector, RawPayload

class TehamaConnector(BaseConnector):
    BASE = "https://common1.mptsweb.com/MBC"

    def _headers(self):
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json,text/html"
        }

    def fetch_identity(self, apn: str) -> RawPayload:
        apn_norm = self.normalize_apn(apn)
        url = f"{self.BASE}/api/search/tehama/0000-CURR/feeparcel/{apn_norm[:11]}"

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
                
        return RawPayload(
            apn_raw=apn,
            data=raw_data,
            source="feeparcel_api",
            county=self.county
        )

    def fetch_snapshot(self, apn: str) -> RawPayload:
        apn_norm = self.normalize_apn(apn)

        # 1. JSON ASMT Endpoint
        api_url = f"{self.BASE}/api/search/tehama/0000-CURR/asmt/{apn_norm[:11]}"
        r = requests.get(api_url, headers=self._headers(), timeout=15)

        if r.status_code == 200:
            try:
                data = r.json()
                rows = data.get("Table", {}).get("Row", [])
                if isinstance(rows, dict):
                    rows = [rows]
                raw_data = rows[0] if rows else {}
                if raw_data:
                    return RawPayload(
                        apn_raw=apn,
                        data=raw_data,
                        source="asmt_api",
                        county=self.county
                    )
            except Exception:
                pass

        # 2. HTML Fallback — parse actual fields from the MPTS page
        html_url = f"{self.BASE}/tehama/tax/main/{apn_norm}"
        r = requests.get(html_url, headers=self._headers(), timeout=15)

        raw_data = {}
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")

            # --- APN from the ASMT header block ---
            asmt_div = soup.find("div", string=lambda t: t and "ASMT" in t)
            if asmt_div:
                sibling = asmt_div.find_next_sibling("div")
                if sibling:
                    raw_data["Asmt"] = sibling.get_text(strip=True)

            # --- Assessment Info tab: dt/dd label-value pairs ---
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
                    # First address dt = situs, second = city/state line
                    if "Situs1" not in raw_data:
                        raw_data["Situs1"] = value
                    elif "Situs2" not in raw_data:
                        raw_data["Situs2"] = value
                        # Combine into full situs
                        raw_data["Situs1"] = f"{raw_data['Situs1']}, {value}"

            # --- Owner from sidebar search results or page owner fields ---
            owner_tag = soup.find("dd", id="ownerName")
            if not owner_tag:
                # Fallback: look for a strong tag near "Owner"
                for dt in soup.find_all("dt"):
                    if "owner" in dt.get_text(strip=True).lower():
                        dd = dt.find_next_sibling("dd")
                        if dd:
                            raw_data["OwnerName"] = dd.get_text(strip=True)
                            break
            else:
                raw_data["OwnerName"] = owner_tag.get_text(strip=True)

            # --- Mailing address (separate from situs) ---
            mailing_dt = None
            for dt in soup.find_all("dt"):
                if "mailing" in dt.get_text(strip=True).lower():
                    mailing_dt = dt
                    break
            if mailing_dt:
                dd = mailing_dt.find_next_sibling("dd")
                if dd:
                    raw_data["MailingAddress"] = dd.get_text(" ", strip=True)

            # --- Total Balance from tax totals block ---
            for dt in soup.find_all("dt"):
                if "total balance" in dt.get_text(strip=True).lower():
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        raw_data["CurrDue"] = dd.get_text(strip=True)
                        break

        return RawPayload(
            apn_raw=apn,
            data=raw_data,
            source="html_fallback",
            county=self.county
        )

