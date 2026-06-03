"""
ui/widgets/transport_bar.py — Barra de transporte (réplica ZaraRadio).

Botones clásicos coloreados (Reproducir, Parar, Pausa, Siguiente, retroceder,
avanzar, cue, pisador manual) + **barra de POSICIÓN** (seek) de la pista que
suena. El volumen NO está aquí: vive en el slider vertical de arriba.

El botón ≈ ("Fundido / pisador") es el PISADOR MANUAL: baja la música y la
mantiene baja hasta volver a pulsarlo (lo maneja el motor).
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

from .seek_slider import SeekSlider

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

# Toggles por-cuña con estado visible (glyph, action_id, tooltip):
_TOGGLES = [
    ("🔁", "media.cyclic", "Cíclico: repite la misma cuña una y otra vez"),
    ("🗑", "media.delete_on_play", "Borrar al reproducir: elimina la cuña al terminar"),
    ("▶■", "media.stop_after", "Parar tras la actual: para al acabar la cuña"),
]


class TransportBar(QWidget):
    action_triggered = pyqtSignal(str)   # emite el action_id
    seek_requested = pyqtSignal(float)   # posición 0.0..1.0
    mode_toggled = pyqtSignal(str, bool)  # (action_id de toggle, activo)

    def __init__(self, parent=None, stacked: bool = False) -> None:
        """`stacked=True` pone la regleta de POSICIÓN en su PROPIA fila (debajo de los
        botones), para paneles estrechos como la planilla auxiliar (la regleta tiene
        todo el ancho y se puede manipular bien)."""
        super().__init__(parent)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(4)

        self.buttons: dict[str, QToolButton] = {}
        for glyph, color, action_id, tip in _BUTTONS:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setObjectName("transportButton")
            btn.setStyleSheet(f"QToolButton {{ color: {color}; }}")
            btn.setMinimumSize(28 if stacked else 34, 30)
            if stacked:
                btn.setProperty("compact", "true")
            btn.clicked.connect(lambda _=False, a=action_id: self.action_triggered.emit(a))
            self.buttons[action_id] = btn
            btn_row.addWidget(btn)

        # --- Toggles por-cuña (estado activado/desactivado visible) ---
        self.toggles: dict[str, QToolButton] = {}
        for glyph, action_id, tip in _TOGGLES:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setObjectName("transportToggle")
            btn.setCheckable(True)
            btn.setMinimumSize(30 if stacked else 38, 30)
            if stacked:
                btn.setProperty("compact", "true")
            btn.toggled.connect(lambda on, a=action_id: self.mode_toggled.emit(a, on))
            self.toggles[action_id] = btn
            btn_row.addWidget(btn)

        # POSICIÓN de la pista: clic = salto exacto, sin adelantar audio en vivo,
        # y reproduce desde donde se suelta (ver seek_slider.SeekSlider).
        self.slider = SeekSlider()
        self.slider.setObjectName("transportSlider")
        self.slider.seek_committed.connect(self.seek_requested)

        if stacked:
            outer = QVBoxLayout(self)
            outer.setContentsMargins(4, 2, 6, 2)
            outer.setSpacing(3)
            btn_row.addStretch(1)
            outer.addLayout(btn_row)
            outer.addWidget(self.slider)
        else:
            outer = QHBoxLayout(self)
            outer.setContentsMargins(4, 2, 6, 2)
            outer.setSpacing(4)
            outer.addLayout(btn_row)
            outer.addSpacing(10)
            outer.addWidget(self.slider, 1)

    # ------------------------------------------------------------------ seek
    def set_position(self, fraction: float) -> None:
        """Mueve la barra según la posición de reproducción (si el usuario no arrastra)."""
        self.slider.set_position(fraction)

    def set_ducked(self, on: bool) -> None:
        """Resalta el botón de pisador manual cuando está activo."""
        btn = self.buttons.get("media.duck")
        if btn:
            btn.setStyleSheet("QToolButton { color: #ffffff; background: #e23b2e; }"
                              if on else "QToolButton { color: #1ea83c; }")

    def set_mode_checked(self, action_id: str, checked: bool) -> None:
        """Sincroniza el estado de un toggle desde el motor (sin re-emitir)."""
        btn = self.toggles.get(action_id)
        if btn and btn.isChecked() != checked:
            btn.blockSignals(True)
            btn.setChecked(checked)
            btn.blockSignals(False)
