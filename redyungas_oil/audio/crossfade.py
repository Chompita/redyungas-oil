"""
audio/crossfade.py — Fundidos por rampa de volumen (FASE 2 / reusado en FASE 4).

CrossfadeController hace la transición entre dos reproductores VLC (saliente ->
entrante) subiendo/bajando el volumen con un QTimer en el hilo Qt.

Dos detalles clave que evitan los cortes en el momento de la transición:

* **Curva de potencia constante (equal-power):** se usa sin/cos en lugar de una
  rampa LINEAL. Una rampa lineal suma potencias `t² + (1-t)²`, que cae a 0.5
  (-3 dB) en el centro → se oye un BACHE/corte de volumen a mitad del fundido.
  Con `sin(t·π/2)` / `cos(t·π/2)` la potencia total es constante: el cruce suena
  parejo, sin hueco.
* **Pre-roll:** el reproductor entrante tarda unos ms en empezar a sacar audio.
  VLC IGNORA `audio_set_volume` mientras no hay salida (gotcha conocido), así que
  si se rampa de inmediato, el entrante puede sonar un instante a volumen MÁXIMO
  (golpe) antes de que la rampa "agarre". Por eso se espera a que el entrante
  esté realmente `Playing` (con un tope de seguridad) antes de empezar a rampar,
  manteniéndolo en 0 mientras tanto.

Limitación: es una mezcla en la capa de audio del SO (dos instancias sonando a la
vez con volúmenes complementarios), no un mixdown de un solo grafo. Suficiente para
radio. Duración por defecto: core.constants.CROSSFADE_MS.
"""

from __future__ import annotations

import math

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

# Tiempo máximo de espera a que el entrante empiece a sonar antes de rampar igual.
_PREROLL_MAX_MS = 2000


class CrossfadeController(QObject):
    finished = pyqtSignal()

    def __init__(self, player_out, player_in, duration_ms: int,
                 target_volume: int = 100, interval_ms: int = 25, parent=None) -> None:
        super().__init__(parent)
        self._out = player_out
        self._in = player_in
        self._target = max(0, min(100, target_volume))
        self._interval = max(10, interval_ms)
        self._steps = max(1, duration_ms // self._interval)
        self._i = 0
        self._ramping = False        # True una vez superado el pre-roll
        self._wait_ticks = 0
        self._max_wait = max(1, _PREROLL_MAX_MS // self._interval)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self) -> None:
        # El entrante arranca en silencio; el saliente en el volumen objetivo.
        self._set(self._in, 0)
        self._set(self._out, self._target)
        self._timer.start(self._interval)

    def cancel(self) -> None:
        self._timer.stop()

    # ------------------------------------------------------------------ interno
    @staticmethod
    def _set(player, volume: int) -> None:
        try:
            player.audio_set_volume(int(volume))
        except Exception:
            pass

    def _in_playing(self) -> bool:
        try:
            return bool(self._in.is_playing())
        except Exception:
            return True

    def _tick(self) -> None:
        # --- Fase de pre-roll: esperar a que el entrante saque audio de verdad ---
        if not self._ramping:
            self._set(self._in, 0)        # mantenerlo mudo hasta que empiece
            self._wait_ticks += 1
            if self._in_playing() or self._wait_ticks >= self._max_wait:
                self._ramping = True
            return

        # --- Fase de rampa: cruce de potencia constante (equal-power) ---
        self._i += 1
        t = min(1.0, self._i / self._steps)
        gain_in = math.sin(t * math.pi / 2)
        gain_out = math.cos(t * math.pi / 2)
        self._set(self._in, self._target * gain_in)
        self._set(self._out, self._target * gain_out)
        if self._i >= self._steps:
            self._timer.stop()
            self._set(self._in, self._target)
            self._set(self._out, 0)
            self.finished.emit()
