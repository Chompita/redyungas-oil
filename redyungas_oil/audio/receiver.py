"""
audio/receiver.py — Receptor del stream, modo ESCLAVA (FASE 4).

Reproduce el stream del estudio (estilo Winamp) con un MediaPlayer VLC dedicado y
vigila la salud de la señal mediante un sondeo en el hilo Qt:
    - caída de conexión: estado VLC (Error/Ended) o atasco prolongado al conectar
    - señal "congelada": el tiempo de reproducción no avanza durante stall_seconds

Cuando se detecta pérdida emite `signal_lost`; mientras está perdida, REINTENTA
reconectar cada ~3 s (autoplay). Al recuperar la señal sana emite `signal_restored`.
El crossfade de vuelta lo coordina network/failover.py.

NOTA: la detección de "silencio con señal presente" (RMS) es un refinamiento
posterior; aquí se cubre la caída/atasco, que es el caso principal ("se pausa la
señal recibida").
"""

from __future__ import annotations

import vlc
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

_RETRY_S = 3.0
_POLL_MS = 500


class StreamReceiver(QObject):
    signal_lost = pyqtSignal()
    signal_restored = pyqtSignal()
    health_changed = pyqtSignal(str)     # "connecting" | "on_air" | "lost"

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        net = (config or {}).get("network", {}) or {}
        self._url = net.get("stream_url", "") or ""
        self._stall_limit = float(net.get("stall_seconds", 8))
        self._vlc = vlc.Instance("--no-video", "--quiet")
        self._player = self._vlc.media_player_new()
        self._volume = 100
        self._active = False
        self._lost = False
        self._ever_ok = False
        self._last_time = -1
        self._stall = 0.0
        self._retry = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)

    # --------------------------------------------------------------- API
    def player(self):
        return self._player

    def url(self) -> str:
        return self._url

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._player.audio_set_volume(self._volume)

    def start(self) -> None:
        self._active = True
        self._lost = False
        self._ever_ok = False
        self._last_time = -1
        self._stall = 0.0
        self._retry = 0.0
        self.health_changed.emit("connecting")
        self._open()
        self._timer.start(_POLL_MS)

    def stop(self) -> None:
        self._active = False
        self._timer.stop()
        self._player.stop()

    # --------------------------------------------------------------- interno
    def _open(self) -> None:
        if not self._url:
            return
        self._player.set_media(self._vlc.media_new(self._url))
        self._player.audio_set_volume(self._volume)
        self._player.play()

    def _poll(self) -> None:
        if not self._active:
            return
        state = self._player.get_state()
        if state == vlc.State.Playing:
            t = self._player.get_time()
            if t == self._last_time and t >= 0:
                self._stall += _POLL_MS / 1000.0
            else:
                self._stall = 0.0
                self._last_time = t
            if self._stall >= self._stall_limit:
                self._mark_lost()
            else:
                self._mark_ok()
        elif state in (vlc.State.Error, vlc.State.Ended):
            self._mark_lost()
            self._tick_retry()
        else:  # Opening / Buffering / NothingSpecial
            self._stall += _POLL_MS / 1000.0
            if self._stall >= self._stall_limit:
                self._mark_lost()
                self._tick_retry()

    def _tick_retry(self) -> None:
        self._retry += _POLL_MS / 1000.0
        if self._retry >= _RETRY_S:
            self._retry = 0.0
            self._stall = 0.0
            self._open()

    def _mark_lost(self) -> None:
        if not self._lost:
            self._lost = True
            self.health_changed.emit("lost")
            self.signal_lost.emit()

    def _mark_ok(self) -> None:
        self._retry = 0.0
        if self._lost:
            self._lost = False
            self.health_changed.emit("on_air")
            self.signal_restored.emit()
        elif not self._ever_ok:
            self._ever_ok = True
            self.health_changed.emit("on_air")
