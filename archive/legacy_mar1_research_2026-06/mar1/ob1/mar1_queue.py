import queue
import multiprocessing
from enum import Enum
from typing import Optional
from mar1.ob1.mar1_event import OB1Event

class QueueResult(Enum):
    ACCEPTED = 1
    DROPPED = 2
    DEGRADED = 3
    SAFE_HALT_TRIGGERED = 4

class OB1Queue:
    """
    Bounded, backpressure-safe queue for MAR-1 -> OB-1 event handoff.
    Enforces non-blocking enqueue semantics to guarantee Temporal Decoupling.
    """
    def __init__(self, maxsize: int = 1000):
        self.maxsize = maxsize
        self._q = queue.Queue(maxsize=self.maxsize)

    def put(self, event: OB1Event) -> QueueResult:
        try:
            current_size = self._q.qsize()
        except NotImplementedError:
            current_size = 0 # macOS/fallback
            
        if current_size >= self.maxsize:
            return QueueResult.SAFE_HALT_TRIGGERED
            
        try:
            self._q.put_nowait(event)
        except queue.Full:
            return QueueResult.SAFE_HALT_TRIGGERED
            
        # Degradation threshold at 80% saturation
        if current_size >= self.maxsize * 0.8:
            return QueueResult.DEGRADED
            
        return QueueResult.ACCEPTED
        
    def get(self, block: bool = True, timeout: Optional[float] = None) -> OB1Event:
        return self._q.get(block=block, timeout=timeout)
        
    def empty(self) -> bool:
        return self._q.empty()
