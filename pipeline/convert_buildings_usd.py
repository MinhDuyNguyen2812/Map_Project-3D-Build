"""
Pipeline step 4: Convert building footprints (GeoJSON) to USD building meshes.

Height calculation priority:
    1. korkeusarvo (absolute height in meters) — most accurate, use when available
    2. kerrosluku × floor_height — floor_height varies by kayttotarkoitus (building use)
    3. Default: 1 floor × 3.5m

Building use codes (kayttotarkoitus):
    011-013  Single/multi family residential     → 3.0 m/floor
    021      Office/admin                        → 3.5 m/floor
    031      Commercial/retail                   → 4.0 m/floor
    041      Transport terminal                  → 5.0 m/floor
    051      Public institution                  → 3.8 m/floor
    061      Industrial/warehouse/factory        → 6.0 m/floor
    099      Other                               → 3.5 m/floor

pohjankorkeus (base elevation) is in millimeters → divide by 1000 for meters.

No dependency on usd-core / pxr. Compatible with Python 3.13+.
"""

import os
import json
from pyproj import Transformer

# Floor height per kayttotarkoitus (building use code)
# Grouped by first digit for simplicity
FLOOR_HEIGHT_BY_USE = {
    1:  3.0,   # Residential (011-013, 019)
    2:  3.5,   # Office / admin
    3:  4.0,   # Commercial / retail
    4:  5.0,   # Transport terminals
    5:  3.8,   # Public institutions (schools, hospitals)
    6:  6.0,   # Industrial / warehouse
    7:  4.5,   # Recreational / sports
    8:  4.0,   # Hotels / restaurants
    9:  3.5,   # Other
}
DEFAULT_FLOOR_HEIGHT = 3.5
DEFAULT_FLOORS       = 1
MIN_HEIGHT           = 2.5    # sanity check — discard implausibly short buildings
MAX_HEIGHT           = 200.0  # sanity check — discard implausibly tall buildings


def _floor_height_for_use(kayttotarkoitus) -> float:
    """Return floor height in meters based on building use code."""
    if not kayttotarkoitus:
        return DEFAULT_FLOOR_HEIGHT
    try:
        code       = int(str(kayttotarkoitus)[:2])   # first 2 digits
        first_digit = code // 10
        return FLOOR_HEIGHT_BY_USE.get(first_digit, DEFAULT_FLOOR_HEIGHT)
    except (ValueError, TypeError):
        return DEFAULT_FLOOR_HEIGHT


def _building_height(props: dict) -> float:
    """
    Calculate building height from NLS properties.

    Priority:
        1. korkeusarvo — absolute height in meters (most accurate)
        2. kerrosluku × floor_height_by_use
        3. Default 1 floor × DEFAULT_FLOOR_HEIGHT
    """
    # Priority 1: absolute height
    korkeusarvo = props.get("korkeusarvo")
    if korkeusarvo and isinstance(korkeusarvo, (int, float)) and korkeusarvo > 0:
        h = float(korkeusarvo)
        if MIN_HEIGHT <= h <= MAX_HEIGHT:
            return h

    # Priority 2: floor count × use-based floor height
    floors      = props.get("kerrosluku") or DEFAULT_FLOORS
    floor_h     = _floor_height_for_use(props.get("kayttotarkoitus"))
    h           = int(floors) * floor_h
    if MIN_HEIGHT <= h <= MAX_HEIGHT:
        return h

    # Fallback
    return DEFAULT_FLOOR_HEIGHT


def _latlon_ring_to_local_xy(
    coordinates: list,
    origin_x: float,
    origin_y: float,
    transformer
) -> list[tuple[float, float]]:
    """Batch transform all coordinates at once using pyproj vectorized API."""
    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    xs, ys = transformer.transform(lons, lats)   # batch transform
    return [(x - origin_x, y - origin_y) for x, y in zip(xs, ys)]


def _extrude_polygon(
    ring: list[tuple[float, float]],
    base_z: float,
    height: float
) -> tuple[list, list, list, list]:
    """Extrude a 2D polygon ring into a 3D solid (walls + top cap)."""
    verts  = ring[:-1] if ring[0] == ring[-1] else ring
    n      = len(verts)
    bottom = [(x, y, base_z)          for x, y in verts]
    top    = [(x, y, base_z + height) for x, y in verts]
    points = bottom + top

    face_vertex_counts  = []
    face_vertex_indices = []
    triangles           = []

    # Wall quads
    for i in range(n):
        j  = (i + 1) % n
        b0, b1, t0, t1 = i, j, i + n, j + n
        face_vertex_counts.append(4)
        # Counter-clockwise winding (outward normals) for both USD and Three.js
        face_vertex_indices.extend([b0, t0, t1, b1])
        triangles.extend([[b0, t0, t1], [b0, t1, b1]])

    # Top cap (fan triangulation)
    face_vertex_counts.append(n)
    face_vertex_indices.extend(range(n, 2 * n))
    for i in range(n, 2 * n - 2):
        triangles.append([n, i + 1, i + 2])

    return points, face_vertex_counts, face_vertex_indices, triangles


def convert_buildings_to_usd(
    geojson_path: str,
    output_usd: str,
    terrain_origin: tuple[float, float],
    tif_path: str = None,
) -> str:
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_usd)), exist_ok=True)

    transformer    = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    origin_x, origin_y = terrain_origin

    # Open DEM for elevation sampling (same as roads/topo)
    import rasterio as _rasterio
    dem = _rasterio.open(tif_path) if tif_path and os.path.exists(tif_path) else None

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    print(f"Converting {len(features)} buildings (terrain origin: "
          f"X={origin_x:.2f}, Y={origin_y:.2f})...")

    mesh_blocks        = []
    viewport_buildings = []
    skipped            = 0
    height_from_abs    = 0
    height_from_floors = 0

    for feature in features:
        geom  = feature.get("geometry", {})
        props = feature.get("properties", {})

        if geom.get("type") != "Polygon":
            skipped += 1
            continue

        # Base elevation: sample from DEM at footprint centroid (same as roads/topo)
        # This guarantees buildings align with terrain regardless of pohjankorkeus quality
        outer_ring_raw = geom["coordinates"][0]
        lons_raw = [c[0] for c in outer_ring_raw]
        lats_raw = [c[1] for c in outer_ring_raw]
        cx_epsg, cy_epsg = transformer.transform(
            [sum(lons_raw)/len(lons_raw)],
            [sum(lats_raw)/len(lats_raw)]
        )
        if dem:
            try:
                elev = list(dem.sample([(cx_epsg[0], cy_epsg[0])]))[0][0]
                if dem.nodata is not None and elev == dem.nodata:
                    elev = 0.0
                base_z = float(elev)
            except Exception:
                base_z = float(props.get("pohjankorkeus") or 0) / 1000.0
        else:
            base_z = float(props.get("pohjankorkeus") or 0) / 1000.0

        # Building height (priority logic)
        height = _building_height(props)

        # Track which method was used
        if props.get("korkeusarvo") and float(props["korkeusarvo"] or 0) > 0:
            height_from_abs += 1
        else:
            height_from_floors += 1

        outer_ring = geom["coordinates"][0]
        local_ring = _latlon_ring_to_local_xy(outer_ring, origin_x, origin_y, transformer)

        if len(local_ring) < 3:
            skipped += 1
            continue

        points, counts, indices, triangles = _extrude_polygon(local_ring, base_z, height)

        pts_str = ", ".join(f"({x:.4f}, {y:.4f}, {z:.4f})" for x, y, z in points)
        cnt_str = ", ".join(str(c) for c in counts)
        idx_str = ", ".join(str(i) for i in indices)
        bid     = feature.get("id", len(mesh_blocks))

        mesh_blocks.append(f"""
        def Mesh "Building_{bid}"
        {{
            point3f[] points = [{pts_str}]
            int[] faceVertexCounts = [{cnt_str}]
            int[] faceVertexIndices = [{idx_str}]
            uniform token subdivisionScheme = "none"
        }}""")

        viewport_buildings.append({
            "vertices":  points,
            "triangles": triangles
        })

    # ── Write .usda ───────────────────────────────────────────────────────────
    print("Writing buildings.usda...")
    all_meshes   = "\n".join(mesh_blocks)
    usda_content = f"""#usda 1.0
(
    upAxis = "Z"
    doc = "Digital Twin Finland - Buildings"
)

def Xform "World"
{{
    def Xform "Buildings"
    {{{all_meshes}
    }}
}}
"""
    with open(output_usd, "w", encoding="utf-8") as f:
        f.write(usda_content)

    # ── Write .json for viewport ──────────────────────────────────────────────
    json_path = output_usd.replace(".usda", ".json")
    print("Writing buildings.json...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(viewport_buildings, f)

    size_mb = os.path.getsize(output_usd) / (1024 * 1024)
    if dem:
        dem.close()

    print(f"{len(mesh_blocks)} buildings saved: {output_usd} ({size_mb:.1f} MB)")
    print(f"   Height source: {height_from_abs} from korkeusarvo, "
          f"{height_from_floors} from kerrosluku × floor_height"
          + (f", {skipped} skipped" if skipped else ""))
    return os.path.abspath(output_usd)