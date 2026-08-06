"""
contracts.py — the port/adapter contract for the NorCal property-intelligence pipeline.

This is the "one language" every county gets translated into. Nothing downstream
(scoring, dossier export, excess-proceeds logic) ever touches a vendor's raw output;
it only ever sees the canonical models defined here. To onboard a county you write
(or reuse) one adapter per source type behind these abstract base classes, then add a
config block — you never modify the pipeline core.

Layering (matches BUILD_BRIEF):
    fetch (raw capture)  ->  parse (vendor-specific)  ->  normalize (canonical)  ->  store
The abstract methods below own parse; they MUST emit canonical records via the injected
Normalizers so that a Tyler field and a MegaByte field collapse into the same schema.

Engineering standards enforced here:
  * raw capture is mandatory  -> BaseAdapter.capture() writes raw + a RawFetch row BEFORE parse
  * no silent fallbacks       -> integrity_gate() raises; unknown mappings record a data_gap
  * versioned parsers         -> every adapter sets parser_version; bumps are visible per vendor

Requires: pydantic v2  (pip install pydantic)
"""
from __future__ import annotations

import abc
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import ClassVar, Optional, Protocol, Sequence, runtime_checkable

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class AdapterError(Exception):
    """Base for anything an adapter raises."""


class IntegrityError(AdapterError):
    """Raised by an integrity gate when parsed data fails an expected invariant.
    Never swallow this. A raised IntegrityError means 'this source changed or broke' —
    that is the signal, not an inconvenience to route around."""


def integrity_gate(condition: bool, message: str) -> None:
    """Assert an expected invariant during parsing. Use liberally.
    Example: integrity_gate(bool(apn), 'recorder row missing APN')."""
    if not condition:
        raise IntegrityError(message)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums (canonical vocabulary)
# --------------------------------------------------------------------------- #
class SourceType(str, Enum):
    RECORDER = "recorder"
    ASSESSOR = "assessor"
    TAX_COLLECTOR = "tax_collector"
    AUCTION = "auction"
    GIS = "gis"
    ENTITY = "entity"  # statewide (CA SOS)


class EventType(str, Enum):
    GRANT_DEED = "grant_deed"
    QUITCLAIM_DEED = "quitclaim_deed"
    DEED_OF_TRUST = "deed_of_trust"
    ASSIGNMENT_OF_DOT = "assignment_of_dot"
    SUBSTITUTION_OF_TRUSTEE = "substitution_of_trustee"
    NOTICE_OF_DEFAULT = "notice_of_default"
    NOTICE_OF_TRUSTEE_SALE = "notice_of_trustee_sale"
    RECONVEYANCE = "reconveyance"
    RELEASE = "release"
    LIEN = "lien"
    ABSTRACT_OF_JUDGMENT = "abstract_of_judgment"
    LIS_PENDENS = "lis_pendens"
    MECHANICS_LIEN = "mechanics_lien"
    TAX_LIEN = "tax_lien"
    AFFIDAVIT_OF_DEATH = "affidavit_of_death"
    PROBATE_FILING = "probate_filing"
    TAX_DEFAULT = "tax_default"
    TAX_SALE_COMPLETED = "tax_sale_completed"
    EXCESS_PROCEEDS_AVAILABLE = "excess_proceeds_available"
    # Fallback ONLY. Mapping a vendor label to UNKNOWN must also append a data_gap
    # like 'unmapped_doc_type:<raw label>'. Never let UNKNOWN pass silently.
    UNKNOWN = "unknown"


class EntityType(str, Enum):
    PERSON = "person"
    LLC = "llc"
    TRUST = "trust"
    CORP = "corp"
    GOV = "gov"
    UNKNOWN = "unknown"


class TaxStatusEnum(str, Enum):
    CURRENT = "current"
    DELINQUENT = "delinquent"
    DEFAULTED = "defaulted"
    INSTALLMENT_PLAN = "installment_plan"  # R&T §4217 — weaker distress
    REDEEMED = "redeemed"
    UNKNOWN = "unknown"


class ExcessStatus(str, Enum):
    AVAILABLE = "available"
    CLAIMED = "claimed"
    DISTRIBUTED = "distributed"
    EXPIRED = "expired"
    CONTESTED = "contested"


class ClaimantType(str, Enum):
    LIENHOLDER = "lienholder"
    FORMER_OWNER = "former_owner"
    HEIR = "heir"


class Reachability(str, Enum):
    KNOWN = "known"
    SKIP_TRACE_REQUIRED = "skip_trace_required"
    DECEASED_HEIRS = "deceased_heirs"


class SalePriceConfidence(str, Enum):
    ASSESSOR_PROXY = "assessor_proxy"
    RECORDER_VERIFIED = "recorder_verified"
    PARCELQUEST = "parcelquest"
    NO_DEED_UNKNOWN = "no_deed_unknown"


class MarketEstimateSource(str, Enum):
    COMPS = "comps"
    AVM = "avm"
    APPRECIATION_FACTOR = "appreciation_factor"
    NONE = "none"


class EquityBand(str, Enum):
    NEGATIVE = "negative"
    THIN = "thin"
    MODERATE = "moderate"
    HIGH = "high"
    TENURE_SHORT = "tenure_short"
    TENURE_MID = "tenure_mid"
    TENURE_LONG = "tenure_long"
    UNKNOWN = "unknown"


class EquityConfidence(str, Enum):
    MEASURED = "measured"
    TENURE_PROXY = "tenure_proxy"
    UNKNOWN = "unknown"



# --------------------------------------------------------------------------- #
# Provenance — every canonical record carries where it came from + its gaps
# --------------------------------------------------------------------------- #
class Provenance(BaseModel):
    county: str
    source_url: Optional[str] = None
    source_file: Optional[str] = None          # path under data/raw/...
    raw_fetch_id: Optional[int] = None
    parser_version: Optional[str] = None
    ingested_at: datetime = Field(default_factory=_utcnow)
    # First-class, queryable gaps. A missing owner name is a data_gap, never a
    # fabricated placeholder and never a silent blank. Downstream scoring DEMOTES
    # records with gaps rather than being surprised by them.
    data_gaps: list[str] = Field(default_factory=list)

    def gap(self, note: str) -> None:
        if note not in self.data_gaps:
            self.data_gaps.append(note)


# --------------------------------------------------------------------------- #
# Raw capture record (written before any parsing happens)
# --------------------------------------------------------------------------- #
class RawFetch(BaseModel):
    id: Optional[int] = None
    county: str
    source: SourceType
    source_url: Optional[str] = None
    http_status: Optional[int] = None
    content_hash: Optional[str] = None         # sha256 of body -> dedupe + integrity
    file_path: Optional[str] = None
    fetched_at: datetime = Field(default_factory=_utcnow)
    parser_version: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Captured:
    """What BaseAdapter.capture() returns: the persisted RawFetch plus the live
    response, so parse() can read the body without a second fetch or a disk round-trip."""
    raw: RawFetch
    status: int
    text: str
    content: bytes


# --------------------------------------------------------------------------- #
# Canonical domain models (adapter outputs)
# --------------------------------------------------------------------------- #
class Owner(Provenance):
    owner_name_raw: Optional[str] = None
    owner_name_norm: Optional[str] = None
    entity_type: EntityType = EntityType.UNKNOWN
    mailing_raw: Optional[str] = None
    mailing_norm: Optional[str] = None
    mailing_out_of_county: Optional[bool] = None
    mailing_out_of_state: Optional[bool] = None
    sos_entity_id: Optional[str] = None        # set once resolved via EntityAdapter


class Property(Provenance):
    apn_raw: Optional[str] = None
    apn_norm: str                              # canonical key: (county, apn_norm)
    situs_raw: Optional[str] = None
    situs_norm: Optional[str] = None
    use_code: Optional[str] = None
    year_built: Optional[int] = None
    lot_size: Optional[str] = None
    beds: Optional[float] = None
    baths: Optional[float] = None


class AssessorSnapshot(Provenance):
    apn_norm: str
    capture_date: datetime = Field(default_factory=_utcnow)
    assessed_land: Optional[float] = None
    assessed_improve: Optional[float] = None
    assessed_total: Optional[float] = None
    base_year_value: Optional[float] = None    # Prop 13 — biggest hidden-equity tell
    last_sale_date: Optional[str] = None
    last_sale_doc_number: Optional[str] = None
    last_sale_price: Optional[float] = None
    exemptions: Optional[str] = None
    tax_rate_area: Optional[str] = None


class SalesEquityValuation(Provenance):
    """Canonical model for sale price resolution and equity feature calculation."""
    apn_norm: str
    sale_price_proxy_assessor: Optional[float] = None
    base_year_value: Optional[float] = None
    last_sale_date: Optional[str] = None
    last_sale_price_recorded: Optional[float] = None
    sale_price_final: Optional[float] = None
    sale_price_confidence: SalePriceConfidence = SalePriceConfidence.NO_DEED_UNKNOWN
    tenure_years: Optional[float] = None
    market_estimate: Optional[float] = None
    market_estimate_source: MarketEstimateSource = MarketEstimateSource.NONE
    equity_estimate: Optional[float] = None
    equity_band: EquityBand = EquityBand.UNKNOWN
    equity_confidence: EquityConfidence = EquityConfidence.UNKNOWN
    excess_proceeds_candidate: bool = False



class Event(Provenance):
    """Unified recorder / tax / auction event. Direction matters:
    grantor = FROM (exit signal), grantee = TO (acquisition)."""
    apn_raw: Optional[str] = None
    apn_norm: Optional[str] = None
    event_type: EventType
    event_date: Optional[str] = None
    recording_date: Optional[str] = None
    document_number: Optional[str] = None
    grantor_raw: Optional[str] = None
    grantee_raw: Optional[str] = None
    owner_name_raw: Optional[str] = None
    owner_name_norm: Optional[str] = None
    situs_raw: Optional[str] = None
    mailing_raw: Optional[str] = None
    amount: Optional[float] = None             # loan / lien / tax due / sale price
    transfer_tax: Optional[float] = None       # CA doc transfer tax -> back out price


class TaxRecord(Provenance):
    apn_norm: str
    status: TaxStatusEnum = TaxStatusEnum.UNKNOWN
    amount_due: Optional[float] = None
    default_year: Optional[int] = None
    years_delinquent: Optional[int] = None
    on_installment_plan: Optional[bool] = None


class DefaultedParcel(Provenance):
    """One row from a tax-defaulted / power-to-sell publication."""
    apn_norm: str
    default_year: Optional[int] = None
    amount_due: Optional[float] = None
    minimum_bid: Optional[float] = None
    redeemed: Optional[bool] = None            # late redemption after publication = the catch


class AuctionListing(Provenance):
    """A parcel offered in an upcoming/active sale."""
    apn_norm: str
    sale_id: Optional[str] = None
    sale_start: Optional[str] = None
    sale_end: Optional[str] = None
    minimum_bid: Optional[float] = None
    platform: Optional[str] = None             # bid4assets | govease | realauction | in_person


class AuctionResult(Provenance):
    """Outcome of a completed sale — the trigger for the excess-proceeds channel."""
    apn_norm: str
    sale_id: Optional[str] = None
    sale_date: Optional[str] = None
    sold: bool = False                         # False = redeemed/pulled/no-sale
    sale_price: Optional[float] = None
    winning_bidder: Optional[str] = None


class ExcessProceeds(Provenance):
    apn_norm: str
    sale_date: Optional[str] = None
    tax_deed_recording_date: Optional[str] = None   # starts the 1-year §4675 clock
    claim_deadline: Optional[str] = None            # recording_date + 1 year
    sale_price: Optional[float] = None
    taxes_and_costs: Optional[float] = None
    excess_amount: Optional[float] = None           # meaningful only if > $150 (§4676)
    county_notice_seen: Optional[bool] = None
    status: ExcessStatus = ExcessStatus.AVAILABLE


class Claimant(Provenance):
    """Party of interest, priority-ordered per R&T §4675(e):
    lienholders of record first (in their priority), then former title holder."""
    claimant_name_raw: Optional[str] = None
    claimant_type: ClaimantType = ClaimantType.FORMER_OWNER
    interest_type: Optional[str] = None        # deed_of_trust | judgment | tax_lien | title
    priority_rank: Optional[int] = None
    recording_date: Optional[str] = None       # establishes lien priority
    reachable: Reachability = Reachability.SKIP_TRACE_REQUIRED


class BusinessEntity(Provenance):
    """CA Secretary of State match for an LLC/trust/corp owner."""
    name_raw: Optional[str] = None
    sos_entity_id: Optional[str] = None
    entity_type: EntityType = EntityType.UNKNOWN
    status: Optional[str] = None
    agent_name: Optional[str] = None
    agent_address: Optional[str] = None


class ParcelGeometry(Provenance):
    """GIS attributes + geometry for a parcel (ArcGIS REST feature, typically)."""
    apn_norm: str
    geometry_geojson: Optional[dict] = None
    acreage: Optional[float] = None
    zoning: Optional[str] = None
    flood_zone: Optional[str] = None
    fire_hazard_zone: Optional[str] = None


class AssessorResult(BaseModel):
    """Assessor pull returns three linked pieces; keep them together."""
    property: Property
    snapshot: AssessorSnapshot
    assessee: Optional[Owner] = None


# --------------------------------------------------------------------------- #
# Config models (mirror counties.yaml)
# --------------------------------------------------------------------------- #
class SourceConfig(BaseModel):
    vendor: str                                # registry key, e.g. 'tyler', 'megabyte'
    url: str = ""
    method: str = ""                           # 'arcgis' | 'html' | 'pdf' | ...
    parser_version: str = "1.0"
    auth: str = ""                             # name of env var, never the secret itself
    params: dict = Field(default_factory=dict) # e.g. {'CN': 'tehama', 'DEPT': 'Asr'}


class CountyConfig(BaseModel):
    key: str                                   # 'butte', 'tehama'
    display_name: str
    apn_format: Optional[str] = None
    tax_deed_recording_lag_days: int = 30      # feeds excess claim_deadline
    sources: dict[SourceType, SourceConfig] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Injected collaborators (the adapter never news-up its own IO)
# --------------------------------------------------------------------------- #
@runtime_checkable
class HttpClient(Protocol):
    def get(self, url: str, **kw) -> "HttpResponse": ...
    def post(self, url: str, **kw) -> "HttpResponse": ...


@runtime_checkable
class HttpResponse(Protocol):
    status_code: int
    content: bytes
    text: str


@runtime_checkable
class RawStore(Protocol):
    """Persists raw bytes to disk and records a RawFetch row. Returns the saved RawFetch
    (with id + file_path populated)."""
    def save(self, raw: RawFetch, body: bytes) -> RawFetch: ...


@runtime_checkable
class Normalizers(Protocol):
    """The single chokepoint where every vendor's dialect becomes canonical.
    This is where unification actually happens — see the architecture diagram."""
    def apn(self, raw: str) -> str: ...
    def address(self, raw: str) -> dict: ...                     # {situs_norm, out_of_county,...}
    def owner(self, raw: str) -> tuple[str, EntityType]: ...     # (name_norm, entity_type)
    def event_type(self, vendor_label: str) -> EventType: ...    # maps to enum; UNKNOWN -> caller gaps it


# --------------------------------------------------------------------------- #
# Base adapter — owns raw capture + integrity, common to every vendor
# --------------------------------------------------------------------------- #
class BaseAdapter(abc.ABC):
    source_type: ClassVar[SourceType]
    vendor: ClassVar[str]
    parser_version: ClassVar[str] = "1.0"

    def __init__(
        self,
        county: str,
        config: SourceConfig,
        http: HttpClient,
        store: RawStore,
        norm: Normalizers,
    ) -> None:
        self.county = county
        self.config = config
        self.http = http
        self.store = store
        self.norm = norm

    # ---- raw capture (concrete, shared, mandatory) ----------------------- #
    def capture(self, url: str, *, method: str = "GET", **kw) -> Captured:
        """Fetch, hash, persist raw bytes, and record a RawFetch BEFORE parsing.
        Every adapter routes its network IO through here. No exceptions.
        Returns Captured(raw, status, text, content) so parse() has the body in hand."""
        resp = (self.http.post if method.upper() == "POST" else self.http.get)(url, **kw)
        body = resp.content or b""
        raw = RawFetch(
            county=self.county,
            source=self.source_type,
            source_url=url,
            http_status=resp.status_code,
            content_hash=hashlib.sha256(body).hexdigest(),
            parser_version=self.parser_version,
        )
        saved = self.store.save(raw, body)
        return Captured(raw=saved, status=resp.status_code, text=resp.text, content=body)

    def gate(self, condition: bool, message: str) -> None:
        integrity_gate(condition, f"[{self.county}/{self.vendor}] {message}")


# --------------------------------------------------------------------------- #
# Per-source ABCs (the ports). Concrete vendor adapters implement these.
# --------------------------------------------------------------------------- #
class RecorderAdapter(BaseAdapter):
    source_type = SourceType.RECORDER

    @abc.abstractmethod
    def search_by_apn(self, apn: str) -> Sequence[Event]: ...

    @abc.abstractmethod
    def search_by_name(self, name: str) -> Sequence[Event]: ...

    @abc.abstractmethod
    def search_by_date_range(self, start: str, end: str,
                             doc_types: Optional[Sequence[EventType]] = None) -> Sequence[Event]: ...


class AssessorAdapter(BaseAdapter):
    source_type = SourceType.ASSESSOR

    @abc.abstractmethod
    def fetch_by_apn(self, apn: str) -> AssessorResult: ...


class TaxCollectorAdapter(BaseAdapter):
    source_type = SourceType.TAX_COLLECTOR

    @abc.abstractmethod
    def fetch_status(self, apn: str) -> TaxRecord: ...

    @abc.abstractmethod
    def fetch_defaulted_list(self) -> Sequence[DefaultedParcel]: ...


class AuctionAdapter(BaseAdapter):
    source_type = SourceType.AUCTION

    @abc.abstractmethod
    def fetch_schedule(self) -> Sequence[AuctionListing]: ...

    @abc.abstractmethod
    def fetch_results(self, sale_id: Optional[str] = None) -> Sequence[AuctionResult]: ...


class GISAdapter(BaseAdapter):
    source_type = SourceType.GIS

    @abc.abstractmethod
    def fetch_parcel(self, apn: str) -> ParcelGeometry: ...


class EntityAdapter(BaseAdapter):
    """Statewide (CA SOS). One implementation serves all counties."""
    source_type = SourceType.ENTITY

    @abc.abstractmethod
    def lookup(self, name: str) -> Sequence[BusinessEntity]: ...


# --------------------------------------------------------------------------- #
# Registry — maps (source_type, vendor) -> concrete adapter class
# --------------------------------------------------------------------------- #
ADAPTER_REGISTRY: dict[tuple[SourceType, str], type[BaseAdapter]] = {}


def register(source_type: SourceType, vendor: str):
    """Decorator each concrete adapter uses to make itself discoverable by config."""
    def _deco(cls: type[BaseAdapter]) -> type[BaseAdapter]:
        cls.source_type = source_type
        cls.vendor = vendor
        ADAPTER_REGISTRY[(source_type, vendor)] = cls
        return cls
    return _deco


def build_adapters_for_county(
    cfg: CountyConfig,
    http: HttpClient,
    store: RawStore,
    norm: Normalizers,
    ignore_missing: bool = True,
) -> dict[SourceType, BaseAdapter]:
    """Instantiate every configured source for a county from the registry.
    Adding a county whose vendors are all registered = pure config, no new code."""
    built: dict[SourceType, BaseAdapter] = {}
    for source_type, sc in cfg.sources.items():
        key = (source_type, sc.vendor)
        adapter_cls = ADAPTER_REGISTRY.get(key)
        if adapter_cls is None:
            if ignore_missing:
                continue
            raise AdapterError(
                f"no adapter registered for {source_type.value}/{sc.vendor} "
                f"(county={cfg.key}). Write one against the matching ABC and @register it."
            )
        adapter = adapter_cls(cfg.key, sc, http, store, norm)
        adapter.parser_version = sc.parser_version
        built[source_type] = adapter
    return built
# --------------------------------------------------------------------------- #
# Concrete adapters live in their own modules and @register themselves, e.g.
# tehama_recorder_tyler.py -> @register(SourceType.RECORDER, "tyler").
# Import them once at startup so the registry is populated before
# build_adapters_for_county() runs.
# --------------------------------------------------------------------------- #
