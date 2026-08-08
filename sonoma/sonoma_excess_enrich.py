"""
Build real Sonoma excess-proceeds leads from the county's own public
auction RESULTS table (not a separate excess-proceeds notice - Sonoma
doesn't publish one with parcel-level detail; this is the actual
per-parcel outcome table embedded directly on the county's own auction
results page):
sonomacounty.gov/.../tax-defaulted-property-auctions/auction-2025-11

Real APN, real former owner (Last Assessee - the actual excess-proceeds
claimant), real minimum bid, real final sale price for the 18 of 57
parcels that sold above minimum bid. Auction: Nov 7-10, 2025.

IMPORTANT HONESTY NOTE: "potential_excess" here is sale price minus
minimum bid, which is a reasonable ESTIMATE (minimum bid is set to
approximate amount owed) but is NOT the exact legal excess-proceeds
figure - the real figure subtracts ALL taxes, penalties, and costs of
sale, which can differ slightly from the published minimum bid. Labeled
as an estimate, not a confirmed amount, in every dossier.

Claim deadline: 1 year from deed recordation. Deed recordation date not
individually published per parcel here; sale was Nov 7-10, 2025, so an
approximate deadline of Nov 10, 2026 is used (recordation is typically
within weeks of sale) - REAL DEADLINE IS LIKELY SLIGHTLY LATER, treat
this as the outer bound to act before, not exact.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

SCRATCH = "/tmp/claude-1000/-home-chuck/e8fa5be3-9aea-4fd1-9c7a-07ad25a9bdf2/scratchpad"
SRC = f"{SCRATCH}/sonoma_nov2025_parsed.csv"
APPROX_DEADLINE = "2026-11-10"


def main():
    with open(SRC, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    sold = [r for r in rows if r["status"] == "Sold" and r.get("sold_amount")]

    generated = 0
    total_estimate = 0.0
    for r in sold:
        estimate = float(r["potential_excess_over_min_bid"])
        total_estimate += estimate
        claim_data = {
            "apn_dash": r["apn"],
            "owner": r["last_assessee"],
            "excess_proceeds": estimate,
            "claim_deadline": APPROX_DEADLINE,
            "deed_status": f"sold_at_auction_2025-11-07_to_2025-11-10_${float(r['sold_amount']):,.0f}",
            "source_file": (
                "Sonoma County official auction results table (public, embedded on the county's own "
                "auction results page) - sonomacounty.gov Tax-Defaulted Property Auction, November 2025"
            ),
            "verification": (
                f"VERIFIED SALE DATA — real minimum bid (${float(r['min_bid']):,.2f}) and real final sale "
                f"price (${float(r['sold_amount']):,.2f}) are both from the county's own published results "
                f"table, not estimated. Excess proceeds amount shown IS AN ESTIMATE (sale price minus "
                f"minimum bid) — minimum bid approximates amount owed but the exact legal excess-proceeds "
                f"figure (which subtracts all taxes/penalties/costs) may differ slightly; not yet confirmed "
                f"by a county-issued excess-proceeds notice. Claim deadline shown is APPROXIMATE (sale date "
                f"+ ~1yr); real deadline is 1yr after deed recordation, not individually published per parcel."
            ),
        }
        report_builder.build_excess_proceeds_report(claim_data, "sonoma")
        generated += 1

    print(f"\nGenerated {generated} real Sonoma excess-proceeds leads (of 57 total auction results, "
          f"18 sold above minimum bid; {len(rows)-len(sold)-3} redeemed, 3 withdrawn, 0 no-bid).")
    print(f"Total estimated excess proceeds across all {generated}: ${total_estimate:,.2f} (estimate, not confirmed)")


if __name__ == "__main__":
    main()
