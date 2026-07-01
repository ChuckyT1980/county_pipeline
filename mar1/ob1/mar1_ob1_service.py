import threading
import queue
from typing import Literal

from mar1.ob1.mar1_event import OB1Event
from mar1.ob1.mar1_queue import OB1Queue, QueueResult
from mar1.ob1.mar1_wal import WALWriter

_service_instance = None

def initialize_ob1(log_dir: str = "logs/mar1_shadow_logs", wal_mode: str = "SAFE"):
    global _service_instance
    if _service_instance is None:
        _service_instance = OB1Service(log_dir=log_dir, wal_mode=wal_mode)

def emit_observation(event: OB1Event, *, mode: Literal["SYNC", "ASYNC"] = "ASYNC") -> QueueResult:
    """
    The single ingestion gate into OB-1.
    Once an event enters here, it is logically dead to MAR-1.
    """
    if _service_instance is None:
        # If OB-1 is not initialized or crashed, telemetry loss != control failure.
        # MAR-1 must continue executing.
        return QueueResult.DROPPED
        
    return _service_instance.emit_observation(event, mode=mode)
    
def shutdown_ob1():
    global _service_instance
    if _service_instance is not None:
        _service_instance.shutdown()
        _service_instance = None

class OB1Service:
    """
    Internal service orchestrator.
    Composes OB1Event -> Queue.put() -> WAL thread (independent).
    No additional layers.
    """
    def __init__(self, log_dir: str, wal_mode: str):
        self.queue = OB1Queue(maxsize=1000)
        self.wal_writer = WALWriter(log_dir=log_dir, mode=wal_mode)
        self._stop_event = threading.Event()
        self._wal_thread = threading.Thread(target=self._wal_worker, daemon=True)
        self._wal_thread.start()
        
    def emit_observation(self, event: OB1Event, *, mode: Literal["SYNC", "ASYNC"] = "ASYNC") -> QueueResult:
        result = self.queue.put(event)
        
        # Rule 9: If DEGRADED, OB-1 degrades (increase flush frequency) - MAR-1 does not slow down.
        if result == QueueResult.DEGRADED:
            # We temporarily force a tighter flush cadence on the WAL writer
            self.wal_writer.flush_cadence = max(1, self.wal_writer.flush_cadence // 2)
            
        return result

    def _wal_worker(self):
        import queue
        while not self._stop_event.is_set():
            try:
                # Wait briefly for events so we can periodically check _stop_event
                event = self.queue.get(block=True, timeout=0.1)
                self.wal_writer.write(event)
                self.wal_writer.rotate_if_needed()
            except queue.Empty:
                pass
            except Exception:
                # Silently catch other queue errors to prevent crashing the thread loop
                pass
                
        # Graceful shutdown flush
        while not self.queue.empty():
            try:
                event = self.queue.get(block=False)
                self.wal_writer.write(event)
            except queue.Empty:
                break
        self.wal_writer.close()

    def shutdown(self):
        self._stop_event.set()
        self._wal_thread.join(timeout=5.0)
