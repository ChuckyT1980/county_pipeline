"""
Build real Tulare excess-proceeds claim dossiers from the county's own
official "March 3, 2026 Tax Auction Excess Proceeds Report" — real
assessee names AND real dollar amounts together (better than both
Humboldt and Shasta, which each only had one of the two). Fetched via
a stealth browser (triggers a direct file download, no page render) from
tc-web.widen.net/s/sbwzrsn592/2026-excess-proceeds-amounts-available,
linked from the county's official 2026 Excess Proceeds page
(tularecounty.ca.gov/auditor/2026-excess-proceeds), 2026-08-07.

Claim deadline is an APPROXIMATION (sale date + 365 days) — exact deed
recordation date not published in this specific report; real deadline
is 1yr after deed recordation, which is typically shortly after the
sale, so true deadline is >= the date used here, same caveat as
Humboldt.
"""
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

SALE_DATE = "2026-03-03"
APPROX_CLAIM_DEADLINE = "2027-03-03"

# Source: tc-web.widen.net/s/sbwzrsn592/2026-excess-proceeds-amounts-available,
# extracted verbatim via pypdf 2026-08-07. (item, apn, assessee, excess)
RECORDS = [
    (34, "093-083-020-000", "STALLINGS L D & JULIE A", 51465.68),
    (35, "094-074-015-000", "GUTIERREZ ERMINIA R, GUTIERREZ OSCAR A, MOORE ROSA LINDA", 10016.01),
    (55, "135-104-011-000", "STRAWN ALEENE", 1075.58),
    (76, "247-030-043-000", "MATHFALLU AMAR SINGH", 8276.44),
    (79, "260-182-016-000", "CAMPOS VINCENTE", 2344.21),
    (89, "307-100-046-000", "HOMER RODNEY P (TR FAM BYPASS TR)", 2765.58),
    (90, "310-100-001-000", "IRELAN VIRGINIA D (EST OF)", 718.69),
    (91, "310-100-002-000", "IRELAN VIRGINIA D (EST OF)", 12375.22),
    (104, "345-294-016-000", "FUHRMEISTER RONALD & MARY", 1665.96),
]


def main():
    total = 0.0
    generated = 0
    for item, apn, assessee, excess in RECORDS:
        total += excess
        claim_data = {
            "apn_dash": apn,
            "owner": assessee,
            "excess_proceeds": excess,
            "claim_deadline": APPROX_CLAIM_DEADLINE,
            "deed_status": f"sold_at_auction_{SALE_DATE}",
            "source_file": (
                f"Tulare County official March 3, 2026 Tax Auction Excess Proceeds "
                f"Report (item #{item}) — Auditor-Controller/Treasurer-Tax Collector "
                f"Cass Cook — tc-web.widen.net/s/sbwzrsn592/2026-excess-proceeds-amounts-available"
            ),
            "verification": (
                "VERIFIED — assessee name AND excess proceeds amount are both from the "
                "county's own official auction excess-proceeds report, not estimated. "
                "Claim deadline shown is an APPROXIMATION (sale date + 365 days); real "
                "statutory deadline is 1 year after Tax Collector's deed recordation "
                "(not published in this report) — true deadline is >= the date shown."
            ),
        }
        report_builder.build_excess_proceeds_report(claim_data, "tulare")
        generated += 1

    print(f"\nGenerated {generated} real, government-sourced Tulare excess-proceeds dossiers.")
    print(f"Total excess proceeds across all {generated} parcels: ${total:,.2f}")


if __name__ == "__main__":
    main()
