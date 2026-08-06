import numpy as np

class CFV4ResidualExtractor:
    """
    Residual Subspace Extractor (CFV-4).
    Computes the orthogonal residual of the unspanned eigenmode.
    """
    def __init__(self, B_matrix: np.ndarray):
        self.B = B_matrix
        
    def get_orthogonal_residual(self, z_target_vec: np.ndarray, u_star: np.ndarray) -> np.ndarray:
        """
        r_perp = r - B(B^+ r)
        """
        # Step 1: Compute raw residual
        # z_target_vec is state (n)
        # B is delta operators (n*n, m)
        # B_u is operator perturbation (n*n)
        # Since B*u is added to P_base, we are comparing the vector z_target against B's projection
        
        # To match the math: we must flatten z_target into the operator space if B operates there,
        # OR project B's effect onto the state space. 
        # The user's math: r = Z2 - B u*. This implies Z2 and B are in the same vector space.
        # We will treat Z2 as a flattened operator target.
        # z_target_vec is length n. Operator space is n*n.
        n = z_target_vec.shape[0]
        z_target_op = np.outer(z_target_vec, np.ones(n)).flatten()
        
        r = z_target_op - (self.B @ u_star)
        
        # Step 2: Compute orthogonal projection
        # B^+ is the pseudoinverse of B
        B_pinv = np.linalg.pinv(self.B)
        
        # r_perp = r - B * B^+ * r
        projection = self.B @ (B_pinv @ r)
        r_perp = r - projection
        
        return r_perp
