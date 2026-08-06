import numpy as np
from typing import Dict, List, Any

class CFV3BasisExtractor:
    """
    Control Basis Extractor (CFV-3).
    Extracts the Intervention Control Matrix B from the measured FTM perturbations.
    """
    def __init__(self, n_classes: int):
        self.n = n_classes
        self.matrix_size = n_classes * n_classes
        
    def _ftm_to_matrix(self, ftm: Dict[str, float], classes: List[str]) -> np.ndarray:
        P = np.zeros((self.n, self.n))
        class_idx = {cls: i for i, cls in enumerate(classes)}
        
        for transfer_key, prob in ftm.items():
            src, dst = transfer_key.split(" -> ")
            if src in class_idx and dst in class_idx:
                P[class_idx[src], class_idx[dst]] = prob
                
        # Normalize
        for i in range(self.n):
            row_sum = np.sum(P[i, :])
            if row_sum > 0:
                P[i, :] = P[i, :] / row_sum
            else:
                P[i, i] = 1.0
        return P

    def extract_basis(self, 
                      baseline_ftm: Dict[str, float], 
                      intervention_ftms: Dict[str, Dict[str, float]], 
                      classes: List[str]) -> Dict[str, Any]:
        """
        Calculates b_k = vec(FTM_after(I_k)) - vec(FTM_baseline)
        Returns the Control Matrix B.
        """
        P_base = self._ftm_to_matrix(baseline_ftm, classes)
        vec_base = P_base.flatten()
        
        B_vectors = {}
        for group_id, ftm in intervention_ftms.items():
            P_int = self._ftm_to_matrix(ftm, classes)
            vec_int = P_int.flatten()
            b_k = vec_int - vec_base
            B_vectors[group_id] = b_k
            
        # Stack into matrix B (matrix_size x num_interventions)
        keys = list(B_vectors.keys())
        B_matrix = np.column_stack([B_vectors[k] for k in keys])
        
        return {
            "P_base": P_base,
            "intervention_keys": keys,
            "B_matrix": B_matrix,
            "b_vectors": B_vectors
        }
