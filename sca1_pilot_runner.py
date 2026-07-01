import json
import os
from vpr3 import ExecutionGraph, ExecutionStep, StepType
from dispatchers_shadow import ShadowDispatcher
from eer1_schemas import SessionContext
from sef_scorer import SEFScorer
from sca1_classifier import SCA1Classifier
from prs_scorer import PRSScorer
from golden_decay_tracker import GoldenDecayTracker

def run_sca1_pilot():
    print(f"--- PHASE 4A.1: SILENT CORRUPTION ATTRIBUTION (SCA-1) PILOT ---")
    
    golden_dataset = {
        "SHASTA_123_456": {"APN": "123-456", "OWNER": "SMITH JOHN", "SITUS": "100 MAIN ST", "ASSESSED_VALUE": "250000"},
        "TEHAMA_789_012": {"APN": "789-012", "OWNER": "DOE JANE", "SITUS": "200 OAK ST", "ASSESSED_VALUE": "150000"}
    }
    
    scorer = SEFScorer(golden_dataset)
    dispatcher = ShadowDispatcher()
    classifier = SCA1Classifier()
    prs = PRSScorer()
    tracker = GoldenDecayTracker()
    
    tracker.register_county("SHASTA", 1)
    tracker.register_county("TEHAMA", 1)
    
    ledger = []
    
    epochs = 120
    print(f"Simulating {epochs} adaptation events across Shasta and Tehama...\n")
    
    for epoch in range(1, epochs + 1):
        target_county = "SHASTA" if epoch % 2 != 0 else "TEHAMA"
        parcel_id = "SHASTA_123_456" if target_county == "SHASTA" else "TEHAMA_789_012"
        
        prod_step = ExecutionStep(f"prod_{epoch}", StepType.HTTP_REQUEST, "https://httpstat.us/403", {}, 3000, "NONE", ["json"])
        prod_graph = ExecutionGraph("target", "CUSTOM_CMS", "HTTP_ONLY", [prod_step], [], ["json"])
        
        shadow_step = ExecutionStep(f"shadow_{epoch}", StepType.HTTP_REQUEST, "https://example.com", {}, 3000, "NONE", ["json"])
        shadow_graph = ExecutionGraph("target", "CUSTOM_CMS", "HTTP_ONLY", [shadow_step], [], ["json"])
        
        # Compile dummy payload to satisfy EAF boundary
        from eaf1 import ExecutionAuthorityFirewall
        from cars3_schemas import InstrumentDivergenceFunction
        from cars2_state import VendorHealthProfile
        from cars2 import EvaluationVector
        from cgr1 import ConstraintGeometryResolver
        
        eval_vec_dummy = EvaluationVector("dummy", "target", "CUSTOM_CMS", 1.0, 1.0, 0.0, 1.0, 0.0)
        profile_dummy = VendorHealthProfile("CUSTOM_CMS", 1.0, 0.0, 1.0, 0.0)
        idf_dummy = InstrumentDivergenceFunction(0.0, 0.0, 0.0, "NONE->NONE", 0.0)
        acv = ConstraintGeometryResolver.resolve(eval_vec_dummy, profile_dummy, idf_dummy)
        
        prod_payload = ExecutionAuthorityFirewall.compile_payload(prod_graph, acv)
        shadow_payload_eaf = ExecutionAuthorityFirewall.compile_payload(shadow_graph, acv)
        
        prod_results, shadow_results = dispatcher.execute_shadow_graph(prod_payload, shadow_payload_eaf, SessionContext())
        
        # Determine failure simulation
        silent_corruption = False
        unscorable_event = False
        
        if epoch == 42:
            silent_corruption = True
            shadow_payload = golden_dataset[parcel_id].copy()
            shadow_payload["OWNER"] = "WRONG_PERSON_LLC"
            exp_sel = "td[4]"
            prop_sel = "td[5]"
            old_dom = "<table><tr><td>...</td><td>Owner</td><td>...</td><td>SMITH JOHN</td></tr></table>"
            new_dom = "<table><tr><td>...</td><td>Owner</td><td>...</td><td>...</td><td>WRONG_PERSON_LLC</td></tr></table>"
            field_failing = "OWNER"
        elif epoch == 87:
            silent_corruption = True
            shadow_payload = golden_dataset[parcel_id].copy()
            shadow_payload["APN"] = "John Smith"
            exp_sel = "div.apn"
            prop_sel = "div.owner"
            old_dom = None # Force Tier 2 Semantic Attribution
            new_dom = None
            field_failing = "APN"
        elif epoch == 105:
            silent_corruption = True
            shadow_payload = golden_dataset[parcel_id].copy()
            shadow_payload["OWNER"] = "DOE JANE" # Extracted neighbor!
            exp_sel = "div.parcel_owner"
            prop_sel = "div.parcel_owner"
            old_dom = "<div><div class='parcel_owner'>SMITH JOHN</div></div>"
            new_dom = "<div><div class='parcel_owner'>DOE JANE</div><span class='adjacent'>neighbor</span></div>"
            field_failing = "OWNER"
        elif epoch == 55:
            unscorable_event = True
            shadow_payload = {"RECORD_NOT_FOUND": True}
            tracker.retire_golden_parcel(target_county)
        else:
            shadow_payload = golden_dataset[parcel_id].copy()
            
        # Compute SEF
        sef_score = scorer.score_proposal(f"arc_prop_{epoch}", target_county, parcel_id, shadow_payload)
        
        prod_success = 1 if prod_results[0].status == "SUCCESS" else 0
        shadow_success = 1 if not unscorable_event else 0
        adaptation_lift = shadow_success - prod_success
        
        # Evaluate Proposal Risk (PRS)
        risk_score = prs.calculate_risk("td[4]", "td[5]", 1) if silent_corruption else 0.1
        
        entry = {
            "epoch": epoch,
            "proposal_id": sef_score.proposal_id,
            "county": target_county,
            "prs_score": risk_score,
            "silent_corruption": sef_score.silent_corruption,
            "adaptation_lift": adaptation_lift
        }
        
        # If silent corruption, perform SCA-1 Attribution
        if sef_score.silent_corruption:
            attribution = classifier.classify(
                field=field_failing,
                expected_val=golden_dataset[parcel_id][field_failing],
                extracted_val=shadow_payload[field_failing],
                expected_selector=exp_sel,
                proposed_selector=prop_sel,
                old_dom=old_dom,
                new_dom=new_dom,
                prs_score=risk_score,
                county=target_county
            )
            entry["attribution"] = attribution.to_dict()
            print(f"  [!] SCR Event -> {attribution.classification} ({attribution.evidence_type}, Conf: {attribution.confidence})")
            
        ledger.append(entry)
        
    # --- Compute Refined Phase 4A.1 Metrics ---
    total_attempts = 120
    unscorable = 1
    scorable_attempts = total_attempts - unscorable
    
    successful_adaptations = sum(1 for e in ledger if e["adaptation_lift"] > 0 and not e["silent_corruption"])
    silent_corruptions = sum(1 for e in ledger if e["silent_corruption"])
    
    lift_rate = successful_adaptations / scorable_attempts
    net_safe_lift = successful_adaptations - silent_corruptions
    
    print("\n--- PHASE 4A.1 METRICS ---")
    print(f"Total Scorable Attempts: {scorable_attempts}")
    print(f"Lift Rate: {lift_rate * 100:.2f}%")
    print(f"Net Safe Lift: +{net_safe_lift}")
    print(f"Silent Corruption Rate (SCR): {(silent_corruptions / scorable_attempts) * 100:.2f}%")
    
    print("\n--- SCA-1 ATTRIBUTION DISTRIBUTION ---")
    attributions = [e["attribution"] for e in ledger if e.get("attribution")]
    for a in attributions:
        print(f"  {a['classification']} | Evidence: {a['evidence_type']} | PRS: {a['prs_score']:.2f}")
        
    print("\n--- GOLDEN DECAY METRICS ---")
    decay = tracker.compute_decay_metrics()
    print(json.dumps(decay, indent=2))
    
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/sca1_ledger.jsonl", "w") as f:
        for entry in ledger:
            f.write(json.dumps(entry) + "\n")

if __name__ == "__main__":
    run_sca1_pilot()
