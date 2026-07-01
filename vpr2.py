from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Any, Optional
from cars3_schemas import ActionConstraintVector

# 2. Failure Mode Ontology (Canonical Enum)
class FailureMode(str, Enum):
    WAF_BLOCK = "WAF_BLOCK"
    JS_CHALLENGE = "JS_CHALLENGE"
    SESSION_REQUIRED = "SESSION_REQUIRED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PARTIAL_RENDER = "PARTIAL_RENDER"
    HTML_SCRAPE_ONLY = "HTML_SCRAPE_ONLY"
    BAD_ENDPOINT = "BAD_ENDPOINT"
    STRUCTURAL_REDIRECT = "STRUCTURAL_REDIRECT"
    UNKNOWN = "UNKNOWN"

# 3. Vendor Behavior Classes
class VendorClass(str, Enum):
    MPTS_HYBRID = "MPTS_HYBRID"
    AUMENTUM_STATEFUL = "AUMENTUM_STATEFUL"
    ASPNET_LEGACY = "ASPNET_LEGACY"
    STATIC_HTML = "STATIC_HTML"
    CUSTOM_CMS = "CUSTOM_CMS"
    UNKNOWN_VENDOR = "UNKNOWN_VENDOR"

# 4. Acquisition Strategy Enum
class AcquisitionStrategy(str, Enum):
    HTTP_ONLY = "HTTP_ONLY"
    STATEFUL_BROWSER = "STATEFUL_BROWSER"
    HEADLESS_RENDER = "HEADLESS_RENDER"
    COOKIE_BOOTSTRAP = "COOKIE_BOOTSTRAP"
    HYBRID_RENDER_PIPE = "HYBRID_RENDER_PIPE"
    NO_AUTOMATION_FEASIBLE = "NO_AUTOMATION_FEASIBLE"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"

# 5. VPR-2 Output Schema
@dataclass
class VPR2Decision:
    county: str
    vendor_class: VendorClass
    failure_mode: FailureMode
    acquisition_strategy: AcquisitionStrategy
    confidence: float
    evidence: Dict[str, Any]
    risk_flags: List[str]
    
    def to_dict(self):
        return {
            "county": self.county,
            "vendor_class": self.vendor_class.value,
            "failure_mode": self.failure_mode.value,
            "acquisition_strategy": self.acquisition_strategy.value,
            "confidence": self.confidence,
            "risk_flags": self.risk_flags,
            "evidence": self.evidence
        }

# 6. Strategy Mapping Rules
mpts_rules = {
    FailureMode.WAF_BLOCK: AcquisitionStrategy.COOKIE_BOOTSTRAP,
    FailureMode.JS_CHALLENGE: AcquisitionStrategy.HEADLESS_RENDER,
    FailureMode.RATE_LIMITED: AcquisitionStrategy.HTTP_ONLY,
    FailureMode.PARTIAL_RENDER: AcquisitionStrategy.HYBRID_RENDER_PIPE,
    FailureMode.UNKNOWN: AcquisitionStrategy.HTTP_ONLY
}

aumentum_rules = {
    FailureMode.SESSION_REQUIRED: AcquisitionStrategy.STATEFUL_BROWSER,
    FailureMode.AUTH_REQUIRED: AcquisitionStrategy.NO_AUTOMATION_FEASIBLE,
    FailureMode.STRUCTURAL_REDIRECT: AcquisitionStrategy.HYBRID_RENDER_PIPE,
    FailureMode.UNKNOWN: AcquisitionStrategy.HTTP_ONLY
}

aspnet_rules = {
    FailureMode.SESSION_REQUIRED: AcquisitionStrategy.COOKIE_BOOTSTRAP,
    FailureMode.PARTIAL_RENDER: AcquisitionStrategy.HYBRID_RENDER_PIPE,
    FailureMode.BAD_ENDPOINT: AcquisitionStrategy.HTTP_ONLY,
    FailureMode.UNKNOWN: AcquisitionStrategy.HTTP_ONLY
}

# 7. Decision Function
def decide_strategy(vendor: VendorClass, failure_mode: FailureMode, signals: dict) -> AcquisitionStrategy:
    if vendor == VendorClass.MPTS_HYBRID:
        return mpts_rules.get(failure_mode, AcquisitionStrategy.HTTP_ONLY)

    if vendor == VendorClass.AUMENTUM_STATEFUL:
        return aumentum_rules.get(failure_mode, AcquisitionStrategy.HTTP_ONLY)

    if vendor == VendorClass.ASPNET_LEGACY:
        return aspnet_rules.get(failure_mode, AcquisitionStrategy.HTTP_ONLY)

    if failure_mode == FailureMode.WAF_BLOCK:
        return AcquisitionStrategy.COOKIE_BOOTSTRAP

    return AcquisitionStrategy.HTTP_ONLY

# VPR-2 Core Interpreter
class VPR2Interpreter:
    def __init__(self):
        self.risk_flag_ontology = {
            "HIGH_WAF_CONFIDENCE",
            "SESSION_UNSTABLE",
            "UNKNOWN_VENDOR_BEHAVIOR",
            "NON_DETERMINISTIC_RENDER",
            "DATA_INACCESSIBLE"
        }
        
    def _map_vendor(self, sda_vendor: str) -> VendorClass:
        sda_vendor = sda_vendor.upper()
        if "MPTS" in sda_vendor: return VendorClass.MPTS_HYBRID
        if "AUMENTUM" in sda_vendor: return VendorClass.AUMENTUM_STATEFUL
        if "GOVOS" in sda_vendor: return VendorClass.CUSTOM_CMS
        return VendorClass.UNKNOWN_VENDOR
        
    def _map_failure_mode(self, aql_diagnostic: dict) -> FailureMode:
        signals = aql_diagnostic.get("signals", {})
        classification = aql_diagnostic.get("classification", "")
        
        waf_score = signals.get("waf_likelihood", 0.0)
        auth_score = signals.get("auth_required_likelihood", 0.0)
        session_score = signals.get("session_dependency_likelihood", 0.0)
        
        if waf_score > 0.8:
            return FailureMode.WAF_BLOCK
        if session_score > 0.8:
            return FailureMode.SESSION_REQUIRED
        if auth_score > 0.8:
            return FailureMode.AUTH_REQUIRED
        if classification == "RATE_LIMITED":
            return FailureMode.RATE_LIMITED
        if classification == "NOT_FOUND":
            return FailureMode.BAD_ENDPOINT
            
        return FailureMode.UNKNOWN
        
    def interpret(self, county: str, aql_diagnostic: dict, acv: Optional[ActionConstraintVector] = None) -> VPR2Decision:
        vendor_raw = aql_diagnostic.get("signals", {}).get("vendor", "UNKNOWN")
        vendor_class = self._map_vendor(vendor_raw)
        
        failure_mode = self._map_failure_mode(aql_diagnostic)
        
        strategy = decide_strategy(vendor_class, failure_mode, aql_diagnostic.get("signals", {}))
        
        if acv and acv.allowed_strategies and strategy.value not in acv.allowed_strategies:
            if AcquisitionStrategy.HTTP_ONLY.value in acv.allowed_strategies:
                strategy = AcquisitionStrategy.HTTP_ONLY
            else:
                strategy = AcquisitionStrategy.OBSERVATION_ONLY
        
        risk_flags = []
        if failure_mode == FailureMode.WAF_BLOCK:
            risk_flags.append("HIGH_WAF_CONFIDENCE")
        if vendor_class == VendorClass.UNKNOWN_VENDOR:
            risk_flags.append("UNKNOWN_VENDOR_BEHAVIOR")
        if strategy == AcquisitionStrategy.NO_AUTOMATION_FEASIBLE:
            risk_flags.append("DATA_INACCESSIBLE")
            
        confidence = aql_diagnostic.get("confidence", 0.5)
        
        return VPR2Decision(
            county=county,
            vendor_class=vendor_class,
            failure_mode=failure_mode,
            acquisition_strategy=strategy,
            confidence=confidence,
            evidence=aql_diagnostic,
            risk_flags=risk_flags
        )
