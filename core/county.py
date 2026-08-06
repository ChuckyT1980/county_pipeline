"""
County-aware core: configuration, storage, and shared primitives for the
unified California county tax-auction intelligence system.

One engine, many counties. Each county is a YAML config file (counties/*.yaml)
declaring its data sources (assessor backend, recorder backend, auction
platform). The core modules turn those configs into a standard per-county
dataset that any tool (Excel, SQL, scripts) can consume.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import re
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
COUNTIES_DIR = REPO_ROOT / "counties"
DATA_DIR = REPO_ROOT / "data" / "counties"

# County tax collector / default-agency party names seen across CA counties
# (Fresno "FRESNO COU TAX COLLR", generic "COUNTY OF X TAX COLLECTOR", etc.).
_DEFAULT_COLLECTOR_RE = re.compile(
    r"(?:TAX\s*COL\w*\s*(?:OFFICE|OF)?|COUNTY\s*OF\s+\w+\s*(?:TAX|DEFAULT)|"
    r"TAX\s*DEFAULT)", re.I)


@dataclass
class AssessorConfig:
    """How to pull a county's full assessor roll."""
    backend: str                    # "arcgis" | "mpts" | "csv" | "manual"
    endpoint: str = ""              # ArcGIS layer query URL, or MPTS base
    where: str = "1=1"              # ArcGIS where clause
    apn_field: str = "APN"          # ArcGIS field holding the APN
    out_fields: str = "*"           # ArcGIS outFields
    apn_includes: list = field(default_factory=lambda: [])
    slug: str = ""                  # MPTS slug when != county name
    notes: str = ""


@dataclass
class RecorderConfig:
    """How to reach a county's recorder/index portal."""
    backend: str                    # "tyler" | "mpts" | "manual"
    base_url: str = ""
    name_search_id: str = ""
    doc_search_id: str = ""
    apn_search_id: str = ""
    typedate_search_id: str = ""    # doc-type + recording-date search (radar)
    ajax_headers_required: bool = True
    doc_number_transform: Optional[str] = None
    doc_field: str = ""             # POST field for doc number (default field_DocumentNumberID)
    notes: str = ""


@dataclass
class AuctionConfig:
    """How to reach a county's auction platform."""
    backend: str                    # "realauction" | "govease" | "pdf" | "manual"
    base_url: str = ""
    calendar_url: str = ""
    preview_url: str = ""
    pdf_urls: list = field(default_factory=list)
    auction_dates: list = field(default_factory=list)
    notes: str = ""


@dataclass
class CountyConfig:
    """Everything the engine needs to run one county."""
    county: str
    assessor: AssessorConfig
    recorder: RecorderConfig
    auction: AuctionConfig
    display_name: str = ""
    notes: str = ""
    collector_names: list = field(default_factory=list)

    @classmethod
    def load(cls, name: str) -> "CountyConfig":
        path = COUNTIES_DIR / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"No county config: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            county=name,
            display_name=raw.get("display_name", name.title()),
            assessor=AssessorConfig(**raw.get("assessor", {})),
            recorder=RecorderConfig(**raw.get("recorder", {})),
            auction=AuctionConfig(**raw.get("auction", {})),
            collector_names=raw.get("collector_names", []),
            notes=raw.get("notes", ""),
        )

    def has_auction(self) -> bool:
        """True only when the county has a real, configured auction backend.
        GovEase entries with empty URLs are placeholders, not sources."""
        a = self.auction
        if a.backend == "realauction":
            return bool(a.preview_url and a.auction_dates)
        if a.backend in ("govease", "pdf"):
            return bool(a.base_url or a.preview_url or a.pdf_urls)
        return False

    def is_county_holder(self, party: str) -> bool:
        """Is this party the county tax collector / county default agency?
        The universal 'county took the property' signal across every county."""
        p = (party or "").upper()
        if not p:
            return False
        if any(n.upper() in p for n in self.collector_names):
            return True
        return _DEFAULT_COLLECTOR_RE.search(p) is not None

    def data_dir(self) -> Path:
        d = DATA_DIR / self.county
        d.mkdir(parents=True, exist_ok=True)
        return d

    def roll_path(self) -> Path:
        """Standard location of the full county parcel roll."""
        return self.data_dir() / "roll.csv"

    def enriched_path(self) -> Path:
        return self.data_dir() / "enriched.csv"

    def recorder_path(self) -> Path:
        return self.data_dir() / "recorder_docs.csv"

    def auction_path(self) -> Path:
        return self.data_dir() / "auction_list.csv"


def list_counties() -> list[str]:
    if not COUNTIES_DIR.exists():
        return []
    return sorted(p.stem for p in COUNTIES_DIR.glob("*.yaml"))
