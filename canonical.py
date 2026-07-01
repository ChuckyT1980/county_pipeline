from typing import Optional, Dict
from datetime import datetime
from dataclasses import dataclass, field
from fr1 import ReconciledField, reconcile_field

@dataclass
class Layer1Facts:
    """Pure extractions. No inferences. Sourced directly from county data."""
    apn: str
    county: str
    owner: ReconciledField = None
    mailing_address: ReconciledField = None
    situs_address: ReconciledField = None
    default_date: Optional[str] = None  # Using str for ISO date for simplicity in JSON serialization
    auction_date: Optional[str] = None
    amount_due: float = 0.0
    
    # Property Utility
    land_use: ReconciledField = None
    acreage: Optional[float] = None
    assessed_value: Optional[float] = None
    improvement_value: Optional[float] = None
    improved_vs_vacant: Optional[bool] = None
    access_quality: Optional[str] = None
    zoning_class: Optional[str] = None
    parcel_shape: Optional[str] = None

@dataclass
class Layer2Signals:
    """Explainable, binary rules applied directly to Layer 1 facts."""
    deceased_owner: bool = False
    trust_owner: bool = False
    entity_owner: bool = False
    out_of_state_owner: bool = False
    owner_occupied: bool = False
    multiple_owners: bool = False

@dataclass
class Layer3States:
    """Continuous variables representing the deeper conditions of the property."""
    ownership_complexity: float = 0.1
    ownership_stability: float = 0.9
    heir_probability: float = 0.0
    tax_pressure: float = 0.0  # [EXPERIMENTAL]
    property_utility_score: float = 0.0

@dataclass
class Layer4Opportunity:
    """The final pipeline output. Maps states to acquisition attractiveness and resolution difficulty."""
    attractiveness_score: float = 0.0
    resolution_difficulty: float = 0.0
    tier: int = 4
    record_explanation: str = "Unprocessed"

@dataclass
class Layer5Confidence:
    """Layered uncertainty metrics."""
    data_confidence: float = 1.0
    ownership_confidence: float = 1.0
    valuation_confidence: float = 1.0
    overall_confidence: float = 1.0

@dataclass
class IntelligenceRecord:
    """The National Property Intelligence Layer canonical record."""
    facts: Layer1Facts
    signals: Layer2Signals = field(default_factory=Layer2Signals)
    states: Layer3States = field(default_factory=Layer3States)
    opportunity: Layer4Opportunity = field(default_factory=Layer4Opportunity)
    confidence: Layer5Confidence = field(default_factory=Layer5Confidence)
    
    metadata: dict = field(default_factory=dict)

    def to_dict(self):
        return {
            "facts": {
                k: (v.to_dict() if isinstance(v, ReconciledField) else v)
                for k, v in self.facts.__dict__.items()
            },
            "signals": self.signals.__dict__,
            "states": self.states.__dict__,
            "opportunity": self.opportunity.__dict__,
            "confidence": self.confidence.__dict__,
            "metadata": self.metadata
        }

def build_layer1_facts(raw: dict, county: str, use_fr1: bool = True) -> Layer1Facts:
    """Initializes Layer 1 from raw ingested data."""
    def _parse_amount(value):
        if not value: return 0.0
        try: return float(value.replace("$", "").replace(",", ""))
        except: return 0.0

    def _normalize(text):
        return text.strip().upper() if text else None

    # Step 1: Adapter Layer for Multi-Source Dictionaries
    def _get_sources(field_name: str, raw_key: str, fallback_key: str = None) -> Dict[str, str]:
        sources_dict = raw.get(f"{field_name}_sources")
        if sources_dict and isinstance(sources_dict, dict):
            return sources_dict
        
        # Single-source fallback
        val = raw.get(raw_key)
        if not val and fallback_key:
            val = raw.get(fallback_key)
            
        if val:
            return {"primary": _normalize(val)}
        return {}

    if use_fr1:
        return Layer1Facts(
            apn=raw.get("apn", ""),
            county=county,
            owner=reconcile_field(_get_sources("owner", "owner_raw")),
            mailing_address=reconcile_field(_get_sources("mailing_address", "mailing_address", "address_raw")),
            situs_address=reconcile_field(_get_sources("situs_address", "situs_address", "situs_raw")),
            amount_due=_parse_amount(raw.get("amount_raw") or raw.get("amount_due")),
            land_use=reconcile_field(_get_sources("land_use", "land_use")),
            acreage=_parse_amount(str(raw.get("acreage")).replace("acres", "").strip()) if raw.get("acreage") else None,
            assessed_value=raw.get("assessed_value"),
            improvement_value=raw.get("improvement_value"),
            improved_vs_vacant=(True if str(raw.get("improved_vs_vacant")).lower() == "improved" else False if str(raw.get("improved_vs_vacant")).lower() == "vacant" else None),
            access_quality=raw.get("access_quality")
        )
    else:
        # FR-0 Baseline: naive flat string assumption
        def _get_naive(key):
            sources = raw.get(f"{key}_sources", {})
            return sources.get("assessor") or sources.get("tax") or sources.get("parcel") or raw.get(key)
            
        return Layer1Facts(
            apn=raw.get("apn", ""),
            county=county,
            owner=ReconciledField(value=_normalize(_get_naive("owner") or raw.get("owner_raw")), confidence=1.0, state="VERIFIED", sources=[], normalized_values=[]),
            mailing_address=ReconciledField(value=_normalize(_get_naive("mailing_address") or raw.get("mailing_address") or raw.get("address_raw")), confidence=1.0, state="VERIFIED", sources=[], normalized_values=[]),
            situs_address=ReconciledField(value=_normalize(_get_naive("situs_address") or raw.get("situs_address") or raw.get("situs_raw") or raw.get("address_raw")), confidence=1.0, state="VERIFIED", sources=[], normalized_values=[]),
            amount_due=_parse_amount(raw.get("amount_raw") or raw.get("amount_due")),
            land_use=ReconciledField(value=_normalize(_get_naive("land_use")), confidence=1.0, state="VERIFIED", sources=[], normalized_values=[]),
            acreage=_parse_amount(str(raw.get("acreage")).replace("acres", "").strip()) if raw.get("acreage") else None,
            assessed_value=raw.get("assessed_value"),
            improvement_value=raw.get("improvement_value"),
            improved_vs_vacant=(True if str(raw.get("improved_vs_vacant")).lower() == "improved" else False if str(raw.get("improved_vs_vacant")).lower() == "vacant" else None),
            access_quality=raw.get("access_quality")
        )

def init_intelligence_record(raw: dict, county: str, source_file: str = "", use_fr1: bool = True) -> IntelligenceRecord:
    """Creates a fresh IntelligenceRecord from raw data."""
    facts = build_layer1_facts(raw, county, use_fr1=use_fr1)
    return IntelligenceRecord(
        facts=facts,
        metadata={
            "line_id": raw.get("line_id"),
            "raw": raw.get("raw", ""),
            "source_file": source_file,
            "last_updated": datetime.utcnow().isoformat(),
        }
    )
