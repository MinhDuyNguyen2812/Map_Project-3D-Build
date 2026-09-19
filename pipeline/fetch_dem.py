"""
Pipeline step 1: Fetch Digital Elevation Model (DEM) from NLS Finland WCS.
"""

import os
import requests
from dotenv import load_dotenv
from utils.geo import get_bounding_box, latlon_to_etrs

load_dotenv()

WCS_URL = "https://avoin-karttakuva.maanmittauslaitos.fi/ortokuvat-ja-korkeusmallit/wcs/v2"


def fetch_dem(
    center_lat: float,
    center_lon: float,
    radius_meters: float,
    output_path: str = "./output/dem_terrain.tif"
) -> str:
    """
    Download a GeoTIFF DEM tile from NLS Finland for the given area.

    Args:
        center_lat:     Latitude of area center (WGS84).
        center_lon:     Longitude of area center (WGS84).
        radius_meters:  Half-size of the bounding box in meters.
        output_path:    Where to save the downloaded .tif file.

    Returns:
        Absolute path to the saved .tif file.

    Raises:
        RuntimeError: If API key is missing or server returns an error.
    """
    api_key = os.getenv("NLS_API_KEY")
    if not api_key:
        raise RuntimeError("NLS_API_KEY not found in .env file.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Convert lat/lon bounding box to EPSG:3067 (meters) for the WCS request
    lat_min, lon_min, lat_max, lon_max = get_bounding_box(center_lat, center_lon, radius_meters)
    x_min, y_min = latlon_to_etrs(lat_min, lon_min)
    x_max, y_max = latlon_to_etrs(lat_max, lon_max)

    params = {
        "service":    "WCS",
        "version":    "2.0.1",
        "request":    "GetCoverage",
        "coverageid": "korkeusmalli_2m",
        "format":     "image/tiff",
        "subset":     [f"E({x_min},{x_max})", f"N({y_min},{y_max})"],
        "api-key":    api_key,
    }

    response = requests.get(WCS_URL, params=params, timeout=120)

    if response.status_code != 200:
        raise RuntimeError(
            f"NLS WCS error {response.status_code}: {response.text[:300]}"
        )

    with open(output_path, "wb") as f:
        f.write(response.content)

    return os.path.abspath(output_path)