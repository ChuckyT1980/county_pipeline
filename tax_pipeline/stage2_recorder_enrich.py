import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import json
import pandas as pd
from playwright.sync_api import sync_playwright

from crm_schema.models import OwnerVesting, EncumbranceSummary, RecorderEvent
from crm_schema.enums import OwnershipVerificationStatus, RecorderEventRole, EquitySignal, DistressSignal

from tax_pipeline.recorder_config import RECORDER_CONFIG

# ==========================================
# STAGE 2 OUTPUT SCHEMA
# ==========================================

STAGE2_OUTPUT_COLUMNS = [
    # Stage 1 (tax portal) fields carried through
    "asmt",                  # internal assessment/parcel ID
    "apn_dash",              # county-formatted APN (e.g. 002-271-003-000)
    "address",               # situs address
    "county",                # county name (e.g. butte, shasta)
    "verified_url",          # tax portal URL used for lookup
    "verified_at",           # timestamp of tax verification
    "v_total_due",           # total tax billed
    "v_total_paid",          # amount paid
    "v_total_balance",       # remaining balance
    "v_delinquent",          # boolean delinquency flag
    "v_document_number",     # base instrument/doc number from tax portal
    "owner_name",            # assessor owner name (may be stale)
    "error",                 # tax-stage error flag, if any
    "parcel_number",         # normalized parcel ID key
    # Stage 2 (recorder) enrichment
    "owner_vesting",         # JSON: ownership/vesting structure
    "encumbrance_summary",   # JSON: mortgages/liens/NOD, equity/distress
    "recorder_chain",        # JSON/list: chain of recorder docs and roles
    # Deterministic adjudication (now part of Stage 2)
    "final_ownership_status",  # e.g. VERIFIED, NO_DATA, DRIFT, etc.
    "final_owner_name",        # adjudicated current owner string
    "manual_review_required",  # boolean: True if needs human/LLM review
    "adjudication_confidence", # numeric confidence score (0.0–1.0)
    "adjudication_reasons",    # short codes/text explaining the decision
]

# ==========================================
# RULES & CLASSIFIERS
# ==========================================

RULES = {
    "ownership_change_doc_types": ["DEED", "GRANT DEED", "QUITCLAIM DEED", "TRUSTEE'S DEED", "AFFIDAVIT OF DEATH", "AFFIDAVIT AFFECTING TITLE"],
    "encumbrance_doc_types": ["DEED OF TRUST", "MORTGAGE", "ASSIGNMENT", "RECONVEYANCE", "RELEASE", "SUBSTITUTION"],
    "distress_doc_types": ["NOTICE OF DEFAULT", "STATE TAX LIEN", "FEDERAL TAX LIEN", "JUDGMENT", "LIEN", "NOTICE OF SALE"],
    "distress_neutralizers": ["RESCISSION", "NOTICE OF RESCISSION", "WITHDRAWAL"]
}

def determine_entity_type(name: str) -> str:
    name_upper = name.upper()
    if any(x in name_upper for x in [" LLC", "L.L.C."]): return "LLC"
    if any(x in name_upper for x in [" INC", "CORP", "COMPANY"]): return "CORPORATION"
    if any(x in name_upper for x in [" TRUST", " TR "]): return "TRUST"
    if any(x in name_upper for x in [" ESTATE "]): return "ESTATE"
    return "INDIVIDUAL"

def classify_doc_role(doc_type: str) -> RecorderEventRole:
    dt = doc_type.upper()
    if any(x in dt for x in RULES["distress_neutralizers"]): return RecorderEventRole.OTHER
    if any(x in dt for x in RULES["ownership_change_doc_types"]): return RecorderEventRole.TRANSFER
    if any(x in dt for x in ["DEED OF TRUST", "MORTGAGE"]): return RecorderEventRole.DEBT
    if any(x in dt for x in ["RECONVEYANCE", "RELEASE"]): return RecorderEventRole.RELEASE
    if any(x in dt for x in ["NOTICE OF DEFAULT", "NOTICE OF SALE"]): return RecorderEventRole.DEFAULT
    if any(x in dt for x in RULES["distress_doc_types"]): return RecorderEventRole.LIEN
    return RecorderEventRole.OTHER

def check_same_control(old_name: str, new_name: str) -> bool:
    """Check if 'MARKS MICHELLE A' -> 'MARKS MICHELLE A TRUSTEE' is same control."""
    if not old_name or not new_name:
        return False
    old_parts = set(old_name.upper().replace(',', '').split())
    new_parts = set(new_name.upper().replace(',', '').split())
    # If the root surname/name matches, it's same control
    return len(old_parts.intersection(new_parts)) >= 1

def parse_doc_line(lines):
    """Scan inner_text lines for a doc number (YYYY-NNNNNNN) and extract doc_type.
    Returns (doc_number, doc_type) or (None, None)."""
    for ln in lines:
        m = re.search(r'(\d{4}[A-Za-z\-]?\d{6,7})', ln)
        if m:
            doc_num = m.group(1)
            after = ln[m.end():].strip()
            after = re.sub(r'^[\s\u00a0\u25a0\u25cf\u2022\ufffd\xef\xbf\xbd]+', '', after)
            after = re.sub(r'[\s\u00a0\u25a0\u25cf\u2022\ufffd\xef\xbf\xbd]+$', '', after)
            doc_type = after.strip() if after.strip() else "UNKNOWN"
            return doc_num, doc_type
    return None, None

def format_doc_number(doc_str, county="shasta"):
    if not doc_str or pd.isna(doc_str): return None
    doc_str = str(doc_str).strip()
    if county.lower() == "tehama":
        return doc_str.replace('R', '') if isinstance(doc_str, str) else doc_str
    if county.lower() == "shasta":
        if 'R' in doc_str:
            return doc_str.replace('R', '-')
        if '-' not in doc_str and len(doc_str) >= 11:
            return doc_str[:4] + '-' + doc_str[4:]
    return doc_str
from shasta_recorder_api import ShastaRecorderClient

def run_stage2_shasta_http(input_csv, county):
    print(f"Starting HTTP Stage 2 Recorder Enrichment on {input_csv} for {county}...")
    import pandas as pd
    import json
    import os
    import time
    df = pd.read_csv(input_csv)
    checkpoint_file = input_csv.replace('.csv', '_ENRICHED_partial.parquet')
    
    processed_apns = set()
    results_list = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results_list = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
        
    # As requested by the user, we use a slower delay of 0.4s for Shasta to avoid rate limiting
    client = ShastaRecorderClient(delay_between_requests=0.4) 
    consecutive_errors = 0
    
    for i, row in df.iterrows():
        apn = row.get("parcel_number")
        if pd.isna(apn) or apn in processed_apns:
            continue
            
        doc_raw = row.get("v_document_number")
        doc_fmt = format_doc_number(doc_raw, county)
        
        vesting = OwnerVesting()
        encumbrance = EncumbranceSummary()
        chain = []
        
        if not doc_fmt:
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
            row["owner_vesting"] = vesting.model_dump_json()
            row["encumbrance_summary"] = encumbrance.model_dump_json()
            row["recorder_chain"] = json.dumps([])
            for k, v in adjud.items():
                row[k] = v
            results_list.append(row.to_dict())
            processed_apns.add(apn)
            continue
            
        print(f"[{i+1}/{len(df)}] Pivot 1 HTTP: Extracting Vesting for {apn} via Doc {doc_fmt}...")
        
        try:
            client.submit_doc_search(doc_fmt)
            results, total = client.get_results(page=1)
            
            if results:
                primary_name = None
                for res in results:
                    grantee_name = res.grantees[0] if res.grantees else None
                    grantor_name = res.grantors[0] if res.grantors else None
                    primary_name = grantee_name or grantor_name
                    
                    if primary_name:
                        vesting.primary_name = primary_name
                        vesting.entity_type = determine_entity_type(primary_name)
                        vesting.acquisition_doc = doc_fmt
                        vesting.verified_current_owner_name = primary_name
                        
                        doc_type_str = res.doc_type if res.doc_type else "UNKNOWN"
                        if doc_type_str and doc_type_str != "UNKNOWN":
                            vesting.vesting_doc_type = doc_type_str
                            
                        if res.recording_date:
                            parsed = pd.to_datetime(res.recording_date, errors='coerce')
                            if not pd.isna(parsed):
                                vesting.acquisition_date = parsed.isoformat()
                                
                        doc_type_str = vesting.vesting_doc_type or "UNKNOWN"
                        chain.append(RecorderEvent(
                            event_id=doc_fmt,
                            doc_type=doc_type_str,
                            role=classify_doc_role(doc_type_str),
                            recorded_date=pd.to_datetime(vesting.acquisition_date).isoformat() if vesting.acquisition_date else None,
                            doc_number=doc_fmt,
                            grantor=grantor_name,
                            grantee=grantee_name,
                            source="recorder"
                        ))
                        vesting.source = "recorder"
                        vesting.confidence = 0.9
                        if not row.get("owner_name") or pd.isna(row.get("owner_name")):
                            row["owner_name"] = primary_name
                        break
            else:
                vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
                
            consecutive_errors = 0
                
        except Exception as e:
            print(f"  Error fetching HTTP for {doc_fmt}: {e}")
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            row["error"] = str(e)
            consecutive_errors += 1
            if consecutive_errors > 5:
                print("Too many consecutive HTTP errors. Re-initializing session...")
                client.close()
                time.sleep(2)
                client = ShastaRecorderClient(delay_between_requests=0.6)
                consecutive_errors = 0
                
        if vesting.primary_name and not vesting.ownership_verification_status:
            vesting.ownership_verification_status = OwnershipVerificationStatus.MATCHES_ASSESSOR
            
        adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
        for k, v in adjud.items():
            row[k] = v
            
        row["owner_vesting"] = vesting.model_dump_json()
        row["encumbrance_summary"] = encumbrance.model_dump_json()
        row["recorder_chain"] = json.dumps([c.model_dump(mode="json") for c in chain])
        
        results_list.append(row.to_dict())
        processed_apns.add(apn)
        
        if len(results_list) % 50 == 0:
            pd.DataFrame(results_list).to_parquet(checkpoint_file, index=False)
            print(f"Checkpoint saved: {len(results_list)} records")

    client.close()
    
    out_csv = input_csv.replace('.csv', '_ENRICHED.csv')
    df_out = pd.DataFrame(results_list)
    df_out.to_csv(out_csv, index=False)
    print(f"Saved final to {out_csv}")

    if county.lower() == "tehama":
        # Tehama recorder does not accept hyphens (e.g. 2024-001625 -> 2024001625)
        return doc_str.replace("-", "").replace("ID", "").replace("R", "")
    if county.lower() == "butte":
        # Butte tax portal gives "2024R0030607" -> recorder needs "2024-0030607"
        m = re.match(r'(\d{4})[A-Za-z]?(\d+)', doc_str)
        if m:
            return f"{m.group(1)}-{m.group(2).zfill(7)}"
        return doc_str.replace("-", "")
    # Add dash for Shasta formats if needed
    return re.sub(r'(\d{4})[A-Za-z](\d+)', r'\1-\2', doc_str)

def deterministic_adjudicate(row, vesting, encumbrance, chain):
    """Compute the 5 adjudication fields from vesting/encumbrance state."""
    status = vesting.ownership_verification_status
    owner_name = vesting.primary_name or (row.get("owner_name") or "")
    is_delinquent = bool(row.get("v_delinquent", False))

    if status == OwnershipVerificationStatus.MATCHES_ASSESSOR:
        return {
            "final_ownership_status": "VERIFIED",
            "final_owner_name": owner_name,
            "manual_review_required": False,
            "adjudication_confidence": 1.0,
            "adjudication_reasons": "DETERMINISTIC_BYPASS",
        }
    elif status == OwnershipVerificationStatus.VESTING_CHANGED_SAME_CONTROL:
        return {
            "final_ownership_status": "VERIFIED",
            "final_owner_name": owner_name,
            "manual_review_required": False,
            "adjudication_confidence": 0.9,
            "adjudication_reasons": "SAME_CONTROL_TRANSFER",
        }
    elif status == OwnershipVerificationStatus.RECORDER_SHOWS_NEW_OWNER_LOW_CONFIDENCE:
        return {
            "final_ownership_status": "DRIFT",
            "final_owner_name": owner_name,
            "manual_review_required": True,
            "adjudication_confidence": 0.5,
            "adjudication_reasons": "RECORDER_DRIFT",
        }
    elif status == OwnershipVerificationStatus.NO_RECORDER_HIT:
        return {
            "final_ownership_status": "NO_DATA",
            "final_owner_name": "",
            "manual_review_required": True,
            "adjudication_confidence": 0.0,
            "adjudication_reasons": "NO_RECORDER_HIT",
        }
    else:
        # Fallback for any other status or error
        reason = vesting.ownership_drift_reason or "UNKNOWN_STATUS"
        return {
            "final_ownership_status": "NO_DATA",
            "final_owner_name": owner_name,
            "manual_review_required": True,
            "adjudication_confidence": 0.0,
            "adjudication_reasons": reason,
        }

# ==========================================
# BROWSER AUTOMATION (MULTI-COUNTY TYLER)
# ==========================================


from tehama_recorder_api import TehamaRecorderClient

def run_stage2_tehama_http(input_csv, county):
    print(f"Starting HTTP Stage 2 Recorder Enrichment on {input_csv} for {county}...")
    import pandas as pd
    import json
    import os
    import time
    df = pd.read_csv(input_csv)
    checkpoint_file = input_csv.replace('.csv', '_ENRICHED_partial.parquet')
    
    processed_apns = set()
    results_list = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results_list = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
        
    client = TehamaRecorderClient(delay_between_requests=0.1) # Much faster
    consecutive_errors = 0
    
    for i, row in df.iterrows():
        apn = row.get("parcel_number")
        if pd.isna(apn) or apn in processed_apns:
            continue
            
        doc_raw = row.get("v_document_number")
        doc_fmt = format_doc_number(doc_raw, county)
        
        vesting = OwnerVesting()
        encumbrance = EncumbranceSummary()
        chain = []
        
        if not doc_fmt:
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
            row["owner_vesting"] = vesting.model_dump_json()
            row["encumbrance_summary"] = encumbrance.model_dump_json()
            row["recorder_chain"] = json.dumps([])
            for k, v in adjud.items():
                row[k] = v
            results_list.append(row.to_dict())
            processed_apns.add(apn)
            continue
            
        print(f"[{i+1}/{len(df)}] Pivot 1 HTTP: Extracting Vesting for {apn} via Doc {doc_fmt}...")
        
        try:
            client.submit_doc_search(doc_fmt)
            results, total = client.get_results(search_type="DOCSEARCH4S2")
            
            if results:
                primary_name = None
                for res in results:
                    grantee_name = res.grantees[0] if res.grantees else None
                    grantor_name = res.grantors[0] if res.grantors else None
                    primary_name = grantee_name or grantor_name
                    
                    if primary_name:
                        vesting.primary_name = primary_name
                        vesting.entity_type = determine_entity_type(primary_name)
                        vesting.acquisition_doc = doc_fmt
                        vesting.verified_current_owner_name = primary_name
                        
                        doc_type_str = res.doc_type if res.doc_type else "UNKNOWN"
                        if doc_type_str and doc_type_str != "UNKNOWN":
                            vesting.vesting_doc_type = doc_type_str
                            
                        if res.recording_date:
                            parsed = pd.to_datetime(res.recording_date, errors='coerce')
                            if not pd.isna(parsed):
                                vesting.acquisition_date = parsed.isoformat()
                                
                        doc_type_str = vesting.vesting_doc_type or "UNKNOWN"
                        chain.append(RecorderEvent(
                            event_id=doc_fmt,
                            doc_type=doc_type_str,
                            role=classify_doc_role(doc_type_str),
                            recorded_date=pd.to_datetime(vesting.acquisition_date).isoformat() if vesting.acquisition_date else None,
                            doc_number=doc_fmt,
                            grantor=grantor_name,
                            grantee=grantee_name,
                            source="recorder"
                        ))
                        vesting.source = "recorder"
                        vesting.confidence = 0.9
                        if not row.get("owner_name") or pd.isna(row.get("owner_name")):
                            row["owner_name"] = primary_name
                        break
            else:
                vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
                
            consecutive_errors = 0
                
        except Exception as e:
            print(f"  Error fetching HTTP for {doc_fmt}: {e}")
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            row["error"] = str(e)
            consecutive_errors += 1
            if consecutive_errors > 5:
                print("Too many consecutive HTTP errors. Re-initializing session...")
                client.close()
                time.sleep(2)
                client = TehamaRecorderClient(delay_between_requests=0.2)
                consecutive_errors = 0
                
        if vesting.primary_name and not vesting.ownership_verification_status:
            vesting.ownership_verification_status = OwnershipVerificationStatus.MATCHES_ASSESSOR
            
        adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
        for k, v in adjud.items():
            row[k] = v
            
        row["owner_vesting"] = vesting.model_dump_json()
        row["encumbrance_summary"] = encumbrance.model_dump_json()
        row["recorder_chain"] = json.dumps([c.model_dump(mode="json") for c in chain])
        
        results_list.append(row.to_dict())
        processed_apns.add(apn)
        
        if len(results_list) % 50 == 0:
            pd.DataFrame(results_list).to_parquet(checkpoint_file, index=False)
            print(f"Checkpoint saved: {len(results_list)} records")

    client.close()
    
    out_csv = input_csv.replace('.csv', '_ENRICHED.csv')
    df_out = pd.DataFrame(results_list)
    df_out.to_csv(out_csv, index=False)
    print(f"Saved final to {out_csv}")


from shasta_recorder_api import ShastaRecorderClient

def run_stage2_shasta_http(input_csv, county):
    print(f"Starting HTTP Stage 2 Recorder Enrichment on {input_csv} for {county}...")
    import pandas as pd
    import json
    import os
    import time
    df = pd.read_csv(input_csv)
    checkpoint_file = input_csv.replace('.csv', '_ENRICHED_partial.parquet')
    
    processed_apns = set()
    results_list = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results_list = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
        
    # As requested by the user, we use a slower delay of 0.4s for Shasta to avoid rate limiting
    client = ShastaRecorderClient(delay_between_requests=0.4) 
    consecutive_errors = 0
    
    for i, row in df.iterrows():
        apn = row.get("parcel_number")
        if pd.isna(apn) or apn in processed_apns:
            continue
            
        doc_raw = row.get("v_document_number")
        doc_fmt = format_doc_number(doc_raw, county)
        
        vesting = OwnerVesting()
        encumbrance = EncumbranceSummary()
        chain = []
        
        if not doc_fmt:
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
            row["owner_vesting"] = vesting.model_dump_json()
            row["encumbrance_summary"] = encumbrance.model_dump_json()
            row["recorder_chain"] = json.dumps([])
            for k, v in adjud.items():
                row[k] = v
            results_list.append(row.to_dict())
            processed_apns.add(apn)
            continue
            
        print(f"[{i+1}/{len(df)}] Pivot 1 HTTP: Extracting Vesting for {apn} via Doc {doc_fmt}...")
        
        try:
            client.submit_doc_search(doc_fmt)
            results, total = client.get_results(page=1)
            
            if results:
                primary_name = None
                for res in results:
                    grantee_name = res.grantees[0] if res.grantees else None
                    grantor_name = res.grantors[0] if res.grantors else None
                    primary_name = grantee_name or grantor_name
                    
                    if primary_name:
                        vesting.primary_name = primary_name
                        vesting.entity_type = determine_entity_type(primary_name)
                        vesting.acquisition_doc = doc_fmt
                        vesting.verified_current_owner_name = primary_name
                        
                        doc_type_str = res.doc_type if res.doc_type else "UNKNOWN"
                        if doc_type_str and doc_type_str != "UNKNOWN":
                            vesting.vesting_doc_type = doc_type_str
                            
                        if res.recording_date:
                            parsed = pd.to_datetime(res.recording_date, errors='coerce')
                            if not pd.isna(parsed):
                                vesting.acquisition_date = parsed.isoformat()
                                
                        doc_type_str = vesting.vesting_doc_type or "UNKNOWN"
                        chain.append(RecorderEvent(
                            event_id=doc_fmt,
                            doc_type=doc_type_str,
                            role=classify_doc_role(doc_type_str),
                            recorded_date=pd.to_datetime(vesting.acquisition_date).isoformat() if vesting.acquisition_date else None,
                            doc_number=doc_fmt,
                            grantor=grantor_name,
                            grantee=grantee_name,
                            source="recorder"
                        ))
                        vesting.source = "recorder"
                        vesting.confidence = 0.9
                        if not row.get("owner_name") or pd.isna(row.get("owner_name")):
                            row["owner_name"] = primary_name
                        break
            else:
                vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
                
            consecutive_errors = 0
                
        except Exception as e:
            print(f"  Error fetching HTTP for {doc_fmt}: {e}")
            vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
            row["error"] = str(e)
            consecutive_errors += 1
            if consecutive_errors > 5:
                print("Too many consecutive HTTP errors. Re-initializing session...")
                client.close()
                time.sleep(2)
                client = ShastaRecorderClient(delay_between_requests=0.6)
                consecutive_errors = 0
                
        if vesting.primary_name and not vesting.ownership_verification_status:
            vesting.ownership_verification_status = OwnershipVerificationStatus.MATCHES_ASSESSOR
            
        adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
        for k, v in adjud.items():
            row[k] = v
            
        row["owner_vesting"] = vesting.model_dump_json()
        row["encumbrance_summary"] = encumbrance.model_dump_json()
        row["recorder_chain"] = json.dumps([c.model_dump(mode="json") for c in chain])
        
        results_list.append(row.to_dict())
        processed_apns.add(apn)
        
        if len(results_list) % 50 == 0:
            pd.DataFrame(results_list).to_parquet(checkpoint_file, index=False)
            print(f"Checkpoint saved: {len(results_list)} records")

    client.close()
    
    out_csv = input_csv.replace('.csv', '_ENRICHED.csv')
    df_out = pd.DataFrame(results_list)
    df_out.to_csv(out_csv, index=False)
    print(f"Saved final to {out_csv}")

def run_stage2(input_csv, county):
    if county.lower() in ["tehama", "shasta"]:
        from stage2_http import run_stage2_http
        return run_stage2_http(input_csv, county)

    print(f"Starting Stage 2 Recorder Enrichment on {input_csv} for {county}...")
    df = pd.read_csv(input_csv)
    checkpoint_file = input_csv.replace('.csv', '_ENRICHED_partial.parquet')
    
    cfg = RECORDER_CONFIG.get(county.lower())
    if not cfg:
        raise ValueError(f"Unknown county {county} in recorder_config.py")
        
    processed_apns = set()
    results = []
    
    if os.path.exists(checkpoint_file):
        existing_df = pd.read_parquet(checkpoint_file)
        results = existing_df.to_dict("records")
        processed_apns = set(existing_df["parcel_number"].dropna().tolist())
        print(f"Resuming from checkpoint: {len(processed_apns)} already processed.")
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        
        # Navigate to search page directly to trigger disclaimer (some counties
        # only show the disclaimer when accessing a search page, not the home page)
        search_url = cfg.get("name_search_url") or cfg.get("doc_search_url") or cfg["login_url"]
        print(f"Loading {county} portal: {search_url}")
        page.goto(search_url, wait_until="networkidle")
        page.wait_for_timeout(2000)
        
        disclaimer_sel = cfg.get("disclaimer_selector", "#submitDisclaimerAccept")
        if cfg.get("has_disclaimer") and disclaimer_sel:
            if page.query_selector(disclaimer_sel):
                print("  Accepting disclaimer...")
                page.click(disclaimer_sel, force=True)
                page.wait_for_timeout(3000)
                page.wait_for_load_state("networkidle")
                # After disclaimer, navigate back to search page
                if "search" not in page.url.lower():
                    print(f"  Disclaimed redirected to: {page.url}. Navigating back to search...")
                    page.goto(search_url, wait_until="networkidle")
                    page.wait_for_timeout(2000)
            
        consecutive_errors = 0
            
        for i, row in df.iterrows():
            apn = row.get("parcel_number")
            if pd.isna(apn) or apn in processed_apns:
                continue
                
            doc_raw = row.get("v_document_number")
            doc_fmt = format_doc_number(doc_raw, county)
            
            # Init empty profile objects using Pydantic schema
            vesting = OwnerVesting()
            encumbrance = EncumbranceSummary()
            chain = []
            
            if not doc_fmt:
                vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
                adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
                row["owner_vesting"] = vesting.model_dump_json()
                row["encumbrance_summary"] = encumbrance.model_dump_json()
                row["recorder_chain"] = json.dumps([])
                for k, v in adjud.items():
                    row[k] = v
                results.append(row.to_dict())
                processed_apns.add(apn)
                continue
                
            print(f"[{i+1}/{len(df)}] Pivot 1: Extracting Vesting for {apn} via Doc {doc_fmt}...")
            primary_name = None
            
            try:
                # ---------------------------------------------------------
                # STEP 1: VESTING PIVOT (Document Search)
                # ---------------------------------------------------------
                page.goto(cfg["doc_search_url"], wait_until="networkidle")
                page.wait_for_timeout(2000)
                
                # Check for disclaimer again (some portals loop back)
                if cfg.get("has_disclaimer") and page.query_selector(disclaimer_sel):
                    page.evaluate(f"() => {{ const btn = document.querySelector('{disclaimer_sel}'); if(btn) btn.removeAttribute('disabled'); }}")
                    page.click(disclaimer_sel, force=True)
                    page.wait_for_timeout(2000)
                    page.wait_for_load_state("networkidle")
                    # After disclaimer, navigate back to search page
                    if "searchResults" not in page.url and "DOCSEARCH" not in page.url:
                        page.goto(cfg["doc_search_url"], wait_until="networkidle")
                        page.wait_for_timeout(2000)
                
                # Wait for the actual search field to exist in DOM (jQuery Mobile loads via AJAX)
                try:
                    page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
                except:
                    print(f"  WARNING: {cfg['doc_search_field']} not found after disclaimer. Retrying full load...")
                    page.goto(cfg["doc_search_url"], wait_until="networkidle")
                    page.wait_for_timeout(3000)
                    page.wait_for_selector(cfg["doc_search_field"], timeout=10000)
                
                # Input document number
                page.fill(cfg["doc_search_field"], doc_fmt)
                # Butte's JQM wraps <a> buttons — use native JS click for reliability
                if county.lower() == "butte":
                    page.evaluate('() => document.querySelector("#searchButton").click()')
                else:
                    page.wait_for_selector(cfg["search_button"], timeout=5000)
                    page.click(cfg["search_button"])
                
                try:
                    page.wait_for_selector(cfg["results_selector"], timeout=15000)
                except:
                    pass
                
                # Bug 3 fix: use networkidle instead of bare sleep
                page.wait_for_timeout(2000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except:
                    pass
                elements = page.query_selector_all(cfg["results_selector"])
                
                if elements:
                    for element in elements:
                        text = element.inner_text()
                        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                        
                        # Find Grantee and Grantor
                        grantee_name = None
                        grantor_name = None
                        for j, ln in enumerate(lines):
                            if "Grantee" in ln and j + 1 < len(lines):
                                grantee_name = lines[j+1]
                            elif "Grantor" in ln and j + 1 < len(lines):
                                grantor_name = lines[j+1]
                        primary_name = grantee_name or grantor_name
                                
                        if primary_name:
                            vesting.primary_name = primary_name
                            vesting.entity_type = determine_entity_type(primary_name)
                            vesting.acquisition_doc = doc_fmt
                            vesting.verified_current_owner_name = primary_name
                            
                            _, doc_type_str = parse_doc_line(lines)
                            if doc_type_str and doc_type_str != "UNKNOWN":
                                vesting.vesting_doc_type = doc_type_str

                            for j, ln in enumerate(lines):
                                if "Recording Date" in ln and j + 1 < len(lines):
                                    raw_dt = lines[j+1].split()[0] if lines[j+1] else None
                                    if raw_dt:
                                        parsed = pd.to_datetime(raw_dt, errors='coerce')
                                        if not pd.isna(parsed):
                                            vesting.acquisition_date = parsed.isoformat()
                                    break
                            
                            doc_type_str = vesting.vesting_doc_type or "UNKNOWN"
                            chain.append(RecorderEvent(
                                event_id=doc_fmt,
                                doc_type=doc_type_str,
                                role=classify_doc_role(doc_type_str),
                                recorded_date=pd.to_datetime(vesting.acquisition_date).isoformat() if vesting.acquisition_date else None,
                                doc_number=doc_fmt,
                                grantor=grantor_name,
                                grantee=grantee_name,
                                source="recorder"
                            ))
                            vesting.source = "recorder"
                            vesting.confidence = 0.9
                            # Backfill owner_name from recorder if Stage 1 left it empty
                            if not row.get("owner_name") or pd.isna(row.get("owner_name")):
                                row["owner_name"] = primary_name
                            break
                            
                # ---------------------------------------------------------
                # STEP 2: ENCUMBRANCE PIVOT (Name Search)
                # ---------------------------------------------------------
                if primary_name:
                    print(f"          Pivot 2: Extracting Chain for {primary_name}...")
                    vesting.ownership_verification_status = OwnershipVerificationStatus.MATCHES_ASSESSOR
                    vesting.ownership_drift_flag = False
                    vesting.ownership_drift_reason = None
                    
                    page.goto(cfg["name_search_url"], wait_until="networkidle")
                    page.wait_for_timeout(2000)
                    
                    if cfg.get("has_disclaimer") and page.query_selector(disclaimer_sel):
                        page.click(disclaimer_sel, force=True)
                        page.wait_for_timeout(2000)
                        page.wait_for_load_state("networkidle")
                        if "searchResults" not in page.url and "DOCSEARCH" not in page.url:
                            page.goto(cfg["name_search_url"], wait_until="networkidle")
                            page.wait_for_timeout(2000)
                    
                    # Wait for the actual search field to exist in DOM
                    try:
                        page.wait_for_selector(cfg["search_field"], timeout=10000)
                    except:
                        print(f"  WARNING: {cfg['search_field']} not found. Retrying...")
                        page.goto(cfg["name_search_url"], wait_until="networkidle")
                        page.wait_for_timeout(3000)
                        page.wait_for_selector(cfg["search_field"], timeout=10000)
                    
                    page.fill(cfg["search_field"], primary_name)
                    # Butte's jQuery Mobile wraps the <a> in a button widget;
                    # Playwright's synthetic click misses the JQM handler.
                    # Use native JS click to trigger the real DOM event.
                    if county.lower() == "butte":
                        page.evaluate('() => document.querySelector("#searchButton").click()')
                    else:
                        page.wait_for_selector(cfg["search_button"], timeout=5000)
                        page.click(cfg["search_button"])
                    
                    # Name search is AJAX-based on Butte (results load inline,
                    # URL never changes). Wait for result rows to appear.
                    try:
                        page.wait_for_selector(cfg["results_selector"], timeout=15000)
                    except:
                        pass
                    
                    page.wait_for_timeout(2000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=8000)
                    except:
                        pass
                    name_elements = page.query_selector_all(cfg["results_selector"])
                    
                    if name_elements:
                        for element in name_elements:
                            text = element.inner_text()
                            if "Document Number" in text and "Recording Date" in text:
                                continue
                                
                            lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
                            if not lines: continue
                            
                            doc_num_str, dtype = parse_doc_line(lines)
                            if not doc_num_str:
                                doc_num_str = "UNKNOWN"
                                dtype = "UNKNOWN"
                            
                            if doc_num_str == doc_fmt:
                                continue
                                
                            d_date = None
                            for j, ln in enumerate(lines):
                                if "Recording Date" in ln and j + 1 < len(lines):
                                    d_date = lines[j+1].split()[0]
                                    break
                                    
                            iso_date = None
                            if d_date:
                                parsed = pd.to_datetime(d_date, errors='coerce')
                                if not pd.isna(parsed):
                                    iso_date = parsed.isoformat()
                            role = classify_doc_role(dtype)

                            # Extract grantor and grantee from result lines
                            row_grantee = None
                            row_grantor = None
                            for j, ln in enumerate(lines):
                                if "Grantee" in ln and j + 1 < len(lines):
                                    row_grantee = lines[j+1]
                                elif "Grantor" in ln and j + 1 < len(lines):
                                    row_grantor = lines[j+1]
                            
                            # Encumbrance metrics
                            if role == RecorderEventRole.DEBT:
                                encumbrance.total_open_mortgages += 1
                                if not encumbrance.last_mortgage_date or (iso_date and iso_date > encumbrance.last_mortgage_date):
                                    encumbrance.last_mortgage_date = iso_date
                            elif role == RecorderEventRole.RELEASE:
                                encumbrance.total_open_mortgages = max(0, encumbrance.total_open_mortgages - 1)
                            elif role == RecorderEventRole.LIEN:
                                encumbrance.active_liens.append(dtype)
                                encumbrance.distress_signal = DistressSignal.HIGH
                            elif role == RecorderEventRole.DEFAULT:
                                encumbrance.notice_of_default = True
                                encumbrance.distress_signal = DistressSignal.CRITICAL
                            elif role == RecorderEventRole.OTHER and any(x in dtype for x in RULES["distress_neutralizers"]):
                                encumbrance.notice_of_default = False
                                encumbrance.distress_signal = DistressSignal.RESOLVED
                                
                            elif role == RecorderEventRole.TRANSFER:
                                if vesting.acquisition_date and (iso_date and iso_date > vesting.acquisition_date):
                                    if row_grantee and check_same_control(vesting.primary_name, row_grantee):
                                        vesting.ownership_verification_status = OwnershipVerificationStatus.VESTING_CHANGED_SAME_CONTROL
                                        vesting.ownership_drift_flag = False
                                        vesting.ownership_drift_reason = f"Intra-entity transfer ({dtype}) on {d_date}"
                                    else:
                                        vesting.ownership_verification_status = OwnershipVerificationStatus.RECORDER_SHOWS_NEW_OWNER_LOW_CONFIDENCE
                                        vesting.ownership_drift_flag = True
                                        vesting.ownership_drift_reason = f"Found newer {dtype} on {d_date}"
                            
                            chain.append(RecorderEvent(
                                event_id=f"{doc_num_str}_{i}",
                                doc_type=dtype,
                                role=role,
                                recorded_date=iso_date,
                                doc_number=doc_num_str,
                                grantor=row_grantor,
                                grantee=row_grantee,
                                source="recorder"
                            ))
                            
                    # Calculate equity signal
                    if encumbrance.notice_of_default or encumbrance.active_liens:
                        encumbrance.equity_signal = EquitySignal.DISTRESSED
                    elif encumbrance.total_open_mortgages == 0:
                        encumbrance.equity_signal = EquitySignal.LIKELY_POSITIVE
                    else:
                        encumbrance.equity_signal = EquitySignal.LEVERAGED
                    encumbrance.source = "recorder"
                    encumbrance.confidence = 0.8 if name_elements else 0.0
                        
                consecutive_errors = 0  # Reset on success
                        
            except Exception as e:
                err_msg = str(e)
                print(f"Error during enrichment for {apn}: {err_msg}")
                
                # Check for internet disconnects
                if "net::ERR_NAME_NOT_RESOLVED" in err_msg or "net::ERR_NETWORK_CHANGED" in err_msg or "Timeout" in err_msg:
                    consecutive_errors += 1
                    if consecutive_errors >= 5:
                        print("CRITICAL: Detected 5 consecutive network errors. Internet likely dropped.")
                        print("Aborting script immediately to preserve checkpoint integrity.")
                        import sys
                        sys.exit(1)
                
                vesting.ownership_verification_status = OwnershipVerificationStatus.NO_RECORDER_HIT
                vesting.ownership_drift_reason = err_msg
            
            # Backfill owner_name from recorder if Stage 1 left it empty
            if not row.get("owner_name") or pd.isna(row.get("owner_name")):
                row["owner_name"] = vesting.primary_name or ""
            
            # Deterministic adjudication
            adjud = deterministic_adjudicate(row, vesting, encumbrance, chain)
            
            row["owner_vesting"] = vesting.model_dump_json()
            row["encumbrance_summary"] = encumbrance.model_dump_json()
            if chain:
                row["recorder_chain"] = json.dumps([e.model_dump(mode="json") for e in chain])
            for k, v in adjud.items():
                row[k] = v
            
            results.append(row.to_dict())
            processed_apns.add(apn)
            
            if len(processed_apns) % 10 == 0:
                pd.DataFrame(results).to_parquet(checkpoint_file)
                
        browser.close()
        
    out_df = pd.DataFrame(results)
    out_name = input_csv.replace("_VERIFIED.csv", "_ENRICHED.csv")
    if out_name == input_csv:
        out_name = input_csv.replace(".csv", "_ENRICHED.csv")
    out_df.to_csv(out_name, index=False)
    
    if os.path.exists(checkpoint_file):
        os.remove(checkpoint_file)
    print(f"Saved {len(out_df)} fully enriched records to {out_name}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv")
    parser.add_argument("county")
    args = parser.parse_args()
    
    run_stage2(args.input_csv, args.county)
