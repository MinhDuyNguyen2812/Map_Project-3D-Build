"""
Background pipeline worker — optimized with parallel fetching.

Steps:
    1. Fetch DEM                        -> dem_terrain.tif
    2. Convert DEM -> USD               -> terrain.usda + terrain.json
    3. Fetch buildings + ortho + roads  -> PARALLEL
    4. Convert all fetched data         -> USD meshes
    5. Assemble master scene            -> scene.usda
"""

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtCore import QThread, pyqtSignal

from pipeline.fetch_dem import fetch_dem
from pipeline.convert_usd import convert_to_usd
from pipeline.fetch_buildings import fetch_buildings
from pipeline.convert_buildings_usd import convert_buildings_to_usd
from pipeline.fetch_orthophoto import fetch_orthophoto
from pipeline.fetch_roads import fetch_roads
from pipeline.convert_roads_usd import convert_roads_to_usd
from pipeline.fetch_terrain_db import fetch_terrain_db
from pipeline.convert_terrain_db_usd import convert_terrain_db_to_usd
from pipeline.assemble_scene import assemble_scene


class PipelineWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(str)
    failed   = pyqtSignal(str)

    def __init__(self, lat: float, lon: float, radius: float):
        super().__init__()
        self.lat    = lat
        self.lon    = lon
        self.radius = radius

    def run(self):
        try:
            tif_path       = "./output/dem_terrain.tif"
            terrain_usd    = "./output/terrain.usda"
            building_json  = "./output/buildings.geojson"
            building_usd   = "./output/buildings.usda"
            ortho_path     = "./output/orthophoto.png"
            roads_json     = "./output/roads.geojson"
            roads_usd      = "./output/roads.usda"
            terrain_db_usd = "./output/terrain_db.usda"
            scene_usd      = "./output/scene.usda"

            # Remove optional topo outputs from an earlier run before fetching
            # fresh layers, so failed or empty requests cannot show stale data.
            for old_path in (terrain_db_usd, terrain_db_usd.replace(".usda", ".json")):
                if os.path.exists(old_path):
                    os.remove(old_path)
            for old_path in ("wetlands", "parks", "cemeteries"):
                old_geojson = f"./output/terrain_{old_path}.geojson"
                if os.path.exists(old_geojson):
                    os.remove(old_geojson)

            lat, lon, radius = self.lat, self.lon, self.radius

            # ── Step 1: Fetch DEM (must be first — provides terrain_origin) ──
            self.progress.emit(5, "Calculating bounding box...")
            self.msleep(200)
            self.progress.emit(10, "Downloading terrain DEM from NLS...")
            fetch_dem(lat, lon, radius, tif_path)

            # ── Step 2: Convert DEM → USD (need terrain_origin for alignment) ──
            self.progress.emit(22, "Building 3D terrain mesh...")
            _, terrain_origin = convert_to_usd(
                tif_path, terrain_usd, sample_step=4,
                orthophoto_path=ortho_path if os.path.exists(ortho_path) else None
            )

            # ── Step 3: Fetch buildings + ortho + roads + terrain DB in PARALLEL ──
            self.progress.emit(32, "Fetching data layers in parallel...")

            fetch_results = {
                "buildings": None,
                "orthophoto": None,
                "roads": None,
                "terrain_db": None,
            }
            fetch_errors = {}

            def _fetch_buildings():
                fetch_buildings(lat, lon, radius, building_json)
                return "buildings"

            def _fetch_orthophoto():
                # Always delete old orthophoto before fetching fresh
                if os.path.exists(ortho_path):
                    os.remove(ortho_path)
                    print("[Orthophoto] Deleted old file, fetching fresh...")
                fetch_orthophoto(
                    lat,
                    lon,
                    radius,
                    ortho_path,
                    progress_callback=lambda done, total: self.progress.emit(
                        32 + min(7, done * 7 // total),
                        f"Orthophoto tiles ({done}/{total})..."
                    ),
                )
                return "orthophoto"

            def _fetch_roads():
                fetch_roads(lat, lon, radius, roads_json)
                return "roads"

            def _fetch_terrain_db():
                return fetch_terrain_db(lat, lon, radius, output_dir="./output")

            tasks = {
                "buildings":  _fetch_buildings,
                "orthophoto": _fetch_orthophoto,
                "roads":      _fetch_roads,
                "terrain_db": _fetch_terrain_db,
            }

            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(fn): name for name, fn in tasks.items()}
                done = 0
                for future in as_completed(futures):
                    name = futures[future]
                    done += 1
                    try:
                        result = future.result()
                        fetch_results[name] = result
                        self.progress.emit(32 + done * 8, f"✓ {name} fetched ({done}/4)")
                    except Exception as e:
                        fetch_errors[name] = str(e)
                        print(f"[Worker] {name} fetch failed (non-fatal): {e}")
                        self.progress.emit(32 + done * 8, f"⚠ {name} skipped")

            # ── Step 4: Convert all fetched data ─────────────────────────────
            self.progress.emit(65, "Converting buildings to 3D mesh...")
            if fetch_results["buildings"] is not None:
                convert_buildings_to_usd(
                    geojson_path=building_json,
                    output_usd=building_usd,
                    terrain_origin=terrain_origin,
                    tif_path=tif_path,
                )

            # Re-convert terrain with orthophoto texture (cheap — just rewrites USDA/JSON)
            if fetch_results["orthophoto"] is not None and os.path.exists(ortho_path):
                self.progress.emit(72, "Applying orthophoto texture to terrain...")
                convert_to_usd(tif_path, terrain_usd, sample_step=4, orthophoto_path=ortho_path)

            self.progress.emit(78, "Converting roads to 3D mesh...")
            roads_ok = False
            if fetch_results["roads"] is not None:
                try:
                    convert_roads_to_usd(
                        geojson_path=roads_json,
                        output_usd=roads_usd,
                        terrain_origin=terrain_origin,
                        tif_path=tif_path,
                    )
                    roads_ok = True
                except Exception as e:
                    print(f"[Worker] Roads convert failed: {e}")

            self.progress.emit(84, "Converting topographic layers...")
            terrain_db_ok = False
            if fetch_results["terrain_db"]:
                try:
                    convert_terrain_db_to_usd(
                        layer_files=fetch_results["terrain_db"],
                        output_usd=terrain_db_usd,
                        terrain_origin=terrain_origin,
                        tif_path=tif_path,
                    )
                    terrain_db_ok = True
                except Exception as e:
                    print(f"[Worker] Terrain DB convert failed: {e}")

            # ── Step 5: Assemble master scene ─────────────────────────────────
            self.progress.emit(92, "Assembling master scene...")
            assemble_scene(
                terrain_usd=terrain_usd,
                building_usd=building_usd,
                output_usd=scene_usd,
                roads_usd=roads_usd if roads_ok else None,
                terrain_db_usd=terrain_db_usd if terrain_db_ok else None,
                center_lat=lat,
                center_lon=lon,
                radius_meters=radius,
            )

            self.progress.emit(100, "Done.")
            self.finished.emit(scene_usd)

        except Exception as e:
            self.failed.emit(str(e))