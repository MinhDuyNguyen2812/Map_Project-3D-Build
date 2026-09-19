"""
ui/viewport_window.py
3D Viewport: reads all JSON layers in Python and injects directly into Three.js.
Avoids file:// fetch restriction in QWebEngineView.
"""

import os
import json
import base64
from PyQt5.QtCore import QUrl, QTimer
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSizePolicy
)
from PyQt5.QtWebEngineWidgets import QWebEngineView


def _read_json(path: str, fallback):
    """Read JSON file safely, return fallback if missing or unreadable."""
    if not path or not os.path.exists(path):
        return fallback
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[Viewport] Could not read {path}: {e}")
        return fallback


class ViewportWindow(QMainWindow):

    def __init__(self, output_dir: str = "./output", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Digital Twin Finland — 3D Viewport")
        self.resize(1280, 800)
        self.output_dir = os.path.abspath(output_dir)
        self._build_ui()
        self.view.loadFinished.connect(self._on_load_finished)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QWidget()
        toolbar.setStyleSheet("background: #111827; padding: 4px 12px;")
        toolbar.setFixedHeight(40)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(8, 0, 8, 0)

        title = QLabel("3D VIEWPORT")
        title.setStyleSheet("color:#00C9A7; font-size:12px; font-weight:600; letter-spacing:2px;")
        tb.addWidget(title)
        tb.addStretch()

        # Layer toggles
        for label, js_fn in [("Terrain","toggleTerrain"),("Buildings","toggleBuildings"),
                              ("Roads","toggleRoads"),("Topo DB","toggleTopoDB")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedHeight(28)
            btn.setStyleSheet("""
                QPushButton         { background:#1E293B; border:1px solid #334155;
                                      border-radius:4px; color:#94A3B8; font-size:11px; padding:0 10px; }
                QPushButton:checked { border-color:#00C9A7; color:#00C9A7; }
                QPushButton:hover   { border-color:#64748B; }
            """)
            btn.toggled.connect(lambda checked, fn=js_fn: self._run_js(f"{fn}({str(checked).lower()});"))
            tb.addWidget(btn)

        tb.addSpacing(8)

        # Wireframe
        wire_btn = QPushButton("Wireframe")
        wire_btn.setCheckable(True)
        wire_btn.setFixedHeight(28)
        wire_btn.setStyleSheet("""
            QPushButton         { background:transparent; border:1px solid #334155;
                                  border-radius:4px; color:#64748B; font-size:12px; padding:0 12px; }
            QPushButton:checked { border-color:#00C9A7; color:#00C9A7; }
        """)
        wire_btn.toggled.connect(lambda c: self._run_js(f"setWireframe({str(c).lower()});"))
        tb.addWidget(wire_btn)

        reset_btn = QPushButton("Reset Camera")
        reset_btn.setFixedHeight(28)
        reset_btn.setStyleSheet("""
            QPushButton       { background:transparent; border:1px solid #334155;
                                border-radius:4px; color:#64748B; font-size:12px; padding:0 12px; }
            QPushButton:hover { border-color:#64748B; color:#94A3B8; }
        """)
        reset_btn.clicked.connect(lambda: self._run_js("resetCamera();"))
        tb.addWidget(reset_btn)
        layout.addWidget(toolbar)

        # Three.js viewport
        self.view = QWebEngineView()
        self.view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "viewport.html")
        self.view.load(QUrl.fromLocalFile(html_path))
        layout.addWidget(self.view)

    def _run_js(self, js: str):
        self.view.page().runJavaScript(js)

    def _on_load_finished(self, ok: bool):
        if not ok:
            return

        # Read all JSON layers from output dir
        terrain_data   = _read_json(
            os.path.join(self.output_dir, "terrain.json"),   {"vertices":[],"triangles":[]})
        buildings_data = _read_json(
            os.path.join(self.output_dir, "buildings.json"), [])
        roads_path = os.path.join(self.output_dir, "roads.json")
        roads_data = _read_json(roads_path, [])
        print(f"[Viewport] roads.json: {'EXISTS' if os.path.exists(roads_path) else 'MISSING'}, {len(roads_data)} segments")
        if roads_data:
            sample = roads_data[0]
            verts  = sample.get('vertices', [])
            tris   = sample.get('triangles', [])
            z_val  = verts[0][2] if verts else 'N/A'
            print(f"[Viewport] roads sample: {len(verts)} vertices, {len(tris)} triangles, Z[0]={z_val}")
        terrain_db     = _read_json(
            os.path.join(self.output_dir, "terrain_db.json"),[])

        # Read orthophoto as base64 data URL (avoids file:// fetch restriction)
        ortho_b64 = "null"
        ortho_path = os.path.join(self.output_dir, "orthophoto.png")
        if os.path.exists(ortho_path):
            try:
                with open(ortho_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                ortho_b64 = '"data:image/png;base64,' + b64 + '"'
                print(f"[Viewport] Orthophoto loaded ({len(b64)//1024} KB base64)")
            except Exception as e:
                print(f"[Viewport] Could not load orthophoto: {e}")

        # Serialize and inject all layers at once
        import json as _json
        t = _json.dumps(terrain_data)
        b = _json.dumps(buildings_data)
        r = _json.dumps(roads_data)
        d = _json.dumps(terrain_db)

        js = f"loadSceneFromData({t}, {b}, {r}, {d}, {ortho_b64});"
        QTimer.singleShot(300, lambda: self._run_js(js))