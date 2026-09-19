"""
Splash screen: shown on startup, checks internet connection in background,
then transitions to the main window.
"""

import math
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal, QTimer,
    QPropertyAnimation, QEasingCurve
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QApplication, QGraphicsOpacityEffect
)
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath

from utils.network import has_internet_connection

# ── Palette ───────────────────────────────────────────────────────────────────
BG_PANEL     = QColor("#111827")
ACCENT_TEAL  = QColor("#00C9A7")
TEXT_PRIMARY = QColor("#F1F5F9")
TEXT_MUTED   = QColor("#64748B")
ERROR_RED    = QColor("#EF4444")


# ── Background thread ─────────────────────────────────────────────────────────

class ConnectionChecker(QThread):
    result = pyqtSignal(bool)

    def run(self):
        self.result.emit(has_internet_connection())


# ── Radar animation widget ────────────────────────────────────────────────────

class RadarWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self._phase  = 0.0
        self._rings  = [0.0, 0.33, 0.66]
        self._result = None   # None = scanning, True = ok, False = fail

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def _tick(self):
        self._phase = (self._phase + 0.012) % 1.0
        self._rings = [(r + 0.008) % 1.0 for r in self._rings]
        self.update()

    def set_result(self, ok):
        self._result = ok
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        max_r  = min(cx, cy) - 4

        # Background circle
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(BG_PANEL))
        p.drawEllipse(int(cx - max_r), int(cy - max_r), int(max_r * 2), int(max_r * 2))

        if self._result is None:
            # Pulsing rings
            for ring_pos in self._rings:
                r     = ring_pos * max_r
                alpha = int(255 * (1.0 - ring_pos) * 0.6)
                color = QColor(ACCENT_TEAL)
                color.setAlpha(alpha)
                p.setPen(QPen(color, 1.5))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

            # Crosshair
            dim = QColor(ACCENT_TEAL.red(), ACCENT_TEAL.green(), ACCENT_TEAL.blue(), 60)
            p.setPen(QPen(dim, 1))
            p.drawLine(int(cx), int(cy - max_r), int(cx), int(cy + max_r))
            p.drawLine(int(cx - max_r), int(cy), int(cx + max_r), int(cy))

            # Sweep line
            angle   = self._phase * 2 * math.pi
            sweep_x = cx + max_r * math.cos(angle)
            sweep_y = cy + max_r * math.sin(angle)
            p.setPen(QPen(ACCENT_TEAL, 1.5))
            p.drawLine(int(cx), int(cy), int(sweep_x), int(sweep_y))

        elif self._result:
            # Checkmark
            p.setPen(QPen(ACCENT_TEAL, 3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            path = QPainterPath()
            path.moveTo(cx - 28, cy)
            path.lineTo(cx - 8,  cy + 22)
            path.lineTo(cx + 32, cy - 26)
            p.drawPath(path)
            p.setPen(QPen(ACCENT_TEAL, 2))
            p.setBrush(Qt.NoBrush)
            r = max_r - 4
            p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        else:
            # X mark
            p.setPen(QPen(ERROR_RED, 3, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(int(cx - 26), int(cy - 26), int(cx + 26), int(cy + 26))
            p.drawLine(int(cx + 26), int(cy - 26), int(cx - 26), int(cy + 26))
            p.setPen(QPen(ERROR_RED, 2))
            p.setBrush(Qt.NoBrush)
            r = max_r - 4
            p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))

        p.end()


# ── Splash window ─────────────────────────────────────────────────────────────

class SplashScreen(QWidget):
    launch_main = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(520, 420)
        self._center_on_screen()
        self._build_ui()
        self._start_check()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width()  - self.width())  // 2,
            (screen.height() - self.height()) // 2,
        )

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.card = QWidget(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet("""
            QWidget#card {
                background: #111827;
                border-radius: 16px;
                border: 1px solid #1E293B;
            }
        """)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(40, 40, 40, 36)
        card_layout.setSpacing(0)

        # Title
        title = QLabel("DIGITAL TWIN")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            color: #F1F5F9; font-size: 28px; font-weight: 700;
            letter-spacing: 6px; font-family: 'Segoe UI', sans-serif;
        """)
        sub = QLabel("Finland Terrain Engine")
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet("""
            color: #00C9A7; font-size: 12px; letter-spacing: 3px;
            font-family: 'Segoe UI', monospace; margin-top: 4px;
        """)
        card_layout.addWidget(title)
        card_layout.addWidget(sub)
        card_layout.addSpacing(32)

        # Radar
        self.radar = RadarWidget()
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.radar)
        row.addStretch()
        card_layout.addLayout(row)
        card_layout.addSpacing(24)

        # Status text
        self.status_label = QLabel("Checking network connection...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #64748B; font-size: 13px; font-family: 'Segoe UI', sans-serif;")
        card_layout.addWidget(self.status_label)
        card_layout.addSpacing(24)

        # Buttons (hidden until needed)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_retry = QPushButton("Retry")
        self.btn_retry.setFixedHeight(40)
        self.btn_retry.setStyleSheet("""
            QPushButton       { background:transparent; border:1.5px solid #00C9A7;
                                border-radius:8px; color:#00C9A7; font-size:13px; padding:0 24px; }
            QPushButton:hover { background:#0A2420; }
        """)
        self.btn_retry.clicked.connect(self._start_check)
        self.btn_retry.hide()

        self.btn_exit = QPushButton("Exit")
        self.btn_exit.setFixedHeight(40)
        self.btn_exit.setStyleSheet("""
            QPushButton       { background:transparent; border:1.5px solid #64748B;
                                border-radius:8px; color:#64748B; font-size:13px; padding:0 24px; }
            QPushButton:hover { background:#1A1A2A; }
        """)
        self.btn_exit.clicked.connect(QApplication.quit)
        self.btn_exit.hide()

        btn_row.addStretch()
        btn_row.addWidget(self.btn_retry)
        btn_row.addWidget(self.btn_exit)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        root.addWidget(self.card)

        # Fade-in animation
        self._fx = QGraphicsOpacityEffect(self.card)
        self.card.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"opacity")
        self._anim.setDuration(600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.start()

    def _start_check(self):
        self.btn_retry.hide()
        self.btn_exit.hide()
        self.radar.set_result(None)
        self._set_status("Checking network connection...", TEXT_MUTED)

        self._checker = ConnectionChecker()
        self._checker.result.connect(self._on_check_result)
        self._checker.start()

    def _on_check_result(self, ok: bool):
        self.radar.set_result(ok)
        if ok:
            self._set_status("Connection established — launching...", ACCENT_TEAL)
            QTimer.singleShot(1200, self._launch)
        else:
            self._set_status(
                "No internet connection detected.\n"
                "The map and terrain data require an active connection.",
                ERROR_RED
            )
            self.btn_retry.show()
            self.btn_exit.show()

    def _set_status(self, text: str, color: QColor = TEXT_MUTED):
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {color.name()}; font-size: 13px; font-family: 'Segoe UI', sans-serif;"
        )

    def _launch(self):
        self.launch_main.emit()
        self.close()