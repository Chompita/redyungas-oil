"""
ui/widgets/vu_widget.py — Barras VU L/R (réplica ZaraRadio).

Dos barras horizontales verdes (canal L arriba, R abajo). En Fase 2 se alimentan
con niveles reales del motor (audio/vu_meter.py); aquí aceptan set_levels(l, r)
con valores 0..1 y se pintan a mano.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget


class VuMeterWidget(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._l = 0.62          # nivel demo hasta la Fase 2
        self._r = 0.55
        self.setMinimumSize(180, 34)

    def set_levels(self, left: float, right: float) -> None:
        self._l = max(0.0, min(1.0, left))
        self._r = max(0.0, min(1.0, right))
        self.update()

    def _paint_bar(self, painter: QPainter, x: int, y: int, w: int, h: int, level: float) -> None:
        # Fondo del riel
        painter.fillRect(x, y, w, h, QColor("#0a0a0a"))
        fill_w = int(w * level)
        grad = QLinearGradient(x, 0, x + w, 0)
        grad.setColorAt(0.0, QColor("#1ea83c"))
        grad.setColorAt(0.75, QColor("#7bd13a"))
        grad.setColorAt(0.9, QColor("#f4d000"))
        grad.setColorAt(1.0, QColor("#e23b2e"))
        painter.fillRect(x, y, fill_w, h, grad)
        # Marcas verticales tenues (segmentos tipo VU)
        painter.setPen(QColor(0, 0, 0, 90))
        seg = max(1, w // 28)
        for i in range(1, 28):
            painter.drawLine(x + i * seg, y, x + i * seg, y + h)

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        painter = QPainter(self)
        painter.setPen(QColor("#444"))
        # Etiquetas L / R
        lbl_w = 12
        painter.drawText(0, 0, lbl_w, self.height() // 2, Qt.AlignmentFlag.AlignCenter, "L")
        painter.drawText(0, self.height() // 2, lbl_w, self.height() // 2,
                         Qt.AlignmentFlag.AlignCenter, "R")
        bar_x = lbl_w + 2
        bar_w = self.width() - bar_x - 1
        bar_h = (self.height() - 6) // 2
        self._paint_bar(painter, bar_x, 1, bar_w, bar_h, self._l)
        self._paint_bar(painter, bar_x, bar_h + 4, bar_w, bar_h, self._r)
        painter.end()
