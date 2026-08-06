import json
from aql1 import AcquisitionQualityLens

def test_aql1_diagnostic():
    vendor_registry_entry = {
        "vendor": "MPTS",
        "portal_pattern": "mptsweb.co.shasta.ca.us",
        "tax_source": "https://mptsweb.co.shasta.ca.us/search.asp"
    }
    
    aql = AcquisitionQualityLens(vendor_registry_entry)
    
    # Simulate a 403 Forbidden with a Cloudflare Server header
    endpoint = "https://mptsweb.co.shasta.ca.us/search.asp?FeeParcel=057120045000"
    status_code = 403
    headers = {
        "Server": "cloudflare",
        "Content-Type": "text/html"
    }
    body_snippet = "<html><body>Please complete the security challenge.</body></html>"
    
    diagnostic = aql.diagnose_failure(endpoint, status_code, headers, body_snippet)
    
    print("--- AQL-1 Diagnostic Output ---")
    print(json.dumps(diagnostic, indent=2))

if __name__ == "__main__":
    test_aql1_diagnostic()
