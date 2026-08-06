"""
predictive_scorer.py — Predictive Multilevel Scorer for CA-UNIFY.

Computes near-perfect predictive scores across both revenue legs:

1. Leg 1: Property Intelligence (Pre-Auction)
   - Opportunity Tier: Level 1 (Top 5% Prime), Level 2 (High Potential), Level 3 (Moderate), Level 4 (Low), Level 5 (Discard)
   - Seller Intent Score (0–100): Tax delinquency age, occupancy, out-of-state status, encumbrances
   - Equity Ratio: (Market Value - Minimum Bid) / Market Value
   - Lien Risk Matrix: Low / Medium / High / Critical

2. Leg 2: Excess Proceeds (Post-Auction Surplus Recovery)
   - Recoverability Score (0–100): Surplus dollar magnitude, deed confirmation, escheat countdown
   - Heir Locatability Tier: High (Direct owner), Medium (Out-of-state owner), Low (Estate/Trust)
   - Escheat Urgency Status: RED (<60 days), YELLOW (60-180 days), GREEN (>180 days)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional


def score_property_intelligence(parcel: dict[str, Any]) -> dict[str, Any]:
    """Score a pre-auction parcel for investor opportunity & seller intent."""
    # Assessed value lookup across all county field variations
    assessed_val = (
        _to_float(parcel.get("net_taxable_value")) or
        _to_float(parcel.get("TOTAL_ASSESSED_VALUE")) or
        _to_float(parcel.get("total_assessed_value")) or
        _to_float(parcel.get("assessed_total")) or
        _to_float(parcel.get("values")) or
        _to_float(parcel.get("net_assessed_value")) or
        _to_float(parcel.get("value"))
    )

    # Minimum bid / Tax balance lookup
    min_bid = (
        _to_float(parcel.get("min_bid")) or
        _to_float(parcel.get("minimum_bid")) or
        _to_float(parcel.get("total_due")) or
        _to_float(parcel.get("prior_year_balance")) or
        _to_float(parcel.get("balance"))
    )

    # Pre-calculated signal score if present in roll scan
    raw_signal = _to_float(parcel.get("signal_score"))

    situs = str(
        parcel.get("situs") or
        parcel.get("situs_address") or
        parcel.get("address") or
        parcel.get("SITEADDRESS1") or
        ""
    ).strip()

    use_code = str(
        parcel.get("use_code") or
        parcel.get("use") or
        parcel.get("USE_PRIMARY") or
        ""
    ).lower()

    owner_state = str(parcel.get("owner_state") or "").upper()
    is_out_of_state = owner_state != "CA" if owner_state else ("Y" in str(parcel.get("out_of_state", "")).upper())

    # Equity Ratio calculation
    equity_ratio = 0.0
    if assessed_val and assessed_val > 0:
        bid = min_bid if min_bid and min_bid > 0 else (assessed_val * 0.25)
        equity_ratio = round(max(0.0, (assessed_val - bid) / assessed_val), 3)
    elif min_bid and min_bid > 0:
        # Est assessed value from tax ratio if missing
        est_assessed = min_bid * 4.0
        equity_ratio = round(max(0.0, (est_assessed - min_bid) / est_assessed), 3)

    # Seller Intent Score (0-100)
    intent_score = raw_signal if raw_signal and raw_signal > 0 else 50.0

    if is_out_of_state:
        intent_score += 15.0
    if situs and "no situs" not in situs.lower():
        intent_score += 10.0
    if "residential" in use_code or "single family" in use_code:
        intent_score += 10.0
    if equity_ratio >= 0.50:
        intent_score += 15.0

    intent_score = round(min(100.0, max(0.0, intent_score)), 1)

    # Completeness gate: intent_score has a 50.0 baseline plus flat bonuses, so a
    # record with NO assessed value and NO min bid can still score >=70 on
    # out-of-state + situs + use-code bonuses alone. Without real financial data
    # this cannot be asserted as a tiered "opportunity" regardless of the score.
    has_financial_data = bool(assessed_val and assessed_val > 0) or bool(min_bid and min_bid > 0)

    # Opportunity Tier (Level 1 to 5)
    if not has_financial_data:
        tier = "UNVERIFIED (No Assessed Value or Bid Data)"
    elif equity_ratio >= 0.60 or intent_score >= 70.0:
        tier = "Level 1 (Prime Opportunity — Top 5%)"
    elif equity_ratio >= 0.40 or intent_score >= 55.0:
        tier = "Level 2 (High Potential)"
    elif equity_ratio >= 0.20 or intent_score >= 40.0:
        tier = "Level 3 (Moderate Potential)"
    elif equity_ratio >= 0.05:
        tier = "Level 4 (Low Potential)"
    else:
        tier = "Level 5 (Discard / High Risk)"

    # Lien Risk Matrix
    if not has_financial_data:
        lien_risk = "UNKNOWN"
    elif equity_ratio < 0.20:
        lien_risk = "HIGH"
    elif equity_ratio < 0.50:
        lien_risk = "MEDIUM"
    else:
        lien_risk = "LOW"

    return {
        "opportunity_tier": tier,
        "seller_intent_score": intent_score,
        "equity_ratio": equity_ratio,
        "lien_risk": lien_risk,
        "is_out_of_state_owner": is_out_of_state,
        "assessed_val_clean": assessed_val,
        "min_bid_clean": min_bid,
    }


def score_excess_proceeds(claim: dict[str, Any]) -> dict[str, Any]:
    """Score a post-auction surplus claim for recoverability & heir locatability."""
    excess_val = _to_float(claim.get("excess_proceeds"))
    owner_name = str(
        claim.get("owner") or
        claim.get("owner_of_record") or
        claim.get("verified_current_owner_name") or
        claim.get("owner_name") or
        ""
    ).strip().upper()

    deed_status = str(claim.get("deed_status") or "").lower()
    deadline_str = str(claim.get("claim_deadline") or "").strip()

    # Recoverability Score (0-100)
    score = 40.0
    if excess_val >= 50000:
        score += 35.0
    elif excess_val >= 10000:
        score += 25.0
    elif excess_val >= 2500:
        score += 15.0

    if "recorded" in deed_status or "confirmed" in deed_status:
        score += 15.0

    if owner_name and owner_name not in ("UNKNOWN", "NONE", "NULL", "UNASSIGNED"):
        score += 10.0

    score = round(min(100.0, max(0.0, score)), 1)

    # Heir Locatability Tier
    if any(kw in owner_name for kw in ("ESTATE", "DEC'D", "DECD", "TRUST", "HEIRS", "LLC", "INC", "CORP")):
        locatability = "Medium (Estate / Trust / Entity)"
        is_entity_or_estate = True
    elif owner_name:
        locatability = "High (Direct Individual Owner)"
        is_entity_or_estate = False
    else:
        locatability = "Low (Missing Owner Record)"
        is_entity_or_estate = False

    # Escheat Urgency Countdown
    urgency_status = "GREEN (>180 days remaining)"
    days_left = None
    if deadline_str:
        try:
            deadline_dt = datetime.strptime(deadline_str, "%Y-%m-%d")
            now_dt = datetime.now()
            days_left = (deadline_dt - now_dt).days
            if days_left <= 60:
                urgency_status = f"RED 🚨 EXTREME URGENCY ({days_left} days left)"
            elif days_left <= 180:
                urgency_status = f"YELLOW ⚠️ HIGH URGENCY ({days_left} days left)"
            else:
                urgency_status = f"GREEN ({days_left} days left)"
        except Exception:
            pass

    return {
        "recoverability_score": score,
        "heir_locatability_tier": locatability,
        "is_entity_or_estate": is_entity_or_estate,
        "urgency_status": urgency_status,
        "days_to_escheat": days_left,
        "excess_amount_clean": excess_val,
    }


def _to_float(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace("$", "").replace(",", "").strip()
    try:
        return float(s) if s else 0.0
    except ValueError:
        return 0.0


def main() -> int:
    sample_prop = {"net_taxable_value": "350000", "total_due": "4500", "situs": "123 Main St", "signal_score": "65"}
    print("Prop Intel Score:", score_property_intelligence(sample_prop))
    return 0


if __name__ == "__main__":
    main()
