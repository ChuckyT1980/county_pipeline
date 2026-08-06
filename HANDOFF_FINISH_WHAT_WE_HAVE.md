# Handoff: Finish Fresno Dossiers + Excess Proceeds MVP

**Owner:** Chuck Terrell / Logic Flow Systems
**Contact:** mrt@logicflowsystems.io
**Date:** 2026-07-31
**Scope discipline:** Finish what's already been built. DO NOT expand to NOD monitoring, probate, code enforcement, or new counties. Those are Q4.

## Business context

- Butte pack (105 parcels) is production quality and shipping.
- Butte marketplace HTML page exists at `marketplace/index.html` — 90 tiles with mailto: $99 order buttons. Ready to deploy to Netlify.
- Fresno per-APN scraper works (100% hit rate with suffix fallback).
- Fresno historical sales data (48 real records with $3.17M in real excess proceeds) is parsed and available.
- Excess proceeds is a real revenue stream — 10% contingency of real dollar recoveries.
- Chuck is cash-constrained; every deliverable should be shippable, not aspirational.

## Two deliverables

### Deliverable 1: Fresno dossier builder + generate 48 dossiers from historical data

**Objective:** Take the 48 real historical Fresno parcels we already have data for, run each through the enrichment scraper, generate dossier PDFs matching the Butte format. This gives us real Fresno inventory to add to the marketplace tonight, without waiting for the Sept Notice of Sale.

**Inputs available:**
- `fresno/fresno_historical_sales.csv` — 48 real APN + sale price + excess proceeds records
- `fresno/fresno_per_apn_pull.py` — working per-APN scraper (100% hit rate with suffix fallback)
- `fresno/fresno_stress_test_48.csv` — 33/48 enriched records from earlier stress test (may need re-run with suffix fallback now enabled)
- `butte/build_dossiers.py` — reference dossier PDF generator (Butte-specific but adaptable)

**Steps:**
1. Re-run `fresno_per_apn_pull.py` with the updated suffix-fallback logic against all 48 historical APNs. Should now hit 100%.
2. Fork `butte/build_dossiers.py` into `fresno/build_fresno_dossiers.py`:
   - Change branding: "Fresno County" instead of "Butte County"
   - Change auction date reference (currently Aug 7-10, 2026 for Butte)
   - Adapt field mappings (FC_PARCEL_SELECT columns: NAME1, ADDRESS1, ASSESS_LAND_VAL, etc.)
   - Note: these are HISTORICAL parcels (already sold in prior auctions), so redact the "Aug 7-10, 2026 Auction" language. Frame as "Historical parcel intelligence" or "Reoffered candidates."
3. For each of the 48 parcels, generate a dossier PDF at `fresno/delivery/historical/dossiers/<APN>_<owner>.pdf`
4. Generate an overview PDF summarizing the 48 parcels (like `butte/build_deliverable_pdf.py`)
5. Package into a zip: `fresno/delivery/fresno_historical_pack_YYYY-MM-DD.zip`

**Output expected:**
- 48 dossier PDFs
- 1 overview PDF
- 1 zip deliverable
- Log file summarizing what was generated + any parcels that failed enrichment

**DO NOT:**
- Do NOT fabricate any data. If a field is missing from FC_PARCEL_SELECT, leave it blank on the dossier.
- Do NOT modify Butte files (Butte is done, don't touch it).
- Do NOT add product lines beyond dossier generation. No NOD watching, no probate, no code enforcement.
- Do NOT add these historical Fresno parcels to the marketplace `index.html` yet — those tiles need Chuck's manual review first to confirm they're marketable.

### Deliverable 2: Excess proceeds outreach MVP

**Objective:** Build the machinery to convert the 48 real historical excess proceeds records into a mailing campaign. 10% contingency, $3.17M total excess = ~$317k potential fees at 100% response rate; realistic capture at 5-10% = $15k-$32k.

**Inputs available:**
- `fresno/fresno_historical_sales.csv` — has APN, auction_date, sales_price, excess_proceeds, min_bid for 48 real parcels
- Fresno per-APN scraper — gets FORMER owner name + last known mailing address per APN

**Steps:**
1. Enrich the 48 historical APNs via `fresno_per_apn_pull.py` (may need to check if current NAME1 is the FORMER owner or the new owner post-sale)
2. Look up former owner's mailing address at time of sale. Check the historical PDFs (`fresno/downloaded_pdfs/`) — they may include former owner name and address directly. If yes, use those (more accurate). If not, use current FC_PARCEL_SELECT NAME1/ADDRESS1 (less accurate — post-sale ownership).
3. Create `excess_proceeds/build_recovery_letters.py`:
   - Reads `fresno/fresno_historical_sales.csv`
   - Generates one letter per parcel using a template (see below)
   - Outputs to `excess_proceeds/letters/<APN>_<owner>.pdf`
   - Also generates a mail-merge CSV for USPS shipping label / envelope printing
4. Letter template must include:
   - Recipient name + address
   - Property APN + situs
   - Sale date + sale price + excess proceeds amount owed
   - Explanation of CA R&TC §4675 (former owner has 1 year to claim excess proceeds from date of deed recording)
   - Offer: "We help former owners recover these funds. 10% contingency fee — you pay nothing unless we recover for you."
   - Chuck's contact info (mrt@logicflowsystems.io)
   - Signature block for Chuck
   - Small legal disclaimer: "This is not legal advice. We are not attorneys. We assist with the recovery process."

**Output expected:**
- 48 personalized recovery letters (PDF)
- 1 mail-merge CSV for shipping
- README explaining the mailing workflow (Chuck buys the bond, prints letters, mails them, tracks responses)

**DO NOT:**
- Do NOT actually mail letters (Chuck decides which to send after review)
- Do NOT charge fees automatically or set up payment infrastructure yet
- Do NOT contact former owners without Chuck's explicit approval on the letter content
- Do NOT skip the legal disclaimer or make claims that only an attorney can make

**Legal note for other agent:**
CA R&TC §4675 governs excess proceeds claims. The 1-year window from deed recording is real and strict. Recovery firms operate legally in CA under contingency-fee agreements. Chuck should consult an attorney before starting the mailing, but that's Chuck's call not yours.

## What NOT to do

- Do not build NOD monitoring
- Do not build probate leads
- Do not add new counties beyond Butte + Fresno
- Do not modify the marketplace HTML at `marketplace/index.html` (it's dialed in for Butte)
- Do not modify any Butte files
- Do not attempt to bypass Akamai on kerncounty.com or fresnocountyca.gov beyond what Playwright already handles

## Files you should touch (green light)

```
fresno/build_fresno_dossiers.py       (new — mirror butte/build_dossiers.py)
fresno/delivery/historical/            (new — dossier output dir)
excess_proceeds/build_recovery_letters.py  (new)
excess_proceeds/letters/               (new — letter output)
excess_proceeds/letter_template.md     (new — template Chuck reviews first)
excess_proceeds/mail_merge.csv         (new — for envelope printing)
```

## Files you should NOT touch (hands off)

```
butte/                                 (done — leave alone)
marketplace/                           (done — leave alone)
verification/                          (working — leave alone)
data/, lead_magnet/, monitor/          (other agent's earlier work)
tax_pipeline/                          (legacy, don't disturb)
```

## Escalate to Chuck if

- Fresno per-APN scraper fails on more than 5% of historical APNs (may indicate schema change)
- The historical PDF former-owner names look wrong / redacted / suspicious
- Excess proceeds letter template raises legal red flags
- Any deliverable requires Chuck's identity (bond purchase, mailing account, etc.)
- You want to expand scope beyond these two deliverables (don't — escalate first)

## Success criteria (how Chuck knows you're done)

1. Chuck can open `fresno/delivery/historical/` and see 48 dossier PDFs with real data (owner name, mailing, values)
2. Chuck can open `excess_proceeds/letters/` and see 48 personalized recovery letters
3. A `mail_merge.csv` exists that maps each letter to a recipient address for envelope printing
4. Zero fabricated data in any output
5. A brief README in each output directory explaining what's there and how Chuck uses it

## Order of operations

Do Deliverable 1 first (Fresno dossiers). It's a straightforward extension of existing infrastructure and produces the biggest immediate confidence signal — Chuck sees real Fresno dossiers with real data.

Then Deliverable 2 (excess proceeds letters). This has real regulatory nuance so slower + more careful is better than fast + wrong.

Report status to Chuck when each deliverable is complete. Don't wait until both are done to report.
