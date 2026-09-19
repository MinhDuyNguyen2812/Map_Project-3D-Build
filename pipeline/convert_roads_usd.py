"""
Pipeline step 7: Convert road network (GeoJSON) to USD road mesh.
Road Z is sampled from DEM at each vertex position — no hardcoded offset.
"""

import os
import json
import math
import numpy as np
import rasterio
from pyproj import Transformer

ROAD_WIDTHS = {1: 14.0, 2: 10.0, 3: 7.0, 4: 5.0, 5: 3.5}
DEFAULT_WIDTH = 4.0
ROAD_Z_OFFSET = 0.3   # meters above terrain surface


def _sample_elevation(dataset, xs, ys):
    """Sample DEM elevation for a list of EPSG:3067 (x, y) coordinates."""
    coords = list(zip(xs, ys))
    try:
        elevs = [val[0] for val in dataset.sample(coords)]
        nodata = dataset.nodata
        if nodata is not None:
            elevs = [e if e != nodata else 0.0 for e in elevs]
        return elevs
    except Exception:
        return [0.0] * len(coords)


def _extrude_road_segment(points_xy, elevations, width, z_offset):
    if len(points_xy) < 2:
        return [], [], [], []

    half_w = width / 2.0
    left, right = [], []

    for i, (x, y) in enumerate(points_xy):
        if i == 0:
            dx, dy = points_xy[1][0]-x, points_xy[1][1]-y
        elif i == len(points_xy)-1:
            dx, dy = x-points_xy[-2][0], y-points_xy[-2][1]
        else:
            dx, dy = points_xy[i+1][0]-points_xy[i-1][0], points_xy[i+1][1]-points_xy[i-1][1]

        ln = math.sqrt(dx*dx+dy*dy) or 1.0
        nx, ny = -dy/ln, dx/ln
        z = elevations[i] + z_offset
        left.append( (x+nx*half_w, y+ny*half_w, z))
        right.append((x-nx*half_w, y-ny*half_w, z))

    n       = len(points_xy)
    points  = left + right
    counts, indices, triangles = [], [], []

    for i in range(n-1):
        l0,l1,r0,r1 = i, i+1, i+n, i+n+1
        counts.append(4)
        indices.extend([l0,l1,r1,r0])
        triangles.extend([[l0,l1,r1],[l0,r1,r0]])

    return points, counts, indices, triangles


def convert_roads_to_usd(
    geojson_path: str,
    output_usd: str,
    terrain_origin: tuple[float, float],
    tif_path: str = None,
    road_z: float = ROAD_Z_OFFSET,
) -> str:
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    os.makedirs(os.path.dirname(os.path.abspath(output_usd)), exist_ok=True)

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    origin_x, origin_y = terrain_origin

    with open(geojson_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features    = data.get("features", [])
    mesh_blocks = []
    viewport_roads = []
    skipped     = 0

    print(f"Converting {len(features)} road segments to USD...")

    # Open DEM for elevation sampling
    dem = rasterio.open(tif_path) if tif_path and os.path.exists(tif_path) else None

    for i, feature in enumerate(features):
        geom  = feature.get("geometry", {})
        props = feature.get("properties", {})

        if geom.get("type") != "LineString":
            skipped += 1
            continue

        road_class = props.get("toiminnallinen_luokka") or props.get("tieluokka") or 5
        width      = ROAD_WIDTHS.get(int(road_class), DEFAULT_WIDTH)

        # Batch transform all coordinates at once (faster + correct)
        _coords = geom["coordinates"]
        _lons   = [c[0] for c in _coords]
        _lats   = [c[1] for c in _coords]
        _xs, _ys = transformer.transform(_lons, _lats)
        points_xy = [(x - origin_x, y - origin_y) for x, y in zip(_xs, _ys)]

        if len(points_xy) < 2:
            skipped += 1
            continue

        # Sample elevation from DEM
        if dem:
            epsg_xs = [p[0] + origin_x for p in points_xy]
            epsg_ys = [p[1] + origin_y for p in points_xy]
            elevations = _sample_elevation(dem, epsg_xs, epsg_ys)
        else:
            elevations = [0.0] * len(points_xy)

        pts, cnt, idx, tri = _extrude_road_segment(points_xy, elevations, width, road_z)
        if not pts:
            skipped += 1
            continue

        pts_str = ", ".join(f"({x:.4f}, {y:.4f}, {z:.4f})" for x, y, z in pts)
        cnt_str = ", ".join(str(c) for c in cnt)
        idx_str = ", ".join(str(j) for j in idx)

        mesh_blocks.append(f"""
        def Mesh "Road_{i}"
        {{
            point3f[] points = [{pts_str}]
            int[] faceVertexCounts = [{cnt_str}]
            int[] faceVertexIndices = [{idx_str}]
            uniform token subdivisionScheme = "none"
        }}""")

        viewport_roads.append({"vertices": pts, "triangles": tri})

    if dem:
        dem.close()

    print("Writing roads.usda...")
    all_meshes = "\n".join(mesh_blocks)
    usda_content = f"""#usda 1.0
(
    upAxis = "Z"
    doc = "Digital Twin Finland - Road Network"
)
def Xform "World"
{{
    def Xform "Roads"
    {{{all_meshes}
    }}
}}
"""
    with open(output_usd, "w", encoding="utf-8") as f:
        f.write(usda_content)

    json_path = output_usd.replace(".usda", ".json")
    print("Writing roads.json...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(viewport_roads, f)

    size_mb = os.path.getsize(output_usd) / (1024*1024)
    print(f"{len(mesh_blocks)} roads saved: {output_usd} ({size_mb:.1f} MB)"
          + (f" ({skipped} skipped)" if skipped else ""))
    return os.path.abspath(output_usd)