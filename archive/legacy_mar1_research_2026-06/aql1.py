import json
from typing import Dict, Any, Optional

class AcquisitionQualityLens:
    def __init__(self, vendor_registry_entry: Optional[Dict[str, Any]] = None):
        self.vendor_registry = vendor_registry_entry or {}
        
    def diagnose_failure(self, endpoint: str, status_code: int, headers: Dict[str, str], body_snippet: str = "", exception_str: str = "") -> Dict[str, Any]:
        """
        Passively diagnoses a failed acquisition attempt.
        """
        classification = "UNKNOWN_ERROR"
        waf_likelihood = 0.0
        auth_likelihood = 0.0
        session_likelihood = 0.0
        
        headers_lower = {k.lower(): v.lower() for k, v in headers.items()}
        server_header = headers_lower.get("server", "")
        
        # 1. Classification
        if status_code == 403:
            classification = "ACCESS_DENIED"
            waf_likelihood = 0.8
        elif status_code == 401:
            classification = "UNAUTHORIZED"
            auth_likelihood = 0.9
        elif status_code == 404:
            classification = "NOT_FOUND"
        elif status_code == 429:
            classification = "RATE_LIMITED"
            waf_likelihood = 0.6
        elif status_code == 503:
            classification = "SERVICE_UNAVAILABLE"
        elif "timeout" in exception_str.lower() or "11001" in exception_str:
            classification = "NETWORK_BLOCK_OR_TIMEOUT"
            waf_likelihood = 0.5
            
        # 2. Heuristics & Signals
        if "cloudflare" in server_header or "akamai" in server_header or "incapsula" in server_header:
            waf_likelihood = 0.95
            
        if "captcha" in body_snippet.lower() or "challenge" in body_snippet.lower():
            waf_likelihood = 0.99
            
        if "login" in body_snippet.lower() or "unauthorized" in body_snippet.lower():
            auth_likelihood = max(auth_likelihood, 0.8)
            
        if "session expired" in body_snippet.lower() or "cookie" in body_snippet.lower():
            session_likelihood = 0.85
            
        # Route Type Detection
        route_type = "unknown_route"
        if "search" in endpoint.lower() or "parcel" in endpoint.lower():
            route_type = "parcel_search_view"
        elif "tax" in endpoint.lower():
            route_type = "tax_bill_view"
            
        # Vendor Context
        vendor = self.vendor_registry.get("vendor", "UNKNOWN")
        
        # Diagnostic payload
        diagnostic = {
            "endpoint": endpoint,
            "status": status_code if status_code else exception_str,
            "classification": classification,
            "signals": {
                "vendor": vendor,
                "route_type": route_type,
                "auth_required_likelihood": auth_likelihood,
                "waf_likelihood": waf_likelihood,
                "session_dependency_likelihood": session_likelihood
            },
            "retry_policy": "NONE",
            "confidence": 0.90 if status_code else 0.70
        }
        
        return diagnostic
