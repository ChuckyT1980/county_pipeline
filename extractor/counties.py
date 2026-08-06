"""
Per-county configuration for the unified CA parcel data extractor.

Based on systematic probe of 58 CA counties (see ca_county_probe_results.csv).
33 counties confirmed on MPTS platform — same tech as Butte.

Each county entry defines:
  mpts_host:      MPTS server hostname (common1 or common2)
  mpts_slug:      County slug used in MPTS URLs
  tax_year:       Current fiscal year (probed / verified per county)
  fips:           FIPS code (for federal cross-references)
  known_owner_in_html: bool - whether MPTS returns owner name in public HTML
  arcgis_endpoint: Optional - if county has verified public ArcGIS parcel service
  notes:          Any county-specific quirks or lacking data
"""

# 33 confirmed MPTS counties from probe
MPTS_COUNTIES = {
    "amador":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06005"},
    "butte":        {"mpts_host": "common2", "tax_year": 2025, "fips": "06007",
                     "notes": "REFERENCE IMPLEMENTATION. Recorder crawl proven (Tyler EagleWeb)."},
    "calaveras":    {"mpts_host": "common1", "tax_year": 2025, "fips": "06009"},
    "colusa":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06011"},
    "del norte":    {"mpts_host": "common1", "tax_year": 2025, "fips": "06015", "mpts_slug": "delnorte"},
    "el dorado":    {"mpts_host": "common1", "tax_year": 2025, "fips": "06017", "mpts_slug": "eldorado"},
    "glenn":        {"mpts_host": "common1", "tax_year": 2025, "fips": "06021"},
    "humboldt":     {"mpts_host": "common1", "tax_year": 2025, "fips": "06023",
                     "arcgis_endpoint": "https://gis.co.humboldt.ca.us/arcgis/rest/services"},
    "imperial":     {"mpts_host": "common1", "tax_year": 2025, "fips": "06025"},
    "kings":        {"mpts_host": "common1", "tax_year": 2025, "fips": "06031"},
    "lake":         {"mpts_host": "common1", "tax_year": 2025, "fips": "06033"},
    "madera":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06039"},
    "mariposa":     {"mpts_host": "common1", "tax_year": 2025, "fips": "06043"},
    "merced":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06047"},
    "modoc":        {"mpts_host": "common1", "tax_year": 2025, "fips": "06049"},
    "mono":         {"mpts_host": "common1", "tax_year": 2025, "fips": "06051"},
    "monterey":     {"mpts_host": "common1", "tax_year": 2025, "fips": "06053"},
    "napa":         {"mpts_host": "common1", "tax_year": 2025, "fips": "06055",
                     "arcgis_endpoint": "https://gis.napa.ca.gov/arcgis/rest/services"},
    "nevada":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06057"},
    "placer":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06061"},
    "plumas":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06063"},
    "san benito":   {"mpts_host": "common1", "tax_year": 2025, "fips": "06069", "mpts_slug": "sanbenito"},
    "san joaquin":  {"mpts_host": "common1", "tax_year": 2025, "fips": "06077", "mpts_slug": "sanjoaquin"},
    "shasta":       {"mpts_host": "common2", "tax_year": 2025, "fips": "06089"},
    "siskiyou":     {"mpts_host": "common1", "tax_year": 2025, "fips": "06093"},
    "sonoma":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06097",
                     "arcgis_endpoint": "https://gis.sonomacounty.ca.gov/arcgis/rest/services"},
    "stanislaus":   {"mpts_host": "common1", "tax_year": 2025, "fips": "06099"},
    "tehama":       {"mpts_host": "common1", "tax_year": 2026, "fips": "06103",
                     "known_owner_in_html": False,
                     "notes": "TaxYear=2026 required. Owner name REDACTED from public HTML."},
    "trinity":      {"mpts_host": "common1", "tax_year": 2025, "fips": "06105"},
    "tulare":       {"mpts_host": "common1", "tax_year": 2025, "fips": "06107"},
    "tuolumne":     {"mpts_host": "common1", "tax_year": 2025, "fips": "06109"},
    "yolo":         {"mpts_host": "common1", "tax_year": 2025, "fips": "06113"},
    "yuba":         {"mpts_host": "common1", "tax_year": 2025, "fips": "06115"},
}

# Non-MPTS counties confirmed accessible via ArcGIS or other means
ARCGIS_COUNTIES = {
    "fresno": {
        "arcgis_endpoint": "https://gisprod10.co.fresno.ca.us/server/rest/services/FC_PARCEL_SELECT/MapServer/0/query",
        "base_apn_endpoint": "https://gisprod10.co.fresno.ca.us/server/rest/services/REGIONAL_VIEWS/ASSESSOR_MAP_PAGES/MapServer/0/query",
        "returns_owner": True,
        "returns_situs": True,
        "returns_values": True,
        "apn_format": "compact_8_or_9",
        "suffix_fallback": ["S", "T", "U", "ST", "SU", "TS"],
        "notes": "Fully working. 315k parcels. Verified 100% hit rate with suffix fallback.",
    },
    "kern": {
        "arcgis_endpoint": "https://services5.arcgis.com/Y8jwjGUWbRjuqpG5/arcgis/rest/services/Assessor_Parcels_Land_2025/FeatureServer/0/query",
        "returns_owner": False,
        "returns_situs": False,
        "returns_values": False,
        "notes": "Only APN + geometry public. Rich data behind Akamai + CAPTCHA. Needs Playwright.",
    },
}

# Counties confirmed on Bid4Assets (for auction schedule + historical results)
BID4ASSETS_COUNTIES = [
    "alameda", "amador", "butte", "calaveras", "contra costa", "del norte",
    "el dorado", "fresno", "glenn", "humboldt", "imperial", "kings", "lake",
    "lassen", "los angeles", "madera", "merced", "modoc", "mono", "monterey",
    "napa", "nevada", "orange", "placer", "plumas", "riverside", "sacramento",
    "san diego", "san joaquin", "santa barbara", "santa clara", "santa cruz",
    "shasta", "sierra", "siskiyou", "sonoma", "stanislaus", "sutter", "tehama",
    "trinity", "tulare", "tuolumne", "ventura", "yolo", "yuba",
]

# Counties with no detected access — need custom investigation
NEEDS_INVESTIGATION = [
    "inyo", "riverside", "san bernardino", "san francisco", "san luis obispo",
    # Also others not fully probed for rich data:
    "alameda", "contra costa", "lassen", "los angeles", "marin", "mendocino",
    "orange", "sacramento", "san diego", "san mateo", "santa barbara",
    "santa clara", "santa cruz", "solano", "sutter", "ventura",
]


def get_county_config(county: str) -> dict:
    """Return unified config for any known county."""
    county = county.lower().strip()

    if county in MPTS_COUNTIES:
        cfg = MPTS_COUNTIES[county].copy()
        cfg["county"] = county
        cfg["platform"] = "mpts"
        cfg["mpts_slug"] = cfg.get("mpts_slug", county.replace(" ", ""))
        cfg["mpts_host"] = f"{cfg['mpts_host']}.mptsweb.com"
        cfg.setdefault("known_owner_in_html", True)  # default assumption; probe to verify
        return cfg

    if county in ARCGIS_COUNTIES:
        cfg = ARCGIS_COUNTIES[county].copy()
        cfg["county"] = county
        cfg["platform"] = "arcgis"
        return cfg

    raise ValueError(f"Unknown county: {county}. Not yet configured.")


def list_configured_counties() -> dict:
    """Return a summary of all configured counties by platform."""
    return {
        "mpts": sorted(MPTS_COUNTIES.keys()),
        "arcgis": sorted(ARCGIS_COUNTIES.keys()),
        "bid4assets_auction": sorted(BID4ASSETS_COUNTIES),
        "needs_investigation": sorted(NEEDS_INVESTIGATION),
    }
