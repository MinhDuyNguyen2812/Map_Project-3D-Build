"""
Pipeline step 2: Convert GeoTIFF DEM to USD terrain mesh.
Optimized with NumPy vectorization — no Python for loops for vertex/face building.
"""

import os
import json
import numpy as np
import rasterio


def convert_to_usd(
    input_tif: str,
    output_usd: str = "./output/terrain.usda",
    sample_step: int = 4,
    orthophoto_path: str = None,
) -> tuple[str, tuple[float, float]]:

    if not os.path.exists(input_tif):
        raise FileNotFoundError(f"Input file not found: {input_tif}")

    os.makedirs(os.path.dirname(os.path.abspath(output_usd)), exist_ok=True)

    print("Reading elevation data from GeoTIFF...")
    with rasterio.open(input_tif) as dataset:
        elevation = dataset.read(1).astype(np.float32)
        if dataset.nodata is not None:
            elevation[elevation == dataset.nodata] = 0.0

        rows, cols         = elevation.shape
        origin_x, origin_y = dataset.transform * (0, 0)
        T                  = dataset.transform

        # Sample indices
        ri = np.arange(0, rows, sample_step)
        ci = np.arange(0, cols, sample_step)
        nr, nc = len(ri), len(ci)

        print(f"Building mesh: {nr} × {nc} vertices (NumPy vectorized)...")

        # ── Vectorized vertex positions ───────────────────────────────────────
        # Grid of pixel indices
        C, R = np.meshgrid(ci, ri)                          # shape (nr, nc)

        # Pixel → EPSG:3067 (affine transform: x = T.a*c + T.b*r + T.c)
        X = T.a * C + T.b * R + T.c - origin_x             # local X
        Y = T.d * C + T.e * R + T.f - origin_y             # local Y
        Z = elevation[R, C]                                  # elevation

        # Flatten to (N, 3)
        pts = np.stack([X.ravel(), Y.ravel(), Z.ravel()], axis=1)

        # UV: use actual orthophoto tile bounds if available for correct alignment
        x_min, x_max = float(X.min()), float(X.max())
        y_min, y_max = float(Y.min()), float(Y.max())

        # Try to read actual tile coverage bounds saved by fetch_orthophoto
        _ortho_bounds_path = None
        if orthophoto_path:
            _ortho_bounds_path = orthophoto_path.replace(".png", "_bounds.json")
        if _ortho_bounds_path and os.path.exists(_ortho_bounds_path):
            import json as _json
            with open(_ortho_bounds_path) as _f:
                _b = _json.load(_f)
            # Convert tile bounds to local coords (subtract origin)
            _ux_min = _b["west"]  - origin_x
            _ux_max = _b["east"]  - origin_x
            _uy_min = _b["south"] - origin_y
            _uy_max = _b["north"] - origin_y
            print(f"  Using tile bounds for UV alignment")
        else:
            _ux_min, _ux_max = x_min, x_max
            _uy_min, _uy_max = y_min, y_max

        U = (X - _ux_min) / (_ux_max - _ux_min + 1e-9)
        V = (Y - _uy_min) / (_uy_max - _uy_min + 1e-9)
        uvs = np.stack([U.ravel(), V.ravel()], axis=1)

        # ── Vectorized quad face topology ─────────────────────────────────────
        # Vertex index grid
        idx = np.arange(nr * nc).reshape(nr, nc)

        p0 = idx[:-1, :-1].ravel()
        p1 = idx[:-1, 1: ].ravel()
        p2 = idx[1:,  1: ].ravel()
        p3 = idx[1:,  :-1].ravel()

        quads      = np.stack([p0, p1, p2, p3], axis=1)    # (nfaces, 4)
        triangles  = np.concatenate([
            np.stack([p0, p1, p2], axis=1),
            np.stack([p0, p2, p3], axis=1),
        ], axis=0)

        face_vertex_counts  = np.full(len(quads), 4, dtype=np.int32)
        face_vertex_indices = quads.ravel()

    # ── Format strings ────────────────────────────────────────────────────────
    print("Writing terrain.usda...")
    points_str  = ", ".join(f"({x:.4f}, {y:.4f}, {z:.4f})" for x, y, z in pts)
    counts_str  = " ".join(str(c) for c in face_vertex_counts)
    indices_str = " ".join(str(i) for i in face_vertex_indices)
    uvs_str     = ", ".join(f"({u:.6f}, {v:.6f})" for u, v in uvs)

    # ── Orthophoto material block ──────────────────────────────────────────────
    texture_block = ""
    material_bind = ""
    if orthophoto_path and os.path.exists(orthophoto_path):
        output_dir = os.path.dirname(os.path.abspath(output_usd))
        ortho_rel  = os.path.relpath(os.path.abspath(orthophoto_path), output_dir).replace("\\", "/")
        texture_block = f"""
def Material "TerrainMaterial"
{{
    token outputs:surface.connect = </World/TerrainMaterial/Shader.outputs:surface>
    def Shader "Shader"
    {{
        uniform token info:id = "UsdPreviewSurface"
        color3f inputs:diffuseColor.connect = </World/TerrainMaterial/DiffuseTexture.outputs:rgb>
        float inputs:roughness = 0.9
        token outputs:surface
    }}
    def Shader "DiffuseTexture"
    {{
        uniform token info:id = "UsdUVTexture"
        asset inputs:file = @{ortho_rel}@
        float2 inputs:st.connect = </World/TerrainMaterial/UVReader.outputs:result>
        token inputs:wrapS = "clamp"
        token inputs:wrapT = "clamp"
        float3 outputs:rgb
    }}
    def Shader "UVReader"
    {{
        uniform token info:id = "UsdPrimvarReader_float2"
        token inputs:varname = "st"
        float2 outputs:result
    }}
}}
"""
        material_bind = '\n        rel material:binding = </World/TerrainMaterial>'
        print(f"  Orthophoto texture: {ortho_rel}")

    usda_content = f"""#usda 1.0
(
    upAxis = "Z"
    doc = "Digital Twin Finland - Terrain Mesh"
)
{texture_block}
def Xform "World"
{{
    def Mesh "TerrainMesh"{material_bind}
    {{
        point3f[] points = [{points_str}]
        int[] faceVertexCounts = [{counts_str}]
        int[] faceVertexIndices = [{indices_str}]
        texCoord2f[] primvars:st = [{uvs_str}] (
            interpolation = "vertex"
        )
        uniform token subdivisionScheme = "none"
    }}
}}
"""
    with open(output_usd, "w", encoding="utf-8") as f:
        f.write(usda_content)

    # ── Write terrain.json for viewport ───────────────────────────────────────
    print("Writing terrain.json...")
    json_path = output_usd.replace(".usda", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "vertices":  pts.tolist(),
            "triangles": triangles.tolist(),
            "uvs":       uvs.tolist(),
        }, f)

    # Save origin for alignment
    origin_path = output_usd.replace(".usda", "_origin.json")
    with open(origin_path, "w", encoding="utf-8") as f:
        json.dump({"origin_x": float(origin_x), "origin_y": float(origin_y)}, f)

    size_mb = os.path.getsize(output_usd) / (1024 * 1024)
    print(f"Terrain saved: {output_usd} ({size_mb:.1f} MB, "
          f"{nr}×{nc}={nr*nc} vertices)")
    return os.path.abspath(output_usd), (float(origin_x), float(origin_y))