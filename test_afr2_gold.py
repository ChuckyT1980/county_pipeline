import json
from afr1 import classify_page

# Mock pages for Gold Failure Cases
cases = {
    # Failure Case 1: Shared Owner, Different Properties -> DO NOT CLUSTER
    "case1": [
        {"id": "c1_pA", "html": "<div>Owner: SMITH FAMILY TRUST</div><div>APN: 057-120-045-000</div>"},
        {"id": "c1_pB", "html": "<div>Owner: SMITH FAMILY TRUST</div><div>APN: 041-330-018-000</div>"}
    ],
    # Failure Case 2: Shared APN, Completely Different Layout -> CLUSTER
    "case2": [
        {"id": "c2_pA", "html": "<div>APN: 057-120-045-000</div><div>Owner: JOHN SMITH</div>"},
        {"id": "c2_pB", "html": "<table><tr><td>Parcel Number:</td><td>057120045000</td></tr><tr><td>Amount Due:</td><td>$8421.22</td></tr></table>"}
    ],
    # Failure Case 3: Neighbor Parcel Trap -> DO NOT CLUSTER
    "case3": [
        {"id": "c3_pA", "html": "<div>APN 057-120-045-000</div>"},
        {"id": "c3_pB", "html": "<div>APN 057-120-046-000</div>"}
    ],
    # Failure Case 4: Duplicate Address, Different Ownership -> ORPHAN / SEPARATE or LOW CONFIDENCE
    "case4": [
        {"id": "c4_pA", "html": "<div>456 RURAL RD</div><div>JOHN SMITH</div>"},
        {"id": "c4_pB", "html": "<div>456 RURAL RD</div><div>SMITH FAMILY TRUST</div>"}
    ],
    # Failure Case 5: Missing Identity Page -> ORPHAN
    "case5": [
        {"id": "c5_pA", "html": "<div>Taxes Due: $12,904.50</div>"}
    ],
    # Failure Case 6: County Template Collision -> DO NOT CLUSTER
    "case6": [
        {"id": "c6_pA", "html": "<div>Taxes Due:</div><div>$1,200</div>"},
        {"id": "c6_pB", "html": "<div>Taxes Due:</div><div>$8,421</div>"}
    ],
    # Failure Case 7: Conflicting APN Signatures -> FORCE SEPARATION
    "case7": [
        {"id": "c7_pA", "html": "<div>APN 057-120-045-000</div><div>Owner: LEE</div>"},
        {"id": "c7_pB", "html": "<div>APN 041-330-018-000</div><div>Owner: LEE</div>"}
    ]
}

def test_cases():
    for case_name, pages in cases.items():
        vectors = []
        for page in pages:
            res = classify_page(page["html"], page["id"])
            vectors.append(res)
            
        result = resolve_identities(vectors)
        print(f"--- {case_name} ---")
        print(json.dumps(result["entity_clusters"], indent=2))
        print(f"Orphans: {result['orphan_pages']}")
        print()

if __name__ == "__main__":
    from afr2 import resolve_identities
    test_cases()
