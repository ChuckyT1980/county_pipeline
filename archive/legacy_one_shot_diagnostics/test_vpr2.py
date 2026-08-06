import json
from vpr2 import VPR2Interpreter

def test_vpr2_routing():
    interpreter = VPR2Interpreter()
    
    # 1. MPTS WAF Block
    aql_mpts_waf = {
      "endpoint": "https://mptsweb.co.shasta.ca.us/search.asp",
      "status": 403,
      "classification": "ACCESS_DENIED",
      "signals": {
        "vendor": "MPTS",
        "route_type": "parcel_search_view",
        "auth_required_likelihood": 0.0,
        "waf_likelihood": 0.99,
        "session_dependency_likelihood": 0.0
      },
      "retry_policy": "NONE",
      "confidence": 0.9
    }
    
    # 2. Aumentum Session Required
    aql_aumentum_session = {
      "endpoint": "https://taxes.fakeaumentum.ca.us/Aumentum/search",
      "status": 200,
      "classification": "SUCCESS",
      "signals": {
        "vendor": "Aumentum",
        "route_type": "parcel_search_view",
        "auth_required_likelihood": 0.0,
        "waf_likelihood": 0.0,
        "session_dependency_likelihood": 0.95
      },
      "retry_policy": "NONE",
      "confidence": 0.9
    }

    print("--- VPR-2 DECISION: MPTS WAF ---")
    decision_mpts = interpreter.interpret("shasta", aql_mpts_waf)
    print(json.dumps(decision_mpts.to_dict(), indent=2))
    
    print("\n--- VPR-2 DECISION: AUMENTUM SESSION ---")
    decision_aumentum = interpreter.interpret("fake_aumentum", aql_aumentum_session)
    print(json.dumps(decision_aumentum.to_dict(), indent=2))

if __name__ == "__main__":
    test_vpr2_routing()
