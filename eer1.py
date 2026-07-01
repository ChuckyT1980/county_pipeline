import json
import time
from typing import Dict, Any
from eer1_schemas import (
    ExecutionResult, SessionContext, RuntimeFailureType, StepFailure, 
    ExecutionFailureState, RuntimeTelemetry
)
from vpr3 import ExecutionGraph, StepType
from dispatchers import HTTPDispatcher, BrowserDispatcher
from cars3_schemas import ActionConstraintVector, ExecutionMode

class ExecutionRuntime:
    def __init__(self):
        self.http_dispatch = HTTPDispatcher()
        self.browser_dispatch = BrowserDispatcher()
        
    def execute_graph(self, graph: ExecutionGraph, acv: ActionConstraintVector = None) -> RuntimeTelemetry:
        session = SessionContext()
        results = []
        failure_state = ExecutionFailureState(False, None, None, "", [])
        
        start_time = time.time()
        
        # Enforce OBSERVATION_ONLY
        if acv and acv.execution_mode == ExecutionMode.OBSERVATION_ONLY:
            failure_state.failed = True
            failure_state.halt_reason = "CARS-3 OBSERVATION_ONLY ENFORCEMENT"
            
            return RuntimeTelemetry(
                execution_graph_id="graph_gen_1",
                step_results=[],
                strategy_planned=graph.strategy,
                strategy_observed="OBSERVATION_ONLY",
                failure_step=None,
                total_latency_ms=0,
                apn_validations={},
                failure_context={"diagnostic": acv.diagnostic_reason}
            )
        
        start_time = time.time()
        
        # Sequentially execute DAG (assuming linear for now based on VPR3 compilation)
        for step in graph.steps:
            # 1. Determine Dispatcher
            is_browser = step.type in [StepType.BROWSER_NAVIGATE, StepType.BROWSER_WAIT]
            dispatcher = self.browser_dispatch if is_browser else self.http_dispatch
            
            # Simulated pure execution logic (no retries)
            if step.type == StepType.COOKIE_INIT:
                session.cookies["session_id"] = "init_token_123"
                result = ExecutionResult(step.id, "SUCCESS", {"action": "cookie_set"}, 10, None, "hash_c")
                
            elif step.type == StepType.EXTRACT_HEADERS:
                # Mock extracting from previous HTTP request
                session.cookies["mpts_token"] = "valid_session"
                result = ExecutionResult(step.id, "SUCCESS", {"action": "extract_headers"}, 15, None, "hash_h")
                
            elif step.type == StepType.VALIDATE_APN or step.type == StepType.STORE_ARTIFACT:
                # Internal pipeline steps
                result = ExecutionResult(step.id, "SUCCESS", {"action": step.type.value}, 5, None, "hash_v")
                
            else:
                # Physical dispatcher execution
                result = dispatcher.execute(step, session)
            
            # 2. Capture Result
            results.append(result)
            
            # 3. Halt Evaluation (Hard Halt Rule)
            if result.status == "FAILURE":
                failure_state.failed = True
                failure_state.failed_step_id = step.id
                failure_state.failure_type = result.error_type
                failure_state.halt_reason = "Hard halt triggered on step failure"
                failure_state.partial_execution_trace = list(results)
                break
                
        total_latency = int((time.time() - start_time) * 1000)
        
        # 4. Telemetry Finalization
        telemetry = RuntimeTelemetry(
            execution_graph_id="graph_gen_1",
            step_results=results,
            strategy_planned=graph.strategy,
            strategy_observed=graph.strategy,
            failure_step=failure_state.failed_step_id,
            total_latency_ms=total_latency,
            apn_validations={},
            failure_context=None
        )
        
        if failure_state.failed:
            telemetry.failure_context = {
                "step_id": failure_state.failed_step_id,
                "strategy": graph.strategy,
                "vendor_class": graph.vendor_class,
                "dispatcher_used": "HTTPDispatcher" if not is_browser else "BrowserDispatcher",
                "last_http_status": result.response.get("status_code") if result.response else None,
                "last_browser_state_hash": None,
                "execution_path_hash": "hash_path_err"
            }
            
        return telemetry
