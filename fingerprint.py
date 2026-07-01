import re
from dataclasses import dataclass
from typing import List, Optional
from source_provider import SourceResult

@dataclass
class VendorFingerprint:
    vendor: str
    vendor_confidence: float
    portal_pattern: str
    fingerprint_features: List[str]

def extract_domain(url: str) -> str:
    match = re.search(r'https?://([^/]+)', url)
    return match.group(1) if match else ""

def fingerprint_vendor(results: List[SourceResult]) -> VendorFingerprint:
    """
    Takes a list of search results for a county and determines the vendor stack.
    """
    if not results:
        return VendorFingerprint("UNKNOWN", 0.0, "", [])
        
    features_found = set()
    vendor_scores = {
        "MPTS": 0,
        "Aumentum": 0,
        "GovOS": 0,
        "TylerTech": 0
    }
    
    primary_domain = ""
    
    for r in results:
        text = (r.url + " " + r.title + " " + r.snippet).lower()
        domain = extract_domain(r.url)
        
        # MPTS
        if "mptsweb" in text or "megabyte" in text:
            vendor_scores["MPTS"] += 2
            features_found.add("mptsweb")
            if not primary_domain and "mptsweb" in r.url:
                primary_domain = domain
                
        # Aumentum
        if "aumentum" in text:
            vendor_scores["Aumentum"] += 2
            features_found.add("Aumentum")
            if not primary_domain and "aumentum" in r.url:
                primary_domain = domain
                
        # GovOS
        if "govos" in text or "kofile" in text:
            vendor_scores["GovOS"] += 2
            features_found.add("GovOS")
            if not primary_domain and "govos" in r.url:
                primary_domain = domain
                
    best_vendor = max(vendor_scores, key=vendor_scores.get)
    best_score = vendor_scores[best_vendor]
    
    if best_score == 0:
        return VendorFingerprint("UNKNOWN", 0.0, "", [])
        
    # Probabilistic confidence based on hits
    conf = min(0.95, 0.5 + (best_score * 0.1))
    
    if not primary_domain and results:
        primary_domain = extract_domain(results[0].url)
        
    return VendorFingerprint(
        vendor=best_vendor,
        vendor_confidence=round(conf, 2),
        portal_pattern=primary_domain,
        fingerprint_features=list(features_found)
    )
