import numpy as np
from typing import Dict, Any, List

class CFV2MetricsEngine:
    """
    Latent Defect Metrics Engine (CFV-2).
    Computes LFR (Latent Failure Rank) and NIS (Non-Identifiability Score).
    """
    def __init__(self, latent_modes: List[Dict[str, Any]]):
        self.latent_modes = latent_modes
        
    def compute_lfr(self) -> List[Dict[str, Any]]:
        """
        Latent Failure Rank (LFR).
        Ranks latent attractors by eigenvalue magnitude.
        High eigenvalue = highly stable, irreducible failure generator.
        """
        lfr_ranking = []
        for mode in self.latent_modes:
            lfr_ranking.append({
                "mode_id": mode["mode_id"],
                "lfr_score": mode["eigenvalue"],
                "primary_surface_manifestation": max(mode["distribution"].items(), key=lambda x: x[1])[0]
            })
            
        return sorted(lfr_ranking, key=lambda x: x["lfr_score"], reverse=True)

    def compute_nis(self, class_labels: List[str]) -> Dict[str, Any]:
        """
        Non-Identifiability Score (NIS).
        Measures how mathematically indistinguishable two surface failure labels are 
        in the latent eigenspace. High NIS means they are the same underlying defect.
        """
        n = len(class_labels)
        nis_matrix = {}
        
        # Build coordinate vectors for each surface class in the latent eigenspace
        coords = {cls: [] for cls in class_labels}
        for mode in self.latent_modes:
            for cls in class_labels:
                coords[cls].append(mode["distribution"][cls])
                
        # Compute cosine similarity between classes in the latent subspace
        for i in range(n):
            for j in range(i+1, n):
                cls1 = class_labels[i]
                cls2 = class_labels[j]
                
                v1 = np.array(coords[cls1])
                v2 = np.array(coords[cls2])
                
                norm1 = np.linalg.norm(v1)
                norm2 = np.linalg.norm(v2)
                
                if norm1 == 0 or norm2 == 0:
                    similarity = 0.0
                else:
                    similarity = np.dot(v1, v2) / (norm1 * norm2)
                    
                key = f"{cls1} <-> {cls2}"
                nis_matrix[key] = float(similarity)
                
        # Sort and return pairs with dangerously high NIS (>0.85)
        highly_coupled = {k: v for k, v in nis_matrix.items() if v > 0.85}
        
        return {
            "nis_matrix": nis_matrix,
            "highly_coupled_defects": highly_coupled
        }
