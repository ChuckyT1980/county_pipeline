from abc import ABC, abstractmethod
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class RawPayload:
    apn_raw: str
    data: Dict[str, Any]
    source: str
    county: str

class BaseConnector(ABC):
    def __init__(self, county: str):
        self.county = county

    @abstractmethod
    def fetch_identity(self, apn: str) -> RawPayload:
        pass

    @abstractmethod
    def fetch_snapshot(self, apn: str) -> RawPayload:
        pass

    def normalize_apn(self, apn: str) -> str:
        return apn.replace("-", "").strip()
