from dataclasses import dataclass
from typing import List, Dict, Optional
import re

@dataclass
class APNIntegrityTuple:
    normalized_apn: str
    svc: float  # Structural Validity Confidence
    scc: float  # Source Certainty Confidence
    origin_type: str # exact_match, formatted_match, padded_match, reconstructed
    inference_rule: Optional[str] = None
    
    def to_dict(self):
        d = {
            "apn": self.normalized_apn,
            "svc": self.svc,
            "scc": self.scc,
            "origin": self.origin_type
        }
        if self.inference_rule:
            d["inference_rule"] = self.inference_rule
        return d

class APNLossAuditor:
    def __init__(self):
        self.loss_log = []
        self.accepted_apns = []
        
    def audit_candidate(self, raw_string: str) -> Optional[APNIntegrityTuple]:
        clean = re.sub(r'\D', '', raw_string)
        
        # EXACT MATCH: "057-120-045-000"
        if re.match(r'^\d{3}-\d{3}-\d{3}-\d{3}$', raw_string.strip()):
            tup = APNIntegrityTuple(raw_string.strip(), svc=1.0, scc=1.0, origin_type="exact_match")
            self.accepted_apns.append(tup)
            return tup
            
        # FORMATTED MATCH: "057120045000" or "APN:057120045000"
        if len(clean) == 12:
            norm = f"{clean[:3]}-{clean[3:6]}-{clean[6:9]}-{clean[9:]}"
            tup = APNIntegrityTuple(
                norm, 
                svc=1.0, 
                scc=0.85, 
                origin_type="formatted_match", 
                inference_rule="dash_insertion"
            )
            self.accepted_apns.append(tup)
            return tup
            
        # PADDED MATCH: missing suffix "012-004-771"
        if len(clean) == 9:
            norm = f"{clean[:3]}-{clean[3:6]}-{clean[6:9]}-000"
            tup = APNIntegrityTuple(
                norm,
                svc=1.0,
                scc=0.40,
                origin_type="padded_match",
                inference_rule="pad_to_12_digit_standard"
            )
            self.accepted_apns.append(tup)
            return tup
            
        # RECONSTRUCTED MATCH: missing leading zero e.g. "57-120-045-000"
        if re.match(r'^\d{2}-\d{3}-\d{3}-\d{3}$', raw_string.strip()):
            norm = f"0{raw_string.strip()}"
            tup = APNIntegrityTuple(
                norm,
                svc=0.8,
                scc=0.30,
                origin_type="reconstructed",
                inference_rule="prepend_missing_zero"
            )
            self.accepted_apns.append(tup)
            return tup

        # REJECTION LOGGING
        reason = "unknown"
        if len(clean) < 9:
            reason = "insufficient_digits"
        elif len(clean) > 12:
            reason = "excess_digits"
        else:
            reason = "malformed_structure"
            
        self.loss_log.append({
            "candidate": raw_string.strip(),
            "rejected_reason": reason,
            "clean_length": len(clean)
        })
        return None
        
    def get_audit_report(self):
        return {
            "candidates_processed": len(self.accepted_apns) + len(self.loss_log),
            "apns_accepted": len(self.accepted_apns),
            "apns_lost": len(self.loss_log),
            "loss_log": self.loss_log,
            "accepted_log": [a.to_dict() for a in self.accepted_apns]
        }
