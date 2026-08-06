import copy
import random
from typing import Literal, Optional, List, Dict, Any

class FaultDescriptor:
    def __init__(self, mode: Literal["NONE", "CLASS_A", "CLASS_B", "CLASS_C", "CLASS_D", "MIXED"], parameters: Optional[dict] = None):
        self.mode = mode
        self.parameters = parameters or {}

class Snapshot:
    def __init__(self, dom: Optional[dict], ob1_stream: Optional[list] = None, wal_view: Optional[list] = None, schema_mapping_view: Optional[dict] = None):
        self.dom = dom
        self.ob1_stream = ob1_stream or []
        self.wal_view = wal_view or []
        self.schema_mapping_view = schema_mapping_view or {}
        
    def deep_copy(self):
        return Snapshot(
            copy.deepcopy(self.dom),
            copy.deepcopy(self.ob1_stream),
            copy.deepcopy(self.wal_view),
            copy.deepcopy(self.schema_mapping_view)
        )

def apply_fault(snapshot: Snapshot, fault: FaultDescriptor) -> Snapshot:
    """
    CFIT-1 Safe Reference Implementation.
    Converts a clean snapshot into a corrupted observation view without ever touching control logic.
    """
    corrupted = snapshot.deep_copy()
    
    if fault.mode == "NONE":
        return corrupted
    elif fault.mode == "CLASS_A":
        return apply_class_a(corrupted)
    elif fault.mode == "CLASS_B":
        return apply_class_b(corrupted, fault.parameters)
    elif fault.mode == "CLASS_C":
        return apply_class_c(corrupted, fault.parameters)
    elif fault.mode == "CLASS_D":
        return apply_class_d(corrupted, fault.parameters)
    elif fault.mode == "MIXED":
        return apply_mixed(corrupted, fault.parameters)
        
    return corrupted

def apply_class_a(s: Snapshot) -> Snapshot:
    # Empty state boot (Cold Start Collapse)
    s.ob1_stream = []
    s.wal_view = []
    s.dom = None
    return s

def apply_class_b(s: Snapshot, p: dict) -> Snapshot:
    # Partial observability loss
    drop_rate = p.get("drop_rate", 0.5)
    s.ob1_stream = [e for e in s.ob1_stream if random.random() > drop_rate]
    return s

import dataclasses

def apply_class_c(s: Snapshot, p: dict) -> Snapshot:
    # Temporal desync (Replay distortion)
    sigma = p.get("jitter_sigma", 200)
    new_wal = []
    for e in s.wal_view:
        new_wal.append(dataclasses.replace(e, timestamp=e.timestamp + random.gauss(0, sigma)))
        
    s.wal_view = sorted(new_wal, key=lambda x: x.timestamp)
    return s

def apply_class_d(s: Snapshot, p: dict) -> Snapshot:
    # Structural corruption (Semantic drift)
    new_stream = []
    factor = p.get("scale_factor", 100)
    for e in s.ob1_stream:
        new_e = dataclasses.replace(
            e,
            risk_score=e.elasticity_score,
            elasticity_score=e.risk_score,
            pressure_scalar=e.pressure_scalar * factor
        )
        new_stream.append(new_e)
    s.ob1_stream = new_stream
        
    return s

def apply_mixed(s: Snapshot, p: dict) -> Snapshot:
    if p.get("a", True): s = apply_class_a(s)
    if p.get("b", True): s = apply_class_b(s, p)
    if p.get("c", True): s = apply_class_c(s, p)
    if p.get("d", True): s = apply_class_d(s, p)
    return s
