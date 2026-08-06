import json
import os
from dispatchers_live import LiveDispatcher
from cva1 import ConstraintViolationAuditor
from cars2 import StatelessEvaluator
from cars3_schemas import ActionConstraintVector, ExecutionMode
from ere1_probes import ProbeGenerator
from eer1_schemas import RuntimeTelemetry

def run_ere1_sweep():
    print("--- PHASE 3.5: ERE-1 OBSERVABILITY ENRICHMENT SWEEP ---")
    
    with open("data/registry/vpr_registry.json", "r") as f:
        registry = json.load(f)["counties"]
        
    dispatcher = LiveDispatcher()
    evaluator = StatelessEvaluator()
    
    # Global explicit Observation Mode constraint
    observability_acv = ActionConstraintVector(
        allowed_strategies=["HTTP_ONLY"],
        retry_budget=0,
        escalation_threshold=1.0,
        vendor_class_lock=None,
        execution_mode=ExecutionMode.OBSERVATION_ONLY,
        confidence_floor=0.9,
        entropy_cap=1.0,
        diagnostic_reason="PHASE_3.5_ERE1_SWEEP",
        allow_recompile=False,
        allow_strategy_switch=False,
        allow_retry=False,
        allow_actuator_fallback=False
    )

    topology_matrix = {}

    for county, data in registry.items():
        print(f"\n[Target] {county} ({data['vendor_class']})")
        target_url = data["target_url"]
        
        county_topology = {}
        
        # Generate the multi-dimensional probe matrix
        probes = ProbeGenerator.generate_matrix(county, data["vendor_class"], target_url)
        
        for probe in probes:
            print(f"  -> Executing {probe.type.value} probe...")
            step = probe.graph.steps[0]
            
            # Execute physical actuator
            result = dispatcher.execute(step, probe.session)
            
            # Telemetry Wrapper
            telemetry = RuntimeTelemetry(
                execution_graph_id=f"ere1_{county}_{probe.type.value}",
                step_results=[result],
                strategy_planned="HTTP_ONLY",
                strategy_observed="HTTP_ONLY",
                failure_step=step.id if result.status == "FAILURE" else None,
                total_latency_ms=result.latency_ms,
                apn_validations={},
                failure_context={"diagnostic": "Probe Completed", "error_type": result.error_type} if result.status == "FAILURE" else None
            )
            
            # CVA-1 Classification
            violation_report = ConstraintViolationAuditor.verify(telemetry, probe.graph, observability_acv, None)
            
            # CARS-2 Extraction
            eval_vector = evaluator.evaluate(telemetry, county, data["vendor_class"])
            
            classification = violation_report.violation_type.value
            if result.status == "FAILURE":
                classification = result.error_type.value if result.error_type else "UNKNOWN_FAILURE"
                
            signature = {
                "EFS": round(eval_vector.efs, 2),
                "VSI": round(eval_vector.vsi_contrib, 2),
                "FME": round(eval_vector.fme_contrib, 2),
                "CVA": classification,
                "Latency": result.latency_ms
            }
            county_topology[probe.type.value] = signature
            
            print(f"     => {classification} | FME: {signature['FME']} | VSI: {signature['VSI']}")
            
        topology_matrix[county] = {
            "vendor_class": data["vendor_class"],
            "entropy_signatures": county_topology
        }

    # Output to disk
    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/entropy_topology.json", "w") as f:
        json.dump(topology_matrix, f, indent=2)
        
    print("\n--- SWEEP COMPLETE ---")
    print("Multi-dimensional entropy topology written to data/telemetry/entropy_topology.json")

if __name__ == "__main__":
    run_ere1_sweep()
