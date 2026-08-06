"""
Fetch, save, and parse Butte County tax bills.

For each parcel:
  1. GET the tax bill HTML from apps.mptsweb.com/TaxBillv2/
  2. Save raw HTML to butte/tax_bills/{apn}.html for archival
  3. Parse structured fields we're not currently capturing:
       - land_value / improvements_value (split of assessed value)
       - net_taxable_value
       - total_tax_billed
       - original_bill_date
       - power_to_sell_date        (when it became auction-eligible)
       - redemption_status          (redeemed / still delinquent / partial)
       - redemption_date            (if applicable — key signal that parcel may be OFF auction)
       - special_assessments_total  (sum of direct charges beyond property tax)
       - special_assessments_list   (pipe-separated: "CSA34 Gridley Pool:$6|...")
       - homeowner_exemption        (Y/N/none — owner-occupied indicator)
       - installment_plan_active    (Y/N)
       - years_delinquent           (roughly, from Power to Sell date)
"""
import os
import re
import time
from dataclasses import dataclass, asdict, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

BUTTE_DIR = Path(__file__).resolve().parent
TAX_BILLS_DIR = BUTTE_DIR / "tax_bills"
BASE_URL = "https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx"
REFERER  = "https://common2.mptsweb.com/mbc/butte/tax/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


@dataclass
class TaxBillFields:
    apn12: str
    fetch_status: str = "pending"          # ok / error / no_data
    fetch_error: str = ""
    saved_html_path: str = ""

    # Value breakdown
    land_value: Optional[float] = None
    improvements_value: Optional[float] = None
    net_taxable_value: Optional[float] = None
    total_tax_billed: Optional[float] = None

    # Dates
    original_bill_date: str = ""
    power_to_sell_date: str = ""
    years_since_power_to_sell: Optional[int] = None

    # Redemption
    redemption_status: str = ""            # "redeemed" / "still_delinquent" / "unknown"
    redemption_date: str = ""

    # Exemption / plan
    homeowner_exemption: str = ""          # Y / N / ""
    installment_plan_active: str = ""      # Y / N / ""

    # Special assessments (direct charges)
    special_assessments_total: Optional[float] = None
    special_assessments_list: str = ""     # pipe-separated "CODE:DESC:$AMT"

    # Convenience: important-messages block (contains distress signals verbatim)
    important_messages: str = ""


def _to_float(s):
    if not s:
        return None
    try:
        return float(str(s).replace("$", "").replace(",", "").replace(" ", "").strip())
    except (ValueError, TypeError):
        return None


def _to_iso(s):
    if not s:
        return ""
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def _years_since(iso_date):
    if not iso_date:
        return None
    try:
        d = date.fromisoformat(iso_date)
        return (date.today() - d).days // 365
    except ValueError:
        return None


def fetch_tax_bill(apn12: str, tax_year: int = 2025, roll_cat: str = "CS",
                    roll_type: str = "S", save: bool = True) -> str | None:
    """Fetch the tax bill HTML. Returns HTML or None on failure."""
    url = f"{BASE_URL}?CN=butte&Asmt={apn12}&TaxYear={tax_year}&RollCat={roll_cat}&RollType={roll_type}&RollYear="
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Referer": REFERER}, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return None
    html = r.text
    if save:
        TAX_BILLS_DIR.mkdir(exist_ok=True)
        (TAX_BILLS_DIR / f"{apn12}.html").write_text(html, encoding="utf-8")
    return html


def parse_tax_bill(html: str, apn12: str = "") -> TaxBillFields:
    result = TaxBillFields(apn12=apn12)
    if not html or "PROPERTY TAX BILL" not in html.upper():
        result.fetch_status = "no_data"
        return result

    result.fetch_status = "ok"

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Important messages block — key distress signals appear here verbatim
    msg_indices = [i for i, l in enumerate(lines) if l.upper() == "IMPORTANT MESSAGES"]
    if msg_indices:
        # Messages appear between "IMPORTANT MESSAGES" line and "FOR TAX YEAR:" line
        start = msg_indices[0] + 1
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("FOR TAX YEAR")), start + 20)
        # Extract only lines that look like messages (start with capital or contain distinctive words)
        msg_lines = []
        for l in lines[start:end]:
            if any(k in l for k in ["Original bill", "Delinquent", "redeemed", "Power to Sell",
                                     "Installment plan", "prior year", "escape", "supplemental"]):
                msg_lines.append(l)
        result.important_messages = " | ".join(msg_lines)

        # Extract redemption status
        for l in msg_lines:
            if "redeemed" in l.lower():
                result.redemption_status = "redeemed"
                m = re.search(r"(\d{1,2}/\d{1,2}/\d{4})", l)
                if m:
                    result.redemption_date = _to_iso(m.group(1))
                break
        else:
            if any("delinquent" in l.lower() for l in msg_lines):
                result.redemption_status = "still_delinquent"

        # Installment plan
        if any("installment plan" in l.lower() for l in msg_lines):
            result.installment_plan_active = "Y"

        # Original bill date
        for l in msg_lines:
            m = re.search(r"[Oo]riginal bill date\s+(\d{1,2}/\d{1,2}/\d{4})", l)
            if m:
                result.original_bill_date = _to_iso(m.group(1))
                break

        # Power to Sell
        for l in msg_lines:
            m = re.search(r"Power to Sell\s+(\d{1,2}/\d{1,2}/\d{4})", l)
            if m:
                result.power_to_sell_date = _to_iso(m.group(1))
                result.years_since_power_to_sell = _years_since(result.power_to_sell_date)
                break

    # Value breakdown — LAND / STRUCTURAL IMPROVEMENTS / NET TAXABLE VALUE
    def _val_after(label, offset_range=(1, 5)):
        """Find `label` and return the largest numeric value in the next few lines."""
        for i, l in enumerate(lines):
            if l.upper() == label.upper():
                nums = []
                for j in range(i + 1, min(len(lines), i + 8)):
                    v = _to_float(lines[j])
                    if v is not None:
                        nums.append(v)
                if nums:
                    return max(nums)   # skip 0 placeholders, return real value
        return None

    result.land_value = _val_after("LAND")
    result.improvements_value = _val_after("STRUCTURAL IMPROVEMENTS")
    result.net_taxable_value = _val_after("NET TAXABLE VALUE")

    # Total tax — look for VALUES X TAX RATE PER $100 pattern and its result
    for i, l in enumerate(lines):
        if "VALUES" in l and "TAX RATE PER" in l:
            for j in range(i + 1, min(i + 4, len(lines))):
                m = re.search(r"\$([\d,]+\.\d{2})", lines[j])
                if m:
                    result.total_tax_billed = _to_float(m.group(1))
                    break
            break

    # Homeowner exemption — look for "Homeowners Exemption" or "HOX"
    for i, l in enumerate(lines):
        if "Homeowners Exemption" in l or "HOMEOWNERS EXEMPTION" in l or "HOX" in l:
            # Look for value nearby
            for j in range(i, min(i + 6, len(lines))):
                v = _to_float(lines[j])
                if v is not None and v > 0:
                    result.homeowner_exemption = "Y"
                    break
            else:
                result.homeowner_exemption = "N"
            break

    # Special assessments (direct charges) — usually listed after property tax section
    # Find blocks with pattern: PHONE / CODE / DESCRIPTION / DIR CHRG followed by dollar amounts
    sa_total = 0.0
    sa_items = []
    # Look for direct-charge blocks
    for i, l in enumerate(lines):
        # Direct charge lines usually have: description then $amount immediately after
        # e.g. "CSA34 GRIDLEY POOL" then "$6.00"
        if l.startswith("CSA") or l.startswith("MOSQ") or "ASSESSMENT" in l.upper() \
           or l.startswith("VECTOR") or l.startswith("SEWER") or l.startswith("WATER"):
            if i + 1 < len(lines):
                v = _to_float(lines[i + 1])
                if v is not None and 0 < v < 10000:  # sanity: not the assessed-value column
                    sa_items.append(f"{l}:${v:.2f}")
                    sa_total += v
    if sa_items:
        result.special_assessments_total = sa_total
        result.special_assessments_list = "|".join(sa_items[:10])   # cap at 10 for CSV sanity

    return result


def enrich_apn(apn_dashed: str, tax_year: int = 2025) -> TaxBillFields:
    """Full workflow: fetch + save + parse for one APN."""
    apn12 = re.sub(r"\D", "", str(apn_dashed))
    html = fetch_tax_bill(apn12, tax_year=tax_year)
    if not html:
        return TaxBillFields(apn12=apn12, fetch_status="error", fetch_error="fetch failed")
    return parse_tax_bill(html, apn12=apn12)


if __name__ == "__main__":
    import argparse, json
    p = argparse.ArgumentParser()
    p.add_argument("apn", help="APN in dashed or undashed format")
    p.add_argument("--year", type=int, default=2025)
    args = p.parse_args()

    result = enrich_apn(args.apn, args.year)
    print(json.dumps(asdict(result), indent=2, default=str))
