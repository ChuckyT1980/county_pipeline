# crm_schema/models.py
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime

from crm_schema.enums import (
    OwnershipVerificationStatus,
    RecorderEventRole,
    EquitySignal,
    DistressSignal,
    ManualReviewPriority,
    CrmStage,
)


class Identity(BaseModel):
    county: str
    state: str = "CA"
    apn: str
    situs_address: str
    legal_description: Optional[str] = None


class AssessorSnapshot(BaseModel):
    assessor_owner_name: str
    assessor_mailing_address: Optional[str] = None
    assessor_transfer_date: Optional[datetime] = None
    assessor_transfer_value: Optional[float] = None
    tax_page_snapshot_date: Optional[datetime] = None
    acquisition_doc_number: Optional[str] = None
    default_date: Optional[datetime] = None
    years_delinquent: Optional[int] = None
    tax_lien_id: Optional[str] = None


class OwnerVesting(BaseModel):
    primary_name: Optional[str] = None
    verified_current_owner_name: Optional[str] = None
    entity_type: Optional[str] = None  # INDIVIDUAL/TRUST/LLC/etc.
    acquisition_date: Optional[datetime] = None
    acquisition_doc: Optional[str] = None
    vesting_doc_type: Optional[str] = None
    ownership_verification_status: OwnershipVerificationStatus = OwnershipVerificationStatus.NO_RECORDER_HIT
    ownership_drift_flag: bool = False
    ownership_drift_reason: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None  # "recorder", "assessor", etc.
    evidence_refs: List[str] = Field(default_factory=list)


class EncumbranceSummary(BaseModel):
    total_open_mortgages: int = 0
    last_mortgage_date: Optional[datetime] = None
    active_liens: List[str] = Field(default_factory=list)
    notice_of_default: bool = False
    notice_of_rescission: bool = False
    equity_signal: EquitySignal = EquitySignal.UNKNOWN
    distress_signal: DistressSignal = DistressSignal.NONE
    confidence: Optional[float] = None
    source: Optional[str] = None
    evidence_refs: List[str] = Field(default_factory=list)


class RecorderEvent(BaseModel):
    event_id: str
    doc_type: str
    role: RecorderEventRole
    recorded_date: Optional[datetime] = None
    doc_number: Optional[str] = None
    grantor: Optional[str] = None
    grantee: Optional[str] = None
    lender: Optional[str] = None
    borrower: Optional[str] = None
    confidence: Optional[float] = None
    source: Optional[str] = None


class PipelineRouting(BaseModel):
    stage2_result: OwnershipVerificationStatus
    stage2_confidence: Optional[float] = None
    stage3_status: Optional[str] = None  # "DETERMINISTIC_BYPASS", "LLM_ADJUDICATED", etc.
    stage3_confidence: Optional[float] = None
    manual_review_required: bool = False
    manual_review_priority: Optional[ManualReviewPriority] = None
    manual_review_reason_codes: List[str] = Field(default_factory=list)
    escalation_path: Optional[str] = None  # "stage2_only", "stage2+stage3", "stage2+stage3+human"


class SellerReadiness(BaseModel):
    seller_contact_eligible: bool = False
    seller_opportunity_status: Optional[str] = None  # e.g. "QUALIFIED_FOR_OUTREACH"
    priority_score: Optional[int] = None
    buyer_fit_tags: List[str] = Field(default_factory=list)
    disqualification_reason: Optional[str] = None


class SalesPipeline(BaseModel):
    crm_stage: CrmStage = CrmStage.NEW_INTEL
    assigned_to: Optional[str] = None
    first_touch_due_at: Optional[datetime] = None
    last_contact_at: Optional[datetime] = None
    contact_attempt_count: int = 0
    seller_motivation_status: Optional[str] = None
    timeline_to_sell: Optional[str] = None
    offer_status: Optional[str] = None
    contract_status: Optional[str] = None


class Provenance(BaseModel):
    source_county: str
    allowed_sources: List[str] = Field(default_factory=lambda: ["assessor", "recorder", "user_enriched"])
    third_party_data_used: bool = False
    pipeline_version: Optional[str] = None
    stage2_version: Optional[str] = None
    stage3_version: Optional[str] = None
    event_hash: Optional[str] = None


class Audit(BaseModel):
    created_by: str = "pipeline"
    last_decision_actor: Optional[str] = None  # "stage2", "stage3", "human"
    last_decision_type: Optional[str] = None  # "deterministic_classification", "llm_adjudication", "manual_override"
    last_decision_at: Optional[datetime] = None
    human_override: bool = False
    override_reason: Optional[str] = None
    review_notes: List[str] = Field(default_factory=list)


class DistressedPropertyProfile(BaseModel):
    schema_version: str = "1.0.0"
    profile_id: str
    created_at: datetime
    updated_at: datetime

    identity: Identity
    assessor_snapshot: AssessorSnapshot
    owner_vesting: OwnerVesting
    encumbrance_summary: EncumbranceSummary
    recorder_chain: List[RecorderEvent] = Field(default_factory=list)
    pipeline_routing: PipelineRouting
    seller_readiness: SellerReadiness
    sales_pipeline: SalesPipeline
    provenance: Provenance
    audit: Audit

class ReviewQueueItem(BaseModel):
    queue_item_id: str
    profile_id: str
    review_type: str = "ownership_adjudication"
    priority: ManualReviewPriority = ManualReviewPriority.HIGH
    reason_codes: List[str]
    current_status: str = "PENDING_REVIEW"
    recommended_action: str
    evidence_refs: List[str]
    assigned_reviewer: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    resolved_at: Optional[str] = None
    resolution: Optional[str] = None
