import uuid
from typing import Dict, Any, List
from vpr3 import ExecutionStep, StepType
from eer1_schemas import ExecutionResult, SessionContext, RuntimeFailureType
from eaf1_schemas import AuthorizedExecutionPayload, ExecutionAuthorityViolation
from actuators_schemas import ActuatorRequest, ActuatorType, ActuatorResponse, ActuatorError, ErrorType
from ddl1_schemas import DeterministicExecutionTrace
from actuators_http import HTTPActuator
from actuators_browser import BrowserActuator

class LiveDispatcher:
    """
    Translates VPR-3 ExecutionSteps into ActuatorRequests and triggers the Live Actuators.
    """
    def __init__(self):
        self.http_actuator = HTTPActuator()
        self.browser_actuator = BrowserActuator()

    def execute_graph(self, payload: AuthorizedExecutionPayload, session: SessionContext) -> List[ExecutionResult]:
        # 1. HARD EAF-1 ENFORCEMENT
        expected_hash = AuthorizedExecutionPayload.compute_hash(payload.graph, payload.constraint_vector)
        if payload.integrity_hash != expected_hash:
            raise ExecutionAuthorityViolation("EER-1 ABORT: Payload Integrity Hash mismatch. Epistemic boundary compromised.")
            
        # 2. DETERMINISTIC EXECUTION
        results = []
        for step in payload.graph.steps:
            res = self._execute_step(step, session)
            results.append(res)
            # Dumb sequential abort on failure
            if res.status == "FAILURE":
                break
        return results

    def _execute_step(self, step: ExecutionStep, session: SessionContext) -> ExecutionResult:
        # Determine Actuator Type
        if step.type in [StepType.HTTP_REQUEST, StepType.EXTRACT_DOM]:
            actuator_type = ActuatorType.HTTP
            actuator = self.http_actuator
            method = "GET" if not step.params.get("payload") else "POST"
            selector = None
        elif step.type in [StepType.BROWSER_NAVIGATE, StepType.FOLLOW_LINK]:
            actuator_type = ActuatorType.PLAYWRIGHT
            actuator = self.browser_actuator
            method = "NAVIGATE" if step.type == StepType.BROWSER_NAVIGATE else "CLICK"
            selector = step.params.get("selector")
        else:
            # Internal steps don't hit actuators
            return ExecutionResult(step.id, "SUCCESS", {"message": "internal_step"}, 10, None, "hash")

        # Compile ActuatorRequest
        req = ActuatorRequest(
            execution_id=str(uuid.uuid4()),
            step_id=step.id,
            actuator_type=actuator_type,
            method=method,
            url=step.target,
            payload=step.params.get("payload"),
            headers=session.cookies, # Merge session context
            selector=selector,
            timeout_ms=step.timeout_ms,
            metadata=step.params.get("metadata", {})
        )

        # Execute Dumb Actuator
        res: ActuatorResponse = actuator.execute(req)
        
        # DDL-1: Generate Deterministic Trace
        import time
        import hashlib
        end_time = time.time()
        start_time = end_time - (res.timing_ms / 1000.0)
        body_hash = hashlib.sha256(res.raw_body.encode('utf-8')).hexdigest() if res.raw_body else "empty"
        
        trace = DeterministicExecutionTrace(
            step_id=step.id,
            actuator_type=req.actuator_type.value,
            req_method=req.method,
            req_url=req.url,
            req_headers=req.headers,
            req_payload=req.payload,
            req_timeout_ms=req.timeout_ms,
            time_start_unix=start_time,
            time_end_unix=end_time,
            duration_ms=res.timing_ms,
            res_status=res.status,
            res_error_type=res.error.type.value if res.error else None,
            res_body_hash=body_hash
        )

        # Map back to EER-1 ExecutionResult
        if res.success:
            return ExecutionResult(
                step_id=step.id,
                status="SUCCESS",
                response={"raw_body": res.raw_body, "status_code": res.status, "headers": res.headers},
                latency_ms=res.timing_ms,
                error_type=None,
                output_hash=f"hash_{len(res.raw_body)}",
                trace=trace
            )
        else:
            # Structure the failure
            err_map = {
                ErrorType.NETWORK_ERROR: RuntimeFailureType.NETWORK_ERROR,
                ErrorType.TIMEOUT: RuntimeFailureType.STEP_TIMEOUT,
                ErrorType.WAF_BLOCK: RuntimeFailureType.HTTP_ERROR,
                ErrorType.SELECTOR_NOT_FOUND: RuntimeFailureType.MISSING_EXPECTED_OUTPUT,
            }
            eer_err_type = err_map.get(res.error.type, RuntimeFailureType.UNKNOWN_RUNTIME_FAILURE) if res.error else RuntimeFailureType.UNKNOWN_RUNTIME_FAILURE
            
            return ExecutionResult(
                step_id=step.id,
                status="FAILURE",
                response={"raw_body": res.raw_body, "status_code": res.status},
                latency_ms=res.timing_ms,
                error_type=eer_err_type,
                output_hash=None,
                trace=trace
            )
