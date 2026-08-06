"""
enrich_sales_equity.py — Enriches parcel CSVs with the Sales & Equity Layer (v1)

Accepts any parcel CSV (e.g. Butte call sheet or master leads) and adds all 13 Sales/Equity
columns, equity gate evaluations, score versioning, and feature contributions per Scoring Spec v1.
"""

import json
import os
import re
import sys
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd

from contracts import MarketEstimateSource, SalePriceConfidence
from sales_equity import compute_sales_equity_layer, evaluate_equity_gate

try:
    from butte.tax_bill import parse_tax_bill
except ImportError:
    parse_tax_bill = None

SCORE_VERSION = "v2.0_sales_equity"

SALES_EQUITY_COLS = [
    "sale_price_proxy_assessor",
    "base_year_value",
    "last_sale_date",
    "last_sale_price_recorded",
    "sale_price_final",
    "sale_price_confidence",
    "tenure_years",
    "market_estimate",
    "market_estimate_source",
    "equity_estimate",
    "equity_band",
    "equity_confidence",
    "excess_proceeds_candidate",
    "equity_gate_status",
    "equity_gate_reason",
    "score_version",
    "score_feature_contributions",
]


def _to_float(val: Any) -> Optional[float]:
    if pd.isna(val) or val is None or str(val).strip() == "":
        return None
    try:
        clean = re.sub(r"[^\d.-]", "", str(val))
        if not clean:
            return None
        return float(clean)
    except Exception:
        return None


def enrich_df_sales_equity(df: pd.DataFrame, county: str = "butte") -> pd.DataFrame:
    df = df.copy()

    # Determine top 15% tier for recorder verification escalation
    total_parcels = len(df)
    top_tier_count = max(1, int(total_parcels * 0.15))

    # Sort key to identify top tier by balance or priority score if available
    sort_col = None
    if "priority_score" in df.columns:
        sort_col = "priority_score"
    elif "v_total_balance" in df.columns:
        sort_col = "v_total_balance"
    elif "total_defaulted_balance" in df.columns:
        sort_col = "total_defaulted_balance"

    top_tier_apns = set()
    if sort_col:
        # Create temp numeric series for sorting
        temp_scores = pd.to_numeric(df[sort_col].astype(str).str.replace(r"[^\d.-]", "", regex=True), errors="coerce").fillna(0.0)
        top_indices = temp_scores.nlargest(top_tier_count).index
        apn_col = "apn" if "apn" in df.columns else ("parcel_number" if "parcel_number" in df.columns else df.columns[0])
        top_tier_apns = set(df.loc[top_indices, apn_col].astype(str).tolist())

    out_records = []

    for idx, row in df.iterrows():
        apn = str(row.get("apn", row.get("parcel_number", row.get("asmt", "")))).strip()

        # Extract land & improvement values (assessed proxy floor)
        land_val = _to_float(row.get("land_value") or row.get("assessed_land"))
        imp_val = _to_float(row.get("improvements_value") or row.get("assessed_improve"))
        total_val = _to_float(row.get("net_taxable_value") or row.get("assessed_value") or row.get("assessed_total"))
        
        # Check captured tax-bill HTML on disk if available and missing in CSV
        if parse_tax_bill and not total_val:
            apn12 = re.sub(r"\D", "", apn)
            html_path = os.path.join(os.path.dirname(__file__), "butte", "tax_bills", f"{apn12}.html")
            if os.path.exists(html_path):
                try:
                    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
                        tb = parse_tax_bill(f.read(), apn12=apn12)
                        land_val = land_val or tb.land_value
                        imp_val = imp_val or tb.improvements_value
                        total_val = total_val or tb.net_taxable_value or ((tb.land_value or 0.0) + (tb.improvements_value or 0.0) if (tb.land_value or tb.improvements_value) else None)
                except Exception:
                    pass

        if not total_val and (land_val or imp_val):
            total_val = (land_val or 0.0) + (imp_val or 0.0)

        base_yr_val = _to_float(row.get("base_year_value"))

        # Recorder deed data
        rec_dates_raw = str(row.get("recorder_doc_dates", row.get("recording_date", "")))
        rec_doc_types = str(row.get("recorder_doc_types", row.get("event_type", "")))
        rec_tax = _to_float(row.get("transfer_tax"))

        # Find latest deed date
        rec_date = None
        if rec_dates_raw and rec_dates_raw != "nan":
            dates = [d.strip() for d in rec_dates_raw.split("|") if d.strip()]
            if dates:
                rec_date = dates[0]

        grantor = str(row.get("grantor_raw", row.get("grantor", "")))
        grantee = str(row.get("verified_current_owner_name", row.get("grantee", "")))

        # Assessor last sale data
        asr_sale_date = str(row.get("last_sale_date", "")) if pd.notna(row.get("last_sale_date")) else None
        asr_sale_price = _to_float(row.get("last_sale_price") or row.get("last_sale_price_recorded"))

        # Check estate / deceased flag
        owner_name = grantee or str(row.get("owner", row.get("verified_current_owner_name", "")))
        entity_type = str(row.get("entity_type", ""))
        is_estate = (
            "ESTATE" in owner_name.upper()
            or "ESTATE" in entity_type.upper()
            or str(row.get("deceased_owner", "")).lower() in ("true", "1", "yes")
        )

        is_top = apn in top_tier_apns

        # Market estimate sourcing (if comps/AVM/appreciation factor present)
        mkt_est = _to_float(row.get("market_estimate"))
        mkt_src_str = str(row.get("market_estimate_source", "")).lower()
        if mkt_src_str == "comps":
            mkt_src = MarketEstimateSource.COMPS
        elif mkt_src_str == "avm":
            mkt_src = MarketEstimateSource.AVM
        elif mkt_src_str == "appreciation_factor":
            mkt_src = MarketEstimateSource.APPRECIATION_FACTOR
        else:
            mkt_src = MarketEstimateSource.NONE

        val_result = compute_sales_equity_layer(
            apn=apn,
            county=county,
            assessed_land=land_val,
            assessed_improve=imp_val,
            assessed_total=total_val,
            base_year_value=base_yr_val,
            recorder_deed_date=rec_date,
            recorder_transfer_tax=rec_tax,
            assessor_last_sale_date=asr_sale_date,
            assessor_last_sale_price=asr_sale_price,
            market_estimate=mkt_est,
            market_estimate_source=mkt_src,
            grantor=grantor,
            grantee=grantee,
            doc_type=rec_doc_types,
            is_estate_or_deceased=is_estate,
            is_top_tier=is_top,
        )

        gate_status, gate_reason = evaluate_equity_gate(val_result)

        # Feature contributions tracking
        distress_bal = _to_float(row.get("v_total_balance") or row.get("total_defaulted_balance") or row.get("amount_due")) or 0.0
        contributions = {
            "distress_balance_usd": distress_bal,
            "valuation_anchor_proxy_usd": val_result.sale_price_proxy_assessor,
            "sale_price_confidence": val_result.sale_price_confidence.value,
            "tenure_years": val_result.tenure_years,
            "equity_band": val_result.equity_band.value,
            "equity_confidence": val_result.equity_confidence.value,
            "equity_gate_status": gate_status,
        }

        row_dict = row.to_dict()
        row_dict.update({
            "sale_price_proxy_assessor": val_result.sale_price_proxy_assessor,
            "base_year_value": val_result.base_year_value,
            "last_sale_date": val_result.last_sale_date or "",
            "last_sale_price_recorded": val_result.last_sale_price_recorded,
            "sale_price_final": val_result.sale_price_final,
            "sale_price_confidence": val_result.sale_price_confidence.value,
            "tenure_years": val_result.tenure_years,
            "market_estimate": val_result.market_estimate,
            "market_estimate_source": val_result.market_estimate_source.value,
            "equity_estimate": val_result.equity_estimate,
            "equity_band": val_result.equity_band.value,
            "equity_confidence": val_result.equity_confidence.value,
            "excess_proceeds_candidate": val_result.excess_proceeds_candidate,
            "equity_gate_status": gate_status,
            "equity_gate_reason": gate_reason,
            "score_version": SCORE_VERSION,
            "score_feature_contributions": json.dumps(contributions),
        })

        # Update priority_score if equity leg gate evaluates
        orig_score = _to_float(row.get("priority_score", row.get("raw_priority_score"))) or 50.0
        if gate_status == "PASS":
            if val_result.equity_band == "high" or (val_result.tenure_years and val_result.tenure_years >= 20):
                new_score = min(100.0, orig_score + 15.0)
            else:
                new_score = min(100.0, orig_score + 5.0)
        elif gate_status == "FAIL_DEMOTE":
            new_score = max(0.0, orig_score - 25.0)
        else:  # UNKNOWN_ROUTE
            new_score = orig_score  # Keep baseline score, but route to excess proceeds track

        row_dict["priority_score"] = round(new_score, 1)

        out_records.append(row_dict)

    enriched_df = pd.DataFrame(out_records)
    return enriched_df


def main():
    if len(sys.argv) < 2:
        print("Usage: python enrich_sales_equity.py <input_csv> [output_csv]")
        sys.exit(1)

    input_csv = sys.argv[1]
    output_csv = sys.argv[2] if len(sys.argv) > 2 else input_csv.replace(".csv", "_SALES_EQUITY.csv")

    print(f"Reading {input_csv}...")
    df = pd.read_csv(input_csv, low_memory=False)

    print(f"Enriching {len(df)} records with Sales & Equity Layer (v1)...")
    enriched_df = enrich_df_sales_equity(df, county="butte")

    enriched_df.to_csv(output_csv, index=False)
    print(f"Enriched dataset saved to {output_csv}")

    # Acceptance criteria verification printout
    print("\n" + "=" * 60)
    print("ACCEPTANCE CRITERIA AUDIT:")
    print("=" * 60)
    print(f"1. Total parcels processed: {len(enriched_df)}")

    conf_counts = enriched_df["sale_price_confidence"].value_counts().to_dict()
    print(f"   sale_price_confidence breakdown: {conf_counts}")

    band_counts = enriched_df["equity_band"].value_counts().to_dict()
    print(f"   equity_band breakdown: {band_counts}")

    gate_counts = enriched_df["equity_gate_status"].value_counts().to_dict()
    print(f"   equity_gate_status breakdown: {gate_counts}")

    unk_eq = enriched_df[enriched_df["equity_confidence"] == "unknown"]
    zero_eq_in_unk = (unk_eq["equity_estimate"] == 0.0).sum()
    print(f"2. Unknown equity parcels: {len(unk_eq)} (Zero equity count in unknown: {zero_eq_in_unk}) -> MUST BE 0")

    excess_cands = enriched_df[enriched_df["excess_proceeds_candidate"] == True]
    print(f"6. Excess proceeds candidates: {len(excess_cands)}")

    print(f"7. score_version set to: {enriched_df['score_version'].iloc[0]}")


if __name__ == "__main__":
    main()
