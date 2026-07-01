from typing import List, Dict, Any
from eer1_schemas import ExecutionResult
from vpr3 import ExecutionGraph

class IFPPropagationAssertion:
    """
    Mathematical ledger for verifying the Intra-Graph Failure Propagation Test (IFP-1).
    Proves that mid-graph failure isolates perfectly without contaminating epistemic history.
    """
    def __init__(self):
        self.runs = []
        
    def record_run(self, graph: ExecutionGraph, results: List[ExecutionResult], eaf1_hash: str, cva1_classes: List[str]):
        self.runs.append({
            "expected_steps": len(graph.steps),
            "executed_steps": len(results),
            "results": results,
            "eaf1_hash": eaf1_hash,
            "cva1_classes": cva1_classes
        })
        
    def compute_report(self) -> Dict[str, Any]:
        report = {}
        
        for idx, run in enumerate(self.runs):
            n = run["expected_steps"]
            k = run["executed_steps"]
            
            # Find the boundary index where failure occurred
            failed_index = -1
            for i, res in enumerate(run["results"]):
                if res.status == "FAILURE":
                    failed_index = i
                    break
                    
            if failed_index == -1:
                # Graph fully succeeded
                report[f"run_{idx}"] = {"status": "INVALID_TEST_NO_FAILURE_INJECTED"}
                continue
                
            # 1. Boundary Verification
            # The execution should have halted EXACTLY at the failed index + 1
            boundary_integrity = (k == failed_index + 1)
            
            # 2. Pre-failure Separation
            # All steps before the failed index must be purely SUCCESS
            pre_failure_clean = all(res.status == "SUCCESS" for res in run["results"][:failed_index])
            
            # 3. Contamination Check
            # Ensure CVA-1 correctly maps SUCCESS to the pre-failure steps, and FAILURE to the boundary step
            cva_clean = all(run["cva1_classes"][i] == "STABLE_HTTP" for i in range(failed_index))
            cva_failed = run["cva1_classes"][failed_index] != "STABLE_HTTP"
            
            # 4. Unexecuted Region Validation
            unexecuted = n - k
            
            report[f"run_{idx}"] = {
                "graph_size_n": n,
                "failure_boundary_index_k": failed_index + 1, # 1-based index
                "unexecuted_steps": unexecuted,
                "boundary_abort_integrity": "PASS" if boundary_integrity else "FAIL_LEAKAGE",
                "pre_failure_isolation": "PASS" if pre_failure_clean else "FAIL_RETROACTIVE_CORRUPTION",
                "cva1_observational_integrity": "PASS" if (cva_clean and cva_failed) else "FAIL_OBSERVATION_POISONING",
                "status": "PASS" if (boundary_integrity and pre_failure_clean and cva_clean and cva_failed) else "FAIL"
            }
            
        report["ifp1_propagation_status"] = "VERIFIED_COMPOSITIONAL_ISOLATION" if all(v.get("status") == "PASS" for v in report.values()) else "FAILED_CONTAMINATION_DETECTED"
        
        return report
