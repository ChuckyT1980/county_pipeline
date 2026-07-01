import numpy as np
from typing import Dict, Any

class CFV4BasisSynthesis:
    """
    Basis Synthesis Engine (CFV-4).
    Extracts the dominant missing control direction from residual structure.
    """
    def extract_new_basis(self, r_perp: np.ndarray) -> np.ndarray:
        """
        C = r_perp.T @ r_perp (or outer product for vectors)
        Returns the dominant eigenvector as b_new.
        Since r_perp is a 1D vector (flattened n*n operator), C = np.outer(r_perp, r_perp)
        The dominant eigenvector of an outer product of a vector with itself is just the normalized vector.
        """
        norm = np.linalg.norm(r_perp)
        if norm > 0:
            b_new = r_perp / norm
        else:
            b_new = np.zeros_like(r_perp)
            
        # We need to scale b_new so it acts as a realistic delta operator probability.
        # But for control geometry, the direction is what matters.
        # Let's scale it to match the magnitude of the target residual.
        b_new = b_new * norm
        
        return b_new
