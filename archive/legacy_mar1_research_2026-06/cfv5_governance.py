import numpy as np
from typing import Dict, Any, List

class CFV5GovernanceLayer:
    """
    Control Governance Layer (CFV-5).
    Evaluates new basis vectors against strict semantic invariants.
    """
    def __init__(self, delta_min: float = 0.1, entropy_threshold: float = 0.5, topology_epsilon: int = 2):
        self.delta_min = delta_min
        self.entropy_threshold = entropy_threshold
        self.topology_epsilon = topology_epsilon

    def _invariant_A_identity_preservation(self, b_new: np.ndarray, base_matrix: np.ndarray) -> bool:
        """
        Class A: Field Identity Preservation.
        Ensures distance between field representations > delta_min.
        Since b_new modifies P_base, we check if the new operator merges the steady-state
        distribution of distinct fields.
        """
        # A simple proxy: if the perturbation b_new aggressively pushes mass from field i 
        # to field j such that they become indistinguishable, we reject.
        # We can measure the off-diagonal mass increase. If b_new shifts > delta_max mass, it's collapsing.
        # For simplicity in this proxy, we ensure the diagonal (self-identity) remains dominant.
        n = int(np.sqrt(len(b_new)))
        b_matrix = b_new.reshape((n, n))
        P_new = base_matrix + b_matrix
        
        # Identity is preserved if diagonal is larger than off-diagonals (simple proxy for distance)
        for i in range(n):
            if P_new[i, i] < np.max(P_new[i, np.arange(n) != i]) - self.delta_min:
                return False
        return True

    def _invariant_B_non_collapse(self, b_new: np.ndarray) -> bool:
        """
        Class B: Non-Collapse Constraint (Topology Preservation).
        Ensures cluster identity entropy does not decrease below threshold.
        """
        # A basis vector that collapses topology will have very low entropy (pushes everything to 1 state)
        # We measure the entropy of the perturbation's absolute mass.
        mass = np.abs(b_new)
        mass_sum = np.sum(mass)
        if mass_sum == 0: return True
        
        p = mass / mass_sum
        entropy = -np.sum(p * np.log(p + 1e-9))
        
        # If entropy is too low, it's a collapsing Dirac-delta mapping.
        if entropy < self.entropy_threshold:
            return False
        return True

    def _invariant_C_locality_preservation(self, b_new: np.ndarray) -> bool:
        """
        Class C: Locality Preservation.
        Ensures GraphEditDistance <= epsilon_topology.
        """
        # A basis vector changes the graph if it introduces new non-zero off-diagonals.
        # Count the number of new significant edges created by the perturbation.
        n = int(np.sqrt(len(b_new)))
        b_matrix = np.abs(b_new.reshape((n, n)))
        
        # Count significant new structural edges
        new_edges = np.sum(b_matrix > 0.05)
        
        if new_edges > self.topology_epsilon:
            return False
        return True

    def validate_basis(self, b_new: np.ndarray, base_matrix: np.ndarray) -> Dict[str, Any]:
        """
        Accept(b_new) <=> I1 and I2 and I3
        """
        i1 = self._invariant_A_identity_preservation(b_new, base_matrix)
        i2 = self._invariant_B_non_collapse(b_new)
        i3 = self._invariant_C_locality_preservation(b_new)
        
        accept = i1 and i2 and i3
        
        return {
            "accepted": accept,
            "I1_identity": i1,
            "I2_non_collapse": i2,
            "I3_locality": i3
        }
