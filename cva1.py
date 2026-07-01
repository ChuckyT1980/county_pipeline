from typing import List, Dict, Any
from cva1_schemas import ConstraintViolationReport, ViolationType, AffectedLayer
from eer1_schemas import RuntimeTelemetry, ExecutionResult
from vpr3 import ExecutionGraph
from cars3_schemas import ActionConstraintVector

class ConstraintViolationAuditor:
    """
    CVA-1: The Type System for Reality.
    Evaluates execution trace against expected schema bounds.
    Pure function.
    """
    
    @staticmethod
    def verify(telemetry: RuntimeTelemetry, graph: ExecutionGraph, acv: ActionConstraintVector, raw_responses: List[Dict[str, Any]] = None) -> ConstraintViolationReport:
        # 1. Verify EER-1 Boundaries (EXECUTION_UNBOUND)
        if len(telemetry.step_results) > len(graph.steps):
            return ConstraintViolationReport(
                violation_type=ViolationType.EXECUTION_UNBOUND,
                severity=1.0,
                affected_layer=AffectedLayer.EER,
                hard_halt=True,
                quarantine_execution=True,
                explanation="EER-1 executed more steps than compiled in VPR-3 graph."
            )
            
        # 2. Verify Schema Drift & Intermediate Observability (ERE-1)
        for i, result in enumerate(telemetry.step_results):
            if result.status == "SUCCESS":
                status_code = result.response.get("status_code", 200)
                raw_body = str(result.response.get("raw_body", ""))
                
                # Intermediate State: Redirect Chain
                if status_code in [301, 302, 307]:
                    return ConstraintViolationReport(
                        violation_type=ViolationType.REDIRECT_CHAIN_OBSERVED,
                        severity=0.3,
                        affected_layer=AffectedLayer.DISPATCH,
                        hard_halt=True,
                        quarantine_execution=True,
                        explanation=f"Endpoint returned {status_code} Redirect."
                    )
                
                # Intermediate State: Partial DOM Render
                if status_code == 200 and len(raw_body) < 500:
                    return ConstraintViolationReport(
                        violation_type=ViolationType.PARTIAL_DOM_RENDER,
                        severity=0.6,
                        affected_layer=AffectedLayer.DISPATCH,
                        hard_halt=True,
                        quarantine_execution=True,
                        explanation="Endpoint returned 200 OK but DOM is anomalously small (potential empty shell)."
                    )
                    
                # Intermediate State: Soft Block / CAPTCHA (simulated via raw_responses or basic text match)
                is_captcha = False
                if raw_responses and i < len(raw_responses) and raw_responses[i].get("mock_is_captcha"):
                    is_captcha = True
                if "captcha" in raw_body.lower() or "distil_ident" in raw_body.lower():
                    is_captcha = True
                    
                if is_captcha:
                    return ConstraintViolationReport(
                        violation_type=ViolationType.SOFT_BLOCK_CAPTCHA,
                        severity=0.8,
                        affected_layer=AffectedLayer.DISPATCH,
                        hard_halt=True,
                        quarantine_execution=True,
                        explanation="Endpoint returned 200 OK but DOM matches known CAPTCHA or Soft Block challenge."
                    )
                    
                # Intermediate State: Session Challenge
                if "session expired" in raw_body.lower() or "login" in raw_body.lower():
                    return ConstraintViolationReport(
                        violation_type=ViolationType.SESSION_CHALLENGE,
                        severity=0.5,
                        affected_layer=AffectedLayer.DISPATCH,
                        hard_halt=True,
                        quarantine_execution=True,
                        explanation="Endpoint returned 200 OK but requires Session or Auth."
                    )
                    
                # Legacy Hard Schema Break
                if raw_responses and i < len(raw_responses) and raw_responses[i].get("mock_is_redesign"):
                    return ConstraintViolationReport(
                        violation_type=ViolationType.HARD_SCHEMA_BREAK,
                        severity=1.0,
                        affected_layer=AffectedLayer.DISPATCH,
                        hard_halt=True,
                        quarantine_execution=True,
                        explanation="Endpoint returned 200 OK but expected data nodes are missing."
                    )

        # 3. Verify CARS-3 Constraints (UNDECLARED_RETRY_BEHAVIOR)
        # Assuming we track actual HTTP calls in telemetry
        if acv and acv.retry_budget == 0:
            # We would look at step_results to see if a single step ID appeared multiple times
            step_ids = [r.step_id for r in telemetry.step_results]
            if len(step_ids) != len(set(step_ids)):
                return ConstraintViolationReport(
                    violation_type=ViolationType.UNDECLARED_RETRY_BEHAVIOR,
                    severity=1.0,
                    affected_layer=AffectedLayer.EER,
                    hard_halt=True,
                    quarantine_execution=True,
                    explanation="EER-1 executed retries despite CARS-3 enforcing a retry_budget of 0."
                )

        return ConstraintViolationReport(
            violation_type=ViolationType.NONE,
            severity=0.0,
            affected_layer=None,
            hard_halt=False,
            quarantine_execution=False,
            explanation="Execution within schema boundaries."
        )
