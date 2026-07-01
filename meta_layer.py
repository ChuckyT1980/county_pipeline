from dataclasses import dataclass
from typing import Dict, Any, List

CANONICAL_SCHEMA = {
    "apn": str,
    "situs_address": str,
    "mailing_address": str,
    "owner": str,
    "assessed_value": float,
    "land_value": float,
    "improvement_value": float,
    "tax_due": float,
    "default_year": int,
    "roll_category": str,
}

TEHAMA_FIELD_MAP = {
    "Asmt": "apn",
    "Situs1": "situs_address",
    "OwnerName": "owner",
    "Name": "owner",
    "MailingAddress": "mailing_address",
    "CurrDue": "tax_due",
    "LandValue": "land_value",
    "ImpValue": "improvement_value",
    "TotalValue": "assessed_value",
    "RollCategory": "roll_category"
}

SHASTA_FIELD_MAP = {
    "Asmt": "apn",
    "Situs1": "situs_address",
    "OwnerName": "owner",
    "Name": "owner",
    "MailingAddress": "mailing_address",
    "CurrDue": "tax_due",
    "LandValue": "land_value",
    "ImpValue": "improvement_value",
    "TotalValue": "assessed_value",
    "RollCategory": "roll_category"
}

@dataclass
class DriftReport:
    county: str
    missing_fields: List[str]
    new_fields: List[str]

class MetaLayer0:
    def __init__(self):
        self.field_maps = {
            "tehama": TEHAMA_FIELD_MAP,
            "shasta": SHASTA_FIELD_MAP
        }
        self.field_confidence = {
            ("tehama", "situs_address"): 0.72,
            ("tehama", "assessed_value"): 0.58,
            ("tehama", "owner"): 0.91,
            ("tehama", "roll_category"): 0.8,
            ("tehama", "apn"): 0.99,
            ("shasta", "situs_address"): 0.72,
            ("shasta", "assessed_value"): 0.58,
            ("shasta", "owner"): 0.91,
            ("shasta", "roll_category"): 0.8,
            ("shasta", "apn"): 0.99,
        }

    def normalize(self, raw: Dict[str, Any], county: str) -> Dict[str, Any]:
        schema_map = self.field_maps.get(county, {})
        normalized = {}

        for raw_field, value in raw.items():
            if raw_field in schema_map:
                canonical_field = schema_map[raw_field]
                normalized[canonical_field] = value
                
        return normalized

    def detect_drift(self, raw: Dict[str, Any], county: str) -> DriftReport:
        schema_map = self.field_maps.get(county, {})
        
        expected_raw_fields = set(schema_map.keys())
        observed_raw_fields = set(raw.keys())
        
        missing_fields = list(expected_raw_fields - observed_raw_fields)
        new_fields = list(observed_raw_fields - expected_raw_fields)
        
        return DriftReport(
            county=county,
            missing_fields=missing_fields,
            new_fields=new_fields
        )

    def assign_confidence(self, normalized: Dict[str, Any], county: str, source: str) -> Dict[str, float]:
        conf_map = {}
        
        # Base confidence from source
        source_base = 0.5
        if "api" in source:
            source_base = 0.8
        elif "html" in source:
            source_base = 0.4
            
        for field in normalized.keys():
            # Blend specific county-field prior with source confidence
            prior = self.field_confidence.get((county, field), 0.6)
            conf_map[field] = min(1.0, (prior + source_base) / 2)
            
        return conf_map
