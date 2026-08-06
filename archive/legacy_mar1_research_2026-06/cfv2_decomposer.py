import numpy as np
from typing import Dict, List, Tuple, Any

class CFV2Decomposer:
    """
    Failure Manifold Decomposer (CFV-2).
    Treats the Failure Transfer Matrix as a stochastic operator and extracts its eigenstructure
    to discover true invariant latent failure attractors (Z_i).
    """
    def __init__(self, failure_classes: List[str]):
        self.classes = failure_classes
        self.class_idx = {cls: i for i, cls in enumerate(failure_classes)}
        self.n = len(failure_classes)
        
    def _build_transition_matrix(self, ftm: Dict[str, float]) -> np.ndarray:
        # P(i -> j)
        P = np.zeros((self.n, self.n))
        
        # Populate transfers
        for transfer_key, prob in ftm.items():
            src, dst = transfer_key.split(" -> ")
            if src in self.class_idx and dst in self.class_idx:
                P[self.class_idx[src], self.class_idx[dst]] = prob
                
        # Normalize rows to make it a true right stochastic matrix
        for i in range(self.n):
            row_sum = np.sum(P[i, :])
            if row_sum > 0:
                P[i, :] = P[i, :] / row_sum
            else:
                # Absorbing state (no transfers out)
                P[i, i] = 1.0
                
        return P

    def decompose(self, ftms: List[Dict[str, float]]) -> Dict[str, Any]:
        """
        Takes multiple FTMs (from different interventions) and averages their transition mechanics
        to find the globally invariant attractors across the entire intervention space.
        """
        avg_P = np.zeros((self.n, self.n))
        for ftm in ftms:
            avg_P += self._build_transition_matrix(ftm)
            
        if len(ftms) > 0:
            avg_P /= len(ftms)
            
        # Extract Eigenstructure
        # Left eigenvectors of P represent stationary distributions (invariant failure attractors)
        eigenvalues, eigenvectors = np.linalg.eig(avg_P.T)
        
        # Sort by eigenvalue magnitude (stability of the attractor)
        idx = np.argsort(np.abs(eigenvalues))[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]
        
        latent_modes = []
        for i in range(self.n):
            # Normalize eigenvector to sum to 1 (representing a failure mass distribution)
            evec = np.abs(eigenvectors[:, i])
            evec_sum = np.sum(evec)
            if evec_sum > 0:
                evec = evec / evec_sum
                
            latent_modes.append({
                "mode_id": f"Z{i+1}",
                "eigenvalue": float(np.abs(eigenvalues[i])),
                "distribution": {self.classes[j]: float(evec[j]) for j in range(self.n)}
            })
            
        return {
            "operator_matrix": avg_P.tolist(),
            "latent_modes": latent_modes
        }
