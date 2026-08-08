"""
Build real Nevada County excess-proceeds leads from the ACTIVE sale
cycle (November 13, 2025 sale + January 28, 2026 Re-Offer) — a
genuinely different, later document than the EXPIRED November 2024
one investigated and excluded earlier tonight (see nevada/
nevada_nov2024_excess_proceeds.pdf and the HIGH-severity exception log
entry). This document's real stated deadline (December 19, 2026) is
what the original discovery pass actually found — it had just been
summarized under the wrong sale-cycle label. Both source documents
were independently downloaded, hashed, and read in full before
concluding anything.

Source: nevadacountyca.gov/DocumentCenter/View/69929 (a .docx, not a
PDF — extracted via python-docx). Deadline stated directly in the
document: "Claims must be filed by December 19, 2026."

Same structural pattern as Shasta/Colusa: real named parties of
interest, no dollar amounts disclosed by the county. One global
deadline for all parcels (unlike Colusa's per-parcel deadlines).

Every record runs through report_builder's lead_status state machine
before being written — this is exactly the case that machine exists
for, so no record here can become ACTIVE_CANDIDATE unless the deadline
genuinely parses as future-dated (it does: 2026-12-19, ~133 days out
as of 2026-08-08).
"""
import hashlib
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder
from excess_proceeds_notice_parser import filter_institutional

DOCX_PATH = "/mnt/c/Users/chuck/Downloads/county_pipeline/nevada/nevada_nov2025_excess_proceeds.docx"
SOURCE_URL = "https://www.nevadacountyca.gov/DocumentCenter/View/69929/2025-pub-excess-proceedseeds"
DEADLINE = "2026-12-19"
SALE_LABEL = "November 13, 2025 sale + January 28, 2026 Re-Offer"

# (apn, situs, all_parties_as_printed)
RAW_RECORDS = [
    ("002-450-012-000", "18633 MUSTANG VALLEY PL", [
        "KANG MANDEEP", "WALTER A AHRENS", "RON GILBERT", "ROBIN ANNETTE GILBERT",
        "CHRISTINE MORRISON", "VINCENT WELLS", "GARY TREECE", "ROSEMARY SKATES",
        "JUSTIN SCHMIDT", "STEVEN PAYETTE, ESQ", "MUSTANG VALLEY PARTNERS LLC",
        "COUNTY OF NEVADA- CODE COMPLIANCE", "NEVADA COUNTY COLLECTIONS DIVISION",
    ]),
    ("012-730-038-000", "14037 ARROWHEAD MINE RD", ["HILTON KUYKENDALL"]),
    ("013-250-012-530", None, [
        "BALTIC CONSOLIDATED TRUST DATED SEP. 8, 1997", "JOSE ZECA SANTANA",
        "THOMAS C. BROEMMEL", "ANTHONY MEIMA", "ROLF MEIMA",
        "SIERRA PACIFIC LAND & TIMBER COMPANY", "SIERRA PACIFIC INDUSTRIES",
    ]),
    ("013-250-013-510", None, [
        "BALTIC CONSOLIDATED TRUST DATED SEP. 8, 1997", "JOSE ZECA SANTANA",
        "THOMAS C. BROEMMEL", "ANTHONY MEIMA", "ROLF MEIMA",
        "WSP INVESTMENT COMPANY, LLC", "SIERRA PACIFIC LAND & TIMBER COMPANY",
        "SIERRA PACIFIC INDUSTRIES",
    ]),
    ("023-590-016-000", "14865 DOG BAR RD", [
        "ALTA NEVADA LLC", "EDWARD WACHTEL", "KENNETH PETRULIS",
        "GOODSON WACHTEL & PETRULIS A PROFESSION CORP",
    ]),
    ("024-290-008-000", "15601 BREWER RD", [
        "ALTA NEVADA LLC", "EDWARD WACHTEL", "KENNETH PETRULIS",
        "GOODSON WACHTEL & PETRULIS A PROFESSION CORP",
    ]),
    ("024-320-005-000", "15788 BREWER RD", [
        "DOUGLAS WILSON", "CAROL WILSON", "SIERRA HIGH c/o WESTERN TITLE INSURANCE CO.",
        "BANK OF AMERICA NT&SA", "THE DEFINED BENEFIT PLAN OF AMERICAN REALTY LTD",
    ]),
    ("024-370-002-000", "16308 BREWER RD", [
        "ALTA NEVADA LLC", "EDWARD WACHTEL", "KENNETH PETRULIS",
        "GOODSON WACHTEL & PETRULIS A PROFESSION CORP",
    ]),
    ("028-070-017-000", "15759 SHEBLEY RD", ["ROBERT E WHITTINGTON", "EDWARD L WHITTINGTON"]),
    ("038-190-011-000", "13305 SUMMIT RIDGE DR", ["DAYNE BRAZZELL", "NEVADA COUNTY CONSOLIDATED FIRE DIST"]),
    ("052-360-058-000", "11791 EMPTY DIGGINS LN", [
        "RONALD T. & BONITA E. SILVA", "CANDACE L. MUMFORD", "ROCKLAND CALIGIURI",
    ]),
    ("062-070-006-000", "14435 GRIZZLY HILL RD", ["GOLDEN SIERRA INC", "KELLY ABREU, ESQ"]),
    ("062-070-007-000", "14550 GRIZZLY HILL RD", ["GOLDEN SIERRA INC", "KELLY ABREU, ESQ", "NEVADA COUNTY COLLECTIONS DIVISION"]),
    ("062-090-012-000", None, ["GOLDEN SIERRA INC", "KELLY ABREU, ESQ"]),
]


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    doc_hash = file_hash(DOCX_PATH)
    print(f"Source sha256={doc_hash}")

    generated = 0
    for apn, situs, all_parties in RAW_RECORDS:
        private, institutional = filter_institutional(all_parties)
        if not private:
            print(f"SKIPPED {apn}: no private (non-institutional) party found")
            continue

        primary = private[0]
        others = private[1:]

        claim_data = {
            "apn_dash": apn,
            "owner": primary,
            "situs": situs,
            "excess_proceeds": None,  # honestly not published by Nevada County
            "claim_deadline": DEADLINE,
            "deed_status": f"sold_at_auction_{SALE_LABEL.replace(' ', '_')}",
            "source_file": (
                f"Nevada County official Notice of Right to Claim Excess Proceeds, covering "
                f"the {SALE_LABEL} — {SOURCE_URL} (sha256={doc_hash[:16]}...). Executed 2026-03-02, "
                f"published The Union Newspaper 2026-03-05/12/19. NOT to be confused with the "
                f"separate, EXPIRED November 2024 sale notice (deadline 2025-11-27, excluded) - "
                f"see county-signal-exception-log.csv for the resolved contradiction."
            ),
            "verification": (
                f"VERIFIED — parcel and named parties of interest are from the county's own signed, "
                f"published legal notice, not estimated. Exact excess proceeds dollar amount is "
                f"honestly NOT AVAILABLE — Nevada County does not publicly disclose it. Claim deadline "
                f"({DEADLINE}) is stated directly in the source document, not estimated."
                + (f" Other named parties of interest on this parcel: {'; '.join(others)}." if others else "")
                + (f" Institutional/government parties excluded from primary claimant: {'; '.join(institutional)}." if institutional else "")
            ),
        }
        report_builder.build_excess_proceeds_report(claim_data, "nevada")
        generated += 1

    print(f"\nGenerated {generated} real, government-sourced Nevada excess-proceeds leads "
          f"(ACTIVE sale cycle - Nov 2025/Jan 2026, deadline {DEADLINE}).")


if __name__ == "__main__":
    main()
