import json
from ala1 import APNLossAuditor

def run_tests():
    auditor = APNLossAuditor()
    
    candidates = [
        "057-120-045-000",   # Exact match
        "057120045000",      # Formatted match
        "068-110-004-000",   # Exact match
        "068-110-04-000",    # Malformed (should be rejected)
        "041330018000",      # Formatted match
        "012-004-771",       # Padded match
        "123456",            # Noise (should be rejected)
        "57-120-045-000"     # Reconstructed match
    ]
    
    for c in candidates:
        auditor.audit_candidate(c)
        
    report = auditor.get_audit_report()
    
    print("--- ALA-1 Loss Audit Report ---")
    print(json.dumps(report, indent=2))
    
if __name__ == "__main__":
    run_tests()
