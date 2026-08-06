import os
import json
import pandas as pd
from datetime import datetime
from pydantic import ValidationError

from crm_schema.models import (
    Identity, AssessorSnapshot, OwnerVesting, EncumbranceSummary, 
    RecorderEvent, PipelineRouting, SellerReadiness, SalesPipeline, 
    Provenance, Audit, DistressedPropertyProfile, ReviewQueueItem
)
from crm_schema.flatten import flatten_profile
from crm_schema.enums import CrmStage, OwnershipVerificationStatus

def parse_date(date_str):
    if not date_str or pd.isna(date_str) or str(date_str).strip() == "":
        return None
    try:
        # Pydantic expects ISO format for dates, convert using pandas
        dt = pd.to_datetime(str(date_str).strip())
        return dt.isoformat()
    except:
        return None

def summarize_encumbrances(chain_json_str):
    try:
        events = json.loads(chain_json_str or "[]")
    except Exception:
        events = []

    total_open_mortgages = 0
    last_mortgage_date = None
    active_liens = []
    notice_of_default = False
    notice_of_rescission = False

    for evt in events:
        doc_type = (evt.get("doc_type") or "").upper()
        role = (evt.get("role") or "").upper()
        recorded_date = evt.get("recorded_date")

        if "DEED OF TRUST" in doc_type and "RELEASE" not in doc_type:
            total_open_mortgages += 1
            if recorded_date:
                try:
                    dt = pd.to_datetime(recorded_date)
                    if not last_mortgage_date or dt > last_mortgage_date:
                        last_mortgage_date = dt
                except Exception:
                    pass

        if "LIEN" in doc_type or "JUDGMENT" in doc_type:
            active_liens.append(f"{doc_type} ({recorded_date or 'No Date'})")

        if "NOTICE OF DEFAULT" in doc_type:
            notice_of_default = True

        if "NOTICE OF RESCISSION" in doc_type:
            notice_of_rescission = True

    if notice_of_default:
        distress_signal = "HIGH"
    elif active_liens or total_open_mortgages >= 2:
        distress_signal = "MEDIUM"
    else:
        distress_signal = "NONE"

    if total_open_mortgages == 0 and not active_liens:
        equity_signal = "LIKELY_POSITIVE"
    elif total_open_mortgages >= 2 or active_liens:
        equity_signal = "LEVERAGED"
    else:
        equity_signal = "UNKNOWN"

    return {
        "total_open_mortgages": total_open_mortgages,
        "last_mortgage_date": last_mortgage_date.isoformat() if last_mortgage_date else None,
        "active_liens": active_liens,
        "notice_of_default": notice_of_default,
        "notice_of_rescission": notice_of_rescission,
        "equity_signal": equity_signal,
        "distress_signal": distress_signal,
        "confidence": None,
    }

def extract_profile_from_row(row, county: str) -> DistressedPropertyProfile:
    # 1. Identity
    identity = Identity(
        county=county.capitalize(),
        state="CA",
        apn=str(row.get("parcel_number", "")),
        situs_address=str(row.get("address", "")) or "See Assessor",
        legal_description=str(row.get("legal_description", "")) if "legal_description" in row else None
    )
    
    # 2. Assessor Snapshot
    bal_str = str(row.get("v_total_balance", "$0.00")).replace("$", "").replace(",", "").strip()
    try:
        tax_bal = float(bal_str) if bal_str else 0.0
    except:
        tax_bal = 0.0

    assessor = AssessorSnapshot(
        assessor_owner_name=str(row.get("owner_name", "")),
        assessor_mailing_address=None, # Update if mailing is present
        assessor_transfer_date=None,
        assessor_transfer_value=None,
        tax_page_snapshot_date=parse_date(row.get("verified_at")),
        acquisition_doc_number=str(row.get("v_document_number", "")) if pd.notna(row.get("v_document_number")) else None,
        default_date=parse_date(row.get("default_date")),
        years_delinquent=int(row.get("years_delinquent")) if pd.notna(row.get("years_delinquent")) else None,
        tax_lien_id=str(row.get("v_document_number", "")) if pd.notna(row.get("v_document_number")) else None
    )
    
    # 3. Owner Vesting
    vesting_raw = json.loads(row.get("owner_vesting", "{}"))
    status_str = vesting_raw.get("ownership_verification_status", "NO_RECORDER_HIT")
    
    try:
        v_status = OwnershipVerificationStatus(status_str)
    except:
        v_status = OwnershipVerificationStatus.NO_RECORDER_HIT

    vesting = OwnerVesting(
        primary_name=vesting_raw.get("primary_name"),
        verified_current_owner_name=vesting_raw.get("verified_current_owner_name"),
        entity_type=vesting_raw.get("entity_type"),
        acquisition_date=parse_date(vesting_raw.get("acquisition_date")),
        acquisition_doc=vesting_raw.get("acquisition_doc"),
        vesting_doc_type=vesting_raw.get("vesting_doc_type"),
        ownership_verification_status=v_status,
        ownership_drift_flag=vesting_raw.get("ownership_drift_flag", True),
        ownership_drift_reason=vesting_raw.get("ownership_drift_reason"),
        confidence=vesting_raw.get("confidence", 1.0)
    )

    # 4. Encumbrance Summary
    chain_str = row.get("chain_of_title") or row.get("recorder_chain")
    enc_raw = summarize_encumbrances(chain_str)
    encumbrance = EncumbranceSummary(
        total_open_mortgages=enc_raw.get("total_open_mortgages", 0),
        last_mortgage_date=parse_date(enc_raw.get("last_mortgage_date")),
        active_liens=enc_raw.get("active_liens", []),
        notice_of_default=enc_raw.get("notice_of_default", False),
        notice_of_rescission=enc_raw.get("notice_of_rescission", False),
        equity_signal=enc_raw.get("equity_signal", "UNKNOWN"),
        distress_signal=enc_raw.get("distress_signal", "NONE"),
        confidence=enc_raw.get("confidence", 1.0)
    )
    
    # 5. Pipeline Routing (Merge Stage 2 and Stage 3 results)
    s3_status = row.get("final_ownership_status", "PENDING_STAGE3")
    from crm_schema.enums import ManualReviewPriority
    routing = PipelineRouting(
        stage2_result=v_status,
        stage3_status=s3_status,
        manual_review_required=row.get("manual_review_required", False),
        manual_review_priority=ManualReviewPriority.HIGH if row.get("manual_review_required", False) else None,
        manual_review_reason_codes=[str(row.get("adjudication_reasons", ""))] if pd.notna(row.get("adjudication_reasons")) else []
    )

    # 6. Seller Readiness
    is_eligible = (
        s3_status == "MATCHES_ASSESSOR" or 
        s3_status == "VESTING_CHANGED_SAME_CONTROL"
    )
    
    readiness = SellerReadiness(
        seller_contact_eligible=is_eligible,
        seller_opportunity_status="QUALIFIED" if is_eligible else "UNQUALIFIED"
    )

    # 7. Rest of Profile
    now = datetime.utcnow()
    return DistressedPropertyProfile(
        profile_id=f"{county.lower()}_{identity.apn}",
        created_at=now,
        updated_at=now,
        identity=identity,
        assessor_snapshot=assessor,
        owner_vesting=vesting,
        encumbrance_summary=encumbrance,
        pipeline_routing=routing,
        seller_readiness=readiness,
        sales_pipeline=SalesPipeline(),
        provenance=Provenance(source_county=county.capitalize()),
        audit=Audit()
    )

def run_export(input_csv: str, county: str):
    print(f"Loading Master Adjudicated Dataset: {input_csv}")
    df = pd.read_csv(input_csv)
    
    success_rows = []
    failure_rows = []
    review_queue = []
    
    for i, row in df.iterrows():
        try:
            profile = extract_profile_from_row(row, county)
            flat = flatten_profile(profile)
            flat["v_delinquent"] = row.get("v_delinquent")
            flat["v_total_balance"] = row.get("v_total_balance")
            success_rows.append(flat)
            
            # Extract to manual review queue if flagged
            if profile.pipeline_routing.manual_review_required:
                rq_item = ReviewQueueItem(
                    queue_item_id=f"mrq_{profile.profile_id}_{i}",
                    profile_id=profile.profile_id,
                    priority=profile.pipeline_routing.manual_review_priority or "HIGH",
                    reason_codes=profile.pipeline_routing.manual_review_reason_codes,
                    recommended_action="Review title chain and adjudicate new owner.",
                    evidence_refs=[]
                )
                review_queue.append(rq_item.model_dump())
                
        except ValidationError as e:
            # Catch Pydantic schema validation failures!
            err_dict = row.to_dict()
            err_dict["validation_error"] = str(e)
            failure_rows.append(err_dict)
            
    # Write Success Leads
    if success_rows:
        out_ready = input_csv.replace(".csv", "_CRM_READY.csv")
        pd.DataFrame(success_rows).to_csv(out_ready, index=False)
        print(f"Validated {len(success_rows)} profiles. Saved to {out_ready}")
        
    # Write Validation Failures
    if failure_rows:
        out_fail = input_csv.replace(".csv", "_VALIDATION_FAILURES.csv")
        pd.DataFrame(failure_rows).to_csv(out_fail, index=False)
        print(f"Failed Validation: {len(failure_rows)} profiles. Saved to {out_fail}")
        
    # Write Manual Review Queue
    if review_queue:
        out_review = input_csv.replace(".csv", "_MANUAL_REVIEW_QUEUE.csv")
        pd.DataFrame(review_queue).to_csv(out_review, index=False)
        print(f"Sent {len(review_queue)} properties to Manual Review. Saved to {out_review}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", nargs="?", default="shasta/shasta_15_percent_sample_ADJUDICATED.csv")
    parser.add_argument("--county", default="shasta")
    args = parser.parse_args()
    
    run_export(args.input_csv, args.county)
