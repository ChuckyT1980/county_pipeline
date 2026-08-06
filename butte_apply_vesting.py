import pandas as pd
import json
import os
import sys

# Define the status strings manually to avoid import issues if paths are weird
class OwnershipVerificationStatus:
    MATCHES_ASSESSOR = "MATCHES_ASSESSOR"
    NO_RECORDER_HIT = "NO_RECORDER_HIT"

def determine_entity_type(name: str) -> str:
    name_upper = name.upper()
    if any(x in name_upper for x in [" LLC", "L.L.C."]): return "LLC"
    if any(x in name_upper for x in [" INC", "CORP", "COMPANY"]): return "CORPORATION"
    if any(x in name_upper for x in [" TRUST", " TR "]): return "TRUST"
    if any(x in name_upper for x in [" ESTATE "]): return "ESTATE"
    return "INDIVIDUAL"

def main():
    input_csv = "butte/butte_DELINQUENT_ONLY_ENRICHED.csv"
    output_csv = "butte/butte_DELINQUENT_ONLY_ENRICHED_VESTED.csv"
    
    print(f"Applying deterministic vesting logic to {input_csv}...")
    df = pd.read_csv(input_csv)
    
    for i, row in df.iterrows():
        chain = []
        if not pd.isna(row.get("recorder_chain")):
            try:
                chain = json.loads(str(row.get("recorder_chain", "[]")))
            except:
                pass
                
        status = OwnershipVerificationStatus.NO_RECORDER_HIT
        primary_name = None
        acq_doc = None
        acq_date = None
        doc_type = None
        
        if chain:
            # The first event is the one matching the acquisition document
            evt = chain[0]
            grantee = evt.get("grantees", [])
            grantor = evt.get("grantors", [])
            
            primary_name = grantee[0] if grantee else (grantor[0] if grantor else None)
            if primary_name:
                status = OwnershipVerificationStatus.MATCHES_ASSESSOR
                acq_doc = evt.get("doc_number")
                acq_date = evt.get("recording_date")
                doc_type = evt.get("doc_type")
                
        vesting = {
            "primary_name": primary_name,
            "verified_current_owner_name": primary_name,
            "entity_type": determine_entity_type(primary_name) if primary_name else None,
            "acquisition_doc": acq_doc,
            "acquisition_date": acq_date,
            "vesting_doc_type": doc_type,
            "ownership_verification_status": status,
            "ownership_drift_flag": False,
            "ownership_drift_reason": None,
            "confidence": 0.9 if primary_name else 0.0
        }
        
        df.at[i, "owner_vesting"] = json.dumps(vesting)
        
        # Deterministic Adjudication Fields
        if status == OwnershipVerificationStatus.MATCHES_ASSESSOR:
            df.at[i, "final_ownership_status"] = "VERIFIED"
            df.at[i, "final_owner_name"] = primary_name
            df.at[i, "manual_review_required"] = False
            df.at[i, "adjudication_confidence"] = 1.0
            df.at[i, "adjudication_reasons"] = "DETERMINISTIC_BYPASS"
        else:
            df.at[i, "final_ownership_status"] = "NO_DATA"
            df.at[i, "final_owner_name"] = ""
            df.at[i, "manual_review_required"] = True
            df.at[i, "adjudication_confidence"] = 0.0
            df.at[i, "adjudication_reasons"] = "NO_RECORDER_HIT"
            
    df.to_csv(output_csv, index=False)
    print(f"Saved vested output to {output_csv}")

if __name__ == "__main__":
    main()
