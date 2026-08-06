from typing import List, Dict, Any, Tuple
from vpr3 import ExecutionGraph
from eer1_schemas import SessionContext, ExecutionResult
from dispatchers_live import LiveDispatcher

class ShadowDispatcher:
    """
    Phase 4A: Shadow Adaptation Fleet Dispatcher.
    Executes ARC-1 proposed graphs against the live target but off-chain from the production registry.
    """
    def __init__(self):
        self.live_dispatcher = LiveDispatcher()
        
    def execute_shadow_graph(self, production_graph: Dict[str, Any], shadow_graph: Dict[str, Any], session_context: SessionContext) -> Tuple[List[ExecutionResult], List[ExecutionResult]]:
        """
        Executes both the old production graph (which may be failing) and the new ARC-1 shadow graph.
        Returns both result sets for Adaptation Lift (AL) computation.
        """
        print(f"  [SHADOW FLEET] Dispatched Production Graph vs ARC-1 Proposal")
        
        # In a real environment, we would execute both safely. 
        # For our local simulation, we just route them to the LiveDispatcher.
        
        # 1. Run Production (Failing Baseline)
        prod_results = self.live_dispatcher.execute_graph(production_graph, session_context)
        
        # 2. Run Shadow Proposal
        shadow_results = self.live_dispatcher.execute_graph(shadow_graph, session_context)
        
        return prod_results, shadow_results
