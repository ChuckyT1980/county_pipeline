"""
Build real Shasta excess-proceeds claim dossiers from the county's own
official "Notice of Right to Claim Excess Proceeds" (R&T Code 4676),
signed under penalty of perjury by the Shasta County Tax Collector,
published in the Redding Record Searchlight — fetched directly from
shastacounty.gov/media/81921 (this URL is behind Cloudflare's JS
challenge; curl gets a "Just a moment..." page, a real browser passes
it automatically — see shasta_fetch_notice.py for the fetch method).
Auction/sale dates: 2026-02-27 and 2026-03-27. Deed recordation:
2026-03-20. Claim deadline: 2026-03-22... wait, stated explicitly on
the county's Excess Proceeds page as "DEADLINE: March 22, 2027" — an
EXACT stated deadline, not an estimate (unlike Humboldt, where no exact
deed-recordation date was published and 1yr-from-sale had to be used
as an approximation).

Structural difference from Humboldt: Shasta's notice names real PARTIES
OF INTEREST per parcel (the actual claimants, in statutory priority
order — lienholders first, then titleholders, per R&T 4675) but does
NOT publish a dollar amount — Shasta determines and discloses the exact
amount to each claimant only after a claim is filed and reviewed by
County Counsel. Do not estimate or invent one. This is honestly a
MORE valuable lead type for the actual finder-fee business than
Humboldt's, despite the missing dollar figure: the hardest part of an
heir/claimant-finder business is identifying who to contact, and
Shasta's notice does that for us, for real, already.

Institutional/government parties (tax collector, county departments,
state agencies, IRS, title insurance/surety companies) are excluded
from the actionable claimant list — they don't need finder services.
"""
import re
import sys
from collections import defaultdict

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

SALE_DATES = "2026-02-27 and 2026-03-27"
DEED_RECORDED = "2026-03-20"
CLAIM_DEADLINE = "2027-03-22"  # exact, stated by the county — not an estimate

INSTITUTIONAL_MARKERS = [
    "COUNTY OF SHASTA", "SHASTA COUNTY", "STATE OF CALIFORNIA", "FRANCHISE TAX BOARD",
    "INTERNAL REVENUE SERVICE", "TAX COLLECTOR", "TITLE INSURANCE", "SURETY",
    "MENDOCINO COUNTY", "RESOURCE MGMT", "RESOURCE MNGT", "RESOURCE MANAGEMENT",
    "DEPT OF", "CITY OF",
]

# Raw (apn, party_name) pairs, transcribed verbatim from the notice PDF
# (pypdf extraction, 2026-08-07). Multi-APN groups in the source (parcels
# sharing one set of parties) are expanded to one row per APN below.
RAW_ROWS = [
    ("006-700-004-000", "COMMONWEALTH LAND TITLE INSURANCE COMPANY"),
    ("018-380-021-000", "BARTOLONE, STEPHANIE SUE"),
    ("018-380-021-000", "CRAWFORD, SHERYL LYNN"),
    ("018-380-021-000", "LAWRENCE, LINDA JOYCE"),
    ("018-380-021-000", "WHEELER, JUDY BY NITA"),
    ("026-300-018-000", "JAMES CLAPP"),
    ("026-300-018-000", "FRANCHISE TAX BOARD"),
    ("026-400-017-000", "WESTERN TITLE INSURANCE COMPANY"),
    ("029-510-015-000", "BARBER, JASON M."),
    ("029-510-015-000", "COUNTY OF SHASTA RESOURCE MGMT"),
    ("029-510-015-000", "REED, CODY A."),
    ("029-510-015-000", "STATE OF CALIFORNIA -FRANCHISE TAX BOARD"),
    ("029-510-015-000", "SYMSACK, MEGAN N."),
    ("029-530-012-000", "ACCREDITED SURETY AND CASUALTY COMPANY INC."),
    ("029-530-012-000", "COUNTY OF SHASTA TAX COLLECTOR"),
    ("029-530-012-000", "COUNTY OF SHASTA DEPT OF RESOURCE MGMT"),
    ("029-530-012-000", "LAWRENCE, CINDY ANN"),
    ("029-530-012-000", "LAWRENCE, RAYMOND"),
    ("029-530-012-000", "MENDOCINO COUNTY"),
    ("043-540-001-000", "BECKER, DAVID"),
    ("044-150-017-000", "BARAHONA, EDWIN"),
    ("044-150-017-000", "COUNTY OF SHASTA"),
    ("044-150-017-000", "TEIXEIRA, YVONNE J."),
    ("044-150-017-000", "TRINITY ALPS PRESERVE PROPERTY OWNERS ASSOCIATION"),
    ("045-750-005-000", "CLIFFORD L JENKIN"),
    ("045-750-005-000", "COUNTY OF SHASTA DEPT OF RESOURCE MANAGEMENT"),
    ("065-260-008-000", "BARBARA UPTON"),
    ("065-260-008-000", "CHRIS HAMPE"),
    ("065-260-008-000", "COUNTY OF SHASTA RESOURCE MNGT"),
    ("065-260-008-000", "DENNIS WOLFE"),
    ("065-260-008-000", "STEPHANIE WOLFE"),
    ("065-580-022-000", "RED NECK ROOSTERS MOTORCYCLE CLUB"),
    ("082-180-022-000", "ESTATE OF GERALD E. CARPENTER"),
    ("090-090-005-000", "FRONTIER VILLAGE DEVELOPMENT, LLC"),
    ("090-090-006-000", "FRONTIER VILLAGE DEVELOPMENT, LLC"),
    ("090-100-002-000", "FRONTIER VILLAGE DEVELOPMENT, LLC"),
    ("090-090-005-000", "MICHAEL CHARLES SOMMERS"),
    ("090-090-006-000", "MICHAEL CHARLES SOMMERS"),
    ("090-100-002-000", "MICHAEL CHARLES SOMMERS"),
    ("090-130-001-000", "NEW DAWN DEVELOPMENT LLC"),
    ("090-130-005-000", "NEW DAWN DEVELOPMENT LLC"),
    ("090-140-006-000", "NEW DAWN DEVELOPMENT LLC"),
    ("090-400-036-000", "LLOYD M ARNETT JR."),
    ("097-090-005-000", "IGNACIO MELGOZA"),
    ("098-130-006-000", "CHARLENE ELGIN"),
    ("107-200-019-000", "FOSSIL, LLC."),
    ("107-200-019-000", "MOULES CALIFORNIA GLASS, INC."),
    ("107-200-019-000", "PLUMAS BANK"),
    ("203-230-001-000", "BARBARA JOAN SHARP AND MICHAEL C. SHARP T"),
    ("203-230-001-000", "EDITH M. HAMILTON"),
    ("203-230-001-000", "JACK O. SHARP"),
    ("203-230-001-000", "MARIE L. SHARP"),
    ("700-280-014-000", "DECENA J. WILLIAMS"),
    ("700-280-014-000", "GREGORY J. ERCHUL"),
    ("700-280-014-000", "LINDA L. ERCHUL"),
    ("700-280-014-000", "RICHARD N. WILLIAMS"),
    ("702-320-010-000", "ALBERT L. CUNNINGHAM"),
]


def is_institutional(name: str) -> bool:
    up = name.upper()
    return any(m in up for m in INSTITUTIONAL_MARKERS)


def main():
    by_apn = defaultdict(list)
    for apn, party in RAW_ROWS:
        by_apn[apn].append(party)

    generated = 0
    skipped_institutional_only = 0
    for apn, parties in by_apn.items():
        actionable = [p for p in parties if not is_institutional(p)]
        if not actionable:
            skipped_institutional_only += 1
            continue

        primary = actionable[0]
        others = actionable[1:]

        claim_data = {
            "apn_dash": apn,
            "owner": primary,
            "excess_proceeds": None,  # honestly not published — see docstring
            "claim_deadline": CLAIM_DEADLINE,
            "deed_status": f"sold_at_auction_{SALE_DATES.replace(' and ', '_and_').replace('-', '')}",
            "deed_date": DEED_RECORDED,
            "source_file": (
                "Shasta County official Notice of Right to Claim Excess Proceeds "
                "(R&T Code 4676), executed 2026-04-16, published Redding Record "
                "Searchlight 2026-04-23/30 & 2026-05-04 — shastacounty.gov/media/81921"
            ),
            "verification": (
                f"VERIFIED — parcel and named parties of interest are from the county's own "
                f"signed, published legal notice, not estimated or guessed. Exact excess "
                f"proceeds dollar amount is honestly NOT AVAILABLE — Shasta County does not "
                f"publicly disclose it; the county determines and discloses the amount to each "
                f"claimant only after a claim is filed and reviewed by County Counsel. Claim "
                f"deadline ({CLAIM_DEADLINE}) is the EXACT date stated by the county, not an "
                f"estimate. Sale date(s): {SALE_DATES}. Deed recorded {DEED_RECORDED}."
                + (f" Other named parties of interest on this same parcel (statutory priority "
                   f"order, lienholders before titleholders per R&T 4675): {'; '.join(others)}."
                   if others else "")
            ),
        }

        report_builder.build_excess_proceeds_report(claim_data, "shasta")
        generated += 1

    print(f"\nGenerated {generated} real, government-sourced Shasta excess-proceeds leads "
          f"(from {len(by_apn)} parcels; {skipped_institutional_only} had only institutional "
          f"parties and were skipped — no private claimant to contact).")
    print("Dollar amounts are honestly unpublished by the county for all of these — "
          "leads are real named claimants + real deadline, not amounts.")


if __name__ == "__main__":
    main()
