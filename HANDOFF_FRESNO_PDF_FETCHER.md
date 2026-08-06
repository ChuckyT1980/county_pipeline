# Handoff: Fresno Excess-Proceeds PDF Fetcher + Parser

**Owner:** Chuck Terrell / Logic Flow Systems
**Contact:** mrt@logicflowsystems.io
**Started:** 2026-07-31

## Objective

Fetch two Fresno County tax-auction result PDFs (Akamai-protected, blocks curl)
using Playwright, then parse them into a structured CSV of real APN + sale price
+ excess proceeds. This gives us real Fresno historical auction data.

## Business context

- The Fresno pipeline currently has synthetic excess-proceeds data (from an earlier
  agent's `run_excess_finder.py` that used `sold_price = min_bid * 1.4` heuristic).
- Real Fresno auction results exist as public PDFs on fresnocountyca.gov.
- fresnocountyca.gov is protected by Akamai edge WAF; curl / requests get 403.
- Playwright with a real Chromium browser bypasses Akamai.
- Once we have real historical Fresno results, we can:
    - Replace the synthetic excess-proceeds pipeline with real data
    - Identify parcels likely to be on the Sept 2026 re-offer list (34 parcels)
    - Use real winning bids as calibration data for future scoring

## The two PDFs to fetch

1. `https://www.fresnocountyca.gov/files/assets/county/v/1/auditor-controller-treasurer-tax-collector/forms/list-of-sales-and-excess-proceeds.pdf`
2. `https://www.fresnocountyca.gov/files/assets/county/v/2/auditor-controller-treasurer-tax-collector/tax-sale-amp-excess-proceeds/march-27-28-april-4-2025-excess-proceed-list.pdf`

## Existing infrastructure

- **Playwright + Chromium already installed** (see `pip list | grep playwright` — done on 2026-07-30)
- **Scaffold file:** `fresno/fresno_per_apn_playwright.py` — copy this pattern for the PDF fetcher
- **Session directory pattern:** `fresno/.playwright_session/` for persistent context (bypasses Akamai after first success)

## Expected sample data format in these PDFs

Sample line already known:
```
ITEM SALES EXCESS
NO. APN PRICE PROCEEDS
13 090-101-15 3,500.00 1,231.97
```

Fields per row:
- ITEM_NO (sequential number in that auction)
- APN (Fresno format: XXX-XXX-XX)
- SALES_PRICE (winning bid at auction)
- EXCESS_PROCEEDS (SALES_PRICE minus minimum bid — belongs to former owner)

## First deliverable

**Script `fresno/fresno_fetch_and_parse_results.py`** that:
1. Uses Playwright to download both PDFs into `fresno/downloaded_pdfs/`
2. Parses each PDF with pdfplumber
3. Writes combined output to `fresno/fresno_historical_sales.csv` with columns:
   - source_pdf (which PDF row came from)
   - auction_date (parse from PDF or filename)
   - item_no
   - apn (normalized to XXX-XXX-XX-000-0 5-part format so it joins with FC_PARCEL_SELECT)
   - sales_price (float)
   - excess_proceeds (float)
   - min_bid (derived: sales_price - excess_proceeds)

## Second deliverable

Update `excess_proceeds/run_excess_finder.py` to use real data:
- Remove the `sold_price = min_bid * 1.4` heuristic (line ~45)
- Read from `fresno/fresno_historical_sales.csv` for Fresno inputs
- Only produce excess-proceeds rows where we have REAL sales data
- Do NOT fabricate data for missing parcels

## Do NOT

- Do NOT touch any Butte files (another agent is fixing Butte QA in parallel)
- Do NOT modify `fresno/fresno_per_apn_pull.py` (working scraper — leave alone)
- Do NOT invent data if PDF parsing fails on some rows — log them and skip
- Do NOT try to bypass Akamai without Playwright — it doesn't work (already tested)
- Do NOT enumerate all Fresno parcels — that's a different task
- Do NOT commit `.playwright_session/` to git (add to .gitignore if not already)

## Escalate to Chuck if

- PDF format is different from the sample line above (may require different parsing)
- Akamai still blocks even with Playwright (unlikely but possible)
- PDFs published dates are older than 6 months (may not represent current auction patterns)

## Test with

Once done, verify with:
```
head -20 fresno/fresno_historical_sales.csv
python -c "import pandas as pd; df=pd.read_csv('fresno/fresno_historical_sales.csv'); print(f'{len(df)} rows, {df[\"excess_proceeds\"].sum():,.0f} total excess')"
```

## Related context

- Fresno's Sept 10-11, 2026 auction has 161 parcels (127 new + 34 re-offer). Re-offer APNs
  are the ones that appeared in prior sales but didn't sell — these are the highest-value
  cross-reference candidates from the historical data.
- Full pipeline reference: `butte/package_delivery.py` shows how Butte's pack is assembled
  end-to-end. Fresno will follow the same pattern once the Notice of Sale drops (~Aug 20-26).
