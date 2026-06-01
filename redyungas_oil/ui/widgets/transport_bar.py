"""
ui/widgets/transport_bar.py — Barra de transporte (réplica ZaraRadio).

Botones clásicos coloreados (Reproducir, Parar, Pausa, Siguiente, retroceder,
avanzar, cue, crossfade) + slider horizontal de volumen/posición. En Fase 2 se
conectan al motor de audio.
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
    ("≈", "#1ea83c", "media.crossfade", "Fundido / crossfade"),
]


class TransportBar(QWidget):
    action_triggered = pyqtSignal(str)   # emite el action_id
    volume_changed = pyqtSignal(int)

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
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("transportSlider")
        self.slider.setRange(0, 100)
        self.slider.setValue(85)
        self.slider.valueChanged.connect(self.volume_changed.emit)
        layout.addWidget(self.slider, 1)
