"""
Build real San Joaquin excess-proceeds dossiers from the county's own
official "Tax Sale Excess Proceeds List, March 11-12, 2026" (updated
April 8, 2026) — sjgov.org/docs/.../tax-sale-excess-proceeds-list-march-2026-public.pdf

Real names AND real amounts together, same gold-standard pattern as
Tulare tonight. Only 3 real line items on this list, extracted verbatim
via pypdf 2026-08-08.

Claim deadline: 1 year from deed recordation. Deed recordation date not
individually published per parcel; sale was March 11-12, 2026, so an
approximate deadline of March 12, 2027 is used (real deadline is likely
slightly later since recordation trails the sale by some weeks).
"""
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

APPROX_DEADLINE = "2027-03-12"

# (item, apn, default_number, previous_owner, situs, redemption_amount, purchase_price, excess_proceeds)
RECORDS = [
    (2, "027-134-130-000", "DEF-200-000-183", "LODUCA, SHANNON TR", "2101 CABRILLO CI, LODI",
     32916.66, 427500.00, 394583.34),
    (65, "147-220-110-000", "DEF-200-001-815", "STRONG CAPITAL V LP", None,
     20459.96, 69077.00, 48617.04),
    (66, "149-170-110-000", "DEF-200-001-844", "OWP PHASE II LP", "440 E WEBER AVE., STOCKTON",
     56767.23, 57500.00, 732.77),
]


def main():
    total = 0.0
    generated = 0
    for item, apn, default_num, owner, situs, redemption, purchase, excess in RECORDS:
        total += excess
        claim_data = {
            "apn_dash": apn,
            "owner": owner,
            "situs": situs,
            "excess_proceeds": excess,
            "claim_deadline": APPROX_DEADLINE,
            "doc_number": default_num,
            "deed_status": f"sold_at_auction_2026-03-11_to_2026-03-12_purchase_${purchase:,.2f}_redemption_${redemption:,.2f}",
            "source_file": (
                f"San Joaquin County official Tax Sale Excess Proceeds List, March 11-12, 2026 "
                f"(updated April 8, 2026), item #{item} — sjgov.org/docs/default-source/"
                f"treasurer---tax-collector-documents/excess-proceeds/"
            ),
            "verification": (
                f"VERIFIED — previous owner name, redemption amount (${redemption:,.2f}), purchase price "
                f"(${purchase:,.2f}), and excess proceeds (${excess:,.2f}) are ALL directly from the county's "
                f"own official published list, not estimated or computed. Claim deadline shown is an "
                f"APPROXIMATION (sale date + ~1yr); real deadline is 1yr after deed recordation, not "
                f"individually published per parcel here."
            ),
        }
        report_builder.build_excess_proceeds_report(claim_data, "san_joaquin")
        generated += 1

    print(f"\nGenerated {generated} real, government-sourced San Joaquin excess-proceeds dossiers.")
    print(f"Total excess proceeds across all {generated}: ${total:,.2f}")


if __name__ == "__main__":
    main()
