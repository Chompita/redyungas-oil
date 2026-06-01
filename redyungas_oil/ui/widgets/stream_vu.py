"""
ui/widgets/stream_vu.py — Visualizador de decibelios L/R estilo Opticodec.

Dos barras horizontales (L arriba, R abajo) con escala en dBFS (-40 → 0),
marcas como las de Opticodec (-30 -24 -18 -12 -6 0), zonas de color
(verde → ámbar → rojo), retención de pico y aviso de CLIP (saturación).

`set_levels(rms_l, rms_r, peak_l, peak_r)` recibe dBFS YA con la ganancia
aplicada por el panel, de modo que el medidor refleja el sonido que sale al aire.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter
from PyQt6.QtWidgets import QWidget

from ...core import constants as C

_LABEL_W = 14
_SCALE_H = 14
_PEAK_DECAY_DB = 0.8      # caída del pico por refresco
_CLIP_DB = -0.3           # a partir de aquí se considera saturación


class StreamVuMeter(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._lo = float(C.STREAM_VU_MIN_DB)
        self._hi = float(C.STREAM_VU_MAX_DB)
        self._rms = [self._lo, self._lo]
        self._peak = [self._lo, self._lo]
        self._hold = [self._lo, self._lo]
        self._clip = [False, False]
        self.setMinimumSize(220, 56)
        # Decaimiento suave del pico aunque no lleguen muestras nuevas.
        self._decay = QTimer(self)
        self._decay.timeout.connect(self._decay_peaks)
        self._decay.start(60)

    # ------------------------------------------------------------------ datos
    def set_levels(self, rms_l: float, rms_r: float, peak_l: float, peak_r: float) -> None:
        self._rms = [self._clamp(rms_l), self._clamp(rms_r)]
        for i, pk in enumerate((peak_l, peak_r)):
            pk = self._clamp(pk)
            self._peak[i] = pk
            if pk > self._hold[i]:
                self._hold[i] = pk
            if pk >= _CLIP_DB:
                self._clip[i] = True
        self.update()

    def reset_clip(self) -> None:
        self._clip = [False, False]
        self.update()

    def _decay_peaks(self) -> None:
        changed = False
        for i in range(2):
            if self._hold[i] > self._lo:
                self._hold[i] = max(self._lo, self._hold[i] - _PEAK_DECAY_DB)
                changed = True
            if self._rms[i] > self._lo:
                self._rms[i] = max(self._lo, self._rms[i] - _PEAK_DECAY_DB * 1.5)
                changed = True
        if changed:
            self.update()

    def _clamp(self, db: float) -> float:
        return max(self._lo, min(self._hi, db))

    def _db_to_x(self, db: float, x0: int, w: int) -> float:
        frac = (db - self._lo) / (self._hi - self._lo)
        return x0 + max(0.0, min(1.0, frac)) * w

    # ------------------------------------------------------------------ pintura
    def _paint_bar(self, p: QPainter, x: int, y: int, w: int, h: int, idx: int) -> None:
        p.fillRect(x, y, w, h, QColor("#0a0a0a"))
        # Relleno hasta el RMS, con gradiente de zonas.
        fill = int(self._db_to_x(self._rms[idx], x, w) - x)
        if fill > 0:
            grad = QLinearGradient(x, 0, x + w, 0)
            grad.setColorAt(0.0, QColor("#1ea83c"))
            grad.setColorAt(0.62, QColor("#7bd13a"))
            grad.setColorAt(0.80, QColor("#f4d000"))
            grad.setColorAt(0.93, QColor("#ff8c1a"))
            grad.setColorAt(1.0, QColor("#e23b2e"))
            p.fillRect(x, y, fill, h, grad)
        # Segmentos tipo LED.
        p.setPen(QColor(0, 0, 0, 110))
        seg = max(2, w // 40)
        for i in range(1, w // seg):
            p.drawLine(x + i * seg, y, x + i * seg, y + h)
        # Retención de pico (línea blanca).
        px = int(self._db_to_x(self._hold[idx], x, w))
        if self._hold[idx] > self._lo:
            p.setPen(QColor("#ffffff"))
            p.drawLine(px, y, px, y + h)

    def paintEvent(self, event) -> None:  # noqa: N802 (API Qt)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        f = QFont(); f.setPointSize(7); p.setFont(f)

        x0 = _LABEL_W
        bar_w = self.width() - x0 - 18          # deja sitio al recuadro CLIP
        usable_h = self.height() - _SCALE_H
        bar_h = (usable_h - 6) // 2

        # Etiquetas L / R
        p.setPen(QColor("#cfcfcf"))
        p.drawText(0, 1, _LABEL_W, bar_h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, "L")
        p.drawText(0, 1 + bar_h + 4, _LABEL_W, bar_h, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignHCenter, "R")

        self._paint_bar(p, x0, 1, bar_w, bar_h, 0)
        self._paint_bar(p, x0, 1 + bar_h + 4, bar_w, bar_h, 1)

        # Recuadros CLIP (uno por canal, a la derecha).
        clip_x = x0 + bar_w + 3
        for idx, y in ((0, 1), (1, 1 + bar_h + 4)):
            on = self._clip[idx]
            p.fillRect(QRectF(clip_x, y, 13, bar_h), QColor("#e23b2e") if on else QColor("#2a0d0b"))

        # Escala de dB (marcas de Opticodec)
        p.setPen(QColor("#9a9a9a"))
        sy = usable_h + 2
        for tick in C.STREAM_VU_TICKS:
            tx = int(self._db_to_x(float(tick), x0, bar_w))
            p.drawLine(tx, usable_h - 1, tx, usable_h + 1)
            label = str(tick)
            align = Qt.AlignmentFlag.AlignVCenter
            tw = p.fontMetrics().horizontalAdvance(label)
            lx = min(max(tx - tw // 2, x0), x0 + bar_w - tw)
            p.drawText(lx, sy, tw + 2, _SCALE_H, align, label)
        p.end()
