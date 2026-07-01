import json
from scda2 import align_candidates

tests = [
    {
        "name": "Case A: Estate Drift",
        "candidates": [
            "JOHN SMITH",
            "EST OF JOHN SMITH",
            "JOHN SMITH DECD"
        ],
        "expected": "LIKELY_MATCH"
    },
    {
        "name": "Case B: Trust Expansion",
        "candidates": [
            "SMITH TRUST",
            "SMITH FAMILY TRUST",
            "THE SMITH REVOCABLE TRUST"
        ],
        "expected": "PARTIAL_CONFLICT"
    },
    {
        "name": "Case C: Name Reversal",
        "candidates": [
            "SMITH JOHN",
            "JOHN SMITH"
        ],
        "expected": "LIKELY_MATCH"
    },
    {
        "name": "Case D: Direct Contradiction",
        "candidates": [
            "JOHN SMITH",
            "ROBERT WILLIAMS"
        ],
        "expected": "CONFLICTED"
    },
    {
        "name": "Case E: Sparse Evidence",
        "candidates": [
            "JOHN",
            "JOHN SMITH"
        ],
        "expected": "INSUFFICIENT_DATA"
    },
    {
        "name": "Case F: Related Entity",
        "candidates": [
            "JOHN SMITH",
            "SMITH FAMILY TRUST"
        ],
        "expected": "RELATED_ENTITY"
    }
]

def run_tests():
    passed = 0
    
    for t in tests:
        res = align_candidates(t["candidates"])
        status = "PASS" if res.state == t["expected"] else "FAIL"
        if status == "PASS": passed += 1
        
        print(f"--- {t['name']} ---")
        print(f"Expected: {t['expected']}")
        print(f"Actual:   {res.state} (Conf: {res.confidence})")
        print(f"Explain:  {res.explanation}")
        print(f"Status:   {status}\n")
        
    print(f"Passed {passed}/{len(tests)} cases.")
    
if __name__ == "__main__":
    run_tests()
