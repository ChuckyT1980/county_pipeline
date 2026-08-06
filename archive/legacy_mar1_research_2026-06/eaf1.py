from vpr3 import ExecutionGraph, StepType
from cars3_schemas import ActionConstraintVector
from eaf1_schemas import AuthorizedExecutionPayload, ExecutionAuthorityViolation

class ExecutionAuthorityFirewall:
    """
    EAF-1: The Compiler Gate.
    Enforces strict binary existence constraints between CGR-1 and EER-1.
    Never interprets weights or quality. Only asks: 'Is this structurally allowed?'
    """
    
    @staticmethod
    def compile_payload(graph: ExecutionGraph, acv: ActionConstraintVector) -> AuthorizedExecutionPayload:
        # 1. Enforce Strategy Inclusion
        if graph.strategy not in acv.allowed_strategies:
            raise ExecutionAuthorityViolation(
                f"EAF-1 REJECTED: Strategy '{graph.strategy}' is not in allowed strategies: {acv.allowed_strategies}"
            )
            
        # 2. Enforce Actuator Existence Weights (Binary Gate)
        # HTTP is StepType.HTTP_REQUEST, StepType.EXTRACT_DOM
        # Playwright is StepType.BROWSER_NAVIGATE, StepType.FOLLOW_LINK
        
        has_http = any(step.type in [StepType.HTTP_REQUEST, StepType.EXTRACT_DOM] for step in graph.steps)
        has_browser = any(step.type in [StepType.BROWSER_NAVIGATE, StepType.FOLLOW_LINK] for step in graph.steps)
        
        weights = acv.instrument_authority_weights or {"HTTP": 1.0, "PLAYWRIGHT": 1.0}
        
        if has_http and weights.get("HTTP", 0.0) <= 0.0:
            raise ExecutionAuthorityViolation(
                f"EAF-1 REJECTED: Graph contains HTTP actuator steps, but HTTP authority weight is <= 0.0"
            )
            
        if has_browser and weights.get("PLAYWRIGHT", 0.0) <= 0.0:
            raise ExecutionAuthorityViolation(
                f"EAF-1 REJECTED: Graph contains Playwright actuator steps, but PLAYWRIGHT authority weight is <= 0.0"
            )
            
        # 3. Compile Hash and Issue Payload
        h = AuthorizedExecutionPayload.compute_hash(graph, acv)
        return AuthorizedExecutionPayload(
            graph=graph,
            constraint_vector=acv,
            integrity_hash=h
        )
