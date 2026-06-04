"""
ui/widgets/onair_panel.py — Paneles "Al aire" y "Siguiente" (réplica ZaraRadio).

Fila de estado:
  * **"Al aire"**: badge que SOLO parpadea en varios colores cuando el PUERTO está
    EMITIENDO o RECIBIENDO señal (`set_air_active`); en reposo queda estático.
  * **"Reproduciendo ahora"**: neutro en reposo, VERDE al sonar.
  * **"Grabando"** + 3 controles de grabación: **grabar/pausar-reanudar** (mismo
    archivo), **detener** (finaliza) y **opciones** (abre la ventana de ajustes).
+ título grande de la pista actual + "Tiempo restante" (LCD) + VU L/R + "Acaba a las".
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .vu_widget import VuMeterWidget

# Paleta "Al aire": colores vivos pero limpios por los que va rotando el badge.
_AIR_COLORS = ["#e23b2e", "#e8800f", "#1ea83c", "#2a6fb5", "#8e44ad", "#16a085"]


class _TitleDisplay(QFrame):
    """Recuadro blanco hundido con el título grande, como los displays de ZaraRadio."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("titleDisplay")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        self.label = QLabel(text)
        self.label.setObjectName("titleText")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    def set_title(self, text: str) -> None:
        self.label.setText(text)


class OnAirPanel(QWidget):
    record_requested = pyqtSignal()       # grabar / pausar / reanudar (mismo botón)
    stop_requested = pyqtSignal()         # detener (finalizar) la grabación
    rec_options_requested = pyqtSignal()  # abrir ventana de opciones de grabación

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(3)

        # --- Fila de estado superior ---
        top = QHBoxLayout()
        top.setSpacing(6)

        # "Al aire": parpadea en colores SOLO cuando el PUERTO emite/recibe.
        self.air = QLabel("Al aire")
        self.air.setObjectName("onAirLive")
        self.air.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._air_i = 0
        self._air_active = False
        self._air_timer = QTimer(self)
        self._air_timer.timeout.connect(self._air_tick)
        self._air_idle_style()        # arranca estático (sin parpadeo)

        # "Reproduciendo ahora": gris en reposo, VERDE cuando suena (sin rojo).
        self.playing = QLabel("Reproduciendo ahora")
        self.playing.setObjectName("badgePlaying")

        # "Grabando": gris en reposo, parpadea ROJO al grabar, ámbar en pausa.
        self.recording = QLabel("Grabando")
        self.recording.setObjectName("badgeRecord")

        # --- Controles de grabación: grabar/pausar · detener · opciones ---
        self.btn_record = QToolButton()
        self.btn_record.setObjectName("recordDot")
        self.btn_record.setText("●")
        self.btn_record.setToolTip("Grabar")
        self.btn_record.clicked.connect(self.record_requested)
        self.btn_stop = QToolButton()
        self.btn_stop.setObjectName("recordStop")
        self.btn_stop.setText("■")
        self.btn_stop.setToolTip("Detener (finaliza la grabación)")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.stop_requested)
        self.btn_opts = QToolButton()
        self.btn_opts.setObjectName("recordOpts")
        self.btn_opts.setText("⚙")
        self.btn_opts.setToolTip("Opciones de grabación (carpeta, formato, calidad)")
        self.btn_opts.clicked.connect(self.rec_options_requested)

        top.addWidget(self.air)
        top.addWidget(self.playing)
        top.addSpacing(8)
        top.addWidget(self.recording)
        top.addWidget(self.btn_record)
        top.addWidget(self.btn_stop)
        top.addWidget(self.btn_opts)
        top.addStretch(1)
        root.addLayout(top)

        # Título grande de la pista actual
        self.title = _TitleDisplay("00000001 FELIZ NAVIDAD-RED YUNGAS")
        root.addWidget(self.title, 1)

        # Fila inferior: tiempo restante | VU | acaba a las
        bottom = QGridLayout()
        bottom.setHorizontalSpacing(12)
        rem_tag = QLabel("Tiempo restante"); rem_tag.setObjectName("sectionTag")
        self.remaining = QLabel("00:15.5"); self.remaining.setObjectName("lcd")
        bottom.addWidget(rem_tag, 0, 0)
        bottom.addWidget(self.remaining, 1, 0)
        self.vu = VuMeterWidget()
        bottom.addWidget(self.vu, 0, 1, 2, 1)
        ends_tag = QLabel("Acaba a las"); ends_tag.setObjectName("sectionTag")
        self.ends_at = QLabel("23:46:01"); self.ends_at.setObjectName("lcdSmall")
        bottom.addWidget(ends_tag, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
        bottom.addWidget(self.ends_at, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)
        bottom.setColumnStretch(1, 1)
        root.addLayout(bottom)

        # Parpadeo de "Grabando".
        self._rec_blink = False
        self._rec_timer = QTimer(self)
        self._rec_timer.timeout.connect(self._rec_tick)

    # --------------------------------------------------------- "Al aire"
    def _air_idle_style(self) -> None:
        self.air.setStyleSheet(
            "QLabel#onAirLive { background-color: #d7d7d7; color: #6a6a6a; "
            "font-size: 8pt; font-weight: bold; padding: 1px 8px; border-radius: 3px; }")

    def _air_tick(self) -> None:
        color = _AIR_COLORS[self._air_i % len(_AIR_COLORS)]
        self._air_i += 1
        self.air.setStyleSheet(
            f"QLabel#onAirLive {{ background-color: {color}; color: #ffffff; "
            "font-size: 8pt; font-weight: bold; padding: 1px 8px; border-radius: 3px; }")

    def set_air_active(self, active: bool) -> None:
        """Parpadeo multicolor SOLO si el PUERTO emite o recibe; si no, estático."""
        active = bool(active)
        if active == self._air_active:
            return
        self._air_active = active
        if active:
            self._air_tick()
            self._air_timer.start(700)
        else:
            self._air_timer.stop()
            self._air_idle_style()

    # --------------------------------------------------------- "Grabando"
    def _rec_tick(self) -> None:
        self._rec_blink = not self._rec_blink
        if self._rec_blink:
            self.recording.setStyleSheet(
                "QLabel#badgeRecord { background-color: #e10000; color: #ffffff; "
                "font-size: 8pt; font-weight: bold; padding: 1px 6px; border-radius: 2px; }")
        else:
            self.recording.setStyleSheet(
                "QLabel#badgeRecord { background-color: #5a1414; color: #ffd5d5; "
                "font-size: 8pt; font-weight: bold; padding: 1px 6px; border-radius: 2px; }")

    # ----------------------------------------------------------- API del motor
    def set_now_playing(self, title: str) -> None:
        self.title.set_title(title)

    def set_remaining(self, text: str) -> None:
        self.remaining.setText(text)

    def set_ends_at(self, text: str) -> None:
        self.ends_at.setText(text)

    def set_playing_active(self, active: bool) -> None:
        self.playing.setObjectName("badgePlayingOn" if active else "badgePlaying")
        self.playing.style().unpolish(self.playing)
        self.playing.style().polish(self.playing)

    def set_record_state(self, state: str) -> None:
        """state: 'stopped' | 'recording' | 'paused'. Ajusta botones e indicador."""
        active = state in ("recording", "paused")
        self.btn_stop.setEnabled(active)
        self.btn_record.setProperty("recState", state)
        self.btn_record.style().unpolish(self.btn_record)
        self.btn_record.style().polish(self.btn_record)
        if state == "recording":
            self.btn_record.setText("❚❚"); self.btn_record.setToolTip("Pausar (sigue el mismo archivo)")
            self.recording.setText("Grabando")
            self._rec_blink = False; self._rec_tick(); self._rec_timer.start(500)
        elif state == "paused":
            self.btn_record.setText("▶"); self.btn_record.setToolTip("Reanudar (mismo archivo)")
            self._rec_timer.stop()
            self.recording.setText("En pausa")
            self.recording.setStyleSheet(
                "QLabel#badgeRecord { background-color: #c87f00; color: #ffffff; "
                "font-size: 8pt; font-weight: bold; padding: 1px 6px; border-radius: 2px; }")
        else:  # stopped
            self.btn_record.setText("●"); self.btn_record.setToolTip("Grabar")
            self._rec_timer.stop()
            self.recording.setText("Grabando")
            self.recording.setStyleSheet("")   # vuelve al estilo neutro del QSS


class NextPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(3)
        tag = QLabel("Siguiente")
        tag.setObjectName("sectionTag")
        root.addWidget(tag)
        self.title = _TitleDisplay("0000001 aaaaaaCuña 2 narcotráfico 52 segundos")
        root.addWidget(self.title, 1)

    def set_next(self, title: str) -> None:
        self.title.set_title(title)
