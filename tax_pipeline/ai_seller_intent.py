import os, json, time
from google import genai
from pydantic import BaseModel
from typing import List, Optional

class SellerIntentResult(BaseModel):
    intent_score: int                    # 0-100
    intent_tier: str                     # URGENT / HIGH / MEDIUM / WATCH / COLD
    motivation_narrative: str            # 2-3 sentence plain English — the "why"
    owner_profile_type: str              # ELDERLY_INDIVIDUAL / ABSENTEE / ESTATE / LLC / INVESTOR / UNKNOWN
    contact_strategy: str                # LETTER_FIRST / PHONE_FIRST / DOOR_KNOCK / AGENT / SKIP_ENTITY
    letter_tone: str                     # COMPASSIONATE / BUSINESS / URGENT / NEUTRAL
    risk_flags: List[str]                # Bear case — reasons this might not close
    best_offer_range_low: Optional[int]  # Dollars
    best_offer_range_high: Optional[int] # Dollars
    time_sensitivity: str                # e.g. "Auction eligible June 2026 — 8 months"
    pre_empt_candidate: bool             # True = contact before auction
    confidence: float                    # 0.0-1.0

def build_evidence_packet(row: dict) -> dict:
    """
    Assemble all pipeline fields into a clean evidence packet for the AI.
    Input: a dict from any stage-4+ output CSV row.
    """
    import re
    from datetime import datetime

    def safe_float(v):
        try:
            import math
            val = float(str(v).replace('$', '').replace(',', '').strip())
            return 0.0 if math.isnan(val) else val
        except:
            return 0.0

    def safe_int(v):
        try:
            import math
            val = float(str(v).replace(',', '').strip())
            return 0 if math.isnan(val) else int(val)
        except:
            return 0

    # ── Tax situation ───────────────────────────────────────────────
    tax_balance = safe_float(row.get('v_total_balance') or row.get('tax_balance'))
    tax_delinquent = str(row.get('v_delinquent', '')).lower() in ('true', '1', 'yes')
    delinquency_streak = safe_int(row.get('delinquency_streak', 0))
    inst1_status = row.get('v_inst1_status', '')
    inst2_status = row.get('v_inst2_status', '')

    # ── Property snapshot ───────────────────────────────────────────
    assessed_value = safe_float(row.get('net_assessed_value') or row.get('assessed_value'))
    land_value = safe_float(row.get('land_value'))
    impr_value = safe_float(row.get('impr_value') or row.get('structural_improvement_value'))
    property_type = row.get('property_type', 'UNKNOWN')
    lot_acres = row.get('lot_acres', '')
    legal_desc = row.get('legal_desc', '')
    situs_address = row.get('address') or row.get('situs_full', '')
    year_built = row.get('year_built', '')
    zoning = row.get('zoning', '')

    # ── Owner profile ────────────────────────────────────────────────
    owner_name = row.get('assessee_name') or row.get('owner_name', '')
    mailing_address = row.get('mailing_address', '')
    out_of_state = bool(row.get('out_of_state', False))
    ownership_status = row.get('ownership_status', 'Current')

    # ── Recorder signals ─────────────────────────────────────────────
    active_liens = safe_int(row.get('active_liens', 0))
    mortgages = safe_int(row.get('mortgages', 0))
    has_assignment_rents = str(row.get('has_assignment_of_rents', '')).lower() in ('true', '1', 'yes')
    has_affidavit_death = str(row.get('has_affidavit_of_death', '')).lower() in ('true', '1', 'yes')
    doc_number = row.get('rec_doc_number') or row.get('current_doc_number', '')
    doc_date = row.get('rec_doc_date') or row.get('current_doc_date', '')
    recorder_chain = row.get('recorder_chain', '[]')

    # ── Compute equity estimate ──────────────────────────────────────
    # Rough: assessed * 1.1 approximates market, minus debt
    market_est = assessed_value * 1.1 if assessed_value else 0
    encumbrance_est = (mortgages * 80000) + (active_liens * 15000) + tax_balance  # rough
    equity_est = max(0, market_est - encumbrance_est)

    # ── Auction timing ───────────────────────────────────────────────
    auction_eligible = row.get('auction_eligible', '')
    next_auction_date = row.get('next_auction_date', '')
    days_to_auction = safe_int(row.get('days_to_auction', 0))
    appeared_on_prior_auction_list = str(row.get('appeared_on_prior_auction_list', '')).lower() in ('true', '1', 'yes')
    times_on_auction_list = safe_int(row.get('times_on_auction_list', 0))

    return {
        "apn": row.get('asmt') or row.get('apn', ''),
        "county": row.get('county', ''),
        "address": situs_address,
        "tax_situation": {
            "total_balance_owed": tax_balance,
            "is_delinquent": tax_delinquent,
            "delinquency_streak_years": delinquency_streak,
            "installment_1_status": inst1_status,
            "installment_2_status": inst2_status,
        },
        "property": {
            "assessed_value": assessed_value,
            "land_value": land_value,
            "improvement_value": impr_value,
            "type": property_type,
            "acres": lot_acres,
            "legal_description": legal_desc,
            "year_built": year_built,
            "zoning": zoning,
        },
        "owner": {
            "name": owner_name,
            "mailing_address": mailing_address,
            "is_out_of_state": out_of_state,
            "ownership_status": ownership_status,
        },
        "recorder": {
            "active_liens_count": active_liens,
            "mortgage_count": mortgages,
            "has_assignment_of_rents": has_assignment_rents,
            "has_affidavit_of_death": has_affidavit_death,
            "vesting_doc_number": doc_number,
            "vesting_doc_date": doc_date,
        },
        "equity_estimate": {
            "market_value_estimate": round(market_est),
            "encumbrance_estimate": round(encumbrance_est),
            "estimated_net_equity": round(equity_est),
            "note": "Rough estimate only — verify with recorder lien amounts"
        },
        "auction": {
            "eligible_for_auction": bool(auction_eligible),
            "next_auction_date": next_auction_date,
            "days_to_auction": days_to_auction,
            "appeared_on_prior_list": appeared_on_prior_auction_list,
            "times_listed": times_on_auction_list,
        }
    }


def load_api_key():
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        env_path = os.path.join(os.path.dirname(__file__), '..', '.env')
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("GEMINI_API_KEY="):
                        key = line.strip().split("=", 1)[1]
    return key

SYSTEM_PROMPT = """
You are an expert real estate acquisition analyst for a distressed property intelligence platform 
operating in Northern California county tax auctions.

Your job is to analyze a property evidence packet and produce a structured seller intent assessment.

GUIDELINES:
- Be specific and concrete — reference actual data from the packet
- Do not speculate beyond what the evidence supports  
- Flag genuine risks — do not oversell bad leads
- The motivation_narrative should read naturally, as if briefing an investor
- offer ranges should be conservative (60-75% of estimated equity)
- pre_empt_candidate = True only if: equity > $50k AND days_to_auction > 45 AND owner is individual (not LLC/bank)
- URGENT tier: delinquency_streak >= 3 AND auction within 90 days AND equity > $80k
- HIGH tier: delinquency_streak >= 2 OR multiple distress signals AND equity > $30k
- COLD tier: equity < $5k OR entity owner with no personal signals
"""

class SellerIntentAdjudicator:
    def __init__(self):
        key = load_api_key()
        if key:
            self.client = genai.Client(api_key=key)
            self.model = "gemini-flash-latest"
        else:
            self.client = None

    def score(self, evidence_packet: dict) -> SellerIntentResult:
        if not self.client:
            # Fallback to static scorer
            from seller_intent_scorer import score_from_dict
            score_val, reasons = score_from_dict(evidence_packet)
            return SellerIntentResult(
                intent_score=score_val,
                intent_tier="HIGH" if score_val >= 60 else "MEDIUM" if score_val >= 35 else "COLD",
                motivation_narrative="AI unavailable — static score used.",
                owner_profile_type="UNKNOWN",
                contact_strategy="LETTER_FIRST",
                letter_tone="NEUTRAL",
                risk_flags=["AI_OFFLINE"],
                best_offer_range_low=None,
                best_offer_range_high=None,
                time_sensitivity="",
                pre_empt_candidate=False,
                confidence=0.3
            )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    {"role": "user", "parts": [{"text": SYSTEM_PROMPT}]},
                    {"role": "user", "parts": [{"text": f"EVIDENCE PACKET:\n{json.dumps(evidence_packet, indent=2)}"}]}
                ],
                config={
                    "response_mime_type": "application/json",
                    "response_schema": SellerIntentResult,
                    "temperature": 0.1,
                }
            )
            return SellerIntentResult.model_validate_json(response.text)
        except Exception as e:
            print(f"  [AI] Error: {e}")
            return SellerIntentResult(
                intent_score=0, intent_tier="REVIEW",
                motivation_narrative=f"AI error: {e}",
                owner_profile_type="UNKNOWN", contact_strategy="SKIP_ENTITY",
                letter_tone="NEUTRAL", risk_flags=[str(e)],
                best_offer_range_low=None, best_offer_range_high=None,
                time_sensitivity="", pre_empt_candidate=False, confidence=0.0
            )
