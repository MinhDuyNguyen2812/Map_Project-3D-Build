"""
Pipeline step 3: Fetch building footprints from NLS Finland Topographic Database
using the OGC API Features endpoint (replaces deprecated INSPIRE WFS after May 2025).

Endpoint: https://avoin-paikkatieto.maanmittauslaitos.fi/maastotiedot/features/v1/
Collection: rakennus (building polygons from Topographic Database)
Returns: GeoJSON, WGS84 (lon/lat) by default
"""

import os
import json
import requests
from dotenv import load_dotenv
from utils.geo import get_bounding_box

load_dotenv()

BASE_URL = "https://avoin-paikkatieto.maanmittauslaitos.fi/maastotiedot/features/v1"
COLLECTION = "rakennus"   
MAX_FEATURES = 1000       # OGC API Features page limit per request


def fetch_buildings(
    center_lat: float,
    center_lon: float,
    radius_meters: float,
    output_path: str = "./output/buildings.geojson"
) -> str:
    """
    Download building footprints (polygons) from NLS Topographic Database
    for the given area.

    Args:
        center_lat:     Latitude of area center (WGS84).
        center_lon:     Longitude of area center (WGS84).
        radius_meters:  Half-size of the bounding box in meters.
        output_path:    Where to save the output GeoJSON file.

    Returns:
        Absolute path to the saved GeoJSON file.

    Raises:
        RuntimeError: If API key is missing or server returns an error.
    """
    api_key = os.getenv("NLS_API_KEY")
    if not api_key:
        raise RuntimeError("NLS_API_KEY not found in .env file.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Bounding box in WGS84 (lon/lat) — OGC API Features default is CRS84 (lon,lat order)
    lat_min, lon_min, lat_max, lon_max = get_bounding_box(center_lat, center_lon, radius_meters)
    bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"

    url = f"{BASE_URL}/collections/{COLLECTION}/items"
    params = {
        "bbox":     bbox,
        "limit":    MAX_FEATURES,
        "api-key":  api_key,
    }

    print(f"Fetching buildings from NLS Topographic Database...")
    print(f"Bounding box (WGS84): {bbox}")

    all_features = []
    page = 1

    while url:
        response = requests.get(url, params=params, timeout=60)

        if response.status_code != 200:
            raise RuntimeError(
                f"NLS OGC API error {response.status_code}: {response.text[:300]}"
            )

        data = response.json()
        features = data.get("features", [])
        all_features.extend(features)

        print(f"  Page {page}: {len(features)} buildings fetched "
              f"(total so far: {len(all_features)})")

        # Follow 'next' link for pagination if more features exist
        next_link = next(
            (link["href"] for link in data.get("links", []) if link.get("rel") == "next"),
            None
        )
        # On subsequent pages, params are already embedded in the next URL
        url = next_link
        params = {}
        page += 1

    # Wrap all features into a single GeoJSON FeatureCollection
    feature_collection = {
        "type": "FeatureCollection",
        "features": all_features
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(feature_collection, f, ensure_ascii=False, indent=2)

    print(f"{len(all_features)} buildings saved to: {output_path}")
    return os.path.abspath(output_path)