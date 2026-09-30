# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for Digital Twin Finland."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH)

# Local HTML, CSS, JavaScript, and Python package files are loaded at runtime.
datas = [
    (str(project_root / "ui"), "ui"),
    (str(project_root / "pipeline"), "pipeline"),
    (str(project_root / "utils"), "utils"),
]

# Include package data used by geospatial libraries. PyInstaller's normal hooks
# still provide the package code and native binaries.
datas += collect_data_files("rasterio")
datas += collect_data_files("pyproj")

hiddenimports = [
    "PyQt5.sip",
    "PyQt5.QtWebChannel",
    "PyQt5.QtWebEngineWidgets",
]
hiddenimports += collect_submodules("rasterio")
hiddenimports += collect_submodules("pyproj")

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="DigitalTwinFinland",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="DigitalTwinFinland",
)
