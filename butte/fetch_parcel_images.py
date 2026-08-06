"""
Fetch satellite images for parcels using Esri World Imagery (free, no API key).

Attribution required per Esri terms: "Source: Esri, Maxar, Earthstar Geographics"
This attribution is embedded in the dossier PDF footer.

Usage:
    fetch(apn, lat, lon)  -> returns local PNG path
"""
import math
import os
from pathlib import Path

import requests

BUTTE_DIR = os.path.dirname(os.path.abspath(__file__))
IMG_DIR = os.path.join(BUTTE_DIR, "parcel_images")

# Esri World Imagery service - public, no auth required for reasonable use
ESRI_ENDPOINT = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/export"
)


def _bbox_from_center(lat: float, lon: float, radius_m: float = 90.0) -> tuple:
    """Compute a WGS84 bounding box in Web Mercator meters centered on lat/lon.

    radius_m = 90 gives roughly a 180m x 180m tile which is one residential
    lot at close-up zoom.
    """
    # Convert lat/lon to Web Mercator meters (EPSG:3857)
    R = 6378137.0
    x = lon * math.pi / 180.0 * R
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * R
    return (x - radius_m, y - radius_m, x + radius_m, y + radius_m)


def fetch(apn: str, lat: float, lon: float, size: int = 480,
          radius_m: float = 90.0, force: bool = False) -> str | None:
    """Fetch a satellite image for the parcel; return local file path or None."""
    if lat is None or lon is None:
        return None
    try:
        lat = float(lat); lon = float(lon)
    except (TypeError, ValueError):
        return None

    Path(IMG_DIR).mkdir(parents=True, exist_ok=True)
    safe_apn = apn.replace("/", "_")
    out_path = os.path.join(IMG_DIR, f"{safe_apn}_sat.png")

    if os.path.exists(out_path) and not force:
        return out_path

    x_min, y_min, x_max, y_max = _bbox_from_center(lat, lon, radius_m)
    params = {
        "bbox": f"{x_min},{y_min},{x_max},{y_max}",
        "bboxSR": "3857",
        "imageSR": "3857",
        "size": f"{size},{size}",
        "format": "png",
        "f": "image",
    }
    try:
        r = requests.get(ESRI_ENDPOINT, params=params, timeout=20,
                         headers={"User-Agent": "LogicFlowSystems/1.0 (mrt@logicflowsystems.io)"})
        r.raise_for_status()
        if not r.content.startswith(b"\x89PNG"):
            print(f"  WARN: {apn} response was not a PNG ({len(r.content)} bytes)")
            return None
        with open(out_path, "wb") as f:
            f.write(r.content)
        return out_path
    except requests.RequestException as e:
        print(f"  ERROR fetching {apn}: {e}")
        return None


def fetch_batch(records: list, radius_m: float = 90.0, force: bool = False) -> dict:
    """records = list of dicts with keys: apn, lat, lon.
    Returns dict {apn: path_or_None}.
    """
    out = {}
    for i, r in enumerate(records, 1):
        p = fetch(r["apn"], r.get("lat"), r.get("lon"), radius_m=radius_m, force=force)
        out[r["apn"]] = p
        status = "ok" if p else "skipped"
        print(f"  [{i}/{len(records)}] {r['apn']}  {status}")
    return out


if __name__ == "__main__":
    import pandas as pd
    df = pd.read_csv(os.path.join(BUTTE_DIR, "butte_SCORED_AUCTION_MATCHES_CALL_SHEET.csv"),
                     dtype=str)
    target = ["035-143-011-000", "069-190-021-000", "035-083-006-000"]
    recs = []
    for apn in target:
        row = df[df["apn"] == apn].iloc[0]
        recs.append({"apn": apn, "lat": row.get("geocode_lat"), "lon": row.get("geocode_lon")})
    result = fetch_batch(recs, force=True)
    for apn, path in result.items():
        if path:
            size = os.path.getsize(path)
            print(f"  {apn}: {path} ({size:,} bytes)")
