"""
Pipeline step 6: Fetch road network from Digiroad (Fintraffic/Väylävirasto).

Correct WFS endpoint: https://avoinapi.vaylapilvi.fi/vaylatiedot/digiroad/wfs
No API key required — open data (CC BY 4.0).
Default CRS: EPSG:3067

Feature type used:
    digiroad:dr_tielinkki_toim_lk — Road links with functional class (geometry + class)
"""

import os
import json
import requests
from utils.geo import get_bounding_box, latlon_to_etrs

DIGIROAD_WFS = "https://avoinapi.vaylapilvi.fi/vaylatiedot/digiroad/wfs"
FEATURE_TYPE = "digiroad:dr_tielinkki_toim_lk"   # Road links + functional class


def fetch_roads(
    center_lat: float,
    center_lon: float,
    radius_meters: float,
    output_path: str = "./output/roads.geojson",
) -> str:
    """
    Download road network from Digiroad WFS for the given area.

    Uses EPSG:3067 bbox (same as terrain origin) for precise alignment.
    Returns GeoJSON with road LineString geometry.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Convert bounding box to EPSG:3067 (Digiroad's native CRS)
    lat_min, lon_min, lat_max, lon_max = get_bounding_box(center_lat, center_lon, radius_meters)
    x_min, y_min = latlon_to_etrs(lat_min, lon_min)
    x_max, y_max = latlon_to_etrs(lat_max, lon_max)
    bbox_3067 = f"{x_min},{y_min},{x_max},{y_max},urn:ogc:def:crs:EPSG::3067"

    print(f"Fetching road network from Digiroad WFS...")
    print(f"Bounding box EPSG:3067: ({x_min:.0f},{y_min:.0f}) → ({x_max:.0f},{y_max:.0f})")

    params = {
        "service":      "WFS",
        "version":      "2.0.0",
        "request":      "GetFeature",
        "typeNames":    FEATURE_TYPE,
        "outputFormat": "application/json",
        "bbox":         bbox_3067,
        "srsName":      "urn:ogc:def:crs:EPSG::4326",  # return in WGS84 for consistency
        "count":        "5000",
    }

    response = requests.get(DIGIROAD_WFS, params=params, timeout=60)

    if response.status_code != 200:
        raise RuntimeError(
            f"Digiroad WFS error {response.status_code}: {response.text[:300]}"
        )

    data     = response.json()
    features = data.get("features", [])
    print(f"  {len(features)} road segments fetched.")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    print(f"Roads saved: {output_path}")
    return os.path.abspath(output_path)