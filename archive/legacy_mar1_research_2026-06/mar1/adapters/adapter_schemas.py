import json
from dataclasses import dataclass, asdict

@dataclass(frozen=True)
class RawSnapshot:
    source_id: str
    timestamp: float
    request_payload: str
    response_payload: str
    response_hash: str
    metadata: dict

    def to_json(self) -> str:
        d = asdict(self)
        d['type'] = 'RawSnapshot'
        return json.dumps(d)
