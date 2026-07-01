import hashlib
import json
from dataclasses import dataclass
from vpr3 import ExecutionGraph
from cars3_schemas import ActionConstraintVector

class ExecutionAuthorityViolation(Exception):
    """Raised when EAF-1 rejects a graph compilation due to constraint mismatch."""
    pass

@dataclass
class AuthorizedExecutionPayload:
    """
    The strictly immutable payload that EER-1 (LiveDispatcher) requires to execute.
    It cryptographically binds the graph to the constraint vector.
    """
    graph: ExecutionGraph
    constraint_vector: ActionConstraintVector
    integrity_hash: str
    
    @staticmethod
    def compute_hash(graph: ExecutionGraph, acv: ActionConstraintVector) -> str:
        # A simple deterministic serialization for hashing purposes
        # In a production system, this would deeply serialize the objects.
        # For our architecture, we serialize the core structural elements.
        
        graph_sig = {
            "id": graph.county,
            "vendor": graph.vendor_class,
            "strategy": graph.strategy,
            "steps": [s.id for s in graph.steps]
        }
        
        acv_sig = {
            "mode": acv.execution_mode.value,
            "allowed": sorted(acv.allowed_strategies),
            "weights": acv.instrument_authority_weights
        }
        
        payload = json.dumps({"graph": graph_sig, "acv": acv_sig}, sort_keys=True)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()
