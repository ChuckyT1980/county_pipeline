"""
Packages the Butte auction call sheet into a client-ready delivery folder.

Ships three files:
  <name>.xlsx   — the primary buyer deliverable (Excel workbook, 4 sheets)
  <name>.pdf    — 3-page branded intelligence report (cover + how-to + dictionary)
  <name>.csv    — the raw data for buyers who prefer CSV / want programmatic import

Prints a suggested email body at the end.
"""
import os
import shutil
from datetime import datetime

import pandas as pd

from build_deliverable_pdf import build as build_pdf
from build_deliverable_xlsx import build as build_xlsx
from build_dossiers import build_all as build_dossiers

# Ensure verification/score adjustments run before packaging
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "..")))
from verification.recompute_verification_score import recompute as _recompute_verification
from verification.apply_score_adjustments import apply as _apply_score_adjustments

BUTTE_DIR = os.path.dirname(os.path.abspath(__file__))
CALL_SHEET = os.path.join(BUTTE_DIR, "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv")
DELIVERY_ROOT = os.path.join(BUTTE_DIR, "delivery")


def _money_to_float(s):
    if pd.isna(s):
        return 0.0
    try:
        return float(str(s).replace("$", "").replace(",", ""))
    except (ValueError, AttributeError):
        return 0.0


def package(csv_path: str = CALL_SHEET) -> str:
    df = pd.read_csv(csv_path, dtype=str)
    df["bal_num"] = df["v_total_balance"].apply(_money_to_float)

    total_leads = len(df)
    total_balance = df["bal_num"].sum()
    has_phone = df["phone_number"].notna() & (df["phone_number"].astype(str).str.strip() != "") & (df["phone_number"].astype(str).str.strip().str.lower() != "nan")
    has_mailing = df["mailing_address"].notna() & (df["mailing_address"].astype(str).str.strip() != "") & (df["mailing_address"].astype(str).str.strip().str.lower() != "nan")
    out_of_state = (df["out_of_state"] == "Y").sum() if "out_of_state" in df.columns else 0
    portfolios = int((pd.to_numeric(df.get("portfolio_apn_count"), errors="coerce") >= 2).sum()) if "portfolio_apn_count" in df.columns else 0
    fire_vh = int((df["fire_hazard_zone"] == "Very High").sum()) if "fire_hazard_zone" in df.columns else 0

    date_slug = datetime.now().strftime("%Y-%m-%d")
    folder = os.path.join(DELIVERY_ROOT, f"butte_auction_{date_slug}")
    os.makedirs(folder, exist_ok=True)

    stem = f"butte_auction_intel_{date_slug}"
    csv_dest       = os.path.join(folder, f"{stem}.csv")
    pdf_dest       = os.path.join(folder, f"{stem}.pdf")
    xlsx_dest      = os.path.join(folder, f"{stem}.xlsx")
    dossiers_dir   = os.path.join(folder, "dossiers")
    all_dossiers   = os.path.join(folder, f"{stem}_all_dossiers.pdf")
    tax_bills_dest = os.path.join(folder, "tax_bills")

    # Recompute verification_score from actual field completeness (fixes stale-run overwrites)
    _recompute_verification(csv_path)
    # Apply post-enrichment score adjustments (redeemed parcels drop to 0, etc.)
    _apply_score_adjustments(csv_path)

    # Copy raw CSV (fallback for buyers who want it) — AFTER adjustments so csv reflects them
    shutil.copyfile(csv_path, csv_dest)

    # Build the branded overview PDF + buyer-facing XLSX
    build_pdf(csv_path, pdf_dest)
    build_xlsx(csv_path, xlsx_dest)

    # Build the per-parcel dossiers + combined all-dossiers PDF
    result = build_dossiers(csv_path, dossiers_dir, all_dossiers)
    print(f"  Built {result['count']} per-parcel dossiers")

    # Copy tax bill HTML archive into the delivery folder so buyers get
    # the county source documents alongside the dossiers.
    tax_bills_src = os.path.join(BUTTE_DIR, "tax_bills")
    if os.path.isdir(tax_bills_src):
        if os.path.isdir(tax_bills_dest):
            shutil.rmtree(tax_bills_dest)
        shutil.copytree(tax_bills_src, tax_bills_dest, ignore=shutil.ignore_patterns("*_sample.html"))
        n_bills = len([f for f in os.listdir(tax_bills_dest) if f.endswith(".html")])
        print(f"  Copied {n_bills} tax bill HTMLs")
    else:
        n_bills = 0

    # Zip everything for one-file email delivery
    zip_path = os.path.join(DELIVERY_ROOT, f"butte_auction_intel_{date_slug}.zip")
    if os.path.exists(zip_path):
        os.remove(zip_path)
    # zipfile from python stdlib — no external dep
    import zipfile
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, filenames in os.walk(folder):
            for name in filenames:
                full = os.path.join(root, name)
                # arcname relative to the parent so buyer sees a single folder inside the zip
                arcname = os.path.relpath(full, DELIVERY_ROOT)
                zf.write(full, arcname)
    zip_size = os.path.getsize(zip_path)

    files = [xlsx_dest, pdf_dest, all_dossiers, csv_dest, zip_path]

    print()
    print("=" * 78)
    print(f"Delivery bundle ready: {folder}")
    print("=" * 78)
    for f in files:
        size = os.path.getsize(f)
        print(f"  {os.path.basename(f):50s} {size:>9,} bytes")
    print()
    print("Suggested email:")
    print("-" * 78)
    print(f"Subject: Butte County Aug 7-10 Tax Auction Intel  {total_leads} scored leads (${total_balance:,.0f} total)")
    print()
    print("Attached: a pre-scored intelligence pack for the Butte County")
    print("tax-defaulted auction, Aug 7-10, 2026.")
    print()
    print("What's inside:")
    print(f"  * {total_leads} auction parcels, ${total_balance:,.0f} total defaulted balance")
    print(f"  * Owner + mailing address ({has_mailing.sum()} of {total_leads} direct-mail ready)")
    print(f"  * Priority score 0-100 per lead (log-scaled on balance)")
    print(f"  * Portfolio detection: {portfolios} owners hold multiple parcels on this auction")
    print(f"  * {out_of_state} out-of-state absentee owners flagged separately")
    print(f"  * {fire_vh} parcels in Very High CalFire fire hazard zones")
    print(f"  * Distress signals per owner (NODs, IRS liens, judgments, tax defaults)")
    print(f"  * Every field carries a source + confidence stamp for verification")
    if has_phone.sum() > 0:
        print(f"  * Phone numbers: {has_phone.sum()} of {total_leads}")
    print()
    print("Files:")
    print(f"  * {os.path.basename(xlsx_dest)}   - primary deliverable (Excel, 4 tabs)")
    print(f"  * {os.path.basename(pdf_dest)}   - 3-page intel overview")
    print(f"  * {os.path.basename(all_dossiers)}   - all {total_leads} two-page dossiers combined (dossier + tax bill each)")
    print(f"  * dossiers/   - folder of {total_leads} individual 2-page dossier PDFs (dossier + tax bill)")
    print(f"  * tax_bills/  - folder of {n_bills} archived county tax bill HTMLs (source docs)")
    print(f"  * {os.path.basename(csv_dest)}   - raw CSV (for programmatic use)")
    print()
    print(f">>> ONE-FILE DELIVERY: {os.path.basename(zip_path)} ({zip_size:,} bytes)")
    print(f"    Attach this zip to your email. Contains everything above in a single folder.")
    print()
    print("Auction is 15 days away. This list is time-sensitive.")
    print("-" * 78)

    return folder


if __name__ == "__main__":
    package()
