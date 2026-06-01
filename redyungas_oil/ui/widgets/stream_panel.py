"""
ui/widgets/stream_panel.py — Panel emisor "PUERTO" (estilo Orban Opticodec).

Dos piezas:

* `StreamRail`  — pestaña vertical SIEMPRE visible en el borde derecho: el texto
  "PUERTO" de abajo hacia arriba y una flecha `»` (que pasa a `«` al abrir). Al
  pulsarla se despliega el panel.
* `StreamPanel` — el panel desplegable: cabecera tipo Opticodec, estado/URL,
  el visualizador de dB L/R (`StreamVuMeter`) y un control de **volumen/saturación
  independiente** del volumen de playout, más Emitir / Detener / Ajustes.

El panel no toca audio directamente: emite señales que conecta `MainWindow` al
`StreamEncoder` y recibe del `StreamMeter` los niveles crudos (les suma la
ganancia para que el medidor muestre la saturación real en vivo).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...core import constants as C
from .stream_vu import StreamVuMeter

RAIL_W = 26


class StreamRail(QWidget):
    """Pestaña vertical 'PUERTO »' del borde derecho (abre/cierra el panel)."""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._open = False
        self._hover = False
        self.setFixedWidth(RAIL_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Emisor de stream (PUERTO) — clic para abrir/cerrar")
        self.setObjectName("streamRail")

    def set_open(self, is_open: bool) -> None:
        self._open = is_open
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._open = not self._open
        self.toggled.emit(self._open)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True; self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False; self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        base = QColor("#2c5d8f") if not self._hover else QColor("#3a6fa8")
        p.fillRect(0, 0, w, h, base)
        p.setPen(QColor("#1b3e60"))
        p.drawLine(0, 0, 0, h)

        # Flecha arriba: » (cerrado, "abrir hacia la izquierda") / « (abierto)
        p.setPen(QColor("#ffffff"))
        af = QFont(); af.setPointSize(11); af.setBold(True); p.setFont(af)
        arrow = "«" if self._open else "»"   # « / »
        p.drawText(0, 4, w, 18, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, arrow)

        # Texto "PUERTO" vertical, de ABAJO hacia ARRIBA.
        p.save()
        p.translate(w // 2 + 5, h - 8)
        p.rotate(-90)
        tf = QFont(); tf.setPointSize(9); tf.setBold(True); p.setFont(tf)
        p.setPen(QColor("#ffffff"))
        p.drawText(0, 0, "PUERTO")
        p.restore()
        p.end()


class StreamPanel(QWidget):
    """Panel emisor desplegable (réplica funcional de Opticodec-PC)."""

    emit_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    gain_changed = pyqtSignal(float)     # dB (debounced)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("streamPanel")
        self.setFixedWidth(286)
        st = (config.get("stream", {}) or {})
        self._gain = float(st.get("gain_db", 0.0))

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # --- Cabecera estilo Opticodec ---
        banner = QFrame(); banner.setObjectName("streamBanner")
        bl = QVBoxLayout(banner); bl.setContentsMargins(8, 6, 8, 6); bl.setSpacing(0)
        title = QLabel("REDYUNGAS OIL"); title.setObjectName("streamBannerTitle")
        sub = QLabel("EMISOR · PUERTO"); sub.setObjectName("streamBannerSub")
        bl.addWidget(title); bl.addWidget(sub)
        root.addWidget(banner)

        codec = (st.get("codec", "mp3") or "mp3").upper()
        srv = (st.get("server_type", "shoutcast") or "shoutcast").upper()
        info = QLabel(f"{st.get('bitrate', 128)} kbps · "
                      f"{int(st.get('sample_rate', 44100))/1000:.1f} kHz · {codec}")
        info.setObjectName("streamInfo")
        root.addWidget(info)

        self.status = QLabel("● Desconectado"); self.status.setObjectName("streamStatusOff")
        root.addWidget(self.status)

        host = st.get("host", ""); port = int(st.get("port", 8032))
        url = QLabel(f"{srv}  ·  http://{host}:{port}")
        url.setObjectName("streamUrl"); url.setWordWrap(True)
        root.addWidget(url)

        # --- Visualizador de dB L/R ---
        self.vu = StreamVuMeter()
        root.addWidget(self.vu)

        # --- Control de volumen / saturación INDEPENDIENTE ---
        gain_tag = QLabel("Volumen de emisión (saturación)")
        gain_tag.setObjectName("sectionTag")
        root.addWidget(gain_tag)

        grow = QHBoxLayout(); grow.setSpacing(6)
        self._g_min = int(C.STREAM_GAIN_MIN_DB * 10)
        self._g_max = int(C.STREAM_GAIN_MAX_DB * 10)
        self.gain_slider = QSlider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(self._g_min, self._g_max)
        self.gain_slider.setValue(int(round(self._gain * 10)))
        self.gain_slider.setObjectName("gainSlider")
        self.gain_readout = QLabel(self._fmt_gain(self._gain))
        self.gain_readout.setObjectName("gainReadout")
        self.gain_readout.setFixedWidth(54)
        reset = QPushButton("0 dB"); reset.setFixedWidth(42)
        reset.setToolTip("Restablecer ganancia a 0 dB")
        grow.addWidget(self.gain_slider, 1)
        grow.addWidget(self.gain_readout, 0)
        grow.addWidget(reset, 0)
        root.addLayout(grow)

        # --- Botones Emitir / Detener / Ajustes ---
        brow = QHBoxLayout(); brow.setSpacing(6)
        self.btn_emit = QPushButton("▶ Emitir"); self.btn_emit.setObjectName("emitButton")
        self.btn_stop = QPushButton("■ Detener"); self.btn_stop.setObjectName("stopEmitButton")
        self.btn_stop.setEnabled(False)
        self.btn_settings = QPushButton("⚙"); self.btn_settings.setFixedWidth(34)
        self.btn_settings.setToolTip("Ajustes del emisor (servidor, códec, credenciales)")
        brow.addWidget(self.btn_emit, 1)
        brow.addWidget(self.btn_stop, 1)
        brow.addWidget(self.btn_settings, 0)
        root.addLayout(brow)

        foot = QLabel("Reemplaza a Orban Opticodec-PC")
        foot.setObjectName("streamFoot")
        root.addWidget(foot)
        root.addStretch(1)

        # --- Debounce de la ganancia (no relanzar ffmpeg en cada tick) ---
        self._gain_debounce = QTimer(self)
        self._gain_debounce.setSingleShot(True)
        self._gain_debounce.setInterval(280)
        self._gain_debounce.timeout.connect(lambda: self.gain_changed.emit(self._gain))

        # Señales
        self.gain_slider.valueChanged.connect(self._on_gain_slider)
        reset.clicked.connect(lambda: self.gain_slider.setValue(0))
        self.btn_emit.clicked.connect(self.emit_requested)
        self.btn_stop.clicked.connect(self.stop_requested)
        self.btn_settings.clicked.connect(self.settings_requested)

    # ------------------------------------------------------------------ API
    def _fmt_gain(self, db: float) -> str:
        return f"{db:+.1f} dB"

    def _on_gain_slider(self, value: int) -> None:
        self._gain = value / 10.0
        self.gain_readout.setText(self._fmt_gain(self._gain))
        self._gain_debounce.start()

    def gain_db(self) -> float:
        return self._gain

    def set_levels_raw(self, rms_l: float, rms_r: float, peak_l: float, peak_r: float) -> None:
        """Aplica la ganancia a los niveles crudos del medidor y los muestra."""
        g = self._gain
        self.vu.set_levels(rms_l + g, rms_r + g, peak_l + g, peak_r + g)

    def set_status(self, state: str) -> None:
        if state == "emitting":
            self.status.setText("● EN VIVO — emitiendo")
            self.status.setObjectName("streamStatusOn")
            self.btn_emit.setEnabled(False); self.btn_stop.setEnabled(True)
        elif state == "reconnecting":
            self.status.setText("● Reconectando…")
            self.status.setObjectName("streamStatusWarn")
            self.btn_emit.setEnabled(False); self.btn_stop.setEnabled(True)
        else:  # stopped
            self.status.setText("● Desconectado")
            self.status.setObjectName("streamStatusOff")
            self.btn_emit.setEnabled(True); self.btn_stop.setEnabled(False)
        # Forzar re-aplicación del QSS al cambiar objectName.
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
