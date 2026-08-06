"""Shasta enrichment pipeline: gate -> stage7 input -> export tiering"""
import pandas as pd, os, sys
from pathlib import Path

BASE = Path(__file__).parent
MASTER = BASE / "northern_ca_MASTER_merged.csv"
GATED_OUT = BASE / "shasta_enrichment_input.csv"
ENRICHED_OUT = BASE / "tax_pipeline" / "shasta_MASTER_leads_with_liens.csv"
TIER_A = BASE / "shasta_tierA.csv"
TIER_B = BASE / "shasta_tierB.csv"
SKIP_Q = BASE / "shasta_skiptrace_queue.csv"
ENRICHED_ALL = BASE / "shasta_enriched.csv"

print("=== Shasta Pipeline ===")

# Step 1: Load and filter
df = pd.read_csv(MASTER)
shasta = df[df["county"] == "shasta"].copy()
print(f"Shasta leads: {len(shasta)}")

# Step 2: Gating — SKIP_TRACE_REQUIRED
print("\n--- Gating ---")
no_address = shasta["address"].isna() | shasta["address"].astype(str).str.strip().eq("")
no_value = shasta["net_assessed_value"].isna() | shasta["net_assessed_value"].astype(str).str.strip().eq("")
no_owner = shasta["owner_name"].isna() | shasta["owner_name"].astype(str).str.strip().eq("")
not_current = shasta["ownership_status"].astype(str).str.lower() != "current"

skip_trace = (no_address & no_value) | no_owner | not_current
shasta["SKIP_TRACE_REQUIRED"] = skip_trace

print(f"  SKIP_TRACE_REQUIRED: {skip_trace.sum()}/{len(shasta)}")
print(f"  Keep for enrichment: {(~skip_trace).sum()}/{len(shasta)}")

for idx in shasta[skip_trace].index:
    row = shasta.loc[idx]
    reasons = []
    if no_address.loc[idx] and no_value.loc[idx]:
        reasons.append("no address + no assessed value")
    if no_owner.loc[idx]:
        reasons.append("no owner name")
    if not_current.loc[idx]:
        reasons.append(f"ownership_status={row['ownership_status']}")
    print(f"    SKIP: {row.get('fee_parcel', '?')} — {', '.join(reasons)}")

# Step 3: Write gated input for Stage 7
gated = shasta[~skip_trace].copy()
gated.to_csv(GATED_OUT, index=False)
print(f"\nWrote {len(gated)} leads -> shasta_enrichment_input.csv")

# Step 4: Check Stage 7 results (already enriched?)
enriched = pd.read_csv(ENRICHED_OUT) if os.path.exists(ENRICHED_OUT) else pd.DataFrame()
has_recorder = "rec_doc_number" in enriched.columns and enriched["rec_doc_number"].notna().any()

if has_recorder:
    print(f"\nStage 7 data found: {enriched['rec_doc_number'].notna().sum()}/{len(enriched)} with rec_doc_number")
else:
    print(f"\nNo Stage 7 recorder data yet. Run: python tax_pipeline/stage7_recorder_enrich.py shasta")
    print(f"  (reads: shasta_MASTER_leads_with_liens.csv, enriches in-place)")
    enriched = gated  # use gated as-is for tiering

# Step 5: Export tiering (use enriched if available, else gated)
export_df = enriched[enriched["county"] == "shasta"].copy() if "county" in enriched.columns else enriched.copy()

# Ensure required columns
for c in ["delinquent", "total_balance", "active_liens", "mortgages",
          "has_assignment_of_rents", "has_affidavit_of_death",
          "address", "net_assessed_value", "rec_doc_number"]:
    if c not in export_df.columns:
        export_df[c] = ""

export_df["delinquent"] = export_df["delinquent"].astype(str).str.lower().isin(["true", "1", "yes"])
export_df["total_balance"] = pd.to_numeric(export_df["total_balance"], errors="coerce").fillna(0)
export_df["active_liens"] = pd.to_numeric(export_df["active_liens"], errors="coerce").fillna(0).astype(int)
export_df["mortgages"] = pd.to_numeric(export_df["mortgages"], errors="coerce").fillna(0).astype(int)
export_df["SKIP_TRACE_REQUIRED"] = export_df.get("SKIP_TRACE_REQUIRED", False)

has_addr = export_df["address"].notna() & ~export_df["address"].astype(str).str.strip().eq("")
has_value = export_df["net_assessed_value"].notna() & ~export_df["net_assessed_value"].astype(str).str.strip().eq("")
has_rec = export_df["rec_doc_number"].notna() & ~export_df["rec_doc_number"].astype(str).str.strip().eq("")

print("\n--- Export Tiering ---")

# Tier A: premium distress
tier_a = (
    export_df["delinquent"]
    & (export_df["total_balance"] >= 7500)
    & (export_df["ownership_status"].astype(str).str.lower() == "current")
    & has_rec
    & has_addr
    & has_value
    & ~export_df["SKIP_TRACE_REQUIRED"]
)

# Tier B: moderate distress
tier_b = (
    export_df["delinquent"]
    & (export_df["total_balance"] >= 3000)
    & (export_df["total_balance"] < 7500)
    & (export_df["ownership_status"].astype(str).str.lower() == "current")
    & has_addr
    & has_value
    & ~export_df["SKIP_TRACE_REQUIRED"]
)

export_df["Export_Tier"] = "C"
export_df.loc[tier_a, "Export_Tier"] = "A"
export_df.loc[tier_b, "Export_Tier"] = "B"

print(f"  Tier A (premium):  {tier_a.sum()}")
print(f"  Tier B (moderate): {tier_b.sum()}")
print(f"  Tier C (suppress): {(~tier_a & ~tier_b).sum()}")

# Motivation text
def motivation(row):
    parts = []
    bal = row["total_balance"]
    liens = row["active_liens"]
    morts = row["mortgages"]
    if bal >= 25000:
        parts.append(f"High delinquent tax balance (~${bal:,.0f})")
    elif bal >= 7500:
        parts.append(f"Mid-size delinquent tax balance (~${bal:,.0f})")
    elif bal >= 3000:
        parts.append(f"Moderate tax delinquency (~${bal:,.0f})")
    if liens > 5:
        parts.append(f"{liens} active liens")
    elif liens > 0:
        parts.append(f"{liens} active lien(s)")
    if morts > 0:
        parts.append(f"{morts} mortgage(s)")
    if row.get("has_assignment_of_rents"):
        parts.append("assignment of rents")
    if row.get("has_affidavit_of_death"):
        parts.append("affidavit of death on record")
    owner = str(row.get("owner_name", "")).upper()
    if any(m in owner for m in ["LLC", "INC", "CORP", "HOLDINGS", "PROPERTIES"]):
        parts.append("corporate/LLC owner")
    return "; ".join(parts) if parts else "No specific distress flags"

export_df["motivation_reason_text"] = export_df.apply(motivation, axis=1)

# Step 6: Write outputs
cols = ["fee_parcel", "apn", "owner_name", "address", "mailing_address",
        "total_balance", "delinquent", "active_liens", "mortgages",
        "has_assignment_of_rents", "has_affidavit_of_death",
        "ownership_status", "net_assessed_value", "rec_doc_number",
        "rec_doc_date", "Export_Tier", "motivation_reason_text",
        "SKIP_TRACE_REQUIRED"]

export_df = export_df[[c for c in cols if c in export_df.columns]]

# All enriched
export_df.to_csv(ENRICHED_ALL, index=False)
print(f"\nWrote {len(export_df)} -> shasta_enriched.csv")

# Tier A
export_df[export_df["Export_Tier"] == "A"].to_csv(TIER_A, index=False)
print(f"Wrote {(export_df['Export_Tier'] == 'A').sum()} -> shasta_tierA.csv")

# Tier B
export_df[export_df["Export_Tier"] == "B"].to_csv(TIER_B, index=False)
print(f"Wrote {(export_df['Export_Tier'] == 'B').sum()} -> shasta_tierB.csv")

# Skip trace queue
skip_df = shasta[shasta["SKIP_TRACE_REQUIRED"]]
skip_df.to_csv(SKIP_Q, index=False)
print(f"Wrote {len(skip_df)} -> shasta_skiptrace_queue.csv")

print("\n=== Done ===")
print(f"Next: python tax_pipeline/stage7_recorder_enrich.py shasta\n"
      f"  (enriches in-place, then re-run this script for updated tiers)")
