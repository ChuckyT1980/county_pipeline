"""
Environmental enrichment: FEMA flood zone + CalFire fire severity zone
per parcel. Requires geocoding situs_address to lat/lon first via Nominatim.

All three sources are plain JSON REST — no browser required.
Nominatim rate limits: 1 request/second, requires User-Agent.
FEMA + CalFire have no documented rate limits.
"""
import time
from dataclasses import dataclass
from typing import Optional

import requests

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
FEMA_NFHL_URL = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query"
# CalFire consolidated SRA + LRA FHSZ. Point queries return "Very High"/"High"/"Moderate"
# only where the parcel falls inside a mapped zone; unmapped means the parcel is in a
# non-fire-prone area, which is itself useful info.
CALFIRE_URL = "https://services1.arcgis.com/jUJYIo9tSA7EHvfZ/arcgis/rest/services/FHSZ_in_SRA_for_FHSZ_in_LRA/FeatureServer/0/query"

USER_AGENT = "county-pipeline/0.1 (chuckterrell740@gmail.com)"
TIMEOUT = 15
NOMINATIM_DELAY = 1.1  # be a good citizen — Nominatim TOS

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


@dataclass
class GeoResult:
    lat: float
    lon: float
    display_name: str


@dataclass
class FloodZoneResult:
    zone: Optional[str]           # "A", "AE", "X", "VE", None if not in a mapped area
    subtype: Optional[str]
    source: str = "fema_nfhl"


@dataclass
class FireZoneResult:
    zone: Optional[str]           # "Very High", "High", "Moderate", None
    responsibility_area: Optional[str]  # "SRA" (state) or "LRA" (local)
    source: str = "calfire_fhsz"


def _clean_situs(raw: str) -> str:
    """Butte situs strings often have double spaces and no comma before city.
    Convert '13329  AMBLESIDE DR  CONCOW' -> '13329 AMBLESIDE DR, CONCOW'."""
    if not raw:
        return raw
    # Collapse whitespace
    normalized = " ".join(str(raw).split())
    # Butte situs format: "<street#> <street_name> <STREET_TYPE> <CITY>"
    # Insert comma before last token (assumed city) if none present.
    if "," not in normalized:
        parts = normalized.rsplit(" ", 1)
        if len(parts) == 2:
            normalized = f"{parts[0]}, {parts[1]}"
    return normalized


def _geocode_nominatim(query: str) -> Optional[GeoResult]:
    try:
        resp = _session.get(
            NOMINATIM_URL,
            params={"q": query, "format": "json", "limit": 1, "countrycodes": "us"},
            timeout=TIMEOUT,
        )
        time.sleep(NOMINATIM_DELAY)
        if resp.status_code != 200:
            return None
        rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        return GeoResult(lat=float(row["lat"]), lon=float(row["lon"]), display_name=row.get("display_name", ""))
    except Exception:
        return None


def _geocode_census(address: str) -> Optional[GeoResult]:
    """US Census geocoder — free, generally better than Nominatim for rural US addresses."""
    try:
        resp = _session.get(
            CENSUS_GEOCODER_URL,
            params={"address": address, "benchmark": "Public_AR_Current", "format": "json"},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        matches = resp.json().get("result", {}).get("addressMatches", [])
        if not matches:
            return None
        m = matches[0]
        coords = m.get("coordinates", {})
        return GeoResult(
            lat=float(coords["y"]),
            lon=float(coords["x"]),
            display_name=m.get("matchedAddress", address),
        )
    except Exception:
        return None


def geocode(address: str, county: str = "Butte", state: str = "CA") -> Optional[GeoResult]:
    """Nominatim first; fall back to US Census geocoder (better for rural addresses)."""
    if not address:
        return None
    cleaned = _clean_situs(address)

    # Try Nominatim with county qualifier
    r = _geocode_nominatim(f"{cleaned}, {county} County, {state}, USA")
    if r:
        return r
    # Then without county
    r = _geocode_nominatim(f"{cleaned}, {state}, USA")
    if r:
        return r
    # Fall back to Census geocoder — much better for rural addresses
    r = _geocode_census(f"{cleaned}, {state}")
    if r:
        return r
    return None


def fema_flood_zone(lat: float, lon: float, retries: int = 2) -> Optional[FloodZoneResult]:
    """Point query against FEMA NFHL flood hazard layer with basic retry."""
    for attempt in range(retries + 1):
        try:
            resp = _session.get(
                FEMA_NFHL_URL,
                params={
                    "f": "json",
                    "geometry": f"{lon},{lat}",
                    "geometryType": "esriGeometryPoint",
                    "inSR": "4326",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "FLD_ZONE,ZONE_SUBTY",
                    "returnGeometry": "false",
                },
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            features = resp.json().get("features", [])
            if not features:
                # Point is not in any mapped flood zone — that's a real answer, treat as unmapped
                return FloodZoneResult(zone="UNMAPPED", subtype=None)
            attrs = features[0].get("attributes", {})
            return FloodZoneResult(
                zone=attrs.get("FLD_ZONE"),
                subtype=attrs.get("ZONE_SUBTY"),
            )
        except Exception as e:
            if attempt < retries:
                time.sleep(1.0 + attempt)  # small backoff
                continue
            print(f"  [fema] error at ({lat:.4f},{lon:.4f}): {type(e).__name__}: {e}")
            return None


def calfire_fire_zone(lat: float, lon: float) -> Optional[FireZoneResult]:
    """Point query against consolidated CalFire FHSZ (SRA + LRA)."""
    try:
        resp = _session.get(
            CALFIRE_URL,
            params={
                "f": "json",
                "geometry": f"{lon},{lat}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "FHSZ,FHSZ_Description,SRA22_2",
                "returnGeometry": "false",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if features:
            attrs = features[0].get("attributes", {})
            zone_desc = attrs.get("FHSZ_Description") or str(attrs.get("FHSZ") or "")
            return FireZoneResult(zone=zone_desc, responsibility_area=attrs.get("SRA22_2"))
        # Not in any mapped FHSZ zone — flat/urban/non-hazardous
        return FireZoneResult(zone="UNZONED", responsibility_area=None)
    except Exception as e:
        print(f"  [calfire] error at ({lat:.4f},{lon:.4f}): {type(e).__name__}: {e}")
        return None


def enrich_point(situs_address: str, county: str = "Butte") -> dict:
    """One-shot: geocode + FEMA + CalFire. Returns a dict of columns to add.
    All values may be None if geocoding failed."""
    geo = geocode(situs_address, county=county)
    if not geo:
        return {
            "geocode_lat": None, "geocode_lon": None,
            "flood_zone": None, "flood_zone_subtype": None,
            "fire_hazard_zone": None, "fire_responsibility_area": None,
        }
    flood = fema_flood_zone(geo.lat, geo.lon)
    fire = calfire_fire_zone(geo.lat, geo.lon)
    return {
        "geocode_lat": geo.lat, "geocode_lon": geo.lon,
        "flood_zone": flood.zone if flood else None,
        "flood_zone_subtype": flood.subtype if flood else None,
        "fire_hazard_zone": fire.zone if fire else None,
        "fire_responsibility_area": fire.responsibility_area if fire else None,
    }
