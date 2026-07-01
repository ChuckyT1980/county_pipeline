import time
from sda2 import StructuralDriftMapper
from sda2_schemas import CVA1AnomalyEvent

def test_sda2_geometric_drift():
    mapper = StructuralDriftMapper()
    
    schema_id = "AUMENTUM_STATEFUL"
    # baseline anchors: ["APN", "Situs Address", "Owner Information", "Tax Bill", "ViewState"]
    
    print("--- SDA-2 TEST: STRUCTURAL DRIFT MAPPING ---\n")
    
    # RUN 1: NO DRIFT
    print("Scenario 1: NO DRIFT (Minor network artifact)")
    e1 = CVA1AnomalyEvent(
        county_id="san_bernardino", vendor_class=schema_id, schema_id=schema_id,
        failure_type="SOFT_SCHEMA_DRIFT", raw_payload_snapshot={},
        dom_signature={"layout_drift": 0.05},
        token_signature={"tokens": ["APN", "Situs Address", "Owner Information", "Tax Bill", "ViewState"]},
        timestamp=time.time()
    )
    r1 = mapper.map_drift(e1)
    print(f"Result: {r1.drift_type.value} | Action: {r1.suggested_action.value} | Delta: {r1.stability_delta}")
    print(f"Explanation: {r1.explanation}\n")
    
    # RUN 2: MICRO DRIFT
    print("Scenario 2: MICRO DRIFT (Missing 'Tax Bill' token)")
    e2 = CVA1AnomalyEvent(
        county_id="san_bernardino", vendor_class=schema_id, schema_id=schema_id,
        failure_type="SOFT_SCHEMA_DRIFT", raw_payload_snapshot={},
        dom_signature={"layout_drift": 0.15},
        token_signature={"tokens": ["APN", "Situs Address", "Owner Information", "ViewState"]},
        timestamp=time.time()
    )
    r2 = mapper.map_drift(e2)
    print(f"Result: {r2.drift_type.value} | Action: {r2.suggested_action.value} | Delta: {r2.stability_delta}")
    print(f"Explanation: {r2.explanation}\n")

    # RUN 3: MACRO DRIFT
    print("Scenario 3: MACRO DRIFT (Missing Owner + Layout shift)")
    e3 = CVA1AnomalyEvent(
        county_id="san_bernardino", vendor_class=schema_id, schema_id=schema_id,
        failure_type="HARD_SCHEMA_BREAK", raw_payload_snapshot={},
        dom_signature={"layout_drift": 0.45},
        token_signature={"tokens": ["APN", "Tax Bill", "ViewState"]},
        timestamp=time.time()
    )
    r3 = mapper.map_drift(e3)
    print(f"Result: {r3.drift_type.value} | Action: {r3.suggested_action.value} | Delta: {r3.stability_delta}")
    print(f"Explanation: {r3.explanation}\n")
    
    # RUN 4: FULL SCHEMA REPLACEMENT
    print("Scenario 4: FULL SCHEMA REPLACEMENT (Complete DOM wipe, e.g. CAPTCHA page)")
    e4 = CVA1AnomalyEvent(
        county_id="san_bernardino", vendor_class=schema_id, schema_id=schema_id,
        failure_type="HARD_SCHEMA_BREAK", raw_payload_snapshot={},
        dom_signature={"layout_drift": 0.95},
        token_signature={"tokens": ["Cloudflare", "Verify", "Human"]},
        timestamp=time.time()
    )
    r4 = mapper.map_drift(e4)
    print(f"Result: {r4.drift_type.value} | Action: {r4.suggested_action.value} | Delta: {r4.stability_delta}")
    print(f"Explanation: {r4.explanation}\n")

if __name__ == "__main__":
    test_sda2_geometric_drift()
