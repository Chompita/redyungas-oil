"""
audio/crossfade.py — Fundidos por rampa de volumen (FASE 2 / reusado en FASE 4).

CrossfadeController hace la transición entre dos reproductores VLC (saliente ->
entrante) subiendo/bajando el volumen en pasos con un QTimer en el hilo Qt.

Limitación: es una mezcla en la capa de audio del SO (dos instancias sonando a la
vez con volúmenes complementarios), no un mixdown de un solo grafo. Suficiente para
radio. Duración por defecto: core.constants.CROSSFADE_MS.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class CrossfadeController(QObject):
    finished = pyqtSignal()

    def __init__(self, player_out, player_in, duration_ms: int,
                 target_volume: int = 100, interval_ms: int = 50, parent=None) -> None:
        super().__init__(parent)
        self._out = player_out
        self._in = player_in
        self._target = max(0, min(100, target_volume))
        self._interval = max(10, interval_ms)
        self._steps = max(1, duration_ms // self._interval)
        self._i = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        # El entrante arranca en silencio; el saliente en el volumen objetivo.
        try:
            self._in.audio_set_volume(0)
            self._out.audio_set_volume(self._target)
        except Exception:
            pass
        self._timer.start(self._interval)

    def cancel(self) -> None:
        self._timer.stop()

    def _tick(self) -> None:
        self._i += 1
        t = self._i / self._steps
        vol_in = int(self._target * t)
        vol_out = int(self._target * (1.0 - t))
        try:
            self._in.audio_set_volume(vol_in)
            self._out.audio_set_volume(vol_out)
        except Exception:
            pass
        if self._i >= self._steps:
            self._timer.stop()
            try:
                self._in.audio_set_volume(self._target)
                self._out.audio_set_volume(0)
            except Exception:
                pass
            self.finished.emit()
