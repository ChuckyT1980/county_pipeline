"""
mpts_assessor.py — MPTS AssessorAdapter for NorCal counties.

Serves MegaByte Property Tax System (MPTS) assessor portals.
Used across ~40 California counties including Tehama, Shasta, Butte, Lassen, etc.

Endpoints (standard shape):
  AsrPrint: https://common1.mptsweb.com/mbap/{county}/asr/AsrPrint/{12_digit_apn}
  TaxBill:  https://apps.mptsweb.com/TaxBillv2/RollCatCS.aspx?CN={county}&Asmt={12_digit_apn}&TaxYear=2025&RollCat=CS&RollType=S

Registered under (SourceType.ASSESSOR, "mpts").
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

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


def _parse_float(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    cleaned = re.sub(r"[^\d.]", "", val)
    try:
        return float(cleaned) if cleaned else None
    except ValueError:
        return None


@register(SourceType.ASSESSOR, "mpts")
class MPTSAssessorAdapter(AssessorAdapter):
    parser_version = "2026.1-mpts-1"

    DEFAULT_HOST = "https://common1.mptsweb.com"

    @property
    def _host(self) -> str:
        param_host = self.config.params.get("mbap_host")
        if param_host:
            return param_host.rstrip("/")
        url = self.config.url or self.DEFAULT_HOST
        parsed = urlparse(url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return url.rstrip("/")

    @property
    def _slug(self) -> str:
        return self.config.params.get("mbap_slug") or self.county.lower()

    def fetch_by_apn(self, apn: str) -> AssessorResult:
        """Fetch AsrPrint record for given APN via MPTS portal."""
        apn_raw = apn.strip()
        apn_compact = re.sub(r"[^0-9]", "", apn_raw).zfill(12)

        self.gate(
            len(apn_compact) == 12,
            f"APN '{apn_raw}' must normalize to 12 digits for MPTS (got {len(apn_compact)})"
        )

        base_host = self._host.rstrip("/")
        url = f"{base_host}/mbap/{self._slug}/asr/AsrPrint/{apn_compact}"
        headers = {"Referer": f"{base_host}/mbap/{self._slug}/asr"}

        cap = self.capture(url, headers=headers)
        self.gate(
            cap.status == 200,
            f"MPTS AsrPrint returned HTTP {cap.status} for APN {apn_compact}"
        )

        soup = BeautifulSoup(cap.text, "html.parser")
        rows = soup.find_all("tr")

        data: dict[str, str] = {}
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True)
                value = cells[1].get_text(strip=True)
                if label and value:
                    data[label] = value

        self.gate(
            bool(data),
            f"MPTS AsrPrint page contained no property table data for APN {apn_compact}"
        )

        apn_norm = self.norm.apn(apn_raw)

        doc_number = data.get("Current Document Number")
        doc_date = data.get("Current Document Date") or data.get("Current Document  Date")
        property_type = data.get("Property Type")
        lot_acres = data.get("Lot Size(Acres)")
        situs_raw = data.get("SitusAddr")
        net_value_raw = data.get("Net Assessed Value")
        assessee_raw = (
            data.get("Assessee Name")
            or data.get("Owner Name")
            or data.get("Owner")
            or data.get("Assessee")
        )

        # Address normalization
        addr_dict = self.norm.address(situs_raw) if situs_raw else {}
        situs_norm = addr_dict.get("situs_norm") if addr_dict else None

        # Property canonical model
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
            use_code=property_type,
            lot_size=lot_acres,
        )
        if not situs_raw:
            prop.gap("missing_situs_address")
        if not property_type:
            prop.gap("missing_property_type")

        # Snapshot canonical model
        snapshot = AssessorSnapshot(
            county=self.county,
            source_url=cap.raw.source_url,
            source_file=cap.raw.file_path,
            raw_fetch_id=cap.raw.id,
            parser_version=self.parser_version,
            apn_norm=apn_norm,
            assessed_total=_parse_float(net_value_raw),
            last_sale_date=doc_date,
            last_sale_doc_number=doc_number,
        )
        if not net_value_raw:
            snapshot.gap("missing_assessed_value")

        # Owner canonical model
        owner = None
        if assessee_raw:
            name_norm, entity_type = self.norm.owner(assessee_raw)
            owner = Owner(
                county=self.county,
                source_url=cap.raw.source_url,
                source_file=cap.raw.file_path,
                raw_fetch_id=cap.raw.id,
                parser_version=self.parser_version,
                owner_name_raw=assessee_raw,
                owner_name_norm=name_norm,
                entity_type=entity_type,
            )
        else:
            snapshot.gap("missing_assessee_name")

        return AssessorResult(property=prop, snapshot=snapshot, assessee=owner)
