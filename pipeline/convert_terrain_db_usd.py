"""
Pipeline step 9: Convert Topographic DB vector layers to USD.
Feature Z is sampled from DEM at centroid position — correct elevation alignment.
"""

import os
import json
import math
import rasterio
from pyproj import Transformer

LAYER_CONFIG = {
    "water":      {"z_offset": -0.3, "color": (0.2, 0.5, 0.9),  "rgb_viewport": [0.2, 0.5, 0.9]},
    "wetlands":   {"z_offset": -0.1, "color": (0.4, 0.7, 0.6),  "rgb_viewport": [0.4, 0.7, 0.6]},
    "parks":      {"z_offset":  0.1, "color": (0.3, 0.7, 0.3),  "rgb_viewport": [0.3, 0.7, 0.3]},
    "cemeteries": {"z_offset":  0.1, "color": (0.6, 0.6, 0.5),  "rgb_viewport": [0.6, 0.6, 0.5]},
    "traffic":    {"z_offset":  0.2, "color": (0.5, 0.5, 0.5),  "rgb_viewport": [0.5, 0.5, 0.5]},
    "paths":      {"z_offset":  0.15,"color": (0.7, 0.55, 0.35),"rgb_viewport": [0.7, 0.55, 0.35]},
}
DEFAULT_Z_OFFSET = 0.1
PATH_WIDTH       = 2.0


def _sample_elev(dem, x: float, y: float) -> float:
    """Sample DEM elevation at single EPSG:3067 point."""
    try:
        val = list(dem.sample([(x, y)]))[0][0]
        if dem.nodata is not None and val == dem.nodata:
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def _centroid_elev(dem, ring_xy, origin_x, origin_y) -> float:
    """Get elevation at polygon centroid."""
    if not dem or not ring_xy:
        return 0.0
    cx = sum(p[0] for p in ring_xy) / len(ring_xy) + origin_x
    cy = sum(p[1] for p in ring_xy) / len(ring_xy) + origin_y
    return _sample_elev(dem, cx, cy)


def _latlon_ring_to_local_xy(ring, origin_x, origin_y, transformer):
    lons = [c[0] for c in ring]
    lats = [c[1] for c in ring]
    xs, ys = transformer.transform(lons, lats)
    return [(x - origin_x, y - origin_y) for x, y in zip(xs, ys)]


def _polygon_to_flat_mesh(ring_xy, z):
    verts = ring_xy[:-1] if ring_xy[0] == ring_xy[-1] else ring_xy
    n = len(verts)
    if n < 3:
        return [], [], [], []
    cx = sum(p[0] for p in verts) / n
    cy = sum(p[1] for p in verts) / n
    points   = [(x, y, z) for x, y in verts] + [(cx, cy, z)]
    center_i = n
    counts, indices, triangles = [], [], []
    for i in range(n):
        j = (i+1) % n
        counts.append(3)
        indices.extend([i, j, center_i])
        triangles.append([i, j, center_i])
    return points, counts, indices, triangles


def _linestring_to_strip(coords_xy, z, width=PATH_WIDTH):
    if len(coords_xy) < 2:
        return [], [], [], []
    half = width / 2.0
    left, right = [], []
    for i, (x, y) in enumerate(coords_xy):
        if i == 0:
            dx, dy = coords_xy[1][0]-x, coords_xy[1][1]-y
        elif i == len(coords_xy)-1:
            dx, dy = x-coords_xy[-2][0], y-coords_xy[-2][1]
        else:
            dx, dy = coords_xy[i+1][0]-coords_xy[i-1][0], coords_xy[i+1][1]-coords_xy[i-1][1]
        ln = math.sqrt(dx*dx+dy*dy) or 1.0
        nx, ny = -dy/ln, dx/ln
        left.append( (x+nx*half, y+ny*half, z))
        right.append((x-nx*half, y-ny*half, z))
    n = len(coords_xy)
    points = left + right
    counts, indices, triangles = [], [], []
    for i in range(n-1):
        counts.append(4)
        indices.extend([i, i+1, i+1+n, i+n])
        triangles.extend([[i, i+1, i+1+n], [i, i+1+n, i+n]])
    return points, counts, indices, triangles


def convert_terrain_db_to_usd(
    layer_files: dict,
    output_usd: str,
    terrain_origin: tuple[float, float],
    tif_path: str = None,
) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_usd)), exist_ok=True)

    transformer    = Transformer.from_crs("EPSG:4326", "EPSG:3067", always_xy=True)
    origin_x, origin_y = terrain_origin

    dem = rasterio.open(tif_path) if tif_path and os.path.exists(tif_path) else None

    layer_blocks    = []
    viewport_layers = []

    for label, geojson_path in layer_files.items():
        if not os.path.exists(geojson_path):
            continue

        cfg       = LAYER_CONFIG.get(label, {"z_offset": DEFAULT_Z_OFFSET,
                                              "color": (0.5,0.5,0.5),
                                              "rgb_viewport": [0.5,0.5,0.5]})
        z_offset  = cfg["z_offset"]
        r, g, b   = cfg["color"]

        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        features   = data.get("features", [])
        mesh_items = []
        vp_meshes  = []
        skipped    = 0

        for i, feature in enumerate(features):
            geom  = feature.get("geometry", {})
            gtype = geom.get("type", "")

            if gtype == "Polygon":
                outer     = geom["coordinates"][0]
                ring      = _latlon_ring_to_local_xy(outer, origin_x, origin_y, transformer)
                elev      = _centroid_elev(dem, ring, origin_x, origin_y)
                z         = elev + z_offset
                pts, cnt, idx, tri = _polygon_to_flat_mesh(ring, z)

            elif gtype == "MultiPolygon":
                pts, cnt, idx, tri = [], [], [], []
                offset = 0
                for poly in geom["coordinates"]:
                    ring  = _latlon_ring_to_local_xy(poly[0], origin_x, origin_y, transformer)
                    elev  = _centroid_elev(dem, ring, origin_x, origin_y)
                    z     = elev + z_offset
                    p, c, ix, tr = _polygon_to_flat_mesh(ring, z)
                    pts.extend(p); cnt.extend(c)
                    idx.extend([v+offset for v in ix])
                    tri.extend([[a+offset,b+offset,cc+offset] for a,b,cc in tr])
                    offset += len(p)

            elif gtype == "LineString":
                coords = _latlon_ring_to_local_xy(
                    geom["coordinates"], origin_x, origin_y, transformer)
                if coords:
                    cx = coords[len(coords)//2][0] + origin_x
                    cy = coords[len(coords)//2][1] + origin_y
                    elev = _sample_elev(dem, cx, cy) if dem else 0.0
                else:
                    elev = 0.0
                z = elev + z_offset
                pts, cnt, idx, tri = _linestring_to_strip(coords, z)
            else:
                skipped += 1
                continue

            if not pts:
                skipped += 1
                continue

            pts_str = ", ".join(f"({x:.4f},{y:.4f},{zv:.4f})" for x, y, zv in pts)
            cnt_str = ", ".join(str(c) for c in cnt)
            idx_str = ", ".join(str(v) for v in idx)

            mesh_items.append(f"""
            def Mesh "{label}_{i}"
            {{
                point3f[] points = [{pts_str}]
                int[] faceVertexCounts = [{cnt_str}]
                int[] faceVertexIndices = [{idx_str}]
                uniform token subdivisionScheme = "none"
            }}""")
            vp_meshes.append({"vertices": pts, "triangles": tri})

        all_items = "\n".join(mesh_items)
        layer_blocks.append(f"""
    def Xform "{label.capitalize()}"
    {{
        color3f[] primvars:displayColor = [({r:.3f},{g:.3f},{b:.3f})]
        {{{all_items}
        }}
    }}""")

        viewport_layers.append({
            "label":  label,
            "color":  cfg["rgb_viewport"],
            "meshes": vp_meshes
        })

        print(f"  ✅ {label}: {len(mesh_items)} meshes"
              + (f" ({skipped} skipped)" if skipped else ""))

    if dem:
        dem.close()

    print("Writing terrain_db.usda...")
    all_layers   = "\n".join(layer_blocks)
    usda_content = f"""#usda 1.0
(
    upAxis = "Z"
    doc = "Digital Twin Finland - Topographic Database"
)
def Xform "World"
{{
    def Xform "TerrainDB"
    {{{all_layers}
    }}
}}
"""
    with open(output_usd, "w", encoding="utf-8") as f:
        f.write(usda_content)

    json_path = output_usd.replace(".usda", ".json")
    print("Writing terrain_db.json...")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(viewport_layers, f)

    size_mb = os.path.getsize(output_usd) / (1024*1024)
    print(f"Terrain DB saved: {output_usd} ({size_mb:.1f} MB)")
    return os.path.abspath(output_usd)