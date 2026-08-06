"""
arcgis_assessor.py — ArcGIS REST AssessorAdapter for NorCal counties.

Serves counties using ArcGIS REST services for parcel / situs data.
Used across Shasta, Fresno, Mendocino, Solano, Sonoma, Placer, etc.

Endpoint shape:
  https://gis.shastacounty.gov/arcgis/rest/services/OpenData/ParcelSitusAddress/MapServer/0/query

Registered under (SourceType.ASSESSOR, "arcgis").
"""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib.parse import urlparse

from contracts import (
    AssessorAdapter,
    AssessorResult,
    AssessorSnapshot,
    Captured,
    EntityType,
    Owner,
    Property,
    SourceType,
    register,
)


def _parse_float(val: Optional[str | float | int]) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (float, int)):
        return float(val)
    cleaned = re.sub(r"[^\d.]", "", str(val))
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


@register(SourceType.ASSESSOR, "arcgis")
class ArcGISAssessorAdapter(AssessorAdapter):
    parser_version = "2026.1-arcgis-1"

    @property
    def _endpoint(self) -> str:
        return self.config.url or self.config.params.get("endpoint", "")

    @property
    def _apn_field(self) -> str:
        return self.config.params.get("apn_field", "ASMT")

    def fetch_by_apn(self, apn: str) -> AssessorResult:
        """Fetch parcel metadata for given APN via ArcGIS REST query endpoint."""
        apn_raw = apn.strip()
        apn_norm = self.norm.apn(apn_raw)
        apn_field = self._apn_field

        self.gate(bool(self._endpoint), f"ArcGIS assessor endpoint not configured for {self.county}")

        # Query parameters: search exact raw or norm APN
        where_clause = f"{apn_field} = '{apn_raw}' OR {apn_field} = '{apn_norm}'"
        params = {
            "where": where_clause,
            "outFields": "*",
            "f": "json",
            "returnGeometry": "false",
        }

        cap = self.capture(self._endpoint, params=params)
        self.gate(cap.status == 200, f"ArcGIS REST returned HTTP {cap.status} for APN {apn_raw}")

        try:
            data = json.loads(cap.text)
        except json.JSONDecodeError as exc:
            self.gate(False, f"ArcGIS REST response was not valid JSON: {exc}")

        features = data.get("features", [])
        if not features:
            # Fallback: try LIKE search if exact match returned 0 features
            params["where"] = f"{apn_field} LIKE '%{apn_norm}%'"
            cap = self.capture(self._endpoint, params=params)
            data = json.loads(cap.text) if cap.status == 200 else {}
            features = data.get("features", [])

        self.gate(bool(features), f"ArcGIS query returned 0 features for APN {apn_raw}")

        attrs = features[0].get("attributes", {})

        # Flexible attribute lookup
        situs_raw = (
            attrs.get("Situs_Address")
            or attrs.get("SITUS_ADDRESS")
            or attrs.get("SITUS")
            or attrs.get("SITE_ADDRESS")
            or attrs.get("PROPERTY_ADDRESS")
        )
        owner_raw = (
            attrs.get("OWNER_NAME")
            or attrs.get("OWNER")
            or attrs.get("ASSESSEE")
            or attrs.get("Assessee")
        )
        use_code = (
            attrs.get("USE_CODE")
            or attrs.get("ZONING")
            or attrs.get("PROP_TYPE")
            or attrs.get("PROPERTY_TYPE")
        )
        acres = (
            attrs.get("ACRES")
            or attrs.get("ACREAGE")
            or attrs.get("LOT_SIZE")
        )
        assessed_total = (
            attrs.get("NET_VALUE")
            or attrs.get("TOTAL_VALUE")
            or attrs.get("ASSESSED_VALUE")
        )

        addr_dict = self.norm.address(situs_raw) if situs_raw else {}
        situs_norm = addr_dict.get("situs_norm") if addr_dict else None

        prop = Property(
            county=self.county,
            source_url=cap.raw.source_url,
            source_file=cap.raw.file_path,
            raw_fetch_id=cap.raw.id,
            parser_version=self.parser_version,
            apn_raw=apn_raw,
            apn_norm=apn_norm,
            situs_raw=situs_raw,
            situs_norm=situs_norm,
            use_code=str(use_code) if use_code else None,
            lot_size=str(acres) if acres is not None else None,
        )
        if not situs_raw:
            prop.gap("missing_situs_address")

        snapshot = AssessorSnapshot(
            county=self.county,
            source_url=cap.raw.source_url,
            source_file=cap.raw.file_path,
            raw_fetch_id=cap.raw.id,
            parser_version=self.parser_version,
            apn_norm=apn_norm,
            assessed_total=_parse_float(assessed_total),
        )

        owner = None
        if owner_raw:
            name_norm, entity_type = self.norm.owner(str(owner_raw))
            owner = Owner(
                county=self.county,
                source_url=cap.raw.source_url,
                source_file=cap.raw.file_path,
                raw_fetch_id=cap.raw.id,
                parser_version=self.parser_version,
                owner_name_raw=str(owner_raw),
                owner_name_norm=name_norm,
                entity_type=entity_type,
            )

        return AssessorResult(property=prop, snapshot=snapshot, assessee=owner)
