"""
Stage 2 (Tehama-specific): API-based verification.
Uses Fee Parcel + ASMT + Owner JSON APIs instead of HTML tax detail pages
(which are in maintenance during tax year rollover).

Output:
  - tehama_audit_{ts}.csv        — all rows, all fields
  - tehama_crm_{ts}.csv          — all rows (forced REVIEW, no balance data)
  - tehama_master_{ts}.csv       — canonical MASTER-schema rows for merge pipeline

Usage:
    python stage2_verify_tehama.py <discovery_csv>
"""
import sys, os, time, re
from datetime import datetime
import pandas as pd
from config import COUNTY_CONFIG

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from connectors.tehama import TehamaConnector

CHECKPOINT_EVERY = 100
connector = TehamaConnector("tehama")


def verify(discovery_csv: str):
    cfg = COUNTY_CONFIG["tehama"]
    df = pd.read_csv(discovery_csv, dtype={"asmt_raw": str, "fee_parcel": str, "tra": str, "roll_cat": str})
    print(f"[Stage 2/Tehama] Verifying {len(df)} parcels via JSON APIs...")
    print(f"  Identity: feeparcel API | Owner: owner API | Balances: PENDING\n")

    checkpoint_path = discovery_csv.replace(".csv", "_verify_partial.parquet")
    loaded_asmt = set()
    all_rows = []

    if os.path.exists(checkpoint_path):
        existing = pd.read_parquet(checkpoint_path)
        all_rows = existing.to_dict("records")
        loaded_asmt = set(str(a) for a in existing["asmt"] if "asmt" in existing.columns)
        print(f"[Resume] Loaded {len(all_rows)} verified parcels from checkpoint", flush=True)
    else:
        print(f"[Start] No existing checkpoint — verifying from scratch", flush=True)

    for i, row in df.iterrows():
        asmt_val = str(row["asmt"]).strip()
        if asmt_val in loaded_asmt:
            continue
        year = str(row.get("year", cfg["tax_year"]))
        print(f"  [{i+1}/{len(df)}] {asmt_val}", end=" ", flush=True)

        apn_raw = str(row.get("asmt_raw", str(row.get("asmt", "")).replace("-", ""))).replace(".0", "")

        identity = connector.fetch_identity(apn_raw)
        id_data = identity.data or {}

        situs = id_data.get("Situs1", row.get("address", ""))
        tra = id_data.get("Tra", row.get("tra", ""))
        roll_cat = id_data.get("RollCategory", row.get("roll_cat", ""))

        has_api_confirm = bool(id_data.get("Asmt"))

        row_clean = row.to_dict()
        for k, v in row_clean.items():
            if pd.isna(v):
                row_clean[k] = ""
            elif isinstance(v, (float, int)) and k in ("fee_parcel", "asmt_raw"):
                row_clean[k] = str(v).replace(".0", "")

        merged = {
            **row_clean,
            "asmt": asmt_val,
            "apn_raw": apn_raw,
            "address": situs,
            "tra": tra,
            "roll_cat": roll_cat,
            "owner_name": "",
            "owner_status": "OWNER_API_UNAVAILABLE",
            "v_fetch_error": None if has_api_confirm else "API_NO_MATCH",
            "v_total_balance": None,
            "v_total_due": None,
            "v_total_paid": None,
            "v_inst1_status": None,
            "v_inst2_status": None,
            "v_delinquent": False,
            "verified_url": f"{cfg['host']}{cfg['appFolder']}tehama/tax/main/{apn_raw}/{year}/0000",
            "verified_at": datetime.utcnow().isoformat(),
            "verified_score": "REVIEW",
            "confidence": 0.5 if has_api_confirm else 0.0,
            "verification_status": "IDENTITY_VERIFIED_BALANCE_PENDING",
            "needs_balance_refresh": True,
            "needs_balance_refresh_reason": "HTML_tax_detail_maintenance",
        }

        all_rows.append(merged)
        loaded_asmt.add(asmt_val)

        tra_str = tra[:10] if tra else "?"
        print(f"-> REVIEW  tra={tra_str}  situs={situs[:30] if situs else '?'}", flush=True)
        time.sleep(0.005)

        if len(all_rows) % CHECKPOINT_EVERY == 0:
            pd.DataFrame(all_rows).to_parquet(checkpoint_path, index=False)
            print(f"  [Checkpoint] {len(all_rows)} rows saved", flush=True)

    pd.DataFrame(all_rows).to_parquet(checkpoint_path, index=False)

    full_df = pd.DataFrame(all_rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    audit_path = f"tehama_audit_{ts}.csv"
    full_df.to_csv(audit_path, index=False)
    print(f"\n[OK] Audit export: {audit_path}  ({len(full_df)} rows)")

    crm_minimal = full_df[[c for c in [
        "asmt", "fee_parcel", "address", "county", "year",
        "tra", "roll_cat",
        "verified_score", "confidence",
        "verification_status", "needs_balance_refresh",
        "verified_url", "verified_at",
    ] if c in full_df.columns]]

    crm_path = f"tehama_crm_{ts}.csv"
    crm_minimal.to_csv(crm_path, index=False)
    print(f"[OK] CRM export:   {crm_path}  ({len(crm_minimal)} rows)")

    master_fields = [
        "county", "apn", "fee_parcel", "address",
        "tra", "roll_cat",
        "verified_score", "confidence",
        "verification_status", "needs_balance_refresh",
        "needs_balance_refresh_reason",
        "verified_url", "verified_at",
    ]
    master_df = full_df[[c for c in master_fields if c in full_df.columns]].copy()
    master_df.rename(columns={
        "asmt": "apn",
        "address": "situs_address",
    }, inplace=True)
    master_df["county"] = "tehama"
    master_df["source"] = "api_verify"

    master_path = f"tehama_master_{ts}.csv"
    master_df.to_csv(master_path, index=False)

    api_ok = len(full_df[full_df["v_fetch_error"].isna()])
    api_err = len(full_df[full_df["v_fetch_error"].notna()])
    with_addr = len(full_df[full_df["address"].notna() & (full_df["address"] != "")])
    with_tra = len(full_df[full_df["tra"].notna() & (full_df["tra"] != "")])

    print(f"[OK] Master export: {master_path}  ({len(master_df)} rows)")
    print(f"\n-- Summary ----------------------")
    print(f"   API confirmed  : {api_ok:>5}")
    print(f"   API no match   : {api_err:>5}")
    print(f"   With address   : {with_addr:>5}")
    print(f"   With TRA       : {with_tra:>5}")
    print(f"   All            : {len(full_df):>5}  (REVIEW — balance+owner pending)")
    print(f"---------------------------------\n")

    return audit_path, crm_path, master_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python stage2_verify_tehama.py <discovery_csv>")
        print("Example: python stage2_verify_tehama.py tehama_discovery_20260627_004437.csv")
        sys.exit(1)
    verify(sys.argv[1])
