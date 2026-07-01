import json
import os
import shutil
import time
from arc1_schemas import RecompileProposal

class RegistryCommitGate:
    """
    Commit Authority Layer (Phase 2.20).
    The ONLY component allowed to mutate registry files.
    """
    def __init__(self, registry_dir: str = "data/registry"):
        self.registry_dir = registry_dir
        self.history_dir = os.path.join(registry_dir, "history")
        os.makedirs(self.history_dir, exist_ok=True)
        self.schema_registry_path = os.path.join(registry_dir, "schema_registry.json")
        self.vpr_registry_path = os.path.join(registry_dir, "vpr_registry.json")

    def _get_next_version(self, target: str) -> str:
        # Simple timestamp-based versioning for prototype
        return f"v{int(time.time())}"

    def commit(self, proposal: RecompileProposal) -> str:
        # 1. Determine target file
        target_path = self.schema_registry_path if proposal.target_registry == "schema_registry" else self.vpr_registry_path
        
        # 2. Backup current state to history log BEFORE mutation
        if os.path.exists(target_path):
            with open(target_path, "r") as f:
                current_data = json.load(f)
        else:
            current_data = {}
            
        version_id = self._get_next_version(proposal.target_registry)
        history_file = os.path.join(self.history_dir, f"{proposal.target_registry}_{version_id}.json")
        
        with open(history_file, "w") as f:
            json.dump({
                "version_id": version_id,
                "previous_state": current_data,
                "proposal_patch": {
                    "vendor_class": proposal.vendor_class,
                    "patch_type": proposal.patch_type.value,
                    "drift_source_event_id": proposal.drift_source_event_id,
                    "risk_score": proposal.risk_score
                }
            }, f, indent=2)

        # 3. Apply the patch atomically
        if proposal.target_registry == "schema_registry":
            if "schemas" not in current_data: current_data["schemas"] = {}
            current_data["schemas"][proposal.vendor_class] = proposal.after_state
        else:
            # VPR Registry update logic
            pass 
            
        temp_path = target_path + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(current_data, f, indent=2)
            
        os.replace(temp_path, target_path) # Atomic overwrite
        
        return version_id

    def rollback(self, target_registry: str, version_id: str) -> bool:
        """Deterministically restores the registry to a previous state."""
        history_file = os.path.join(self.history_dir, f"{target_registry}_{version_id}.json")
        if not os.path.exists(history_file):
            return False
            
        with open(history_file, "r") as f:
            history_data = json.load(f)
            
        target_path = self.schema_registry_path if target_registry == "schema_registry" else self.vpr_registry_path
        
        temp_path = target_path + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(history_data["previous_state"], f, indent=2)
            
        os.replace(temp_path, target_path)
        return True
