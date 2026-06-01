"""
ui/widgets/transport_bar.py — Barra de transporte (réplica ZaraRadio).

Botones clásicos coloreados (Reproducir, Parar, Pausa, Siguiente, retroceder,
avanzar, cue, pisador manual) + **barra de POSICIÓN** (seek) de la pista que
suena. El volumen NO está aquí: vive en el slider vertical de arriba.

El botón ≈ ("Fundido / pisador") es el PISADOR MANUAL: baja la música y la
mantiene baja hasta volver a pulsarlo (lo maneja el motor).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QSlider, QToolButton, QWidget

# (glyph, color, action_id, tooltip)
_BUTTONS = [
    ("▶", "#1ea83c", "media.play", "Reproducir"),
    ("■", "#e8b500", "media.stop", "Parar"),
    ("❚❚", "#1ea83c", "media.pause", "Pausa"),
    ("▶❙", "#e8b500", "media.next", "Siguiente"),
    ("◀◀", "#e23b2e", "media.rewind", "Retroceder"),
    ("▶▶", "#e23b2e", "media.forward", "Avanzar"),
    ("⟳", "#2a6fb5", "media.cue", "Cue"),
    ("≈", "#1ea83c", "media.duck", "Fundido / pisador manual (baja la música hasta volver a pulsar)"),
]

_RES = 1000   # resolución del slider de posición


class TransportBar(QWidget):
    action_triggered = pyqtSignal(str)   # emite el action_id
    seek_requested = pyqtSignal(float)   # posición 0.0..1.0

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 6, 2)
        layout.setSpacing(4)

        self.buttons: dict[str, QToolButton] = {}
        for glyph, color, action_id, tip in _BUTTONS:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setObjectName("transportButton")
            btn.setStyleSheet(f"QToolButton {{ color: {color}; }}")
            btn.setMinimumSize(34, 30)
            btn.clicked.connect(lambda _=False, a=action_id: self.action_triggered.emit(a))
            self.buttons[action_id] = btn
            layout.addWidget(btn)

        layout.addSpacing(10)
        self.slider = QSlider(Qt.Orientation.Horizontal)   # POSICIÓN de la pista
        self.slider.setObjectName("transportSlider")
        self.slider.setRange(0, _RES)
        self.slider.setValue(0)
        self.slider.setToolTip("Posición de la pista (arrastra para navegar)")
        self._seeking = False
        self.slider.sliderPressed.connect(self._on_press)
        self.slider.sliderReleased.connect(self._on_release)
        layout.addWidget(self.slider, 1)

    # ------------------------------------------------------------------ seek
    def _on_press(self) -> None:
        self._seeking = True

    def _on_release(self) -> None:
        self._seeking = False
        self.seek_requested.emit(self.slider.value() / _RES)

    def set_position(self, fraction: float) -> None:
        """Mueve la barra según la posición de reproducción (si el usuario no arrastra)."""
        if self._seeking:
            return
        v = max(0, min(_RES, int(fraction * _RES)))
        if v != self.slider.value():
            self.slider.blockSignals(True)
            self.slider.setValue(v)
            self.slider.blockSignals(False)

    def set_ducked(self, on: bool) -> None:
        """Resalta el botón de pisador manual cuando está activo."""
        btn = self.buttons.get("media.duck")
        if btn:
            btn.setStyleSheet("QToolButton { color: #ffffff; background: #e23b2e; }"
                              if on else "QToolButton { color: #1ea83c; }")
