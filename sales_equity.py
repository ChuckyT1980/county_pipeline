"""
sales_equity.py — Sales & Equity Feature Layer (v1)

Implements the sale price resolution ladder and derived equity feature engine
for the NorCal property-intelligence pipeline per Scoring Spec v1.

Key principles enforced:
1. Assessed value != market value. Assessed total (land + improvements) is the factored
   base-year value (valuation floor), NOT current market value.
2. No deed on file / unknown equity is NEVER coerced to 0. Unknown equity parcels
   (estates, never-recorded land) are routed to the excess-proceeds track.
3. Provenance and confidence tags are attached to every derived feature.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Optional, Tuple

from contracts import (
    EquityBand,
    EquityConfidence,
    MarketEstimateSource,
    SalePriceConfidence,
    SalesEquityValuation,
)

BUTTE_TRANSFER_TAX_RATE = 1.10  # CA standard $1.10 per $1,000


def _parse_date(val: Any) -> Optional[date]:
    if not val:
        return None
    s = str(val).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def calculate_tenure_years(sale_date_val: Any, ref_date: Optional[date] = None) -> Optional[float]:
    d = _parse_date(sale_date_val)
    if not d:
        return None
    today = ref_date or date.today()
    delta_days = (today - d).days
    if delta_days < 0:
        return 0.0
    return round(delta_days / 365.25, 2)


def is_non_arms_length_transfer(
    grantor: Optional[str] = None,
    grantee: Optional[str] = None,
    doc_type: Optional[str] = None,
    transfer_tax: Optional[float] = None,
) -> bool:
    """Detect family, entity, gift, or nominal tax transfers where transfer tax math != market price."""
    doc_upper = (doc_type or "").upper()
    if any(dt in doc_upper for dt in ["QUITCLAIM", "GIFT", "AFFIDAVIT", "TRUST", "INTERSPOUSAL"]):
        return True

    if transfer_tax is not None and transfer_tax <= 1.10:
        return True  # Nominal or zero tax

    if grantor and grantee:
        g1_words = [w for w in re.split(r"\W+", grantor.upper()) if len(w) > 2]
        g2_words = [w for w in re.split(r"\W+", grantee.upper()) if len(w) > 2]
        # Surname or common entity match
        if any(w in g2_words for w in g1_words):
            return True

    return False


def calculate_price_from_transfer_tax(
    transfer_tax: float, rate_per_thousand: float = BUTTE_TRANSFER_TAX_RATE
) -> Optional[float]:
    if transfer_tax is None or transfer_tax <= 0:
        return None
    return round((transfer_tax / rate_per_thousand) * 1000.0, 2)


def resolve_sale_price(
    assessed_total: Optional[float],
    recorder_deed_date: Optional[str] = None,
    recorder_transfer_tax: Optional[float] = None,
    assessor_last_sale_date: Optional[str] = None,
    assessor_last_sale_price: Optional[float] = None,
    grantor: Optional[str] = None,
    grantee: Optional[str] = None,
    doc_type: Optional[str] = None,
    is_top_tier: bool = False,
) -> Tuple[Optional[float], SalePriceConfidence, Optional[str], Optional[float]]:
    """
    Resolution Ladder (§4):
    1. Recorder-verified (top ~10-20% tier or escalated if valid transfer tax & arm's length)
    2. Assessor / ParcelQuest last sale (if recorded date/price available)
    3. Assessor proxy (default, ~100% coverage)
    4. No deed on file (no sale date/price anywhere -> unknown sale)

    Returns: (sale_price_final, sale_price_confidence, resolved_last_sale_date, last_sale_price_recorded)
    """
    sale_price_final: Optional[float] = None
    confidence: SalePriceConfidence = SalePriceConfidence.NO_DEED_UNKNOWN
    resolved_sale_date: Optional[str] = None
    recorded_price: Optional[float] = None

    # Check recorder grant deed transfer tax
    if recorder_transfer_tax is not None and recorder_transfer_tax > 0:
        non_arms = is_non_arms_length_transfer(grantor, grantee, doc_type, recorder_transfer_tax)
        if not non_arms:
            recorded_price = calculate_price_from_transfer_tax(recorder_transfer_tax)

    # Ladder Step 1: Recorder-verified (for top tier or explicit recorder hit)
    if is_top_tier and recorded_price is not None and recorder_deed_date:
        sale_price_final = recorded_price
        confidence = SalePriceConfidence.RECORDER_VERIFIED
        resolved_sale_date = recorder_deed_date
        return sale_price_final, confidence, resolved_sale_date, recorded_price

    # Ladder Step 2: Assessor / ParcelQuest roll sale date + price
    if assessor_last_sale_price is not None and assessor_last_sale_price > 0 and assessor_last_sale_date:
        sale_price_final = assessor_last_sale_price
        confidence = SalePriceConfidence.PARCELQUEST
        resolved_sale_date = assessor_last_sale_date
        return sale_price_final, confidence, resolved_sale_date, recorded_price or assessor_last_sale_price

    # Ladder Step 3: Assessor proxy (assessed total from tax bill)
    if assessed_total is not None and assessed_total > 0:
        sale_price_final = assessed_total
        confidence = SalePriceConfidence.ASSESSOR_PROXY
        resolved_sale_date = recorder_deed_date or assessor_last_sale_date
        return sale_price_final, confidence, resolved_sale_date, recorded_price

    # Ladder Step 4: No deed on file (estates, never-recorded land)
    resolved_sale_date = recorder_deed_date or assessor_last_sale_date
    confidence = SalePriceConfidence.NO_DEED_UNKNOWN
    return None, confidence, resolved_sale_date, recorded_price


def compute_sales_equity_layer(
    apn: str,
    county: str,
    assessed_land: Optional[float] = None,
    assessed_improve: Optional[float] = None,
    assessed_total: Optional[float] = None,
    base_year_value: Optional[float] = None,
    recorder_deed_date: Optional[str] = None,
    recorder_transfer_tax: Optional[float] = None,
    assessor_last_sale_date: Optional[str] = None,
    assessor_last_sale_price: Optional[float] = None,
    market_estimate: Optional[float] = None,
    market_estimate_source: MarketEstimateSource = MarketEstimateSource.NONE,
    grantor: Optional[str] = None,
    grantee: Optional[str] = None,
    doc_type: Optional[str] = None,
    is_estate_or_deceased: bool = False,
    is_top_tier: bool = False,
) -> SalesEquityValuation:
    """
    Main entry point to compute all sales & equity fields for a parcel.
    """
    # 1. Valuation anchor (factored base-year proxy floor)
    if assessed_total is None or assessed_total <= 0:
        val_land = assessed_land or 0.0
        val_imp = assessed_improve or 0.0
        assessed_total = val_land + val_imp if (val_land + val_imp) > 0 else None

    proxy_assessor = base_year_value or assessed_total

    # 2. Resolve Sale Price via ladder
    sale_price_final, sale_conf, last_sale_date, recorded_price = resolve_sale_price(
        assessed_total=proxy_assessor,
        recorder_deed_date=recorder_deed_date,
        recorder_transfer_tax=recorder_transfer_tax,
        assessor_last_sale_date=assessor_last_sale_date,
        assessor_last_sale_price=assessor_last_sale_price,
        grantor=grantor,
        grantee=grantee,
        doc_type=doc_type,
        is_top_tier=is_top_tier,
    )

    # 3. Calculate Tenure
    tenure_years = calculate_tenure_years(last_sale_date)

    # 4. Equity Feature Engine (§5)
    equity_estimate: Optional[float] = None
    equity_band: EquityBand = EquityBand.UNKNOWN
    equity_conf: EquityConfidence = EquityConfidence.UNKNOWN
    excess_candidate: bool = False

    # (a) Measured equity gap — when market_estimate exists
    if market_estimate is not None and market_estimate > 0 and proxy_assessor is not None and proxy_assessor > 0:
        equity_estimate = round(market_estimate - proxy_assessor, 2)
        equity_conf = EquityConfidence.MEASURED

        gap_ratio = equity_estimate / proxy_assessor
        if equity_estimate <= 0:
            equity_band = EquityBand.NEGATIVE
        elif gap_ratio <= 0.15:
            equity_band = EquityBand.THIN
        elif gap_ratio <= 0.50:
            equity_band = EquityBand.MODERATE
        else:
            equity_band = EquityBand.HIGH

    # (b) Tenure proxy — when last_sale_date exists but no market_estimate
    elif tenure_years is not None:
        equity_conf = EquityConfidence.TENURE_PROXY
        equity_estimate = None  # Do not invent dollar figure

        if tenure_years >= 25.0:
            equity_band = EquityBand.TENURE_LONG
        elif tenure_years >= 12.0:
            equity_band = EquityBand.TENURE_MID
        else:
            equity_band = EquityBand.TENURE_SHORT

    # (c) Unknown — no last_sale_date and no market_estimate (no_deed_unknown parcels)
    else:
        equity_estimate = None
        equity_band = EquityBand.UNKNOWN
        equity_conf = EquityConfidence.UNKNOWN

        # Estate / no-deed parcels are flagged excess proceeds candidates
        if is_estate_or_deceased or sale_conf == SalePriceConfidence.NO_DEED_UNKNOWN:
            if is_estate_or_deceased:
                excess_candidate = True

    return SalesEquityValuation(
        county=county,
        apn_norm=apn,
        sale_price_proxy_assessor=proxy_assessor,
        base_year_value=base_year_value,
        last_sale_date=last_sale_date,
        last_sale_price_recorded=recorded_price,
        sale_price_final=sale_price_final,
        sale_price_confidence=sale_conf,
        tenure_years=tenure_years,
        market_estimate=market_estimate,
        market_estimate_source=market_estimate_source if market_estimate else MarketEstimateSource.NONE,
        equity_estimate=equity_estimate,
        equity_band=equity_band,
        equity_confidence=equity_conf,
        excess_proceeds_candidate=excess_candidate,
    )


def evaluate_equity_gate(val: SalesEquityValuation) -> Tuple[str, str]:
    """
    Evaluates the Equity Leg of the gated score (§7).

    Rules:
      - PASS if (equity_confidence == measured and equity_band in {moderate, high})
           OR (equity_confidence == measured and equity_estimate > 0)
           OR (equity_confidence == tenure_proxy and tenure_years >= 12)
      - UNKNOWN_ROUTE if equity_confidence == unknown
      - FAIL_DEMOTE otherwise
    """
    if val.equity_confidence == EquityConfidence.UNKNOWN:
        if val.excess_proceeds_candidate:
            return "UNKNOWN_ROUTE", "Unknown equity on estate parcel -> route to excess-proceeds track"
        return "UNKNOWN_ROUTE", "Unknown equity -> route to excess-proceeds / estate track"

    if val.equity_confidence == EquityConfidence.MEASURED:
        if val.equity_band in (EquityBand.MODERATE, EquityBand.HIGH):
            return "PASS", f"Qualified measured equity gap (${val.equity_estimate:,.2f}, band: {val.equity_band.value})"
        return "FAIL_DEMOTE", f"Measured equity thin/negative ({val.equity_band.value}) — no room in deal"

    if val.equity_confidence == EquityConfidence.TENURE_PROXY:
        if val.tenure_years is not None and val.tenure_years >= 12.0:
            return "PASS", f"Tenure proxy ({val.tenure_years:.1f} years held — band: {val.equity_band.value})"
        return "FAIL_DEMOTE", f"Tenure proxy too short ({val.tenure_years:.1f} years held — band: {val.equity_band.value})"

    return "FAIL_DEMOTE", f"Insufficient equity signal ({val.equity_band.value})"

