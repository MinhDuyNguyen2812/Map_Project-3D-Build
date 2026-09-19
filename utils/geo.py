"""
GIS utilities: bounding box calculation and coordinate system conversion.
"""

import math
from pyproj import Transformer


def get_bounding_box(
    center_lat: float,
    center_lon: float,
    radius_meters: float
) -> tuple[float, float, float, float]:
    """
    Compute a square bounding box from a center point and a half-size radius.

    Args:
        center_lat: Latitude of the center point (WGS84).
        center_lon: Longitude of the center point (WGS84).
        radius_meters: Half-size of the box in meters (e.g. 1000 → 2 km wide box).

    Returns:
        (lat_min, lon_min, lat_max, lon_max) in WGS84 degrees.
    """
    lat_offset = radius_meters / 111_320
    lon_offset = radius_meters / (111_320 * math.cos(math.radians(center_lat)))

    return (
        center_lat - lat_offset,  # lat_min
        center_lon - lon_offset,  # lon_min
        center_lat + lat_offset,  # lat_max
        center_lon + lon_offset,  # lon_max
    )


def latlon_to_etrs(lat: float, lon: float) -> tuple[float, float]:
    """
    Convert WGS84 (lat, lon) to EPSG:3067 (ETRS-TM35FIN) in meters.
    This is the coordinate system used by NLS Finland WCS.

    Returns:
        (x, y) in meters.
    """
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    x, y = transformer.transform(lon, lat)
    return x, y


def etrs_to_latlon(x: float, y: float) -> tuple[float, float]:
    """
    Convert EPSG:3067 (x, y) back to WGS84 (lat, lon).
    Useful for verifying downloaded file bounds.

    Returns:
        (lat, lon) in degrees.
    """
    transformer = Transformer.from_crs("EPSG:3067", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return lat, lon