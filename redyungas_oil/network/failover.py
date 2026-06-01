"""
network/failover.py — Protocolo radio-offline + coordinador de la esclava (FASE 4).

Máquina de estados que mantiene la emisión SIN BACHES en una esclava:

    stream  ── señal cae ──▶ grace ── 15 s sin volver ──▶ offline
       ▲                       │                              │
       └──── señal vuelve ─────┴───── señal vuelve (crossfade)┘

- En `grace`: avisa por Telegram y deja que el receptor reintente 15 s.
- En `offline`: reproduce una cuña publicitaria CERCANA A LA HORA (carpeta tipo
  PUBLI H:MM) en bucle, con fundido de entrada.
- Al volver la señal estando offline: **transición suave** (crossfade) de la cuña
  al stream del estudio.
- Cada cambio de estado se notifica por Telegram (degradación elegante).

Reutiliza StreamReceiver (audio/receiver.py) y CrossfadeController (audio/crossfade.py).
"""

from __future__ import annotations

import logging
import random
from datetime import datetime
from pathlib import Path

import vlc
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..audio.crossfade import CrossfadeController
from ..audio.receiver import StreamReceiver
from ..core import constants as C
from ..integrations.telegram_notifier import TelegramNotifier
from ..playlist.item_types import is_audio

log = logging.getLogger("redyungas_oil.failover")


class OfflineFailover(QObject):
    state_changed = pyqtSignal(str)     # "stream" | "grace" | "offline"

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        net = (config.get("network", {}) or {})
        paths = (config.get("paths", {}) or {})
        self.station = (config.get("general", {}) or {}).get("station_name", "emisora")
        self.reconnect_timeout = float(net.get("reconnect_timeout_s", C.RECONNECT_TIMEOUT_S))
        self.offline_folder = net.get("offline_folder", "") or paths.get("emergency_folder", "")
        self.crossfade_ms = int((config.get("audio", {}) or {}).get("crossfade_ms", C.CROSSFADE_MS))

        self.receiver = StreamReceiver(config, self)
        self.notifier = TelegramNotifier(config)
        self._vlc = vlc.Instance("--no-video", "--quiet")
        self._cuna = self._vlc.media_player_new()
        self._xfade: CrossfadeController | None = None
        self.state = "idle"

        self._grace = QTimer(self)
        self._grace.setSingleShot(True)
        self._grace.timeout.connect(self._go_offline)
        self._cuna_timer = QTimer(self)
        self._cuna_timer.timeout.connect(self._cuna_poll)

        self.receiver.signal_lost.connect(self._on_lost)
        self.receiver.signal_restored.connect(self._on_restored)

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        self.receiver.set_volume(100)
        self.receiver.start()
        self._set_state("stream")

    def stop(self) -> None:
        self._grace.stop()
        self._cuna_timer.stop()
        self._cancel_xfade()
        self.receiver.stop()
        self._cuna.stop()

    def _set_state(self, state: str) -> None:
        self.state = state
        self.state_changed.emit(state)

    # --------------------------------------------------------------- eventos
    def _on_lost(self) -> None:
        if self.state in ("grace", "offline"):
            return
        self._set_state("grace")
        self.notifier.notify(
            f"⚠️ Compu {self.station} está sin recibir señal. "
            f"Reintentando reconexión ({int(self.reconnect_timeout)} s)…"
        )
        self._grace.start(int(self.reconnect_timeout * 1000))

    def _go_offline(self) -> None:
        self._set_state("offline")
        self.notifier.notify(
            f"🔴 {self.station}: sin señal. Protocolo offline activado: publicidad al aire."
        )
        self._play_cuna(initial=True)
        self._cuna_timer.start(700)

    def _on_restored(self) -> None:
        self._grace.stop()
        if self.state == "offline":
            self.notifier.notify(f"🟢 {self.station}: señal recuperada. Volviendo al estudio.")
            self._cuna_timer.stop()
            self.receiver.player().audio_set_volume(0)
            self._crossfade(self._cuna, self.receiver.player())
        elif self.state == "grace":
            self.notifier.notify(f"🟢 {self.station}: señal recuperada.")
        self._set_state("stream")

    # --------------------------------------------------------------- cuñas
    def _play_cuna(self, initial: bool) -> None:
        path = self._pick_cuna()
        if not path:
            self.notifier.notify(
                f"⚠️ {self.station}: protocolo offline SIN cuñas. Configura la carpeta de emergencia."
            )
            return
        self._cuna.set_media(self._vlc.media_new(path))
        if initial:
            self._cuna.audio_set_volume(0)
            self._cuna.play()
            self._crossfade(self.receiver.player(), self._cuna)   # fundido de entrada
        else:
            self._cuna.audio_set_volume(100)
            self._cuna.play()
        log.info("Cuña offline al aire: %s", Path(path).name)

    def _cuna_poll(self) -> None:
        if self._cuna.get_state() in (vlc.State.Ended, vlc.State.Error):
            self._play_cuna(initial=False)

    def _pick_cuna(self) -> str | None:
        folder = self.offline_folder
        if not folder or not Path(folder).is_dir():
            return None
        files = [str(f) for f in Path(folder).rglob("*") if f.is_file() and is_audio(str(f))]
        if not files:
            return None
        hour = datetime.now().hour
        preferred = [f for f in files if self._matches_hour(f, hour)]
        return random.choice(preferred or files)

    @staticmethod
    def _matches_hour(path: str, hour: int) -> bool:
        s = path.lower()
        return (f"{hour:02d}" in s or f"h:{hour}" in s or f"h {hour}" in s
                or f"publi {hour}" in s or f"/{hour}/" in s)

    # --------------------------------------------------------------- crossfade
    def _crossfade(self, out_player, in_player) -> None:
        self._cancel_xfade()
        self._xfade = CrossfadeController(out_player, in_player, self.crossfade_ms,
                                          target_volume=100, parent=self)
        self._xfade.finished.connect(lambda: self._after_xfade(out_player))
        self._xfade.start()

    def _after_xfade(self, out_player) -> None:
        # No paramos el stream (lo seguimos vigilando); sí la cuña si quedó saliente.
        if out_player is self._cuna:
            self._cuna.stop()
        self._cancel_xfade()

    def _cancel_xfade(self) -> None:
        if self._xfade:
            self._xfade.cancel()
            self._xfade = None
