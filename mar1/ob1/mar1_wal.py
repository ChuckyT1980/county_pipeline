import os
import time
from typing import Optional
from mar1.ob1.mar1_event import OB1Event

class WALWriter:
    """
    Append-only JSONL Write-Ahead Log for OB-1 events.
    Supports SAFE (buffered) and STRICT (fsync per event) modes.
    """
    def __init__(self, log_dir: str, mode: str = "SAFE", flush_cadence: int = 100):
        self.log_dir = log_dir
        self.mode = mode.upper() # "SAFE" or "STRICT"
        self.flush_cadence = flush_cadence if self.mode == "SAFE" else 1
        self._unflushed_count = 0
        
        os.makedirs(self.log_dir, exist_ok=True)
        self._current_file_path = self._get_current_log_path()
        
        # Open in strictly append mode
        self._file = open(self._current_file_path, "a", encoding="utf-8")
        
    def _get_current_log_path(self) -> str:
        date_str = time.strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{date_str}.jsonl")
        
    def write(self, event: OB1Event):
        # 1 event per line, no pretty printing, no transformation
        self._file.write(event.to_json() + "\n")
        self._unflushed_count += 1
        
        if self._unflushed_count >= self.flush_cadence:
            self._sync()
            
    def _sync(self):
        self._file.flush()
        # fsync to guarantee disk persistence
        os.fsync(self._file.fileno())
        self._unflushed_count = 0
        
    def rotate_if_needed(self):
        new_path = self._get_current_log_path()
        if new_path != self._current_file_path:
            self._sync()
            self._file.close()
            self._current_file_path = new_path
            self._file = open(self._current_file_path, "a", encoding="utf-8")
            
    def close(self):
        if not self._file.closed:
            self._sync()
            self._file.close()
