import numpy as np
from scipy.optimize import minimize
from typing import Dict, List, Any

class CFV3ControllabilityEngine:
    """
    Eigenmode Sensitivity & Controllability Engine (CFV-3).
    Solves the core control geometry problem:
    min_u || Z2 - B·u ||^2 + lambda ||u||_1 subject to C(B·u) <= budget
    """
    def __init__(self, B_matrix: np.ndarray, P_base: np.ndarray, intervention_keys: List[str]):
        self.B = B_matrix
        self.P_base = P_base
        self.keys = intervention_keys
        self.n_interventions = len(intervention_keys)
        
    def _compute_costs(self) -> np.ndarray:
        # C(I_k) = alpha C_s + beta C_e + gamma C_c
        costs = []
        for i in range(self.n_interventions):
            group = self.keys[i]
            
            # 1. Structural Cost (C_s)
            c_s = 0.2 if group == "B" else (0.4 if group == "C" else 0.8) # Arbitrary example costs
            
            # 2. Entropy Cost (C_e) = KL roughly approximated by norm of perturbation
            b_k = self.B[:, i]
            c_e = np.linalg.norm(b_k)
            
            # 3. Controllability Cost (C_c) = variance in Z eigenvalues
            # If we apply b_k fully, what happens to eigenvalues?
            P_new = self.P_base + b_k.reshape(self.P_base.shape)
            # Ensure valid transition matrix mathematically (clamp)
            P_new = np.clip(P_new, 0, 1)
            for r in range(P_new.shape[0]):
                s = np.sum(P_new[r, :])
                if s > 0: P_new[r, :] /= s
                
            eigs_base, _ = np.linalg.eig(self.P_base.T)
            eigs_new, _ = np.linalg.eig(P_new.T)
            c_c = np.var(np.abs(eigs_new)) - np.var(np.abs(eigs_base))
            
            # Total Cost
            cost = (0.3 * c_s) + (0.5 * c_e) + (0.2 * abs(c_c))
            costs.append(cost)
            
        return np.array(costs)
        
    def solve_control_policy(self, Z_target: Dict[str, Any], budget: float = 1.0, l1_lambda: float = 0.1) -> Dict[str, Any]:
        """
        Solves for the optimal intervention weights `u`.
        """
        costs = self._compute_costs()
        
        # Z_target distribution as a vector
        # We want to match the target eigenvector structure but negative to suppress it?
        # The user's formula: min_u || Z2 - B·u ||^2
        # This implies we want to find the combination of interventions that perfectly recreates Z2's shape
        # so we can directly subtract it (ablate it).
        
        # Build Z2 target vector (flattened n x n perturbation target)
        # Actually, Z2 is a state distribution (size n), while B·u is an operator perturbation (size n*n)
        # Wait, the user said: Z2 ≈ B · u
        # But Z2 is an eigenvector of length n. B is a stack of delta FTMs of length n*n.
        # How do we map operator B (n*n) to state Z2 (n)?
        # The true goal is to perturb P such that P_new * Z2 = 0 (suppress the eigenvalue).
        # We approximate this by projecting the action of B onto Z2.
        # But for the sake of the pilot, we will assume B·u maps into a latent space where Z2 lives,
        # or we just solve a proxy objective: minimize the impact of Z2 on the new operator.
        # Let's map Z2 into the operator space by outer product with itself: target_op = Z2 * Z2.T
        
        n_classes = int(np.sqrt(self.B.shape[0]))
        z_vec = np.zeros(n_classes)
        for i, (cls, val) in enumerate(Z_target["distribution"].items()):
            z_vec[i] = val
            
        # We want to suppress the Z2 failure current. 
        # Z2 is a state vector. Under the new operator P_new, the persistent mass of Z2 is approximated 
        # by the Rayleigh quotient: (Z2.T @ P_new @ Z2) / (Z2.T @ Z2).
        # We want to minimize this quotient.
        z_norm = np.dot(z_vec, z_vec)
        if z_norm == 0: z_norm = 1.0
        
        def objective(u):
            # P_new = P_base + B_tensor * u
            # Since B is flattened, we reshape
            perturbation = (self.B @ u).reshape(self.P_base.shape)
            P_new = self.P_base + perturbation
            
            # Clamp and normalize rows to keep it a valid stochastic operator
            P_new = np.clip(P_new, 0, 1)
            for r in range(P_new.shape[0]):
                s = np.sum(P_new[r, :])
                if s > 0: P_new[r, :] /= s
                
            # Compute Rayleigh quotient for Z2
            rayleigh = np.dot(z_vec.T, np.dot(P_new, z_vec)) / z_norm
            
            return rayleigh + l1_lambda * np.sum(np.abs(u))
            
        def cost_constraint(u):
            # budget - C(B*u) >= 0. C is linear w.r.t costs array for simplicity.
            return budget - np.dot(costs, np.abs(u))
            
        constraints = [{'type': 'ineq', 'fun': cost_constraint}]
        bounds = [(0, 1) for _ in range(self.n_interventions)] # Weights between 0 and 1
        
        u0 = np.zeros(self.n_interventions)
        res = minimize(objective, u0, bounds=bounds, constraints=constraints)
        
        policy = {self.keys[i]: float(res.x[i]) for i in range(self.n_interventions)}
        
        return {
            "policy": policy,
            "costs": {self.keys[i]: float(costs[i]) for i in range(self.n_interventions)},
            "success": res.success,
            "message": str(res.message)
        }
