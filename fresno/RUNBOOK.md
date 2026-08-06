# Fresno Pipeline Runbook

**How to run the full Fresno tax auction intelligence pipeline yourself, without me.**

## What this pipeline does

Turns Fresno County's public data into a sellable per-parcel dossier pack, using only public sources (no paid data, no AI dependency).

**Stages:**
1. Fetch the Notice of Impending Power to Sell PDF (once/year, via Playwright)
2. Parse the PDF into a candidate APN list (thousands of parcels)
3. Enrich each candidate via the Fresno public assessor ArcGIS
4. Filter by auction signals (absentee, no HOX, value threshold)
5. Cross-reference against the Sept 10-11 Notice of Sale (when it publishes)
6. Build dossiers

**One command runs the whole thing:**
```
python run_fresno_pipeline.py --stage all
```

Or run individual stages if something fails:
```
python run_fresno_pipeline.py --stage 1_fetch_pts
python run_fresno_pipeline.py --stage 2_parse_pts
python run_fresno_pipeline.py --stage 3_enrich
python run_fresno_pipeline.py --stage 4_filter
python run_fresno_pipeline.py --stage 5_crossref  # when Notice of Sale drops
python run_fresno_pipeline.py --stage 6_dossiers
```

## What each stage produces

| Stage | Input | Output | Time |
|---|---|---|---|
| 1 | (none) | `downloaded_pdfs/fresno_pts_2026.pdf` | ~30 sec (Playwright) |
| 2 | PDF from stage 1 | `fresno_pts_candidates.csv` (2k-5k APNs) | ~10 sec |
| 3 | candidates from stage 2 | `fresno_pts_enriched.csv` (with owner/situs/values) | ~30-60 min |
| 4 | enriched from stage 3 | `fresno_auction_likely.csv` (filtered shortlist) | ~5 sec |
| 5 | actual Notice of Sale + our enriched pool | `fresno_auction_final.csv` (161 confirmed APNs enriched) | ~2 min |
| 6 | final list from stage 5 | dossier PDFs + Excel + zip | ~5 min |

## First-time setup (one-time only)

1. Confirm Python 3.11+ and pip are installed
2. Install requirements:
   ```
   pip install requests pandas pdfplumber fpdf2 playwright
   playwright install chromium
   ```
3. Run the Playwright session setup (opens a visible browser once so you can solve any CAPTCHA if Fresno challenges it):
   ```
   python run_fresno_pipeline.py --setup
   ```

That's it. After first-time setup, everything is automated.

## What to do when something breaks

**Stage 1 fails (can't download PDF)**
- Fresno might have moved the URL. Look on `fresnocountyca.gov` for "Notice of Impending Power to Sell" or "Notice of Sale."
- Update the URL in `run_fresno_pipeline.py` (constant `PTS_PDF_URL`)
- Re-run stage 1

**Stage 3 hits rate limits (403 errors)**
- Fresno's ArcGIS started throttling. Wait 15 minutes, then re-run.
- Or edit `run_fresno_pipeline.py` and increase the `--delay` parameter to 1.0 or 2.0 seconds.

**Notice of Sale (stage 5) drops**
- Fresno publishes it ~Aug 20-27 for Sept auctions.
- Download the Notice of Sale PDF manually (or run stage 1 again if URL is the same).
- Save as `downloaded_pdfs/fresno_notice_of_sale_YYYY.pdf`.
- Run stage 5.

## Adding a new county

Once Fresno is proven, the same pattern applies to Kern, Nevada, San Benito, etc.

To add a new county:
1. Create `<county>/run_<county>_pipeline.py` from the Fresno template
2. Change 3 things: PDF source URL, ArcGIS endpoint, output naming
3. Run the pipeline

Full instructions in `docs/ADD_NEW_COUNTY.md` (to be built after Fresno ships).

## Files this pipeline creates

```
fresno/
  downloaded_pdfs/
    fresno_pts_2026.pdf              # Stage 1
    fresno_notice_of_sale_2026.pdf   # Stage 5
  fresno_pts_candidates.csv          # Stage 2
  fresno_pts_enriched.csv            # Stage 3
  fresno_auction_likely.csv          # Stage 4
  fresno_auction_final.csv           # Stage 5
  delivery/
    fresno_auction_YYYY-MM-DD/       # Stage 6 output
      *.pdf, *.xlsx, *.csv, dossiers/
      fresno_auction_intel_YYYY-MM-DD.zip
```

## What to do if I'm not around

You have everything to run this yourself. The scripts are documented, the runbook explains the stages, and the failure modes are covered above. If any stage produces unexpected output, look at the CSV or the raw PDF — the data is right there, no black boxes.

## The one thing you'll always need to check manually

Verify the top 10-20 output APNs make sense. Every county's data has edge cases (subdivisions, exempt parcels, weird formats). A 5-minute spot-check before shipping catches issues no automated test would.
