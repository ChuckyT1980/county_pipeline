import json
import os
from source_provider import MockSourceProvider
from fingerprint import fingerprint_vendor

def discover_county(county: str, state: str, search_provider):
    query = f"{county} county {state} property tax"
    results = search_provider.search(query)
    
    fp = fingerprint_vendor(results)
    
    tax_source = ""
    assessor_source = ""
    for r in results:
        text = r.title.lower() + r.snippet.lower()
        if "tax" in text and not tax_source:
            tax_source = r.url
        elif "assessor" in text and not assessor_source:
            assessor_source = r.url
            
    if not tax_source and results:
        tax_source = results[0].url
        
    return {
        "vendor": fp.vendor,
        "vendor_confidence": fp.vendor_confidence,
        "portal_pattern": fp.portal_pattern,
        "fingerprint_features": fp.fingerprint_features,
        "tax_source": tax_source,
        "assessor_source": assessor_source,
        "data_quality_score": 0.85 if fp.vendor != "UNKNOWN" else 0.50
    }

def run_discovery():
    provider = MockSourceProvider()
    targets = [
        ("shasta", "ca"),
        ("tehama", "ca"),
        ("fake_aumentum", "ca"),
        ("fake_govos", "ca"),
        ("unknown", "ca")
    ]
    
    registry = {}
    
    for c, s in targets:
        key = f"{c}_{s}"
        print(f"Discovering {key}...")
        res = discover_county(c, s, provider)
        registry[key] = res
        
    os.makedirs("data/registry", exist_ok=True)
    out_path = "data/registry/tech_registry.json"
    with open(out_path, "w") as f:
        json.dump(registry, f, indent=2)
        
    print(f"\nSaved registry to {out_path}")

if __name__ == "__main__":
    run_discovery()
