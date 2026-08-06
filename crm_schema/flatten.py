# crm_schema/flatten.py
from typing import Dict, Any
from crm_schema.models import DistressedPropertyProfile


def flatten_profile(profile: DistressedPropertyProfile) -> Dict[str, Any]:
    """
    Flatten a DistressedPropertyProfile into a single dict of scalar fields
    suitable for CSV/Parquet/Streamlit table rows.
    """
    return {
        # top-level
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "created_at": profile.created_at.isoformat(),
        "updated_at": profile.updated_at.isoformat(),

        # identity
        "county": profile.identity.county,
        "state": profile.identity.state,
        "apn": profile.identity.apn,
        "situs_address": profile.identity.situs_address,
        "legal_description": profile.identity.legal_description,

        # assessor snapshot
        "assessor_owner_name": profile.assessor_snapshot.assessor_owner_name,
        "assessor_mailing_address": profile.assessor_snapshot.assessor_mailing_address,
        "assessor_transfer_date": profile.assessor_snapshot.assessor_transfer_date.isoformat()
            if profile.assessor_snapshot.assessor_transfer_date else None,
        "assessor_transfer_value": profile.assessor_snapshot.assessor_transfer_value,
        "tax_page_snapshot_date": profile.assessor_snapshot.tax_page_snapshot_date.isoformat()
            if profile.assessor_snapshot.tax_page_snapshot_date else None,
        "acquisition_doc_number": profile.assessor_snapshot.acquisition_doc_number,

        # owner vesting
        "primary_name": profile.owner_vesting.primary_name,
        "verified_current_owner_name": profile.owner_vesting.verified_current_owner_name,
        "entity_type": profile.owner_vesting.entity_type,
        "acquisition_date": profile.owner_vesting.acquisition_date.isoformat()
            if profile.owner_vesting.acquisition_date else None,
        "vesting_doc_type": profile.owner_vesting.vesting_doc_type,
        "ownership_verification_status": profile.owner_vesting.ownership_verification_status.value,
        "ownership_drift_flag": profile.owner_vesting.ownership_drift_flag,
        "ownership_drift_reason": profile.owner_vesting.ownership_drift_reason,
        "owner_vesting_confidence": profile.owner_vesting.confidence,

        # encumbrance summary
        "total_open_mortgages": profile.encumbrance_summary.total_open_mortgages,
        "last_mortgage_date": profile.encumbrance_summary.last_mortgage_date.isoformat()
            if profile.encumbrance_summary.last_mortgage_date else None,
        "active_liens": ";".join(profile.encumbrance_summary.active_liens),
        "notice_of_default": profile.encumbrance_summary.notice_of_default,
        "notice_of_rescission": profile.encumbrance_summary.notice_of_rescission,
        "equity_signal": profile.encumbrance_summary.equity_signal.value,
        "distress_signal": profile.encumbrance_summary.distress_signal.value,
        "encumbrance_confidence": profile.encumbrance_summary.confidence,

        # pipeline routing
        "stage2_result": profile.pipeline_routing.stage2_result.value,
        "stage2_confidence": profile.pipeline_routing.stage2_confidence,
        "stage3_status": profile.pipeline_routing.stage3_status,
        "stage3_confidence": profile.pipeline_routing.stage3_confidence,
        "manual_review_required": profile.pipeline_routing.manual_review_required,
        "manual_review_priority": profile.pipeline_routing.manual_review_priority.value
            if profile.pipeline_routing.manual_review_priority else None,
        "manual_review_reason_codes": ";".join(profile.pipeline_routing.manual_review_reason_codes),
        "escalation_path": profile.pipeline_routing.escalation_path,

        # seller readiness
        "seller_contact_eligible": profile.seller_readiness.seller_contact_eligible,
        "seller_opportunity_status": profile.seller_readiness.seller_opportunity_status,
        "priority_score": profile.seller_readiness.priority_score,
        "buyer_fit_tags": ";".join(profile.seller_readiness.buyer_fit_tags),
        "disqualification_reason": profile.seller_readiness.disqualification_reason,

        # sales pipeline
        "crm_stage": profile.sales_pipeline.crm_stage.value,
        "assigned_to": profile.sales_pipeline.assigned_to,
        "first_touch_due_at": profile.sales_pipeline.first_touch_due_at.isoformat()
            if profile.sales_pipeline.first_touch_due_at else None,
        "last_contact_at": profile.sales_pipeline.last_contact_at.isoformat()
            if profile.sales_pipeline.last_contact_at else None,
        "contact_attempt_count": profile.sales_pipeline.contact_attempt_count,
        "seller_motivation_status": profile.sales_pipeline.seller_motivation_status,
        "timeline_to_sell": profile.sales_pipeline.timeline_to_sell,
        "offer_status": profile.sales_pipeline.offer_status,
        "contract_status": profile.sales_pipeline.contract_status,

        # provenance
        "source_county": profile.provenance.source_county,
        "allowed_sources": ";".join(profile.provenance.allowed_sources),
        "third_party_data_used": profile.provenance.third_party_data_used,
        "pipeline_version": profile.provenance.pipeline_version,
        "stage2_version": profile.provenance.stage2_version,
        "stage3_version": profile.provenance.stage3_version,

        # audit
        "created_by": profile.audit.created_by,
        "last_decision_actor": profile.audit.last_decision_actor,
        "last_decision_type": profile.audit.last_decision_type,
        "last_decision_at": profile.audit.last_decision_at.isoformat()
            if profile.audit.last_decision_at else None,
        "human_override": profile.audit.human_override,
        "override_reason": profile.audit.override_reason,
        "review_notes": ";".join(profile.audit.review_notes),
    }
