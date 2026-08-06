"""
Build Master California Tax Auction Calendar Spreadsheet (2025 - 2027)
Outputs:
  data/california_tax_auction_calendar_2025_2027.xlsx (Multi-tab formatted Excel)
  data/california_tax_auction_calendar_2025_2027.csv  (Single master CSV)
"""
import os
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_XLSX = os.path.join(DATA_DIR, "california_tax_auction_calendar_2025_2027.xlsx")
OUT_CSV = os.path.join(DATA_DIR, "california_tax_auction_calendar_2025_2027.csv")

# Full Master Dataset starting with 2025 chronologically
MASTER_AUCTIONS = [
    # --- 2025 AUCTIONS ---
    {"Year": 2025, "Start Date": "2025-02-14", "End Date": "2025-02-17", "County": "Imperial", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://treasurer-taxcollector.imperialcounty.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-02-21", "End Date": "2025-02-21", "County": "Shasta", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.shastacounty.gov/tax-collector", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-02-24", "End Date": "2025-02-27", "County": "Sacramento", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://sacramento.mytaxsale.com", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-02-26", "End Date": "2025-02-26", "County": "Contra Costa", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.cctax.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-03-07", "End Date": "2025-03-11", "County": "Ventura", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.ventura.org/ttc/", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-03-10", "End Date": "2025-03-12", "County": "Kern", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.kcttc.co.kern.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-03-10", "End Date": "2025-03-12", "County": "Amador", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.amadorgov.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-03-15", "End Date": "2025-03-18", "County": "San Joaquin", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.sjgov.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-03-18", "End Date": "2025-03-18", "County": "Tulare", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://tularecounty.ca.gov/treasurertaxcollector/", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-03-14", "End Date": "2025-03-19", "County": "San Diego", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://sdttc.mytaxsale.com", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-04-19", "End Date": "2025-04-22", "County": "Los Angeles", "Platform": "GovEase", "Sale Type": "Main (2025A)", "Status": "Completed", "Portal URL": "https://ttc.lacounty.gov", "Notes": "2025A Spring auction"},
    {"Year": 2025, "Start Date": "2025-04-24", "End Date": "2025-04-29", "County": "Riverside", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.countytreasurer.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-05-09", "End Date": "2025-05-12", "County": "Siskiyou", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.siskiyou.ca.us", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-05-09", "End Date": "2025-05-14", "County": "San Diego", "Platform": "MyTaxSale", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://sdttc.mytaxsale.com", "Notes": "Re-offer sale"},
    {"Year": 2025, "Start Date": "2025-05-09", "End Date": "2025-05-12", "County": "Tuolumne", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.tuolumnecounty.ca.gov", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-05-10", "End Date": "2025-05-13", "County": "Madera", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://maderacounty.com", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-05-12", "End Date": "2025-05-12", "County": "Del Norte", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.del-norte.ca.us", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-05-13", "End Date": "2025-05-16", "County": "San Bernardino", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.sbcountyatc.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-05-15", "End Date": "2025-05-15", "County": "Humboldt", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://humboldtgov.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-05-16", "End Date": "2025-05-19", "County": "Lassen", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.lassencounty.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-05-16", "End Date": "2025-05-19", "County": "Modoc", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.modoc.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-05-19", "End Date": "2025-05-21", "County": "Stanislaus", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.stancounty.com", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-05-30", "End Date": "2025-06-02", "County": "San Luis Obispo", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.slocounty.ca.gov", "Notes": "Biennial sale"},
    {"Year": 2025, "Start Date": "2025-05-30", "End Date": "2025-06-03", "County": "Lake", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.lakecountyca.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-06-09", "End Date": "2025-06-09", "County": "Del Norte", "Platform": "GovEase", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.co.del-norte.ca.us", "Notes": "Re-offer sale"},
    {"Year": 2025, "Start Date": "2025-06-13", "End Date": "2025-06-16", "County": "Siskiyou", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.co.siskiyou.ca.us", "Notes": "Re-offer sale"},
    {"Year": 2025, "Start Date": "2025-06-18", "End Date": "2025-06-18", "County": "Fresno", "Platform": "Realauction", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.fresno.ca.us", "Notes": "Vesting deadline Jun 18, 2025"},
    {"Year": 2025, "Start Date": "2025-06-19", "End Date": "2025-06-23", "County": "Plumas", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.plumascounty.us", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-06-25", "End Date": "2025-06-25", "County": "Orange", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://octreasurer.gov", "Notes": "Main annual sale"},
    {"Year": 2025, "Start Date": "2025-08-08", "End Date": "2025-08-08", "County": "Madera", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://maderacounty.com", "Notes": "Re-offer sale"},
    {"Year": 2025, "Start Date": "2025-09-05", "End Date": "2025-09-08", "County": "Plumas", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.plumascounty.us", "Notes": "Re-offer sale"},
    {"Year": 2025, "Start Date": "2025-09-17", "End Date": "2025-09-17", "County": "Orange", "Platform": "Bid4Assets", "Sale Type": "Timeshares", "Status": "Completed", "Portal URL": "https://octreasurer.gov", "Notes": "Timeshares only"},
    {"Year": 2025, "Start Date": "2025-10-18", "End Date": "2025-10-21", "County": "Los Angeles", "Platform": "GovEase", "Sale Type": "Main (2025B)", "Status": "Completed", "Portal URL": "https://ttc.lacounty.gov", "Notes": "2025B Fall auction"},
    {"Year": 2025, "Start Date": "2025-10-29", "End Date": "2025-10-31", "County": "Glenn", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.countyofglenn.net", "Notes": "Biennial sale"},
    {"Year": 2025, "Start Date": "2025-11-05", "End Date": "2025-11-05", "County": "El Dorado", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.edcgov.us/", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-11-07", "End Date": "2025-11-10", "County": "Sonoma", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://sonomacounty.ca.gov/", "Notes": "Biennial sale"},
    {"Year": 2025, "Start Date": "2025-11-13", "End Date": "2025-11-13", "County": "Nevada", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.nevadacountyca.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2025, "Start Date": "2025-11-14", "End Date": "2025-11-17", "County": "Calaveras", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://calaverasgov.us", "Notes": "Main annual sale"},

    # --- 2026 AUCTIONS ---
    {"Year": 2026, "Start Date": "2026-01-06", "End Date": "2026-01-06", "County": "Merced", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.merced.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-01-26", "End Date": "2026-01-26", "County": "Calaveras", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://calaverasgov.us", "Notes": "Re-offer carry-over"},
    {"Year": 2026, "Start Date": "2026-02-20", "End Date": "2026-02-23", "County": "Imperial", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://treasurer-taxcollector.imperialcounty.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-02-20", "End Date": "2026-02-20", "County": "Yuba", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.yuba.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-02-23", "End Date": "2026-02-25", "County": "Sacramento", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://sacramento.mytaxsale.com", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-02-25", "End Date": "2026-02-25", "County": "Contra Costa", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.cctax.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-02-27", "End Date": "2026-02-27", "County": "Shasta", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.shastacounty.gov/tax-collector", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-03-03", "End Date": "2026-03-03", "County": "Tulare", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://tularecounty.ca.gov/treasurertaxcollector/", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-03-09", "End Date": "2026-03-11", "County": "Amador", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.amadorgov.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-03-11", "End Date": "2026-03-12", "County": "San Joaquin", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.sjgov.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-03-13", "End Date": "2026-03-18", "County": "San Diego", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://sdttc.mytaxsale.com", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-03-20", "End Date": "2026-03-23", "County": "Alameda", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.acgov.org/treasurer/", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-03-20", "End Date": "2026-03-20", "County": "Lake", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.lakecountyca.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-03-27", "End Date": "2026-03-27", "County": "Shasta", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.shastacounty.gov/tax-collector", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-04-18", "End Date": "2026-04-21", "County": "Los Angeles", "Platform": "GovEase", "Sale Type": "Main (2026A)", "Status": "Completed", "Portal URL": "https://ttc.lacounty.gov", "Notes": "2026A Spring auction"},
    {"Year": 2026, "Start Date": "2026-04-23", "End Date": "2026-04-28", "County": "Riverside", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.countytreasurer.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-05-08", "End Date": "2026-05-12", "County": "Ventura", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.ventura.org/ttc/", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-05-08", "End Date": "2026-05-11", "County": "Siskiyou", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.siskiyou.ca.us", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-05-08", "End Date": "2026-05-13", "County": "San Diego", "Platform": "MyTaxSale", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://sdttc.mytaxsale.com", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-05-08", "End Date": "2026-05-11", "County": "Tuolumne", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.tuolumnecounty.ca.gov", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-05-11", "End Date": "2026-05-14", "County": "Madera", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://maderacounty.com", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-05-15", "End Date": "2026-05-18", "County": "Alameda", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.acgov.org/treasurer/", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-05-15", "End Date": "2026-05-18", "County": "Lassen", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.lassencounty.gov", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-05-15", "End Date": "2026-05-18", "County": "Yolo", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.yolocounty.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-05-15", "End Date": "2026-05-15", "County": "Del Norte", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.del-norte.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-05-18", "End Date": "2026-05-20", "County": "Stanislaus", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.stancounty.com", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-05-19", "End Date": "2026-05-19", "County": "Tulare", "Platform": "GovEase", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://tularecounty.ca.gov/treasurertaxcollector/", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-05-29", "End Date": "2026-05-29", "County": "Humboldt", "Platform": "GovEase", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://humboldtgov.org", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-06-05", "End Date": "2026-06-08", "County": "Butte", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.buttecounty.net", "Notes": "Main annual sale"},
    {"Year": 2026, "Start Date": "2026-06-06", "End Date": "2026-06-09", "County": "Los Angeles", "Platform": "GovEase", "Sale Type": "Main (2026B)", "Status": "Completed", "Portal URL": "https://ttc.lacounty.gov", "Notes": "2026B Summer auction"},
    {"Year": 2026, "Start Date": "2026-06-12", "End Date": "2026-06-15", "County": "Modoc", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.co.modoc.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-06-12", "End Date": "2026-06-15", "County": "Siskiyou", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.co.siskiyou.ca.us", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-06-12", "End Date": "2026-06-15", "County": "Tuolumne", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.tuolumnecounty.ca.gov", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-06-12", "End Date": "2026-06-15", "County": "Lassen", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "Completed", "Portal URL": "https://www.lassencounty.gov", "Notes": "Re-offer sale"},
    {"Year": 2026, "Start Date": "2026-06-18", "End Date": "2026-06-18", "County": "Solano", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://solano.mytaxsale.com", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-07-11", "End Date": "2026-07-17", "County": "San Bernardino", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "Completed", "Portal URL": "https://www.sbcountyatc.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-08-06", "End Date": "2026-08-06", "County": "Mariposa", "Platform": "In-Person", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.mariposacounty.org", "Notes": "Courthouse steps sale"},
    {"Year": 2026, "Start Date": "2026-08-07", "End Date": "2026-08-10", "County": "Butte", "Platform": "Bid4Assets", "Sale Type": "Re-offer", "Status": "UPCOMING - TOP TARGET", "Portal URL": "https://www.buttecounty.net", "Notes": "104 active parcels ($5.05M total default)"},
    {"Year": 2026, "Start Date": "2026-09-10", "End Date": "2026-09-11", "County": "Fresno", "Platform": "Realauction", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.co.fresno.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-09-14", "End Date": "2026-09-16", "County": "Kern", "Platform": "GovEase", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.kcttc.co.kern.ca.us", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-10-21", "End Date": "2026-10-21", "County": "Placer", "Platform": "In-Person", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.placer.ca.gov", "Notes": "Courthouse steps sale"},
    {"Year": 2026, "Start Date": "2026-10-15", "End Date": "2026-10-31", "County": "San Benito", "Platform": "GovEase", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.cosb.us", "Notes": "Fall annual sale"},
    {"Year": 2026, "Start Date": "2026-11-05", "End Date": "2026-11-05", "County": "Nevada", "Platform": "GovEase", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.nevadacountyca.gov", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-11-06", "End Date": "2026-11-06", "County": "El Dorado", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://www.edcgov.us/", "Notes": "Annual tax-defaulted sale"},
    {"Year": 2026, "Start Date": "2026-11-13", "End Date": "2026-11-16", "County": "Calaveras", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "UPCOMING", "Portal URL": "https://calaverasgov.us", "Notes": "Main annual sale"},

    # --- 2027 & PERIODIC / AS-NEEDED SCHEDULES ---
    {"Year": 2027, "Start Date": "2027-02-15", "End Date": "2027-02-18", "County": "Sacramento", "Platform": "MyTaxSale", "Sale Type": "Main", "Status": "TENTATIVE 2027", "Portal URL": "https://sacramento.mytaxsale.com", "Notes": "Expected Feb 2027"},
    {"Year": 2027, "Start Date": "2027-02-19", "End Date": "2027-02-19", "County": "Yuba", "Platform": "GovEase", "Sale Type": "Main", "Status": "TENTATIVE 2027", "Portal URL": "https://www.yuba.org", "Notes": "Expected Feb 2027"},
    {"Year": 2027, "Start Date": "2027-05-10", "End Date": "2027-05-13", "County": "Madera", "Platform": "Bid4Assets", "Sale Type": "Main", "Status": "TENTATIVE 2027", "Portal URL": "https://maderacounty.com", "Notes": "Expected May 2027"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "Tehama", "Platform": "GovEase / Bid4Assets", "Sale Type": "Main", "Status": "TENTATIVE 2027", "Portal URL": "https://tehama.ca.us", "Notes": "Expected H1 2027"},
    
    # 21 Periodic / Biennial / As-Needed Counties
    {"Year": 2027, "Start Date": "2027-05-01", "End Date": "2027-05-05", "County": "Monterey", "Platform": "Bid4Assets", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.co.monterey.ca.us", "Notes": "Periodic sales (Last: May 2024)"},
    {"Year": 2027, "Start Date": "2027-06-01", "End Date": "2027-06-05", "County": "Santa Barbara", "Platform": "Bid4Assets", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.countyofsb.org", "Notes": "Periodic sales (Last: Jun 2024)"},
    {"Year": 2027, "Start Date": "2027-05-01", "End Date": "2027-05-05", "County": "Mendocino", "Platform": "Bid4Assets", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.mendocinocounty.org", "Notes": "Periodic sales (Last: May 2024)"},
    {"Year": 2027, "Start Date": "2027-05-01", "End Date": "2027-05-05", "County": "Kings", "Platform": "Bid4Assets", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://countyofkings.com", "Notes": "Periodic sales (Last: May 2024)"},
    {"Year": 2027, "Start Date": "2027-05-01", "End Date": "2027-05-05", "County": "Napa", "Platform": "Bid4Assets/GovEase", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.countyofnapa.org", "Notes": "Periodic sales (Last: May 2024)"},
    {"Year": 2027, "Start Date": "2027-05-01", "End Date": "2027-05-05", "County": "Sutter", "Platform": "Bid4Assets", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.suttercounty.org", "Notes": "Periodic sales (Last: May 2024)"},
    {"Year": 2027, "Start Date": "2027-05-01", "End Date": "2027-05-05", "County": "Trinity", "Platform": "Bid4Assets", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.trinitycounty.org", "Notes": "Periodic sales (Last: May 2024)"},
    {"Year": 2027, "Start Date": "2027-05-28", "End Date": "2027-06-01", "County": "San Luis Obispo", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://www.slocounty.ca.gov", "Notes": "Biennial sales (Last: May 30-Jun 2, 2025)"},
    {"Year": 2027, "Start Date": "2027-11-05", "End Date": "2027-11-08", "County": "Sonoma", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://sonomacounty.ca.gov/", "Notes": "Biennial sales (Last: Nov 7-10, 2025)"},
    {"Year": 2027, "Start Date": "2027-10-25", "End Date": "2027-10-27", "County": "Colusa", "Platform": "GovEase", "Sale Type": "Periodic", "Status": "PERIODIC / AS-NEEDED", "Portal URL": "https://www.countyofcolusaca.gov", "Notes": "As-needed sales (MPTS / Last: Oct 2024)"},
    {"Year": 2027, "Start Date": "2027-10-27", "End Date": "2027-10-29", "County": "Glenn", "Platform": "GovEase", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://www.countyofglenn.net", "Notes": "Biennial sales (Last: Oct 29-31, 2025)"},
    {"Year": 2027, "Start Date": "2027-06-18", "End Date": "2027-06-22", "County": "Plumas", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://www.plumascounty.us", "Notes": "Biennial sales (Last: Jun 19-23 & Sep 5-8, 2025)"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "Alpine", "Platform": "In-Person/Bid4Assets", "Sale Type": "Sporadic", "Status": "SPORADIC SCHEDULE", "Portal URL": "https://www.alpinecountyca.gov", "Notes": "Sporadic mountain county sales"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "Inyo", "Platform": "Bid4Assets", "Sale Type": "Sporadic", "Status": "SPORADIC SCHEDULE", "Portal URL": "https://www.inyocounty.us", "Notes": "Sporadic mountain county sales"},
    {"Year": 2026, "Start Date": "2026-11-15", "End Date": "2026-11-18", "County": "Mono", "Platform": "Bid4Assets", "Sale Type": "Sporadic", "Status": "SPORADIC SCHEDULE", "Portal URL": "https://www.monocounty.ca.gov", "Notes": "Sporadic mountain sales (Last: Nov 14, 2023)"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "Sierra", "Platform": "In-Person", "Sale Type": "Sporadic", "Status": "SPORADIC SCHEDULE", "Portal URL": "https://www.sierracounty.ca.gov", "Notes": "Sporadic mountain county sales"},
    {"Year": 2027, "Start Date": "2027-02-15", "End Date": "2027-02-18", "County": "Marin", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://www.marincounty.org", "Notes": "Biennial coastal sales (Last: Feb 2025)"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "San Francisco", "Platform": "Bid4Assets/GovEase", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://sftreasurer.org", "Notes": "Biennial sales (Last: May 2025)"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "San Mateo", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://tax.smcgov.org", "Notes": "Biennial sales (Last: May 2025)"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "Santa Clara", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://www.sccgov.org", "Notes": "Biennial sales (Last: May 2025)"},
    {"Year": 2027, "Start Date": "2027-05-15", "End Date": "2027-05-18", "County": "Santa Cruz", "Platform": "Bid4Assets", "Sale Type": "Biennial", "Status": "BIENNIAL SCHEDULE", "Portal URL": "https://www.co.santa-cruz.ca.us", "Notes": "Biennial sales (Last: May 2025)"},
]

def build_excel_calendar():
    df_master = pd.DataFrame(MASTER_AUCTIONS)
    
    # Save CSV
    df_master.to_csv(OUT_CSV, index=False)
    print(f"Master CSV saved: {OUT_CSV} ({len(df_master)} rows)")

    # Build Multi-Tab Formatted Excel Workbook
    wb = openpyxl.Workbook()
    
    # Styles
    font_header = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    fill_navy = PatternFill(start_color="1F3A5F", end_color="1F3A5F", fill_type="solid")
    fill_gold = PatternFill(start_color="FFEBC8", end_color="FFEBC8", fill_type="solid")
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
    font_bold = Font(name="Calibri", size=11, bold=True)
    align_center = Alignment(horizontal="center", vertical="center")
    align_left = Alignment(horizontal="left", vertical="center")
    border_thin = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1")
    )

    # Tab 1: Master Calendar (All starting 2025)
    ws1 = wb.active
    ws1.title = "Master Calendar (2025-2027)"
    
    # Tab 2: 2025 Auctions
    ws2 = wb.create_sheet(title="2025 Auctions")
    
    # Tab 3: 2026 Auctions
    ws3 = wb.create_sheet(title="2026 Auctions")
    
    # Tab 4: 2027 & Periodic
    ws4 = wb.create_sheet(title="2027 & Periodic Schedule")

    tabs = [
        (ws1, df_master),
        (ws2, df_master[df_master["Year"] == 2025]),
        (ws3, df_master[df_master["Year"] == 2026]),
        (ws4, df_master[df_master["Year"] == 2027]),
    ]

    for ws, df_tab in tabs:
        ws.views.sheetView[0].showGridLines = True
        
        # Add headers
        headers = list(df_tab.columns)
        ws.append(headers)
        
        for col_num in range(1, len(headers) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.font = font_header
            cell.fill = fill_navy
            cell.alignment = align_center
            
        # Add rows
        for r_idx, row_data in enumerate(df_tab.values, start=2):
            ws.append(list(row_data))
            
            status_val = str(row_data[6]) # Status column
            is_target = "TOP TARGET" in status_val or "UPCOMING" in status_val
            
            for col_num in range(1, len(headers) + 1):
                cell = ws.cell(row=r_idx, column=col_num)
                cell.border = border_thin
                
                # Column specific alignment
                if col_num in (1, 2, 3, 7): # Year, Start, End, Status
                    cell.alignment = align_center
                else:
                    cell.alignment = align_left
                    
                # Highlighting
                if "TOP TARGET" in status_val:
                    cell.fill = fill_gold
                    if col_num == 4 or col_num == 7:
                        cell.font = font_bold
                elif r_idx % 2 == 0:
                    cell.fill = fill_zebra
                    
        # Auto-fit column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

    wb.save(OUT_XLSX)
    print(f"Master Excel Workbook saved: {OUT_XLSX}")

if __name__ == "__main__":
    build_excel_calendar()
