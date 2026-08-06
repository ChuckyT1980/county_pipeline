"""
county_config_loader.py — loader mapping counties/*.yaml into CountyConfig domain models.

Reads county definition YAML files and instantiates canonical CountyConfig
and SourceConfig objects compatible with contracts.build_adapters_for_county().
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml

from contracts import CountyConfig, SourceConfig, SourceType


COUNTIES_DIR = Path(__file__).resolve().parent / "counties"

_SOURCE_KEY_MAP = {
    "assessor": SourceType.ASSESSOR,
    "recorder": SourceType.RECORDER,
    "auction": SourceType.AUCTION,
    "tax_collector": SourceType.TAX_COLLECTOR,
    "gis": SourceType.GIS,
    "entity": SourceType.ENTITY,
}


def load_county_config(county_key: str, dir_path: Optional[Path] = None) -> CountyConfig:
    """Load and parse a county YAML file by county key (e.g. 'tehama', 'shasta', 'butte')."""
    base_dir = dir_path or COUNTIES_DIR
    clean_key = county_key.lower().strip()
    yaml_path = base_dir / f"{clean_key}.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(f"County config file not found: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as fh:
        raw_data = yaml.safe_load(fh) or {}

    sources: dict[SourceType, SourceConfig] = {}

    for section_name, source_type in _SOURCE_KEY_MAP.items():
        sec = raw_data.get(section_name)
        if not sec or not isinstance(sec, dict):
            continue

        vendor = str(sec.get("backend") or sec.get("vendor") or "").strip()
        if not vendor:
            continue

        url = str(sec.get("base_url") or sec.get("endpoint") or sec.get("url") or "").strip()
        method = str(sec.get("method") or "").strip()
        parser_version = str(sec.get("parser_version") or "1.0").strip()
        auth = str(sec.get("auth") or "").strip()

        # Extract remaining fields as parameters
        reserved = {"backend", "vendor", "base_url", "endpoint", "url", "method", "parser_version", "auth"}
        params = {k: v for k, v in sec.items() if k not in reserved}

        sources[source_type] = SourceConfig(
            vendor=vendor,
            url=url,
            method=method,
            parser_version=parser_version,
            auth=auth,
            params=params,
        )

    return CountyConfig(
        key=clean_key,
        display_name=raw_data.get("display_name", f"{clean_key.capitalize()} County"),
        apn_format=raw_data.get("apn_format"),
        tax_deed_recording_lag_days=raw_data.get("tax_deed_recording_lag_days", 30),
        sources=sources,
    )


def list_available_counties(dir_path: Optional[Path] = None) -> list[str]:
    """Return list of available county keys in counties/ directory."""
    base_dir = dir_path or COUNTIES_DIR
    if not base_dir.exists():
        return []
    return [p.stem for p in sorted(base_dir.glob("*.yaml"))]
