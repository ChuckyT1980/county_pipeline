"""
raw_store.py — file-backed RawStore implementation.

Every network fetch that goes through BaseAdapter.capture() writes its bytes
here before any parsing runs. Two properties this store gives us that
enforce the raw-capture mandate at the storage layer:

  1. Content-addressed on disk (sharded by content_hash prefix). Identical
     bodies dedupe automatically — re-fetching a page we already have costs
     one index-append, not another copy on disk. That's the "leave everything
     like we were not there" property, translated to bytes: never re-hit if
     the content already exists.

  2. Every call produces a RawFetch row in the index. If parsing later fails
     an integrity_gate(), the RawFetch is still on disk with its URL and
     timestamp — replaying is one file read, not another live fetch. That
     keeps every future adapter change auditable and cheap.

Index format is JSONL at data/raw_index.jsonl — one JSON object per fetch.
No SQLite dependency, no ORM. If we later want SQL, `sqlite3 -init` can
consume the JSONL in one command.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from contracts import RawFetch


class FileRawStore:
    """Content-addressed raw store. Satisfies the RawStore protocol.

    Layout under root_dir:
        raw/{county}/{source}/{hash[:2]}/{hash[2:]}.bin   — the body
        raw_index.jsonl                                    — one line per fetch

    Thread-safe on the index via a lock; concurrent adapter runs can share
    one FileRawStore instance without racing on the id counter or file writes.
    """

    def __init__(self, root_dir: str | Path = "data") -> None:
        self.root = Path(root_dir)
        self.raw_root = self.root / "raw"
        self.index_path = self.root / "raw_index.jsonl"
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._next_id = self._compute_next_id()

    def _compute_next_id(self) -> int:
        """Highest id in the index +1. Zero if the index is empty/missing."""
        if not self.index_path.exists():
            return 1
        max_id = 0
        with self.index_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = row.get("id")
                if isinstance(rid, int) and rid > max_id:
                    max_id = rid
        return max_id + 1

    def _body_path(self, county: str, source: str, content_hash: Optional[str]) -> Path:
        # If the caller didn't supply a hash for some reason, fall back to
        # id-based naming so we still persist bytes and never silently drop.
        h = content_hash or "nohash"
        shard = h[:2] if len(h) >= 2 else "xx"
        stem = h[2:] if len(h) > 2 else h
        return self.raw_root / county / source / shard / f"{stem}.bin"

    def save(self, raw: RawFetch, body: bytes) -> RawFetch:
        """Persist body (content-addressed, dedupe) and append the fetch to
        the index. Returns the RawFetch with id + file_path populated."""
        with self._lock:
            path = self._body_path(raw.county, raw.source.value, raw.content_hash)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_bytes(body or b"")
            raw.id = self._next_id
            self._next_id += 1
            raw.file_path = str(path.relative_to(self.root)).replace("\\", "/")
            # Persist the index row. model_dump(mode='json') so datetime,
            # enum, etc. serialize to primitives without extra work.
            row = raw.model_dump(mode="json")
            with self.index_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, separators=(",", ":")) + "\n")
            return raw
