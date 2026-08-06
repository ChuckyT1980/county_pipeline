import os
import json
import pandas as pd
from typing import List, Optional
from pydantic import BaseModel
try:
    from google import genai as new_genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

# ==========================================
# SCHEMA DEFINITIONS (LLM OUTPUT)
# ==========================================

class AdjudicationResult(BaseModel):
    final_ownership_status: str
    final_owner_name: Optional[str]
    ownership_drift_flag: bool
    adjudication_confidence: float
    manual_review_required: bool
    reason_codes: List[str]
    evidence_refs: List[str]

# ==========================================
# ADJUDICATION ENGINE
# ==========================================

class TitleAdjudicator:
    def __init__(self, api_key: str = None):
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key and os.path.exists(".env"):
                with open(".env") as f:
                    for line in f:
                        if line.startswith("GEMINI_API_KEY="):
                            api_key = line.strip().split("=")[1]
        
        if HAS_GENAI and api_key:
            self.client = new_genai.Client(api_key=api_key)
            self.model = "gemini-3.5-flash"
        else:
            self.client = None
            self.model = None

    def adjudicate_record(self, record: dict) -> AdjudicationResult:
        if not self.client:
            return AdjudicationResult(
                final_ownership_status="LLM_NOT_CONFIGURED",
                final_owner_name=record.get("assessor_owner_name"),
                ownership_drift_flag=True,
                adjudication_confidence=0.0,
                manual_review_required=True,
                reason_codes=["llm_offline"],
                evidence_refs=[]
            )

        prompt = f"""ROLE:
You are a deterministic county-recorder extraction and adjudication engine for a distressed property intelligence platform.

PRIMARY TASKS:
Analyze the provided JSON evidence packet. The Python deterministic engine flagged this property as ambiguous or having ownership drift.
Adjudicate the true ownership status and drift flag based on the chronological chain of events.

STRICT RULES:
- If evidence is weak, set manual_review_required = true.
- Use only the provided JSON context.

OWNERSHIP STATUSES:
- MATCHES_ASSESSOR
- RECORDER_SHOWS_NEW_OWNER
- VESTING_CHANGED_SAME_CONTROL
- AMBIGUOUS_NAME_MATCH
- NO_RECORDER_HIT

Return JSON matching the AdjudicationResult schema.

EVIDENCE PACKET:
{json.dumps(record, indent=2)}
"""
        
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": AdjudicationResult,
                    "temperature": 0.0,
                }
            )
            return AdjudicationResult.model_validate_json(response.text)
        except Exception as e:
            print(f"LLM Error: {e}")
            return AdjudicationResult(
                final_ownership_status="LLM_ERROR",
                final_owner_name=None,
                ownership_drift_flag=True,
                adjudication_confidence=0.0,
                manual_review_required=True,
                reason_codes=[str(e)],
                evidence_refs=[]
            )

def run_stage3(input_csv, confidence_threshold=0.5):
    """LLM escalation only. Reads Stage 2 adjudication fields, overrides
    rows where manual_review_required=True and confidence < threshold."""
    print(f"Starting Stage 3 LLM Adjudication on {input_csv}...")
    df = pd.read_csv(input_csv)
    
    adjudicator = TitleAdjudicator()
    
    results = []
    adjudicated_count = 0
    passed_count = 0
    
    for i, row in df.iterrows():
        needs_llm = False
        try:
            needs_llm = bool(row.get("manual_review_required", False))
            confidence = float(row.get("adjudication_confidence", 0))
        except (ValueError, TypeError):
            needs_llm = True
            confidence = 0.0
        
        if needs_llm and confidence < confidence_threshold:
            # Build the context packet for the LLM
            try:
                vesting = json.loads(row.get("owner_vesting", "{}"))
            except:
                vesting = {}
            try:
                enc = json.loads(row.get("encumbrance_summary")) if pd.notna(row.get("encumbrance_summary")) else {}
            except:
                enc = {}
            try:
                chain = json.loads(row.get("recorder_chain")) if pd.notna(row.get("recorder_chain")) else []
            except:
                chain = []
            
            packet = {
                "profile_id": str(row.get("parcel_number", "")),
                "county": row.get("county", "Unknown"),
                "apn": str(row.get("parcel_number", "")),
                "assessor_owner_name": str(row.get("owner_name", "")),
                "owner_vesting": vesting,
                "encumbrance_summary": enc,
                "recorder_chain": chain,
                "ambiguity_reasons": [vesting.get("ownership_drift_reason", "")],
            }
            
            print(f"  [{i+1}] Escalating {packet['apn']} (confidence {confidence:.1f} < {confidence_threshold}) to LLM...")
            
            adj = adjudicator.adjudicate_record(packet)
            
            # Rate limit for Gemini
            import time
            time.sleep(4.2)
            
            # Override adjudication fields with LLM results
            row["final_ownership_status"] = adj.final_ownership_status
            row["final_owner_name"] = adj.final_owner_name or row.get("final_owner_name", "")
            row["manual_review_required"] = adj.manual_review_required
            row["adjudication_confidence"] = adj.adjudication_confidence
            row["adjudication_reasons"] = " | ".join(adj.reason_codes)
            
            adjudicated_count += 1
        else:
            # Pass through Stage 2's deterministic adjudication unchanged
            passed_count += 1
        
        results.append(row.to_dict())
        
    out_df = pd.DataFrame(results)
    out_name = input_csv.replace("_ENRICHED.csv", "_ADJUDICATED.csv")
    if out_name == input_csv:
        out_name = input_csv.replace(".csv", "_ADJUDICATED.csv")
    out_df.to_csv(out_name, index=False)
    
    print(f"Completed! {adjudicated_count} records escalated to LLM, {passed_count} passed through.")
    print(f"Saved {len(out_df)} finalized records to {out_name}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Confidence threshold below which rows get sent to LLM (default: 0.5)")
    args = parser.parse_args()
    
    if not os.path.exists(args.input_csv):
        print(f"Error: {args.input_csv} not found.")
    else:
        run_stage3(args.input_csv, confidence_threshold=args.threshold)
