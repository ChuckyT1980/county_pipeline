"""
Combine Shasta + Tehama tiered leads into one buyer-ready export CSV.
"""
import pandas as pd, os
from pathlib import Path

BASE = Path(__file__).parent

# ── Load Shasta tier outputs ──
ta = pd.read_csv(BASE / "shasta_tierA.csv")
tb = pd.read_csv(BASE / "shasta_tierB.csv")
shasta = pd.concat([ta, tb], ignore_index=True)
shasta["county"] = "Shasta"
shasta["Export_Tier"] = shasta["Export_Tier"].map({"A": "Tier A", "B": "Tier B"})
print(f"Shasta: {len(shasta)} (A={len(ta)}, B={len(tb)})")

# ── Load Tehama CRM output ──
tehama = pd.read_csv(BASE / "crm_ready_leads.csv")
tehama["county"] = "Tehama"
# Rename to match Shasta column names
tehama.rename(columns={
    "assessee_name": "owner_name",
    "property_address": "address",
    "live_total_balance": "total_balance",
    "Verification Status": "verification_status",
}, inplace=True)
# Normalize Tier labels
tehama["Export_Tier"] = tehama["Export_Tier"].replace({
    "Tier A \u2014 Verified export": "Tier A",
    "Tier B \u2014 Auto-review queue": "Tier B",
    "Tier C \u2014 Suppress": "Tier C",
})
print(f"Tehama: {len(tehama)} (A={8}, B={44})")

# ── Define unified output columns ──
OUT_COLS = [
    "county", "Export_Tier",
    "owner_name", "address", "mailing_address",
    "total_balance", "delinquent",
    "active_liens", "mortgages",
    "has_assignment_of_rents", "has_affidavit_of_death",
    "ownership_status",
    "net_assessed_value",
    "rec_doc_number", "rec_doc_date",
    "motivation_reason_text",
    "apn",
]

# ── Build unified rows from Shasta ──
rows = []
for _, r in shasta.iterrows():
    row = {c: r.get(c, "") for c in OUT_COLS}
    row["county"] = "Shasta"
    rows.append(row)

# ── Build unified rows from Tehama ──
for _, r in tehama.iterrows():
    row = {c: r.get(c, "") for c in OUT_COLS}
    row["county"] = "Tehama"
    # Fill gaps
    row["delinquent"] = True  # CRM export only exports delinquent leads
    rows.append(row)

combined = pd.DataFrame(rows, columns=OUT_COLS)

# Fill NaN
combined = combined.fillna("").replace({float("nan"): "", "nan": "", "None": ""})

# Sort by county then tier
combined["_tier_sort"] = combined["Export_Tier"].map({"Tier A": 0, "Tier B": 1, "Tier C": 2}).fillna(3)
combined.sort_values(["county", "_tier_sort", "total_balance"], ascending=[True, True, False], inplace=True)
combined.drop(columns=["_tier_sort"], inplace=True)

# ── Write combined export ──
out_path = BASE / "northern_ca_export_ready.csv"
combined.to_csv(out_path, index=False)

print(f"\nCombined: {len(combined)} leads -> northern_ca_export_ready.csv")
print(f"  Tier A: {(combined['Export_Tier'] == 'Tier A').sum()}")
print(f"  Tier B: {(combined['Export_Tier'] == 'Tier B').sum()}")
print(f"  Total tax balance: ${pd.to_numeric(combined['total_balance'], errors='coerce').sum():,.0f}")

# Show top 10
print(f"\nTop 10 by balance:")
top = combined.head(10)
for _, r in top.iterrows():
    bal = pd.to_numeric(r['total_balance'], errors='coerce')
    print(f"  {r['county']:7s} {r['Export_Tier']:8s} {r['owner_name'][:30]:30s} ${bal:,.0f}")
