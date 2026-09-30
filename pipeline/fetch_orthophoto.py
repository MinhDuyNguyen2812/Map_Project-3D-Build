"""
Pipeline step 5: Fetch orthophoto from NLS Finland via WMTS.

Open data WMTS endpoint (no contract needed, just API key):
    https://avoin-karttakuva.maanmittauslaitos.fi/avoin/wmts/1.0.0

Layer: ortokuva (colour orthophoto, 0.5m resolution)
Tile grid: ETRS-TM35FIN
    Origin:     (-548576, 8388608)
    Resolution: 8192 m/pixel at zoom 0, halves each level
    Tile size:  256 px

Note: WMS orthophoto requires a paid contract (sopimus endpoint).
      WMTS is the correct open data approach with just an API key.
"""

import os
import io
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from dotenv import load_dotenv
from utils.geo import get_bounding_box, latlon_to_etrs

load_dotenv()

WMTS_BASE  = "https://avoin-karttakuva.maanmittauslaitos.fi/avoin/wmts/1.0.0"
LAYER      = "ortokuva"           # colour orthophoto (NOT ortokuva_vari)
TILESET    = "ETRS-TM35FIN"
ZOOM       = 14                   # 0.5 m/pixel

# ETRS-TM35FIN tile grid parameters (from NLS GetCapabilities)
ORIGIN_X   = -548576.0            # TopLeftCorner X (west boundary)
ORIGIN_Y   = 8388608.0            # TopLeftCorner Y (north boundary)
RES_0      = 8192.0               # meters/pixel at zoom 0
TILE_PX    = 256                  # tile size in pixels


def _etrs_to_tile(x: float, y: float, zoom: int) -> tuple[int, int]:
    """Convert EPSG:3067 (x,y) to WMTS tile (col, row) for ETRS-TM35FIN grid."""
    res       = RES_0 / (2 ** zoom)
    tile_m    = TILE_PX * res          # tile coverage in meters
    col       = int((x - ORIGIN_X) / tile_m)
    row       = int((ORIGIN_Y - y) / tile_m)
    return col, row


def fetch_orthophoto(
    center_lat: float,
    center_lon: float,
    radius_meters: float,
    output_path: str = "./output/orthophoto.png",
    progress_callback=None,
) -> str:
    """
    Download and stitch WMTS orthophoto tiles into a single PNG.
    Saves georeferencing bounds alongside for UV alignment.
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow required: pip install Pillow")

    api_key = os.getenv("NLS_API_KEY")
    if not api_key:
        raise RuntimeError("NLS_API_KEY not found in .env file.")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Bounding box in EPSG:3067
    lat_min, lon_min, lat_max, lon_max = get_bounding_box(center_lat, center_lon, radius_meters)
    x_min, y_min = latlon_to_etrs(lat_min, lon_min)
    x_max, y_max = latlon_to_etrs(lat_max, lon_max)

    # Get tile range
    col_min, row_max = _etrs_to_tile(x_min, y_min, ZOOM)
    col_max, row_min = _etrs_to_tile(x_max, y_max, ZOOM)

    n_cols = col_max - col_min + 1
    n_rows = row_max - row_min + 1
    total  = n_cols * n_rows

    print(f"Fetching orthophoto: {n_cols}×{n_rows} = {total} tiles "
          f"(zoom {ZOOM}, layer={LAYER})...")

    canvas = Image.new("RGB", (n_cols * TILE_PX, n_rows * TILE_PX), (200, 200, 200))
    ok     = 0

    tile_positions = [
        (col, row)
        for row in range(row_min, row_max + 1)
        for col in range(col_min, col_max + 1)
    ]

    def _download_tile(position):
        col, row = position
        url = (f"{WMTS_BASE}/{LAYER}/default/{TILESET}"
               f"/{ZOOM}/{row}/{col}.png?api-key={api_key}")
        try:
            response = requests.get(url, timeout=20)
            if response.status_code == 200 and len(response.content) > 500:
                tile = Image.open(io.BytesIO(response.content)).convert("RGB")
                return col, row, tile, None
            return col, row, None, (
                f"HTTP {response.status_code} / {len(response.content)} bytes"
            )
        except Exception as error:
            return col, row, None, str(error)

    completed = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_download_tile, position) for position in tile_positions]
        for future in as_completed(futures):
            col, row, tile, error = future.result()
            completed += 1
            if tile is not None:
                x = (col - col_min) * TILE_PX
                y = (row - row_min) * TILE_PX
                canvas.paste(tile, (x, y))
                ok += 1
            else:
                print(f"  ⚠ Tile ({col},{row}): {error}")
            if progress_callback:
                progress_callback(completed, total)

    if ok == 0:
        raise RuntimeError(
            f"No orthophoto tiles downloaded. "
            f"Check API key, network, or try a different area."
        )

    canvas.save(output_path, "PNG")
    size_mb = os.path.getsize(output_path) / (1024 * 1024)

    # Save actual tile coverage bounds for UV alignment
    res       = RES_0 / (2 ** ZOOM)
    tile_m    = TILE_PX * res
    bounds = {
        "west":  ORIGIN_X + col_min * tile_m,
        "east":  ORIGIN_X + (col_max + 1) * tile_m,
        "north": ORIGIN_Y - row_min * tile_m,
        "south": ORIGIN_Y - (row_max + 1) * tile_m,
        "terrain_x_min": x_min,
        "terrain_x_max": x_max,
        "terrain_y_min": y_min,
        "terrain_y_max": y_max,
    }
    with open(output_path.replace(".png", "_bounds.json"), "w") as f:
        json.dump(bounds, f, indent=2)

    print(f"Orthophoto saved: {output_path} "
          f"({canvas.width}×{canvas.height}px, {size_mb:.1f} MB, {ok}/{total} tiles OK)")
    return os.path.abspath(output_path)