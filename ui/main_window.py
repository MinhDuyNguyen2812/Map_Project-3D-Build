"""
Main application window: embeds the Leaflet map, handles user interaction,
and connects to the pipeline worker.
"""

import os
import socket
from PyQt5.QtCore import QObject, pyqtSlot, QUrl, Qt
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSlider, QSizePolicy,
    QMessageBox, QProgressBar, QFrame
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWebChannel import QWebChannel

from pipeline.worker import PipelineWorker
from utils.network import has_internet_connection
from ui.viewport_window import ViewportWindow


class MapBridge(QObject):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    @pyqtSlot(float, float, float)
    def receive_coordinates(self, lat: float, lon: float, radius: float):
        self._callback(lat, lon, radius)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital Twin Finland")
        self.resize(1100, 780)

        self.selected_lat    = None
        self.selected_lon    = None
        self.selected_radius = 1000
        self._worker         = None
        self._viewport       = None

        self._build_ui()
        self._check_connection()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Map view
        self.map_view = QWebEngineView()
        html_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "map_view.html")
        self.map_view.load(QUrl.fromLocalFile(html_path))
        self.map_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.map_view)

        # Wire JS <-> Python channel
        self.channel = QWebChannel()
        self.bridge  = MapBridge(self._on_coords_received)
        self.channel.registerObject("bridge", self.bridge)
        self.map_view.page().setWebChannel(self.channel)

        # Divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: #2D3748;")
        layout.addWidget(line)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(4)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar        { background: #1A202C; border: none; }
            QProgressBar::chunk { background: #00C9A7; }
        """)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # Control bar
        ctrl = QWidget()
        ctrl.setStyleSheet("background: #111827; padding: 6px 12px;")
        ctrl_layout = QHBoxLayout(ctrl)
        ctrl_layout.setContentsMargins(12, 6, 12, 6)

        self.info_label = QLabel("Click on the map to select an area.")
        self.info_label.setStyleSheet("color: #94A3B8; font-size: 13px;")
        ctrl_layout.addWidget(self.info_label, stretch=3)

        ctrl_layout.addWidget(self._muted_label("Radius (m):"))

        self.radius_slider = QSlider(Qt.Horizontal)
        self.radius_slider.setMinimum(500)
        self.radius_slider.setMaximum(2000)
        self.radius_slider.setValue(1000)
        self.radius_slider.setSingleStep(100)
        self.radius_slider.setFixedWidth(160)
        self.radius_slider.valueChanged.connect(self._on_radius_changed)
        ctrl_layout.addWidget(self.radius_slider)

        self.radius_label = QLabel("1000 m")
        self.radius_label.setStyleSheet("color: #CBD5E1; font-size: 13px; min-width: 52px;")
        ctrl_layout.addWidget(self.radius_label)

        ctrl_layout.addSpacing(16)

        self.confirm_btn = QPushButton("Generate 3D Model")
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.setFixedHeight(36)
        self.confirm_btn.setStyleSheet("""
            QPushButton          { background:#00C9A7; color:#0A0E1A; border:none;
                                   border-radius:6px; font-weight:600; font-size:13px;
                                   padding:0 20px; }
            QPushButton:hover    { background:#00B396; }
            QPushButton:disabled { background:#1E293B; color:#475569; }
        """)
        self.confirm_btn.clicked.connect(self._on_confirm)
        ctrl_layout.addWidget(self.confirm_btn)

        self.network_btn = QPushButton("Check Network")
        self.network_btn.setFixedHeight(36)
        self.network_btn.setStyleSheet("""
            QPushButton       { background:transparent; border:1px solid #334155;
                                border-radius:6px; color:#64748B; font-size:13px;
                                padding:0 14px; }
            QPushButton:hover { border-color:#64748B; color:#94A3B8; }
        """)
        self.network_btn.clicked.connect(self._retry_connection)
        ctrl_layout.addWidget(self.network_btn)

        layout.addWidget(ctrl)

    def _muted_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color: #64748B; font-size: 13px;")
        return lbl

    # ── Network ───────────────────────────────────────────────────────────────

    def _check_connection(self):
        if not has_internet_connection():
            self._set_status("⚠  No internet connection detected.", error=True)
            self.confirm_btn.setEnabled(False)

    def _retry_connection(self):
        if has_internet_connection():
            self._set_status("Connected — reloading map...")
            self.map_view.reload()
            if self.selected_lat is not None:
                self.confirm_btn.setEnabled(True)
        else:
            QMessageBox.warning(
                self, "No Connection",
                "Still no internet connection detected.\n"
                "Please check your network and try again."
            )

    # ── Map interaction ───────────────────────────────────────────────────────

    def _on_coords_received(self, lat: float, lon: float, radius: float):
        self.selected_lat    = lat
        self.selected_lon    = lon
        self.selected_radius = radius
        self._set_status(
            f"Selected   lat {lat:.5f}   lon {lon:.5f}   radius {radius:.0f} m"
        )
        self.confirm_btn.setEnabled(True)

    def _on_radius_changed(self, value: int):
        self.radius_label.setText(f"{value} m")
        self.map_view.page().runJavaScript(f"updateRadius({value});")
        if self.selected_lat is not None:
            self.selected_radius = value

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _on_confirm(self):
        if self.selected_lat is None:
            return

        self.confirm_btn.setEnabled(False)
        self.radius_slider.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_bar.show()

        self._worker = PipelineWorker(
            self.selected_lat,
            self.selected_lon,
            self.selected_radius
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_pipeline_done)
        self._worker.failed.connect(self._on_pipeline_failed)
        self._worker.start()

    def _on_progress(self, percent: int, message: str):
        self.progress_bar.setValue(percent)
        self._set_status(message)

    def _on_pipeline_done(self, scene_usd: str):
        self.progress_bar.hide()
        self.radius_slider.setEnabled(True)
        self.confirm_btn.setEnabled(True)
        self._set_status(f"✓  Scene ready →  {scene_usd}")

        self._viewport = ViewportWindow(
            output_dir=os.path.abspath("./output"),
            parent=self
        )
        self._viewport.show()

    def _on_pipeline_failed(self, error: str):
        self.progress_bar.hide()
        self.radius_slider.setEnabled(True)
        self.confirm_btn.setEnabled(True)
        self._set_status(f"⚠  Error: {error}", error=True)
        QMessageBox.critical(self, "Pipeline Error", f"Something went wrong:\n\n{error}")

    def _set_status(self, text: str, error: bool = False):
        color = "#EF4444" if error else "#94A3B8"
        self.info_label.setStyleSheet(f"color: {color}; font-size: 13px;")
        self.info_label.setText(text)