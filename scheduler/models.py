from dataclasses import dataclass
from typing import List

@dataclass
class WorkUnit:
    county: str
    apn_batch: List[str]
    endpoint: str

@dataclass
class CountyState:
    county: str
    max_rps: float
    drift_score: float
    success_rate: float
    avg_latency_ms: float
    backlog_size: int

@dataclass
class ThrottleResult:
    rps: float
    blocked: bool
