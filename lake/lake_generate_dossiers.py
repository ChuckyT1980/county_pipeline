"""
Generate real, both-sites-verified Lake County Property Intelligence Dossiers.

Methodology (both sites verified, parcel-tied, matching the Kern reference
standard):
  - Assessor: common1.mptsweb.com/mbap/lake/asr (live, confirmed 2026-08-08):
    net assessed value, situs, lot size, property type, and the parcel's
    current recorded VESTING document number/date (unchanged since before
    the tax lien -- confirms no ownership transfer since default).
  - Recorder: lakecountyca-web.tylerhost.net, Official Records Search - Web
    (DOCSEARCH4S3), field_ParcelID + recording-date-range search (live,
    confirmed 2026-08-08, no CAPTCHA past disclaimer accept): confirms a
    real "TAX DEFAULT PROPERTY LIEN" was recorded against this specific
    parcel (grantor = defaulted owner, grantee = Lake County Tax
    Collector) with NO subsequent "Release of Lien" or "Deed Tax" (tax-sale
    deed) recorded through 2026-08-08 -- i.e. this parcel did not redeem
    and did not sell at the county's TDLS164 sale (March 20-31, 2026,
    already concluded) and remains genuinely tax-defaulted today.

Source list: Lake County Tax Collector's official TDLS164 "BOS Submitted"
parcel list (lakecountyca.gov/DocumentCenter/View/15507), cross-checked
against the live recorder for every one of 311 non-"REDEEMED" parcels on
that list. Of 311: 178 sold at the March 2026 sale (Deed Tax recorded),
111 redeemed (Release of Lien recorded), 5 had no recorder activity found
in the window checked, and 17 showed an active, unreleased tax lien with
no subsequent sale deed. One of those 17 (032-042-330-000) was EXCLUDED
because its assessor record shows a brand-new 2026-dated "Current Document
Number" that does not appear anywhere in the recorder's Official Records
index for that parcel even on a widened 2020-2026 search -- an unresolved
assessor/recorder discrepancy, logged separately, NOT shipped.

Since Lake County's next tax sale (TDLS165) has not yet been published,
signal_priority.get_signal("lake") correctly falls through to the shared
"NO_SCHEDULED_AUCTION" / "No scheduled auction -- monitor for a future
sale date" signal (Lake is not in AUCTION_CALENDAR) -- this is left
untouched, not overridden, since it is the honest current state.
"""
import csv
import sys

sys.path.insert(0, "/mnt/c/Users/chuck/Downloads/county_pipeline")
import report_builder

SRC = "/mnt/c/Users/chuck/Downloads/county_pipeline/lake/lake_still_defaulted_full.csv"
EXCLUDE_APNS = {"032-042-330-000"}  # unresolved assessor/recorder doc-number discrepancy


def clean_money(s):
    if not s:
        return None
    s = s.replace('"', '').replace(',', '').replace('$', '').strip()
    try:
        return float(s)
    except ValueError:
        return None


def clean_situs(raw):
    if not raw:
        return None
    return " ".join(raw.split())


def main():
    rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
    generated = []
    skipped = []

    for row in rows:
        apn = row["apn"]
        if apn in EXCLUDE_APNS:
            skipped.append((apn, "unresolved assessor/recorder doc-number discrepancy"))
            continue

        net_val = clean_money(row.get("net_assessed_value"))
        situs = clean_situs(row.get("situs_addr")) or clean_situs(row.get("source_situs"))
        owner = row.get("recorder_owner")
        lien_doc = row.get("lien_doc_number")
        lien_date = row.get("lien_doc_date")
        vesting_doc = row.get("assessor_current_doc_number")
        vesting_date = row.get("assessor_current_doc_date")
        min_bid = clean_money(row.get("min_bid"))
        lot_acres = row.get("lot_acres")
        prop_type = row.get("property_type")

        parcel_data = {
            "apn_dash": apn,
            "owner_name": owner,
            "net_taxable_value": net_val,
            "net_assessed_value": net_val,
            "min_bid": min_bid,
            "situs": situs,
            "use": prop_type,
            "acreage": lot_acres if lot_acres else None,
            "current_doc_number": vesting_doc,
            "deed_date": vesting_date,
            "tax_status": (
                f"TAX-DEFAULTED — confirmed via a real 'TAX DEFAULT PROPERTY LIEN' "
                f"(doc #{lien_doc}, recorded {lien_date}) against this exact parcel, "
                f"recorded by the Lake County Tax Collector after this parcel appeared "
                f"on the county's official Tax Defaulted Land Sale #164 (TDLS164, sale "
                f"conducted March 20-31, 2026) publication. Live recorder recheck "
                f"(2026-08-08, date range 2024-01-01 through 2026-08-08) found NO "
                f"subsequent 'Release of Lien' and NO 'Deed Tax' (tax-sale deed) "
                f"recorded against this parcel — i.e. it neither redeemed nor sold at "
                f"TDLS164 and remains tax-defaulted as of last check. No next sale "
                f"(TDLS165) has been published yet by Lake County as of 2026-08-08."
            ),
            "notice_of_default_present": True,
            "source_file": (
                "common1.mptsweb.com/mbap/lake/asr (live, verified 2026-08-08) + "
                "lakecountyca-web.tylerhost.net Official Records Search - Web "
                f"(DOCSEARCH4S3, parcel-tied, live, verified 2026-08-08, lien doc "
                f"#{lien_doc}) + Lake County Tax Collector TDLS164 official parcel "
                "list (lakecountyca.gov/DocumentCenter/View/15507)"
            ),
            "verification_status": (
                f"VERIFIED — BOTH SITES. Assessed value, situs, and parcel vesting "
                f"document (unchanged since {vesting_date}, confirming no ownership "
                f"transfer) confirmed live against the Lake County MPTS assessor. "
                f"Current tax-defaulted status and owner of record confirmed via the "
                f"recorder's parcel-ID search (not name-only) against the recorded "
                f"Tax Default Property Lien document #{lien_doc} ({lien_date}) — the "
                f"grantor on that lien ({owner}) is the verified defaulted owner. No "
                f"release-of-lien or tax-sale deed found on recheck through 2026-08-08. "
                f"CAVEAT: this parcel's defaulted status was last directly reconfirmed "
                f"via recorder document search on 2026-08-08; the Lake MPTS assessor "
                f"system does not expose a live day-of delinquency flag, so this reflects "
                f"the most recent public recorder evidence, not a same-day county "
                f"confirmation."
            ),
        }

        try:
            out_file = report_builder.build_property_intelligence_dossier(parcel_data, "lake")
            generated.append((apn, str(out_file)))
        except Exception as e:
            skipped.append((apn, f"report_builder error: {e}"))

    print(f"\nGenerated {len(generated)} real, both-sites-verified Lake County dossiers.")
    for apn, path in generated:
        print(f"  {apn} -> {path}")
    if skipped:
        print(f"\nSkipped {len(skipped)}:")
        for apn, reason in skipped:
            print(f"  {apn}: {reason}")


if __name__ == "__main__":
    main()
