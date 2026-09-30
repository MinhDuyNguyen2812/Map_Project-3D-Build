# Digital Twin Finland

A Windows desktop application for downloading Finnish map data and generating an interactive 3D scene.

The application combines:

- Leaflet for selecting an area on a 2D map
- NLS Finland DEM data for terrain elevation
- NLS orthophoto tiles for terrain textures
- NLS building and topographic database layers
- Digiroad road data
- Three.js for the 3D viewport
- USD and JSON exports for the generated scene

## Requirements

- Windows 10 or later
- Python 3.13 recommended
- An NLS Finland API key
- Internet access while downloading map data

The repository already contains an `openusd_env` virtual environment. If it is not usable on another computer, create a new environment and install the packages listed below.

## Setup

Open PowerShell in the project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PyQt5 PyQtWebEngine numpy rasterio pyproj Pillow requests python-dotenv pyinstaller
```

Download the local browser libraries once:

```powershell
python download_assets.py
```

This creates or verifies:

- `ui/leaflet.js`
- `ui/leaflet.css`
- `ui/three.min.js`

## API Key

If you have not had the API key, please visit: https://www.maanmittauslaitos.fi/en/rajapinnat/api-avaimen-ohje

Create your account and copy the API key.

Create a file named `.env` in the project directory:

```text
NLS_API_KEY=your_nls_api_key_here
```

Do not commit `.env` or distribute it inside a public executable. The application reads the key at runtime.

## Run From Source

```powershell
.\.venv\Scripts\Activate.ps1
python main.py
```

Using the existing environment:

```powershell
.\openusd_env\Scripts\Activate.ps1
python main.py
```

Click the map, choose a radius, and select **Generate 3D Model**. The generated files are written to `output/`, including:

- `scene.usda`: assembled USD scene
- `terrain.usda`, `buildings.usda`, `roads.usda`, `terrain_db.usda`: individual USD layers
- `terrain.json`, `buildings.json`, `roads.json`, `terrain_db.json`: viewport data
- `orthophoto.png`: downloaded terrain texture

## Export A Windows EXE

Build a one-folder distribution from PowerShell. Run this from the project directory with the environment activated:

```powershell
python build.py
```

`build.py` uses `build.spec`, cleans the previous `build/` and `dist/` folders, and verifies the resulting executable. To keep previous build folders, use `python build.py --no-clean`.

The result is:

```text
dist/DigitalTwinFinland/DigitalTwinFinland.exe
```

For the executable to work:

1. Copy `.env` beside `DigitalTwinFinland.exe`.
2. Start the executable with its working directory set to that folder.
3. Keep the `output/` folder beside it, or allow the application to create it.
4. Distribute the complete `dist/DigitalTwinFinland/` folder, not only the `.exe` file.

Example deployment layout:

```text
DigitalTwinFinland/
	DigitalTwinFinland.exe
	.env
	output/
```

The build is intentionally one-folder rather than one-file. This keeps the local HTML, JavaScript, CSS, Qt, and geospatial libraries reliable and makes startup faster.

## Build Notes

- The executable is Windows-specific; build it on Windows.
- `.env` is external because it contains a secret API key.
- Data downloads can take time, especially the orthophoto tiles. The status bar reports tile progress.
- A large search radius produces more geometry, larger JSON files, and slower viewport startup.
- If the browser assets are missing, run `python download_assets.py` before building.

## Troubleshooting

### `NLS_API_KEY not found`

Check that `.env` is beside the project directory when running from source, or beside the executable when deployed.

### The map or 3D viewport is blank

Run:

```powershell
python download_assets.py
```

Then rebuild the executable. Confirm that `ui/leaflet.js`, `ui/leaflet.css`, and `ui/three.min.js` exist in the distribution folder.

### The viewport has no roads or topographic layers

Check that the pipeline completed and that the corresponding files exist in `output/`:

```text
roads.json
terrain_db.json
```

### Rebuilding after code changes

Delete the previous build outputs and build again:

```powershell
python build.py
```