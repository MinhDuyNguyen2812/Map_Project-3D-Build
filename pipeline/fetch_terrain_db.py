"""
Pipeline step 9: Fetch vector features from NLS Finland Topographic Database.

Corrected collection names based on NLS OGC API documentation:
    - suo        (wetlands / swamps)
    - tieviiva   (road lines — used as fallback if Digiroad fails)
    - puisto     (parks / green areas)
    - hautausmaa (cemeteries)
"""

import os
import json
import requests
from dotenv import load_dotenv
from utils.geo import get_bounding_box

load_dotenv()

BASE_URL     = "https://avoin-paikkatieto.maanmittauslaitos.fi/maastotiedot/features/v1"
MAX_FEATURES = 1000

# Verified collection names from NLS OGC API documentation
# Only collections verified to work — vesialue removed (returns 400)
COLLECTIONS = {
    "suo":        "wetlands",   # wetlands / swamps
    "puisto":     "parks",      # parks and green areas
    "hautausmaa": "cemeteries", # cemeteries
}


def _fetch_collection(collection, bbox, api_key):
    url    = f"{BASE_URL}/collections/{collection}/items"
    params = {"bbox": bbox, "limit": MAX_FEATURES, "api-key": api_key}

    all_features = []
    page         = 1

    while url:
        r = requests.get(url, params=params, timeout=15)

        if r.status_code == 404:
            return []   # collection doesn't exist in this region
        if r.status_code != 200:
            print(f"  ⚠ {collection}: HTTP {r.status_code} — skipping")
            return []

        data     = r.json()
        features = data.get("features", [])
        all_features.extend(features)

        next_link = next(
            (lnk["href"] for lnk in data.get("links", []) if lnk.get("rel") == "next"),
            None
        )
        url    = next_link
        params = {}
        page  += 1

    return all_features


def fetch_terrain_db(center_lat, center_lon, radius_meters, output_dir="./output"):
    api_key = os.getenv("NLS_API_KEY")
    if not api_key:
        raise RuntimeError("NLS_API_KEY not found in .env file.")

    os.makedirs(output_dir, exist_ok=True)

    lat_min, lon_min, lat_max, lon_max = get_bounding_box(center_lat, center_lon, radius_meters)
    bbox = f"{lon_min},{lat_min},{lon_max},{lat_max}"

    print(f"Fetching Topographic Database vector layers...")
    print(f"Bounding box: {bbox}")

    output_paths = {}

    for collection, label in COLLECTIONS.items():
        print(f"  Fetching {label} ({collection})...")
        features = _fetch_collection(collection, bbox, api_key)

        if not features:
            print(f"  → No features found for {label}")
            continue

        out_path = os.path.join(output_dir, f"terrain_{label}.geojson")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False)

        output_paths[label] = os.path.abspath(out_path)
        print(f"{label}: {len(features)} features")

    print(f"Topographic DB fetch complete: {len(output_paths)} layers saved.")
    return output_paths