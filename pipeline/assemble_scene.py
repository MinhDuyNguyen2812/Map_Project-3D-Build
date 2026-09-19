"""
Pipeline step 10: Assemble all layers into a single master USD scene.

Layers included:
    - terrain.usda      (required)
    - buildings.usda    (required)
    - roads.usda        (optional)
    - terrain_db.usda   (optional)
"""

import os


def _to_relative_path(target: str, reference_file: str) -> str:
    ref_dir = os.path.dirname(os.path.abspath(reference_file))
    rel     = os.path.relpath(os.path.abspath(target), ref_dir)
    return rel.replace("\\", "/")


def _optional_layer(name: str, usd_path: str, prim_path: str, output_usd: str) -> str:
    if not usd_path or not os.path.exists(usd_path):
        return ""
    rel = _to_relative_path(usd_path, output_usd)
    return f"""
# ── {name} layer ───────────────────────────────────────────────────────────────
def Xform "{name}" (
    references = @{rel}@<{prim_path}>
)
{{
}}"""


def assemble_scene(
    terrain_usd:     str,
    building_usd:    str,
    output_usd:      str = "./output/scene.usda",
    roads_usd:       str = None,
    terrain_db_usd:  str = None,
    center_lat:      float = 0.0,
    center_lon:      float = 0.0,
    radius_meters:   float = 1000.0,
) -> str:
    os.makedirs(os.path.dirname(os.path.abspath(output_usd)), exist_ok=True)

    terrain_rel  = _to_relative_path(terrain_usd,  output_usd)
    building_rel = _to_relative_path(building_usd, output_usd)

    layers = ["terrain", "buildings"]
    if roads_usd      and os.path.exists(roads_usd):      layers.append("roads")
    if terrain_db_usd and os.path.exists(terrain_db_usd): layers.append("topographic DB")

    optional_blocks = (
        _optional_layer("Roads",       roads_usd,      "/World/Roads",      output_usd) +
        _optional_layer("TerrainDB",   terrain_db_usd, "/World/TerrainDB",  output_usd)
    )

    usda_content = f"""#usda 1.0
(
    upAxis = "Z"
    metersPerUnit = 1.0
    doc = \"\"\"Digital Twin Finland — Master Scene
    Origin : lat={center_lat:.6f}, lon={center_lon:.6f}
    Radius : {radius_meters:.0f} m
    Layers : {", ".join(layers)}
    \"\"\"
)

# ── Terrain layer ─────────────────────────────────────────────────────────────
def Xform "Terrain" (
    references = @{terrain_rel}@</World/TerrainMesh>
)
{{
}}

# ── Buildings layer ───────────────────────────────────────────────────────────
def Xform "Buildings" (
    references = @{building_rel}@</World/Buildings>
)
{{
}}{optional_blocks}
"""

    with open(output_usd, "w", encoding="utf-8") as f:
        f.write(usda_content)

    print(f"Master scene saved: {output_usd} ({', '.join(layers)})")
    return os.path.abspath(output_usd)