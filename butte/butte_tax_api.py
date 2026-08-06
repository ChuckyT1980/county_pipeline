import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from bs4 import BeautifulSoup

BASE_URL = "https://common2.mptsweb.com"
SEARCH_PATH = "/mbc/butte/tax/search"
CURRENT_ROLL_YEAR = 2026  # confirmed 7/13 — bump manually each year, do not derive from datetime.now()


@dataclass
class DefaultedTaxRecord:
    default_number: str
    pay_plan_in_effect: str
    annual_payment: str
    balance: str
    default_year: Optional[int] = None
    years_delinquent: Optional[int] = None


@dataclass
class ButteTaxResult:
    parcel_number: str
    assessment: str
    tax_year: str
    roll_category: str
    document_number_raw: str      # as shown on tax site, e.g. "2024R0030607"
    address: str
    history_url: str = ""         # link found alongside Document Number, unexplored
    defaulted_taxes: list = None  # list[DefaultedTaxRecord] — empty if parcel has no defaults

    def __post_init__(self):
        if self.defaulted_taxes is None:
            self.defaulted_taxes = []

    @property
    def is_delinquent(self) -> bool:
        """True if this parcel has any defaulted tax balance — the actual
        lead-qualification signal, confirmed via the PAY DEFAULTED TAXES
        tab (e.g. Default DEF260000028, Balance $1,148.04)."""
        return len(self.defaulted_taxes) > 0

    @property
    def total_defaulted_balance(self) -> float:
        total = 0.0
        for rec in self.defaulted_taxes:
            try:
                total += float(rec.balance.replace("$", "").replace(",", ""))
            except (ValueError, AttributeError):
                pass
        return total


def to_dashed(parcel_raw: str) -> str:
    """Accepts either format, returns dashed (e.g. 002-271-003-000) for search.
    Zero-pads to 12 digits first, since CSVs typed as int64 strip leading zeros
    (asmt 2271001000 must become 002-271-001-000)."""
    digits = re.sub(r"\D", "", parcel_raw).zfill(12)
    if len(digits) != 12:
        return parcel_raw  # unexpected input — pass through
    return f"{digits[0:3]}-{digits[3:6]}-{digits[6:9]}-{digits[9:12]}"


def to_undashed(parcel_raw: str) -> str:
    """Returns undashed 12-digit form for the detail URL (e.g. 002271003000).
    Zero-pads to 12 digits — a bare 10-digit int-typed asmt (2271003000) must
    become 002271003000 or the detail URL 404s."""
    return re.sub(r"\D", "", parcel_raw).zfill(12)


class ButteTaxClient:
    def __init__(self, timeout: float = 15.0, delay_between_requests: float = 0.5,
                 roll_year: int = CURRENT_ROLL_YEAR):
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
        self.roll_year = roll_year
        self._session_ready = False

    def _get_csrf_token(self, html: str) -> Optional[str]:
        """Scrapes the ASP.NET anti-forgery token from a page's hidden
        input. This is what was missing — the bare GET to the detail URL
        had no session context at all, hence the generic 'Main Page | MBC'
        template instead of real parcel data."""
        soup = BeautifulSoup(html, "html.parser")
        token_input = soup.find("input", {"name": "__RequestVerificationToken"})
        return token_input.get("value") if token_input else None

    def _init_session(self):
        """Establishes real session state before hitting the detail page:
        Just fetching the search page once sets the ASP.NET_SessionId
        and verification token cookies required for the detail page.
        No POST search is actually required.
        """
        resp = self.client.get(SEARCH_PATH)
        resp.raise_for_status()
        time.sleep(self.delay)
        self._session_ready = True

    def get_detail(self, parcel_raw: str) -> Optional[ButteTaxResult]:
        """Fixed 7/13: must establish session via _init_session() first —
        a bare GET to the detail URL with no prior search returns the
        generic site template, not parcel data (confirmed via smoke test)."""
        parcel12 = to_undashed(parcel_raw)
        parcel_dashed = to_dashed(parcel_raw)

        if not self._session_ready:
            self._init_session()

        url = f"/MBC/butte/tax/main/{parcel12}/{self.roll_year}/0000"
        resp = self.client.get(url)
        resp.raise_for_status()
        time.sleep(self.delay)

        result = self._parse_detail_html(resp.text, parcel12)
        if result is None:
            # Surface the failure clearly rather than returning silently —
            # this is exactly the kind of thing that produced 20,000 blank
            # Tehama/Shasta records when it failed quietly instead.
            print(
                f"[butte_tax_api] WARNING: got a 200 response for parcel {parcel_dashed} "
                f"but couldn't parse expected fields — check if this is the generic "
                f"template again (session/token issue) or a genuinely different page "
                f"structure for this parcel."
            )
        return result

    def _parse_detail_html(self, html: str, parcel12: str) -> Optional[ButteTaxResult]:
        soup = BeautifulSoup(html, "html.parser")

        fields = {}
        history_url = ""

        for dl in soup.find_all("dl"):
            dts = dl.find_all("dt")
            dds = dl.find_all("dd")
            for dt, dd in zip(dts, dds):
                label = dt.get_text(strip=True)
                link = dd.find("a")
                if link:
                    val = link.get_text(strip=True)
                    if label == "Document Number":
                        history_url = link.get("href", "")
                else:
                    val = dd.get_text(" ", strip=True)
                
                if label:
                    fields[label] = val
                elif "Address" in fields:
                    fields["Address"] += f" {val}"

        if not fields:
            print(
                f"[butte_tax_api] WARNING: got a 200 response for parcel {parcel12} "
                f"but couldn't parse expected fields. HTML starts with: {html[:200]}"
            )
            return None  # page didn't have the expected structure — don't guess

        defaulted_taxes = self._parse_defaulted_taxes(soup)

        return ButteTaxResult(
            parcel_number=fields.get("Parcel Number", parcel12),
            assessment=fields.get("Assessment", ""),
            tax_year=fields.get("Tax Year", ""),
            roll_category=fields.get("Roll Category", ""),
            document_number_raw=fields.get("Document Number", ""),
            address=fields.get("Address", ""),
            history_url=history_url,
            defaulted_taxes=defaulted_taxes,
        )

    def _parse_defaulted_taxes(self, soup: BeautifulSoup) -> list:
        """Parses the PAY DEFAULTED TAXES section.

        Confirmed live structure (re-verified 7/13 against raw HTML):
        Each default record is a plain <div> row containing four
        <div class="col-sm-3"> cells. The labels are <strong> elements
        inside the first <div> of each cell; the values are the second
        <div>. There is NO <table> — earlier docstring was wrong.

        Example raw HTML:
            <div>
                <div class="col-sm-3">
                    <div><strong>Default Number</strong></div>
                    <div>DEF260000028</div>
                </div>
                <div class="col-sm-3">
                    <div><strong>Pay Plan in Effect</strong></div>
                    <div>NO</div>
                </div>
                <div class="col-sm-3">
                    <div><strong>Annual Payment</strong></div>
                    <div>N/A</div>
                </div>
                <div class="col-sm-3">
                    <div><strong>Balance</strong></div>
                    <div>$1,148.04</div>
                </div>
            </div>

        A parcel with no defaults simply won't have a DEF* number at all,
        which is expected and NOT an error (returns empty list, not None).
        """
        records = []

        # Find all rows that contain exactly 4 col-sm-3 cells
        for row_div in soup.find_all("div"):
            cells = row_div.find_all("div", class_="col-sm-3", recursive=False)
            if len(cells) != 4:
                continue

            def _cell_value(cell):
                inner_divs = cell.find_all("div", recursive=False)
                # Value is the second inner div (first is the label/strong)
                return inner_divs[1].get_text(strip=True) if len(inner_divs) >= 2 else ""

            def _cell_label(cell):
                strong = cell.find("strong")
                return strong.get_text(strip=True) if strong else ""

            labels = [_cell_label(c) for c in cells]
            # Only process rows that look like defaulted-tax records
            if "Default Number" not in labels:
                continue

            values = [_cell_value(c) for c in cells]
            row_data = dict(zip(labels, values))
            default_number = row_data.get("Default Number", "")
            
            # Extract year from format like DEF260000028
            default_year = None
            years_delinquent = None
            if default_number.startswith("DEF") and len(default_number) > 4:
                try:
                    yy = int(default_number[3:5])
                    default_year = 2000 + yy if yy < 80 else 1900 + yy
                    years_delinquent = max(0, CURRENT_ROLL_YEAR - default_year)
                except ValueError:
                    pass

            records.append(
                DefaultedTaxRecord(
                    default_number=default_number,
                    pay_plan_in_effect=row_data.get("Pay Plan in Effect", ""),
                    annual_payment=row_data.get("Annual Payment", ""),
                    balance=row_data.get("Balance", ""),
                    default_year=default_year,
                    years_delinquent=years_delinquent
                )
            )

        return records

    def close(self):
        self.client.close()


if __name__ == "__main__":
    # Ground-truth smoke test using the confirmed live parcel. This now
    # exercises the full fixed flow: GET search page -> scrape token ->
    # POST search -> GET detail page -> parse.
    client = ButteTaxClient()
    try:
        result = client.get_detail("002-271-003-000")
        if result:
            print(f"Parcel:           {result.parcel_number}")
            print(f"Roll Category:    {result.roll_category}")
            print(f"Document Number:  {result.document_number_raw}")
            print(f"Address:          {result.address}")
            print(f"History link:     {result.history_url}")
            print(f"Is delinquent:    {result.is_delinquent}")
            print(f"Total defaulted:  ${result.total_defaulted_balance:,.2f}")
            for rec in result.defaulted_taxes:
                print(f"  Default {rec.default_number}: balance={rec.balance} "
                      f"pay_plan={rec.pay_plan_in_effect} annual={rec.annual_payment}")
            if not result.document_number_raw:
                print(
                    "\nNOTE: parsed successfully but Document Number is empty — "
                    "if this persists across multiple parcels, the session/token "
                    "flow may still not be fully working even though a 200 came back."
                )
        else:
            print(
                "FAILED: no data parsed. If you see the generic 'Main Page | MBC' "
                "template mentioned in this failure, the SearchValue field name "
                "assumption is likely wrong — inspect the live search <form> and "
                "correct _init_session() accordingly."
            )
    finally:
        client.close()
