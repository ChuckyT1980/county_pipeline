import os
import json

class CompatibilityAnalyzer:
    def __init__(self, matrix_path: str = "analysis/compatibility_matrix.json"):
        self.matrix_path = matrix_path
        
    def _load_matrix(self):
        if not os.path.exists(self.matrix_path):
            raise FileNotFoundError(f"Matrix file missing: {self.matrix_path}")
        with open(self.matrix_path, "r") as f:
            return json.load(f)

    def load_signature(self, command: str, version: str):
        matrix = self._load_matrix()
        if command not in matrix:
            raise ValueError(f"Command {command} not found in compatibility matrix")
        if version not in matrix[command]:
            raise ValueError(f"Version {version} not found for {command} in matrix")
        return matrix[command][version]

    def _diff(self, sig1: dict, sig2: dict) -> dict:
        shape_diff = sig1.get("output_shape") != sig2.get("output_shape")
        behavior_diff = sig1.get("behavior_hash") != sig2.get("behavior_hash")
        
        breaking_changes = []
        if shape_diff:
            breaking_changes.append(f"Output shape changed: {sig1.get('output_shape')} -> {sig2.get('output_shape')}")
            
        if behavior_diff:
            breaking_changes.append(f"Semantic behavior shifted: {sig1.get('behavior_hash')} -> {sig2.get('behavior_hash')}")

        if shape_diff:
            risk = "HIGH"
            compat = False
            cls = "BREAKING"
        elif behavior_diff:
            risk = "MEDIUM"
            compat = False
            cls = "SEMANTIC_SHIFT"
        else:
            risk = "LOW"
            compat = True
            cls = "SAFE"
            
        return {
            "compatible": compat,
            "classification": cls,
            "risk_level": risk,
            "breaking_changes": breaking_changes
        }

    def compare(self, command: str, v1: str, v2: str):
        sig1 = self.load_signature(command, v1)
        sig2 = self.load_signature(command, v2)
        return self._diff(sig1, sig2)
