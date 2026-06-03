"""
ui/widgets/seek_slider.py — Regleta de POSICIÓN (seek) con el comportamiento que
pidió el operador, reutilizable por la planilla principal y la auxiliar:

* **Clic = salto exacto a esa posición** (sin los "saltos" por pasos de página del
  QSlider normal: el manillar va justo a donde pinchas).
* **NO se adelanta el audio en vivo** mientras arrastras: solo se mueve el manillar.
* **Al soltar**, recién entonces se reproduce **exactamente desde donde lo soltaste**
  (`seek_committed`).

Mientras el usuario arrastra, las actualizaciones de posición que llegan del motor
se ignoran (`set_position`), para que el manillar no "pelee" con el dedo.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QSlider, QStyle

_RES = 1000   # resolución interna del slider


class SeekSlider(QSlider):
    seek_committed = pyqtSignal(float)   # posición final 0.0..1.0 (al soltar/clicar)

    def __init__(self, parent=None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setRange(0, _RES)
        self.setValue(0)
        self.setToolTip("Posición de la cuña (clic o arrastra; reproduce al soltar)")
        self._dragging = False

    # ------------------------------------------------------ valor desde el ratón
    def _value_at(self, pos) -> int:
        opt_min, opt_max = self.minimum(), self.maximum()
        span = self.width() if self.orientation() == Qt.Orientation.Horizontal else self.height()
        coord = pos.x() if self.orientation() == Qt.Orientation.Horizontal else (span - pos.y())
        val = QStyle.sliderValueFromPosition(opt_min, opt_max, int(coord), span)
        return max(opt_min, min(opt_max, val))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self.setValue(self._value_at(event.position().toPoint()))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging:
            # Solo mover el manillar; NO se hace seek en vivo (no adelanta el audio).
            self.setValue(self._value_at(event.position().toPoint()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._dragging and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setValue(self._value_at(event.position().toPoint()))
            self.seek_committed.emit(self.value() / _RES)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # --------------------------------------------------- actualización del motor
    def set_position(self, fraction: float) -> None:
        """Mueve la barra siguiendo la reproducción (si el usuario no la está tocando)."""
        if self._dragging:
            return
        v = max(0, min(_RES, int(fraction * _RES)))
        if v != self.value():
            self.blockSignals(True)
            self.setValue(v)
            self.blockSignals(False)

    def is_dragging(self) -> bool:
        return self._dragging
