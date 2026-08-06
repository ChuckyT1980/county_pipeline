import json
import os
from cars2 import EvaluationVector
from cars2_state import VendorHealthProfile
from cars3_schemas import InstrumentDivergenceFunction, ActionConstraintVector
from cgr1 import ConstraintGeometryResolver

def run_cgr1_evaluation():
    print("--- PHASE 3.8: CGR-1 CONSTRAINT CONTRACTION EVALUATION ---")
    
    with open("data/telemetry/divergence_field_topology.json", "r") as f:
        topology = json.load(f)["los_angeles"]
        
    contracted_geometries = {}

    for probe_type, data in topology.items():
        print(f"\n[Geometry Resolution] Regime: {probe_type}")
        
        http_vec = data["http_vector"]
        pw_vec = data["playwright_vector"]
        idf_raw = data["idf"]
        
        # We need a stable aggregate of VSI/FME to simulate the historical VendorHealthProfile
        # We will use the baseline HTTP state as the 'current' state representation.
        vsi = http_vec["VSI"]
        fme = http_vec["FME"]
        efs = http_vec["EFS"]
        
        profile = VendorHealthProfile("CUSTOM_CMS", vsi, fme, 1.0, 0.0)
        eval_vec = EvaluationVector("eval_cgr1", "los_angeles", "CUSTOM_CMS", efs, 1.0, fme, vsi, 0.0)
        
        idf = InstrumentDivergenceFunction(
            delta_efs=idf_raw["delta_vector"]["d_EFS"],
            delta_vsi=idf_raw["delta_vector"]["d_VSI"],
            delta_fme=idf_raw["delta_vector"]["d_FME"],
            transition_label=idf_raw["transition"],
            ivd=idf_raw["ivd"]
        )
        
        # Resolve Constraint Geometry
        acv: ActionConstraintVector = ConstraintGeometryResolver.resolve(eval_vec, profile, idf)
        
        print(f"  -> Input IVD: {idf.ivd} | Transition: {idf.transition_label}")
        print(f"  -> Output Diagnostic: {acv.diagnostic_reason}")
        print(f"  -> Instrument Authority Weights: {acv.instrument_authority_weights}")
        print(f"  -> Allowed Strategies: {acv.allowed_strategies}")
        print(f"  -> Execution Mode: {acv.execution_mode.value}")
        
        contracted_geometries[probe_type] = {
            "diagnostic": acv.diagnostic_reason,
            "instrument_authority": acv.instrument_authority_weights,
            "allowed_strategies": acv.allowed_strategies,
            "execution_mode": acv.execution_mode.value,
            "retry_budget": acv.retry_budget,
            "allow_recompile": acv.allow_recompile
        }

    os.makedirs("data/telemetry", exist_ok=True)
    with open("data/telemetry/cgr1_contracted_geometries.json", "w") as f:
        json.dump({"los_angeles": contracted_geometries}, f, indent=2)
        
    print("\n--- RESOLUTION COMPLETE ---")
    print("Contracted geometries written to data/telemetry/cgr1_contracted_geometries.json")

if __name__ == "__main__":
    run_cgr1_evaluation()
