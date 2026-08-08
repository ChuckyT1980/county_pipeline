"""
California statewide parcel foundation - canonical Property model.

Built because Kern's pipeline was found (2026-08-08) silently conflating
two genuinely different identifiers into one "apn" field: the ATN
(Assessment/Tax Number, e.g. "017-490-06-00-3" - the 5-segment form
used on Kern's tax-default/auction lists) and the assessor's own parcel
number (a shorter form, e.g. "017-490-06"). kern/kern_enrich_docnum_verified.py
normalized both through the same digits-only comparison and displayed
whichever matched as "**APN**" in every dossier - correct-looking, but
wrong: an ATN is not an APN, even though Kern's own assessor search
form happens to accept both.

This module does NOT change any existing Kern/Butte output. It defines
the target model that county-specific data will be migrated INTO, one
county at a time, only after being tested against real records.

Do not add a field here "just in case." Every field exists because a
real county source distinguishes it, or a real bug (see above) required
separating two things that had been merged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class IdentifierType(str, Enum):
    """
    Every value here corresponds to a real, distinct identifier a CA
    county source can produce. Do not collapse two of these into one
    just because a given county's data happens to make them look similar
    - that collapsing is the exact bug this model exists to prevent.
    """
    ATN = "atn"  # Assessment/Tax Number - the tax roll's own identifier, may differ from the assessor's APN (confirmed distinct for Kern)
    ASSESSOR_PARCEL_NUMBER = "assessor_parcel_number"  # the assessor's own parcel number, as the assessor's office prints it
    PRIOR_APN = "prior_apn"  # a parcel's earlier APN before a lot split/merge/re-numbering
    RECORDER_DOCUMENT_NUMBER = "recorder_document_number"  # a specific recorded instrument's document number (deed, notice, etc.) - NOT a parcel identifier itself, but the evidence tying a parcel to a recorder event
    COUNTY_FIPS = "county_fips"  # 3-digit FIPS county code, part of forming ca_property_id but tracked as its own identifier for provenance


class ConfidenceLevel(str, Enum):
    CONFIRMED = "confirmed"  # directly read from a live official source this run
    CARRIED_FORWARD = "carried_forward"  # seen on a prior run, not re-verified this run
    SOURCE_LIST_ONLY = "source_list_only"  # present on a source list (e.g. a historical CSV) but never independently verified against a live official source
    UNCONFIRMED = "unconfirmed"  # present but contradicted or not yet checked


class AdapterStatus(str, Enum):
    NOT_STARTED = "not_started"
    RECORDER_PROBE_ONLY = "recorder_probe_only"  # recorder capability tested, nothing else built yet
    PARTIAL = "partial"  # some but not all of assessor/recorder/tax-default/auction chain working
    BOTH_SITES_VERIFIED = "both_sites_verified"  # full Butte/Kern-style chain proven, matches the reference pipeline standard
    BLOCKED = "blocked"  # a hard blocker (CAPTCHA, Cloudflare, legal restriction) stops further automation


@dataclass
class Property:
    """
    One row per real California parcel. This is the durable anchor every
    identifier, event, and dossier ultimately points back to - it should
    almost never change once assigned; ATNs, APNs, and owners all change
    over a parcel's life, but ca_property_id should not.
    """
    ca_property_id: str  # format: CA-{county_fips}-{primary_identifier_digits}-{disambiguator} - e.g. "CA-029-425-182-05-2"
    county_fips: str  # 3-digit FIPS code, e.g. "029" for Kern
    county_name: str  # e.g. "Kern"
    baseline_source: str  # the specific source (URL, file, or dataset name) that first established this property record
    baseline_snapshot_date: date  # date the baseline_source data was captured
    geometry_or_map_reference: str | None = None  # parcel map book/page, GIS feature ID, or similar - None if not yet sourced, never guessed


@dataclass
class PropertyIdentifier:
    """
    One row per (property, identifier type, source) - a property can and
    usually will have MULTIPLE rows here (an ATN from the tax roll, a
    separate assessor_parcel_number from the assessor's own page, maybe
    a prior_apn from before a lot split). Never merge these into a single
    field on Property itself - that merging is exactly what caused the
    Kern ATN/APN bug.
    """
    ca_property_id: str
    identifier_type: IdentifierType
    identifier_value: str
    source: str  # e.g. "assessorapps.kerncounty.com live page", "kern_REAL_AUCTION_PARCELS_CLEAN.csv (historical snapshot)"
    first_seen_date: date
    last_seen_date: date
    confidence: ConfidenceLevel


@dataclass
class CountySourceConfig:
    """
    One per county. Declares WHERE a county's real sources live and what
    state its adapter is in - does not itself fetch anything. Read
    config/counties/*.yaml into instances of this via a small loader
    (see load_county_config() below) rather than hand-constructing these
    in code, so the source-of-truth stays the YAML file.
    """
    county_name: str
    county_fips: str
    assessor_url: str | None
    recorder_url: str | None
    gis_url: str | None
    tax_default_source: str | None  # the real source of a tax-default/delinquency signal, if one is separately available from the auction list
    auction_source: str | None  # the real, current auction/tax-sale list source - NOT the same as tax_default_source; a parcel can be tax-default without yet being on a confirmed auction list, or vice versa if redeemed after listing
    identifier_rules: dict[str, str] = field(default_factory=dict)  # e.g. {"atn_format": "###-###-##-00-#", "apn_format": "###-###-##"} - documents each county's real identifier formats so they're never assumed to match another county's
    refresh_cadence: str = "unknown"  # how often this county's source data realistically changes - informs how stale carried_forward confidence should be treated
    adapter_status: AdapterStatus = AdapterStatus.NOT_STARTED


def load_county_config(path: str) -> CountySourceConfig:
    """Load a config/counties/*.yaml file into a CountySourceConfig. Requires pyyaml."""
    import yaml
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    raw = dict(raw)
    if "adapter_status" in raw:
        raw["adapter_status"] = AdapterStatus(raw["adapter_status"])
    return CountySourceConfig(**raw)


def make_ca_property_id(county_fips: str, primary_identifier_digits: str, disambiguator: str = "1") -> str:
    """
    Build a ca_property_id. primary_identifier_digits should be the
    assessor_parcel_number's digits (not the ATN) wherever an
    assessor_parcel_number is known - the ATN's extra trailing segment
    (e.g. Kern's "-00-9") is county-tax-system bookkeeping, not part of
    the parcel's durable identity, so it is deliberately excluded here.
    """
    digits = primary_identifier_digits.replace("-", "")
    return f"CA-{county_fips}-{digits}-{disambiguator}"
