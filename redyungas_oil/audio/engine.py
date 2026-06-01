"""
audio/engine.py — Motor de audio central (FASE 2 + FASE 3).

Envuelve libVLC con DOS reproductores principales (A/B) para crossfade, 9 carts y
un canal de PISADOR (voz superpuesta con ducking). Resuelve los tipos de ítem de
ZaraRadio: TRACK, RANDOM (rotativa), STOP, PAUSE, y locuciones TIME/TEMPERATURE/
HUMIDITY (audio/locutions.py).

THREAD-SAFE: sin callbacks de VLC; un QTimer en el hilo Qt sondea estado/posición.
Esta API es la que controlarán las herramientas MCP (Fase 7).
"""

from __future__ import annotations

import random
from pathlib import Path

import vlc
from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core import constants as C
from ..playlist.item_types import ItemType, is_audio
from .crossfade import CrossfadeController
from .locutions import LocutionMaker

_CROSSFADE_TYPES = {ItemType.TRACK, ItemType.RANDOM}
_DUCK_LEVEL = C.DUCK_LEVEL    # nivel al que baja la música con el pisador (auto o manual)
_ANIM_INTERVAL_MS = 30       # paso de las animaciones de volumen (pisador / fade-in)


class AudioEngine(QObject):
    now_playing_changed = pyqtSignal(int, str)
    next_changed = pyqtSignal(int, str)
    position_changed = pyqtSignal(float, float)    # restante_seg, total_seg
    levels_changed = pyqtSignal(float, float)
    state_changed = pyqtSignal(str)                # playing/paused/stopped/pausa

    def __init__(self, config: dict, model=None, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.model = model

        self._vlc = vlc.Instance("--no-video", "--quiet")
        self._players = [self._vlc.media_player_new(), self._vlc.media_player_new()]
        self._active = 0
        self._carts = [self._vlc.media_player_new() for _ in range(C.CARTWALL_SLOTS)]
        self._cart_paths: list[str | None] = [None] * C.CARTWALL_SLOTS
        self._pisador = self._vlc.media_player_new()

        self.current_index = -1
        self.next_index = -1
        self._forced_next = -1        # "Marcar como siguiente" (click derecho)
        self._paused = False
        self._crossfading = False
        self._xfade: CrossfadeController | None = None
        self._pending_index = -1
        # --- Volumen efectivo del player activo = _volume * _duck * _fade ---
        #   _duck: pisador (1.0 normal -> _DUCK_LEVEL bajado), con rampa suave.
        #   _fade: fundido de entrada/salida de la pista (0.0 -> 1.0), con rampa.
        self._duck = 1.0
        self._duck_target = 1.0
        self._fade = 1.0
        self._fade_target = 1.0
        self._fade_wait_play = False   # esperar a que el player empiece a sonar antes del fade-in
        self._fade_wait_ticks = 0
        self._auto_pisador = False    # pisador disparado por voz/locución (temporal)
        self._manual_duck = False     # pisador manual (botón ≈), persistente
        self._vu_l = 0.0
        self._vu_r = 0.0
        self._weather = (0.0, 0.0)
        self._locutions = LocutionMaker(config)

        au = (config.get("audio", {}) or {})
        self._volume = int(au.get("volume", 80))
        # Pasos por tick para que las rampas duren ~fade_in_ms / ~duck_ms.
        fade_in_ms = max(0, int(au.get("fade_in_ms", C.FADE_IN_MS)))
        duck_ms = max(1, int(au.get("duck_ms", C.DUCK_MS)))
        self._fade_in_ms = fade_in_ms
        self._fade_step = 1.0 if fade_in_ms <= 0 else 1.0 / max(1, fade_in_ms / _ANIM_INTERVAL_MS)
        self._duck_step = (1.0 - _DUCK_LEVEL) / max(1, duck_ms / _ANIM_INTERVAL_MS)
        self._fade_wait_max = max(1, int(2000 / _ANIM_INTERVAL_MS))
        for p in self._players:
            p.audio_set_volume(self._volume)

        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._anim_step)

        self._pause_timer = QTimer(self)
        self._pause_timer.setSingleShot(True)
        self._pause_timer.timeout.connect(self._after_pause)
        self._pause_next = -1

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(100)

    # --------------------------------------------------------------- helpers
    def set_model(self, model) -> None:
        self.model = model

    def set_weather(self, temp_c: float, humidity_pct: float) -> None:
        self._weather = (temp_c, humidity_pct)

    def _player(self):
        return self._players[self._active]

    def _other(self):
        return self._players[1 - self._active]

    def _items(self):
        return self.model.items if self.model else []

    def _load(self, player, path: str) -> None:
        player.set_media(self._vlc.media_new(path))

    def _resolve(self, item) -> tuple[str | None, str]:
        """Devuelve (ruta_a_reproducir, título_a_mostrar) para un ítem."""
        if item.type == ItemType.TRACK:
            return (item.path or None), item.title
        if item.type == ItemType.RANDOM:
            path = self._random_in(item.path)
            return path, (Path(path).stem if path else item.title)
        if item.type == ItemType.TIME:
            return self._locutions.make("time", self._weather), item.title
        if item.type == ItemType.TEMPERATURE:
            return self._locutions.make("temperature", self._weather), item.title
        if item.type == ItemType.HUMIDITY:
            return self._locutions.make("humidity", self._weather), item.title
        return None, item.title

    @staticmethod
    def _random_in(folder: str) -> str | None:
        try:
            files = [str(f) for f in Path(folder).iterdir()
                     if f.is_file() and is_audio(str(f))]
            return random.choice(files) if files else None
        except OSError:
            return None

    # --------------------------------------------------------------- control
    def play(self) -> None:
        if self._paused:
            self._player().play()
            self._paused = False
            self.state_changed.emit("playing")
            return
        self.play_index(self.current_index if self.current_index >= 0 else 0)

    def play_index(self, i: int) -> None:
        self._pause_timer.stop()
        items = self._items()
        if not items or i < 0 or i >= len(items):
            self.stop()
            return
        if i == self._forced_next:
            self._forced_next = -1        # se consume al reproducirla
        item = items[i]
        if item.type == ItemType.STOP:
            self.current_index = i
            if self.model:
                self.model.set_playing(i, -1)
            self.stop()
            return
        if item.type == ItemType.PAUSE:
            self._enter_pause(i, int(item.meta.get("seconds", 3)))
            return
        path, title = self._resolve(item)
        if not path:
            # No se pudo resolver (carpeta vacía, sin voz...): saltar al siguiente.
            if i + 1 < len(items):
                self.play_index(i + 1)
            else:
                self.stop()
            return
        self._cancel_crossfade()
        player = self._player()
        self._load(player, path)
        self._start_fade_in()          # fundido de entrada suave (no arranca de golpe)
        player.play()
        # VLC pierde el volumen si se setea antes de tener salida de audio:
        # se aplica DESPUÉS de play() y el poll/animación lo refuerzan (arregla el
        # silencio y, con _fade, evita el golpe inicial del click derecho/doble clic).
        player.audio_set_volume(self._effective_volume())
        self._paused = False
        self.current_index = i
        self._emit_track(i, title)
        self.state_changed.emit("playing")
        pisador = item.meta.get("pisador")          # pisador asignado a la pista
        if pisador:
            self.play_voiceover(pisador)

    def _enter_pause(self, i: int, seconds: int) -> None:
        self._cancel_crossfade()
        for p in self._players:
            p.stop()
        self.current_index = i
        self._emit_track(i, self._items()[i].title)
        self.state_changed.emit("pausa")
        self._pause_next = i + 1
        self._pause_timer.start(max(1, seconds) * 1000)

    def _after_pause(self) -> None:
        self.play_index(self._pause_next)

    def pause(self) -> None:
        player = self._player()
        if player.is_playing():
            player.pause()
            self._paused = True
            self.state_changed.emit("paused")
        elif self._paused:
            player.play()
            self._paused = False
            self.state_changed.emit("playing")

    def stop(self) -> None:
        self._pause_timer.stop()
        self._cancel_crossfade()
        for p in self._players:
            p.stop()
        self._paused = False
        # Deja el fundido listo para el próximo arranque; el pisador MANUAL persiste.
        self._fade = 1.0
        self._fade_target = 1.0
        self._fade_wait_play = False
        if self._duck == self._duck_target:
            self._anim_timer.stop()
        self.state_changed.emit("stopped")
        self.levels_changed.emit(0.0, 0.0)
        self.position_changed.emit(0.0, 0.0)

    def _next_to_play(self) -> int:
        """Índice de la próxima pista: el 'marcado como siguiente' o el secuencial."""
        items = self._items()
        if 0 <= self._forced_next < len(items):
            return self._forced_next
        nxt = (self.current_index + 1) if self.current_index >= 0 else 0
        return nxt if nxt < len(items) else -1

    def set_next(self, i: int) -> None:
        """'Marcar como siguiente' (click derecho): la pista i sonará después."""
        items = self._items()
        if not (0 <= i < len(items)):
            return
        self._forced_next = i
        self.next_index = i
        self.next_changed.emit(i, items[i].title)
        if self.model:
            self.model.set_playing(self.current_index, i)

    def next(self) -> None:
        nxt = self._next_to_play()
        self._forced_next = -1
        self.play_index(nxt if nxt >= 0 else (self.current_index + 1))

    def previous(self) -> None:
        if self.current_index > 0:
            self.play_index(self.current_index - 1)

    def _target_volume(self) -> int:
        """Volumen de la música ya con el pisador (sin el fundido de entrada).
        Es el destino del crossfade y el estado estable de reproducción."""
        return max(0, min(100, int(self._volume * self._duck)))

    def _effective_volume(self) -> int:
        """Volumen REAL del player activo: música * pisador * fundido de entrada."""
        return max(0, min(100, int(self._volume * self._duck * self._fade)))

    def _apply_volume(self) -> None:
        """Aplica el volumen efectivo al player activo (salvo durante el crossfade,
        que gestiona sus propios volúmenes)."""
        if self._crossfading:
            return
        try:
            self._player().audio_set_volume(self._effective_volume())
        except Exception:
            pass

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self._apply_volume()

    # ----------------------------------------------------- rampas de volumen
    def _start_fade_in(self) -> None:
        """Prepara un fundido de entrada suave para la pista que va a sonar."""
        if self._fade_in_ms <= 0:
            self._fade = 1.0
            self._fade_target = 1.0
            self._fade_wait_play = False
            return
        self._fade = 0.0
        self._fade_target = 1.0
        self._fade_wait_play = True       # no rampar hasta que el player saque audio
        self._fade_wait_ticks = 0
        if not self._anim_timer.isActive():
            self._anim_timer.start(_ANIM_INTERVAL_MS)

    def _set_duck_target(self, value: float) -> None:
        """Fija el destino del pisador y arranca la rampa suave hacia él."""
        self._duck_target = max(0.0, min(1.0, value))
        if self._duck != self._duck_target and not self._anim_timer.isActive():
            self._anim_timer.start(_ANIM_INTERVAL_MS)

    def _active_playing(self) -> bool:
        try:
            return self._player().get_state() == vlc.State.Playing
        except Exception:
            return True

    def _anim_step(self) -> None:
        """Anima _fade y _duck hacia sus destinos y aplica el volumen (suave)."""
        # --- Fundido de entrada (espera a que el player empiece a sonar) ---
        if self._fade < self._fade_target:
            if self._fade_wait_play and not self._active_playing():
                self._fade_wait_ticks += 1
                if self._fade_wait_ticks >= self._fade_wait_max:
                    self._fade_wait_play = False   # tope de seguridad: rampar igual
            else:
                self._fade_wait_play = False
                self._fade = min(self._fade_target, self._fade + self._fade_step)
        elif self._fade > self._fade_target:
            self._fade = max(self._fade_target, self._fade - self._fade_step)

        # --- Pisador (ducking) suave ---
        if self._duck < self._duck_target:
            self._duck = min(self._duck_target, self._duck + self._duck_step)
        elif self._duck > self._duck_target:
            self._duck = max(self._duck_target, self._duck - self._duck_step)

        self._apply_volume()

        settled = (self._fade == self._fade_target and self._duck == self._duck_target
                   and not self._fade_wait_play)
        if settled:
            self._anim_timer.stop()

    def set_position(self, fraction: float) -> None:
        """Salta a una posición de la pista actual (0.0..1.0) — barra de seek."""
        if self._crossfading:
            return
        try:
            self._player().set_position(max(0.0, min(1.0, float(fraction))))
        except Exception:
            pass

    # --------------------------------------------------------------- cartwall
    def assign_cart(self, slot: int, path: str) -> None:
        if 0 <= slot < len(self._cart_paths):
            self._cart_paths[slot] = path

    def cart_path(self, slot: int) -> str | None:
        return self._cart_paths[slot] if 0 <= slot < len(self._cart_paths) else None

    def fire_cart(self, slot: int) -> bool:
        path = self.cart_path(slot)
        if not path:
            return False
        cart = self._carts[slot]
        cart.set_media(self._vlc.media_new(path))
        cart.audio_set_volume(self._volume)
        cart.play()
        return True

    # --------------------------------------------------- pisador / locuciones
    def play_voiceover(self, path: str) -> bool:
        """Reproduce una voz superpuesta bajando (ducking) la música activa."""
        if not path:
            return False
        self._pisador.set_media(self._vlc.media_new(path))
        self._pisador.audio_set_volume(self._volume)
        self._pisador.play()
        self._auto_pisador = True
        self._set_duck_target(_DUCK_LEVEL)      # baja la música SUAVE bajo la voz
        return True

    def toggle_manual_duck(self) -> bool:
        """Pisador MANUAL (botón ≈): baja/sube la música SUAVEMENTE (en rampa, no de
        golpe) y se mantiene hasta volver a pulsar. Devuelve el nuevo estado
        (True = música bajada)."""
        self._manual_duck = not self._manual_duck
        self._set_duck_target(_DUCK_LEVEL if (self._manual_duck or self._auto_pisador) else 1.0)
        return self._manual_duck

    def is_ducked(self) -> bool:
        return self._manual_duck

    def play_locution(self, kind: str) -> bool:
        """Dispara una locución (time/temperature/humidity) como pisador."""
        path = self._locutions.make(kind, self._weather)
        return self.play_voiceover(path) if path else False

    def locutions_available(self) -> bool:
        return self._locutions.available()

    # ------------------------------------------------------------- crossfade
    def _start_crossfade(self, next_i: int) -> bool:
        items = self._items()
        if next_i < 0 or next_i >= len(items) or items[next_i].type not in _CROSSFADE_TYPES:
            return False
        path, title = self._resolve(items[next_i])
        if not path:
            return False
        other = self._other()
        self._load(other, path)
        other.audio_set_volume(0)
        other.play()
        # El crossfade entrega la entrante a volumen pleno (sin fundido aparte).
        self._fade = 1.0
        self._fade_target = 1.0
        self._fade_wait_play = False
        self._crossfading = True
        self._pending_index = next_i
        self._pending_title = title
        duration = int((self.config.get("audio", {}) or {}).get("crossfade_ms", C.CROSSFADE_MS))
        self._xfade = CrossfadeController(self._player(), other, duration,
                                          target_volume=self._target_volume(), parent=self)
        self._xfade.finished.connect(self._finish_crossfade)
        self._xfade.start()
        return True

    def _finish_crossfade(self) -> None:
        self._player().stop()
        self._active = 1 - self._active
        self._player().audio_set_volume(self._effective_volume())   # asegurar el entrante
        self._crossfading = False
        self._xfade = None
        self.current_index = self._pending_index
        self._emit_track(self.current_index, self._pending_title)
        self.state_changed.emit("playing")

    def _cancel_crossfade(self) -> None:
        if self._crossfading and self._xfade:
            self._xfade.cancel()
            self._other().stop()
        self._crossfading = False
        self._xfade = None

    # ----------------------------------------------------------------- señales
    def _emit_track(self, i: int, title: str | None = None) -> None:
        items = self._items()
        self.now_playing_changed.emit(i, title or items[i].title)
        if 0 <= self._forced_next < len(items) and self._forced_next != i:
            nxt = self._forced_next
        else:
            nxt = i + 1 if i + 1 < len(items) else -1
        self.next_index = nxt
        self.next_changed.emit(nxt, items[nxt].title if nxt >= 0 else "")
        if self.model:
            self.model.set_playing(i, nxt)

    # -------------------------------------------------------------------- poll
    def _poll(self) -> None:
        self._update_ducking()
        if self._crossfading:
            self._update_vu(True)
            return
        player = self._player()
        state = player.get_state()
        if state == vlc.State.Playing:
            length = player.get_length() / 1000.0
            elapsed = player.get_time() / 1000.0
            items = self._items()
            fallback = items[self.current_index].duration if 0 <= self.current_index < len(items) else 0.0
            total = length if length > 0 else fallback
            remaining = max(0.0, total - elapsed) if total > 0 else 0.0
            self.position_changed.emit(remaining, total)
            self._enforce_volume()        # auto-cura: el entrante a veces queda mudo
            self._update_vu(True)
            self._maybe_crossfade(total, remaining)
        elif state == vlc.State.Ended:
            self._update_vu(False)
            nxt = self._next_to_play()
            if 0 <= nxt < len(self._items()):
                self.play_index(nxt)
            else:
                self.stop()
        else:
            self._update_vu(False)

    def _enforce_volume(self) -> None:
        """Garantiza que la música activa suene al volumen efectivo (no mudo).
        Coincide con la animación (mismo _effective_volume), así que no pelean."""
        if self._crossfading:
            return
        p = self._player()
        tgt = self._effective_volume()
        try:
            if p.audio_get_volume() != tgt:
                p.audio_set_volume(tgt)
        except Exception:
            pass

    def _update_ducking(self) -> None:
        if not self._auto_pisador:
            return
        if self._pisador.get_state() in (vlc.State.Ended, vlc.State.Error):
            self._auto_pisador = False
            if not self._manual_duck:        # el pisador MANUAL persiste
                self._set_duck_target(1.0)   # sube la música SUAVE al acabar la voz

    def _maybe_crossfade(self, total: float, remaining: float) -> None:
        cf = int((self.config.get("audio", {}) or {}).get("crossfade_ms", C.CROSSFADE_MS)) / 1000.0
        if cf <= 0 or self._paused or total <= cf or remaining > cf:
            return
        nxt = self._next_to_play()
        items = self._items()
        if 0 <= nxt < len(items) and items[nxt].type in _CROSSFADE_TYPES:
            if self._start_crossfade(nxt) and nxt == self._forced_next:
                self._forced_next = -1

    def _update_vu(self, active: bool) -> None:
        # FASE 2: VU aproximado (animado). Medidor PCM real = refinamiento posterior.
        if active and not self._paused:
            target = 0.55 + random.random() * 0.40
            self._vu_l += (target - self._vu_l) * 0.35
            self._vu_r += (target * 0.92 + random.random() * 0.06 - self._vu_r) * 0.35
        else:
            self._vu_l *= 0.6
            self._vu_r *= 0.6
        self.levels_changed.emit(self._vu_l, self._vu_r)

    # ------------------------------------------------------------------ cierre
    def release(self) -> None:
        self._timer.stop()
        self._pause_timer.stop()
        self._anim_timer.stop()
        self._cancel_crossfade()
        for p in self._players + self._carts + [self._pisador]:
            p.stop()
            p.release()
