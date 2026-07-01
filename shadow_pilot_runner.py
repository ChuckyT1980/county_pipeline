import json
import os
import time
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from dispatchers_shadow import ShadowDispatcher
from eer1_schemas import SessionContext
from sef_scorer import SEFScorer
from eaf1 import ExecutionAuthorityFirewall
from cgr1 import ConstraintGeometryResolver
from cars2 import EvaluationVector
from cars2_state import VendorHealthProfile
from cars3_schemas import InstrumentDivergenceFunction

def run_phase4a_pilot():
    print(f"--- PHASE 4A: SHADOW ADAPTATION FLEET PILOT ---")
    
    # 1. Initialize Golden Dataset (Tier A Counties)
    golden_dataset = {
        "SHASTA_123_456": {
            "APN": "123-456",
            "OWNER": "SMITH JOHN",
            "SITUS": "100 MAIN ST",
            "ASSESSED_VALUE": "250000"
        },
        "TEHAMA_789_012": {
            "APN": "789-012",
            "OWNER": "DOE JANE",
            "SITUS": "200 OAK ST",
            "ASSESSED_VALUE": "150000"
        }
    }
    
    scorer = SEFScorer(golden_dataset)
    dispatcher = ShadowDispatcher()
    
    ledger = []
    
    # 2. Simulate 30-day Drift Event (100+ Adaptation Events)
    epochs = 120
    print(f"Simulating {epochs} adaptation events across Shasta and Tehama...\n")
    
    for epoch in range(1, epochs + 1):
        # Alternate between Shasta and Tehama
        target_county = "SHASTA" if epoch % 2 != 0 else "TEHAMA"
        parcel_id = "SHASTA_123_456" if target_county == "SHASTA" else "TEHAMA_789_012"
        
        # Simulate Production Failure (e.g. County DOM changed)
        # Production Graph tries to hit httpstat.us/403 (representing the failing selector)
        prod_step = ExecutionStep(f"prod_{epoch}", StepType.HTTP_REQUEST, "https://httpstat.us/403", {}, 3000, "NONE", ["json"])
        prod_graph = ExecutionGraph("target", "CUSTOM_CMS", "HTTP_ONLY", [prod_step], [], ["json"])
        
        # Simulate ARC-1 Proposed Adaptation Graph
        # We simulate ARC-1 finding the new selector and hitting a mock endpoint returning valid JSON
        # To simulate SCR (Silent Corruption), we will intentionally inject a wrong value in a small % of cases.
        silent_corruption = (epoch == 42 or epoch == 87) # 2 events out of 120 ~ 1.6% SCR
        unscorable_event = (epoch == 55) # 1 event
        
        if unscorable_event:
            # Emulate missing record
            shadow_payload = {"RECORD_NOT_FOUND": True}
        else:
            shadow_payload = golden_dataset[parcel_id].copy()
            if silent_corruption:
                # Corrupt the Owner field silently (Extraction succeeds, validates, but is wrong)
                shadow_payload["OWNER"] = "WRONG_PERSON_LLC"
                
        # We pass this payload to the shadow actuator by encoding it in the target_url query or we just 
        # intercept the response in the dispatcher. For this test runner, we will inject a dummy step 
        # and override the result to test the SEF scoring machinery.
        
        # Dummy step (Execution authority logic still applies)
        shadow_step = ExecutionStep(f"shadow_{epoch}", StepType.HTTP_REQUEST, "https://example.com", {}, 3000, "NONE", ["json"])
        shadow_graph = ExecutionGraph("target", "CUSTOM_CMS", "HTTP_ONLY", [shadow_step], [], ["json"])
        
        # EAF Compilation
        eval_vec_dummy = EvaluationVector("dummy", "target", "CUSTOM_CMS", 1.0, 1.0, 0.0, 1.0, 0.0)
        profile_dummy = VendorHealthProfile("CUSTOM_CMS", 1.0, 0.0, 1.0, 0.0)
        idf_dummy = InstrumentDivergenceFunction(0.0, 0.0, 0.0, "NONE->NONE", 0.0)
        acv = ConstraintGeometryResolver.resolve(eval_vec_dummy, profile_dummy, idf_dummy)
        
        prod_payload = ExecutionAuthorityFirewall.compile_payload(prod_graph, acv)
        shadow_payload_eaf = ExecutionAuthorityFirewall.compile_payload(shadow_graph, acv)
        
        # Dispatch
        prod_results, shadow_results = dispatcher.execute_shadow_graph(prod_payload, shadow_payload_eaf, SessionContext())
        
        # Override the shadow extraction with our mocked payload for SEF testing
        shadow_extraction = shadow_payload
        
        # Compute SEF
        sef_score = scorer.score_proposal(f"arc_prop_{epoch}", target_county, parcel_id, shadow_extraction)
        
        # Compute Adaptation Lift (AL)
        # AL = shadow_success_rate - production_success_rate
        # Here: Prod = 0 (FAIL), Shadow = 1 (PASS) -> Lift = +1
        prod_success = 1 if prod_results[0].status == "SUCCESS" else 0
        shadow_success = 1 if not unscorable_event else 0 # Shadow failed if unscorable
        adaptation_lift = shadow_success - prod_success
        
        # Record to ledger
        field_results = {fs.field_name: fs.status for fs in sef_score.field_scores}
        
        entry = {
            "epoch": epoch,
            "proposal_id": sef_score.proposal_id,
            "county": target_county,
            "field_fidelity": field_results,
            "silent_corruption": sef_score.silent_corruption,
            "adaptation_lift": adaptation_lift
        }
        ledger.append(entry)
        print(f"  -> {target_county} | AL: +{adaptation_lift} | Fields: {field_results}")
        
    # --- Compute Final Metrics ---
    total_scored = 0
    total_silent_corruption = 0
    field_totals = {"APN": [0,0], "OWNER": [0,0], "SITUS": [0,0], "ASSESSED_VALUE": [0,0]} # [passes, total]
    total_lift = 0
    
    for entry in ledger:
        # Ignore completely unscorable events
        if "ALL" in entry["field_fidelity"] and entry["field_fidelity"]["ALL"] == "UNSCORABLE":
            continue
            
        is_unscorable = False
        for field, status in entry["field_fidelity"].items():
            if status == "UNSCORABLE":
                is_unscorable = True
                break
                
        if is_unscorable:
            continue
            
        total_scored += 1
        if entry["silent_corruption"]:
            total_silent_corruption += 1
            
        total_lift += entry["adaptation_lift"]
        
        for field, status in entry["field_fidelity"].items():
            if field in field_totals:
                field_totals[field][1] += 1
                if status == "PASS":
                    field_totals[field][0] += 1
                    
    print("\n--- PHASE 4A METRICS ---")
    print(f"Total Scorable Adaptation Events: {total_scored}")
    print(f"Total Adaptation Lift: +{total_lift}")
    print(f"Silent Corruption Rate (SCR): {(total_silent_corruption / total_scored) * 100:.2f}%")
    print("\nField-Level Golden Fidelity:")
    for field, stats in field_totals.items():
        if stats[1] > 0:
            print(f"  {field}: {(stats[0] / stats[1]) * 100:.2f}%")
            
    # Write Shadow Ledger
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/shadow_ledger.jsonl", "w") as f:
        for entry in ledger:
            f.write(json.dumps(entry) + "\n")
            
    print("\n[!] Shadow Fleet 30-Day Pilot complete. Telemetry saved to shadow_ledger.jsonl.")

if __name__ == "__main__":
    run_phase4a_pilot()
