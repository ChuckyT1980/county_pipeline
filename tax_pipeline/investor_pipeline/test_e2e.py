"""E2E test of the full investor pipeline."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
from datetime import datetime

from investor_pipeline.bid4assets_extractor import load_auction_csv
from investor_pipeline.recorder_linker import load_recorder_csv, link_auction_recorder
from investor_pipeline.investor_aggregator import build_investor_tables

# ---- Build synthetic test data ----
auction_data = pd.DataFrame({
    "county": ["Butte", "Butte", "Butte", "Tehama"],
    "auction_id": ["BA-2026-001", "BA-2026-001", "BA-2026-001", "TA-2026-001"],
    "auction_date": [
        datetime(2026, 6, 8), datetime(2026, 6, 8),
        datetime(2026, 6, 8), datetime(2026, 5, 15),
    ],
    "apn": [
        "050-120-121-000", "013-216-006-000",
        "028-410-121-000", "100-200-030-000",
    ],
    "minimum_bid": [5000.0, 10000.0, 20000.0, 7500.0],
    "winning_bid_amount": [12300.0, 25000.0, 0.0, 18500.0],
    # note: 028-410-121-000 is UNSOLD (0 bid), won't appear in linked results
    "status": ["SOLD", "SOLD", "UNSOLD", "SOLD"],
})
ap = "/tmp/test_auctions.csv"
auction_data.to_csv(ap, index=False)

recorder_data = pd.DataFrame({
    "county": ["Butte", "Butte", "Butte", "Tehama"],
    "apn": [
        "050-120-121-000",
        "013-216-006-000",
        "050-120-121-000",
        "100-200-030-000",
    ],
    "recording_date": [
        datetime(2026, 6, 20),
        datetime(2026, 6, 25),
        datetime(2025, 3, 1),     # too old — before auction, won't match
        datetime(2026, 5, 30),
    ],
    "document_number": [
        "2026-001234",
        "2026-001890",
        "2025-000999",
        "2026-004321",
    ],
    "document_type": [
        "TRUSTEE DEED",
        "TRUSTEE DEED",
        "DEED OF TRUST",          # not a tax-deed type, won't match
        "TRUSTEE DEED",
    ],
    "grantee_raw": [
        "2585 ORO DAM LLC",
        "2585 ORO DAM LLC",       # same buyer bought both Butte parcels
        "2585 ORO DAM LLC",
        "TEHAMA INVESTMENTS INC",
    ],
    "grantor_raw": [
        "BUTTE COUNTY TREASURER",
        "BUTTE COUNTY TAX COLLECTOR",
        "SOME BANK",
        "TEHAMA COUNTY TAX COLLECTOR",
    ],
})
rp = "/tmp/test_recorder.csv"
recorder_data.to_csv(rp, index=False)

# ---- Run pipeline ----
print("=== E2E Pipeline Test ===")
auction_df = load_auction_csv(ap)
recorder_df = load_recorder_csv(rp)

print(f"Auction: {len(auction_df)} parcels ({auction_df['sold_flag'].sum()} sold)")
print(f"Recorder: {len(recorder_df)} records")

linked = link_auction_recorder(auction_df, recorder_df)
print(f"Linked matches: {len(linked)}")

investors, deeds = build_investor_tables(linked, output_dir="/tmp/investor_test")

print()
print("--- Investors ---")
for _, r in investors.iterrows():
    print(f"  {r['entity_name_normalized']:40s} {r['entity_type']:10s}"
          f" ${r['total_capital_deployed']:>7,.0f}  {r['total_deeds']} deeds  {r['counties']}")

print()
print("--- Investor Deeds ---")
for _, r in deeds.iterrows():
    print(f"  {r['entity_name_normalized']:40s} {r['county']:8s}"
          f" ${r['winning_bid_amount']:>7,.0f}  {str(r['recording_date'])[:10]}  {r['document_number']}")

# -- Verify expectations --
assert len(investors) == 2, f"Expected 2 investors, got {len(investors)}"
assert len(deeds) == 3, f"Expected 3 deed records, got {len(deeds)}"
assert "2585 ORO DAM LLC" in investors["entity_name_normalized"].values
assert "TEHAMA INVESTMENTS INC" in investors["entity_name_normalized"].values

# "2585 ORO DAM LLC" bought 2 Butte parcels = $12,300 + $25,000
e = investors[investors["entity_name_normalized"] == "2585 ORO DAM LLC"].iloc[0]
assert e["total_deeds"] == 2, f"Expected 2 deeds for 2585 ORO DAM, got {e['total_deeds']}"
assert e["total_capital_deployed"] == 37300.0, f"Expected 37300, got {e['total_capital_deployed']}"
assert "Butte" in e["counties"]

# "TEHAMA INVESTMENTS INC" bought 1 Tehama parcel = $18,500
e2 = investors[investors["entity_name_normalized"] == "TEHAMA INVESTMENTS INC"].iloc[0]
assert e2["total_deeds"] == 1
assert e2["total_capital_deployed"] == 18500.0

print()
print("=== ALL ASSERTIONS PASSED ===")

# Cleanup
import shutil
shutil.rmtree("/tmp/investor_test", ignore_errors=True)
os.remove(ap)
os.remove(rp)
