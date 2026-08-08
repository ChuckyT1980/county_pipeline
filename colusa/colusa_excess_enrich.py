"""
Build real Colusa excess-proceeds leads using the reusable
excess_proceeds_notice_parser module (COLUSA_CONFIG).

Source: Colusa County official "Notice of Right to Claim Excess Proceeds
(Parties of Interest)", executed 2025-12-15, published Pioneer Review
12/26/2025 / 1/2/2026 / 1/9/2026. Covers sales on 2025-09-18 and
2025-11-05. countyofcolusaca.gov/DocumentCenter/View/19919

Same structural pattern as Shasta: real named parties of interest, NO
dollar amounts (county doesn't publish them). UNLIKE Shasta: each
parcel has its OWN "LAST DAY TO FILE" deadline (Oct 2 - Nov 17, 2026),
not one global deadline - the parser's per_parcel_deadline=True config
handles this correctly.

3 of 8 records had situs/first-party-name fields that the automated
parser couldn't cleanly split (see excess_proceeds_notice_parser.py's
documented KNOWN EXCEPTIONS) - those 3 were hand-corrected against the
original clean pypdf text extraction before use here, not guessed.
"""
import hashlib
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
from pypdf import PdfReader
import report_builder
from excess_proceeds_notice_parser import parse_parties_of_interest_notice, filter_institutional, COLUSA_CONFIG

PDF_PATH = "/mnt/c/Users/chuck/Downloads/county_pipeline/colusa/colusa_parties_of_interest.pdf"

# Hand-corrections for the 3 records where the automated parser's
# situs/party split was unreliable (see module docstring) - values
# taken directly from the original clean pypdf text extraction, not
# guessed or estimated.
SITUS_CORRECTIONS = {
    "005-320-011-000": "522 WATERFOWL WAY, WILLIAMS",
    "012-025-003-000": "238 COMMERCIAL ST #B, PRINCETON",
    "015-330-049-000": "1638 WILSON AVE, COLUSA",
}
PARTIES_CORRECTIONS = {
    "005-320-011-000": ["AMBER MENDEZ KESTERSON"],
    "012-025-003-000": ["SEANA KATHLEEN HOGAN"],
    "015-330-049-000": ["OLEND DEE CRABTREE SR", "EDNA MAE CALVIN"],  # COLUSA PENTECOSTAL CHURCH excluded (org, not a finder-service target)
}


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    pdf_hash = file_hash(PDF_PATH)
    print(f"Source PDF sha256={pdf_hash}")

    reader = PdfReader(PDF_PATH)
    text = reader.pages[0].extract_text()
    result = parse_parties_of_interest_notice(text, COLUSA_CONFIG)

    print(f"Parser: {len(result['records'])} records, {len(result['parse_failures'])} parse failures")
    for f in result["parse_failures"]:
        print(f"  PARSE FAILURE: {f}")

    generated = 0
    for rec in result["records"]:
        apn = rec["apn"]
        situs = SITUS_CORRECTIONS.get(apn, rec["situs"])
        parties = PARTIES_CORRECTIONS.get(apn)
        if parties is None:
            private, institutional = filter_institutional(rec["parties_of_interest"])
            parties = private
        else:
            institutional = []

        if not parties:
            print(f"  SKIPPED {apn}: no private (non-institutional) party found")
            continue

        primary = parties[0]
        others = parties[1:]

        claim_data = {
            "apn_dash": apn,
            "owner": primary,
            "situs": situs,
            "excess_proceeds": None,  # honestly not published - Colusa doesn't disclose amounts
            "claim_deadline": rec["deadline"],
            "deed_status": "sold_at_auction_2025-09-18_or_2025-11-05",
            "source_file": (
                f"Colusa County official Notice of Right to Claim Excess Proceeds (Parties of "
                f"Interest), executed 2025-12-15 — {COLUSA_CONFIG.source_url} (sha256={pdf_hash[:16]}...)"
            ),
            "verification": (
                f"VERIFIED — parcel and named parties of interest are from the county's own signed, "
                f"published legal notice, not estimated. Exact excess proceeds dollar amount is "
                f"honestly NOT AVAILABLE — Colusa County does not publicly disclose it. Claim "
                f"deadline ({rec['deadline']}) is PER-PARCEL and stated directly in the notice, not "
                f"a global estimate (unlike Shasta's single county-wide deadline)."
                + (f" Other named parties of interest on this parcel: {'; '.join(others)}." if others else "")
                + (f" Institutional/organizational parties excluded from primary claimant: {'; '.join(institutional)}." if institutional else "")
            ),
        }
        report_builder.build_excess_proceeds_report(claim_data, "colusa")
        generated += 1

    print(f"\nGenerated {generated} real, government-sourced Colusa excess-proceeds leads.")


if __name__ == "__main__":
    main()
