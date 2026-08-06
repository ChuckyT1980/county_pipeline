"""
County source configuration for excess proceeds lists.

Each CountySource declares:
  - where to find the list (URL or list of URLs)
  - the format (pdf / html_table)
  - a parser callable to convert raw file/HTML into structured rows

Add a county by appending to COUNTY_SOURCES.

All counties confirmed live via web search; URLs verified 2026-07-22.
Some counties (Butte, Shasta) don't post the raw list publicly at all times;
they publish "in early August" post-auction. For those, this scraper waits
until the list appears and then ingests it.
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class CountySource:
    county: str
    display_name: str
    ttc_url: str
    format: str                                  # "pdf" or "html_table" or "index_page"
    list_urls: list[str] = field(default_factory=list)   # direct URLs to the actual list files
    index_url: str = ""                          # a page that LISTS the current PDF (we discover list_urls by scraping this)
    parser_key: str = "generic_pdf"              # which parser to use (see parsers.py)
    processing_cadence: str = "unknown"          # rolling / monthly / quarterly / annual
    fee_cap_pct: float | None = None             # CA has no general cap on tax-sale surplus recovery fees,
                                                 # but some counties may have local rules
    notes: str = ""


COUNTY_SOURCES: list[CountySource] = [
    CountySource(
        county="butte",
        display_name="Butte County",
        ttc_url="https://www.buttecounty.net/960/Property-Taxes",
        format="index_page",
        index_url="https://www.buttecounty.net/960/Property-Taxes",
        parser_key="generic_pdf",
        processing_cadence="annual",
        notes="List published 'early August' after each auction. Claims processed 1 year after trustee's deed recording. Batch distribution once/year in December.",
    ),
    CountySource(
        county="mono",
        display_name="Mono County",
        ttc_url="https://monocounty.ca.gov/print/8997",
        format="pdf",
        list_urls=[
            "https://monocounty.ca.gov/sites/default/files/fileattachments/treasurer_-_tax_collector/page/8997/excess_proceeds_list_november_14_2023.pdf",
            "https://monocounty.ca.gov/sites/default/files/fileattachments/treasurer_-_tax_collector/page/8997/excess_proceeds_list_february_7_2024.pdf",
        ],
        parser_key="generic_pdf",
        processing_cadence="periodic",
        notes="Publishes updated list ~quarterly. Index page: monocounty.ca.gov/print/8997",
    ),
    CountySource(
        county="contra_costa",
        display_name="Contra Costa County",
        ttc_url="https://www.contracosta.ca.gov/5675/Excess-Proceeds-Policy-and-Forms",
        format="index_page",
        index_url="https://www.contracosta.ca.gov/5675/Excess-Proceeds-Policy-and-Forms",
        parser_key="generic_pdf",
        processing_cadence="rolling",
        notes="Rolling process. Has separate forms for assignment and probate cases.",
    ),
    CountySource(
        county="kern",
        display_name="Kern County",
        ttc_url="https://www.kerncounty.com/services/property-land-and-taxes/property-tax-portal/tax-defaulted-property-sales",
        format="index_page",
        index_url="https://www.kerncounty.com/services/property-land-and-taxes/property-tax-portal/tax-defaulted-property-sales",
        parser_key="generic_pdf",
        processing_cadence="unknown",
        notes="Publishes Power to Sell list and Excess Proceeds Claim Form.",
    ),
    CountySource(
        county="el_dorado",
        display_name="El Dorado County",
        ttc_url="https://www.eldoradocounty.ca.gov/County-Government/County-Departments/Auditor-Controller/Property-Tax/Tax-Sale-Excess-Proceeds",
        format="index_page",
        index_url="https://www.eldoradocounty.ca.gov/County-Government/County-Departments/Auditor-Controller/Property-Tax/Tax-Sale-Excess-Proceeds",
        parser_key="generic_pdf",
        processing_cadence="unknown",
        notes="Contact: (530) 621-5470 ext. 4 or AuditorPropertyTaxDivision@edcgov.us",
    ),
    CountySource(
        county="solano",
        display_name="Solano County",
        ttc_url="https://www.solanocounty.gov/government/treasurer-tax-collector-county-clerk/tax-collector/tax-sale-general-information/excess-proceeds",
        format="index_page",
        index_url="https://www.solanocounty.gov/government/treasurer-tax-collector-county-clerk/tax-collector/tax-sale-general-information/excess-proceeds",
        parser_key="generic_pdf",
        processing_cadence="unknown",
    ),
    CountySource(
        county="shasta",
        display_name="Shasta County",
        ttc_url="https://www.shastacounty.gov/tax-collector/page/excess-proceeds",
        format="index_page",
        index_url="https://www.shastacounty.gov/tax-collector/page/excess-proceeds",
        parser_key="generic_pdf",
        processing_cadence="unknown",
        notes="Site returned 403 on programmatic fetch; may need User-Agent tuning or manual.",
    ),
]


def get_source(county: str) -> CountySource | None:
    for s in COUNTY_SOURCES:
        if s.county == county:
            return s
    return None
