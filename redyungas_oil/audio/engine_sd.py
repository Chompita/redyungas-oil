"""
audio/engine_sd.py — Motor de audio de UN SOLO GRAFO (rama audio-pro).

Reemplazo (drop-in) de `audio/engine.py` (VLC) con la MISMA API y señales, pero
mezclando todo en numpy y sacando UNA sola salida (sounddevice/PortAudio). Esto
elimina de raíz el tartamudeo/caídas al solapar dos pistas (que ocurría al dejar
que el SO mezclara dos reproductores VLC) y permite que TODO sea suave y
sample-accurate:

* **Crossfade equal-power** entre pistas, tanto en el auto-avance como **al darle
  Reproducir / click derecho mientras algo suena** (la pista actual baja y se
  SOLAPA con la nueva — petición expresa del operador).
* **Pisador (ducking)** que baja/sube la música en rampa por-muestra.
* **Fundido de entrada** cuando se arranca sin nada sonando.
* **VU REAL** (pico del mix), seek, volumen maestro, cuñas (cartwall) y pisador/voz.

Se selecciona con `[audio].engine = "sounddevice"`. Si PortAudio no está
disponible (p. ej. servidor headless), el motor se construye igual y no rompe; el
sonido solo suena en una máquina con tarjeta (las esclavas).
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core import constants as C
from ..playlist.item_types import ItemType, is_audio
from .locutions import LocutionMaker
from .sd_decoder import PcmStream
from .sd_mixer import Mixer, SoundDeviceOutput, Voice

log = logging.getLogger("redyungas_oil.engine_sd")

_CROSSFADE_TYPES = {ItemType.TRACK, ItemType.RANDOM}
_DUCK_LEVEL = C.DUCK_LEVEL


class SoundDeviceEngine(QObject):
    now_playing_changed = pyqtSignal(int, str)
    next_changed = pyqtSignal(int, str)
    position_changed = pyqtSignal(float, float)    # restante_seg, total_seg
    levels_changed = pyqtSignal(float, float)
    state_changed = pyqtSignal(str)
    cart_started = pyqtSignal(int)                 # slot de cuña que arranca
    cart_finished = pyqtSignal(int)                # slot de cuña que terminó/silenció
    playout_mode_changed = pyqtSignal(str, bool)   # ("cyclic"|"delete_on_play"|"stop_after", activo)

    def __init__(self, config: dict, model=None, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        self.model = model
        au = (config.get("audio", {}) or {})
        self.samplerate = int(au.get("samplerate", 44100))
        self.channels = 2
        self.crossfade_ms = int(au.get("crossfade_ms", C.CROSSFADE_MS))
        # Lead del avance AUTOMÁTICO: empieza 1,75 s antes de acabar (solo automático).
        self.auto_crossfade_ms = int(au.get("auto_crossfade_ms", C.AUTO_CROSSFADE_MS))
        self.fade_in_ms = int(au.get("fade_in_ms", C.FADE_IN_MS))
        self.duck_ms = int(au.get("duck_ms", C.DUCK_MS))
        self.duck_level = float(au.get("duck_level", C.DUCK_LEVEL))

        self.mixer = Mixer(self.samplerate, self.channels, int(au.get("blocksize", 1024)))
        self._volume = int(au.get("volume", 80))
        self.mixer.master = self._volume / 100.0
        self._output = SoundDeviceOutput(self.mixer, device=(au.get("output_device") or None))
        self._output_started = False

        self._locutions = LocutionMaker(config)
        self._weather = (0.0, 0.0)

        self.current_index = -1
        self.next_index = -1
        self._forced_next = -1
        self._deck: Voice | None = None          # voz de música actual
        self._crossfading = False
        self._paused = False
        self._manual_duck = False
        self._auto_pisador = False
        self._pisador_voice: Voice | None = None
        self._duck_val = 1.0
        self._cart_paths: list[str | None] = [None] * C.CARTWALL_SLOTS
        self._cart_voices: dict[int, Voice] = {}    # slot -> voz activa (toggle/estado)
        self._cart_volume = 1.0                     # volumen general de las cuñas 0..1
        # Modos por-cuña (botones con estado visible activado/desactivado):
        self._cyclic = False            # Cíclico: repite la misma cuña una y otra vez
        self._delete_on_play = False    # Borrar al reproducir: la elimina al terminar
        self._stop_after = False        # Parar tras la actual: para al acabar la cuña
        self._mic_ducking = False       # micrófono del locutor activo -> baja la música
        self._mic_deck_level = 1.0      # nivel al que baja la PRINCIPAL con el mic
        self._mic_voice: Voice | None = None

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

    def _items(self):
        return self.model.items if self.model else []

    def _ensure_output(self) -> None:
        if self._output_started:
            return
        self._output_started = True       # intentar una sola vez
        try:
            self._output.start()
        except Exception as exc:           # sin tarjeta (headless): no romper
            log.warning("Salida de audio no disponible (sounddevice): %s", exc)

    def _resolve(self, item) -> tuple[str | None, str]:
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

    def _make_deck(self, path: str, fade: float) -> Voice:
        src = PcmStream(path, self.samplerate, self.channels, self.config)
        return Voice(src, self.samplerate, vol=self._duck_val, fade=fade, tag="deck")

    # --------------------------------------------------------------- control
    def play(self) -> None:
        if self._paused:
            self._resume()
            return
        self.play_index(self.current_index if self.current_index >= 0 else 0)

    def play_index(self, i: int) -> None:
        self._pause_timer.stop()
        items = self._items()
        if not items or i < 0 or i >= len(items):
            self.stop()
            return
        if i == self._forced_next:
            self._forced_next = -1
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
            if i + 1 < len(items):
                self.play_index(i + 1)
            else:
                self.stop()
            return

        self._ensure_output()
        self._resume_if_paused_stream()
        playing = (self._deck is not None and not self._paused
                   and not self._deck.source.finished)
        incoming = self._make_deck(path, fade=0.0)
        if playing:
            # SOLAPE: la pista actual baja y se cruza con la nueva (equal-power).
            incoming.set_fade(1.0, self.crossfade_ms)
            self.mixer.add(incoming)
            self._deck.set_fade(0.0, self.crossfade_ms)
            self._deck.stop_when_silent = True
            self._begin_crossfade_window()
        else:
            # Nada sonando: fundido de entrada suave.
            incoming.set_fade(1.0, self.fade_in_ms)
            self.mixer.add(incoming)
        self._deck = incoming
        self._paused = False
        self.current_index = i
        self._emit_track(i, title)
        self.state_changed.emit("playing")
        pisador = item.meta.get("pisador")
        if pisador:
            self.play_voiceover(pisador)

    def _begin_crossfade_window(self) -> None:
        # "Crossfading" mientras existan 2 decks (la saliente se va apagando). El poll
        # lo limpia solo cuando el mixer ya quitó la saliente (robusto, sin timers).
        self._crossfading = True

    def _enter_pause(self, i: int, seconds: int) -> None:
        self._clear_voices()
        self.current_index = i
        self._emit_track(i, self._items()[i].title)
        self.state_changed.emit("pausa")
        self._pause_next = i + 1
        self._pause_timer.start(max(1, seconds) * 1000)

    def _after_pause(self) -> None:
        self.play_index(self._pause_next)

    def pause(self) -> None:
        if self._deck is None and not self._paused:
            return
        if not self._paused:
            self._paused = True
            try:
                self._output.stop()
            except Exception:
                pass
            self._output_started = False
            self.state_changed.emit("paused")
        else:
            self._resume()

    def _resume(self) -> None:
        self._paused = False
        self._ensure_output()
        self.state_changed.emit("playing")

    def _resume_if_paused_stream(self) -> None:
        if self._paused:
            self._paused = False

    def stop(self) -> None:
        self._pause_timer.stop()
        self._clear_voices()
        self._deck = None
        self._crossfading = False
        self._paused = False
        self._auto_pisador = False
        self._pisador_voice = None
        for slot in list(self._cart_voices.keys()):
            self.cart_finished.emit(slot)
        self._cart_voices.clear()
        self.state_changed.emit("stopped")
        self.levels_changed.emit(0.0, 0.0)
        self.position_changed.emit(0.0, 0.0)

    def _clear_voices(self) -> None:
        self.mixer.clear()

    def _next_to_play(self) -> int:
        items = self._items()
        if 0 <= self._forced_next < len(items):
            return self._forced_next
        nxt = (self.current_index + 1) if self.current_index >= 0 else 0
        return nxt if nxt < len(items) else -1

    def set_next(self, i: int) -> None:
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

    def set_volume(self, volume: int) -> None:
        self._volume = max(0, min(100, int(volume)))
        self.mixer.master = self._volume / 100.0

    def set_position(self, fraction: float) -> None:
        if self._crossfading or self._deck is None:
            return
        total = self._deck.source.duration
        if total > 0:
            self._deck.source.seek(max(0.0, min(1.0, float(fraction))) * total)

    # ----------------------------------------------------------- cartwall
    def assign_cart(self, slot: int, path: str) -> None:
        if 0 <= slot < len(self._cart_paths):
            self._cart_paths[slot] = path

    def cart_path(self, slot: int) -> str | None:
        return self._cart_paths[slot] if 0 <= slot < len(self._cart_paths) else None

    def fire_cart(self, slot: int) -> bool:
        """Toggle: 1er clic dispara la cuña; 2º clic la SILENCIA con pisador suave
        (no la vuelve a reproducir). Devuelve False solo si el slot está vacío."""
        path = self.cart_path(slot)
        if not path:
            return False
        active = self._cart_voices.get(slot)
        if active is not None and not active.finished and active in self.mixer.voices("cart"):
            # 2º clic: silenciar suave (pisador) en vez de reproducir otra vez.
            active.set_fade(0.0, self.duck_ms)
            active.stop_when_silent = True
            self._cart_voices.pop(slot, None)
            self.cart_finished.emit(slot)
            return True
        self._ensure_output()
        src = PcmStream(path, self.samplerate, self.channels, self.config)
        voice = Voice(src, self.samplerate, vol=self._cart_volume, fade=1.0, tag="cart")
        self._cart_voices[slot] = voice
        self.mixer.add(voice)
        self.cart_started.emit(slot)
        return True

    def fade_all_carts(self) -> None:
        """Fundido general: baja y silencia TODAS las cuñas activas."""
        for slot, v in list(self._cart_voices.items()):
            try:
                v.set_fade(0.0, self.duck_ms)
                v.stop_when_silent = True
            except Exception:
                pass
            self.cart_finished.emit(slot)
        self._cart_voices.clear()

    def set_cart_volume(self, value: int) -> None:
        """Volumen general de las cuñas (0..100); afecta a las activas y futuras."""
        self._cart_volume = max(0, min(100, int(value))) / 100.0
        for v in list(self._cart_voices.values()):
            try:
                v.set_vol(self._cart_volume, 120)
            except Exception:
                pass

    # --------------------------------------------------- pisador / locuciones
    def play_voiceover(self, path: str) -> bool:
        if not path:
            return False
        self._ensure_output()
        src = PcmStream(path, self.samplerate, self.channels, self.config)
        self._pisador_voice = Voice(src, self.samplerate, vol=1.0, fade=1.0, tag="pisador")
        self.mixer.add(self._pisador_voice)
        self._auto_pisador = True
        self._apply_duck()
        return True

    def toggle_manual_duck(self) -> bool:
        self._manual_duck = not self._manual_duck
        self._apply_duck()
        return self._manual_duck

    # --------------------------------------------------- modos por-cuña (toggles)
    def set_cyclic(self, on: bool) -> None:
        self._cyclic = bool(on)
        self.playout_mode_changed.emit("cyclic", self._cyclic)

    def set_delete_on_play(self, on: bool) -> None:
        self._delete_on_play = bool(on)
        self.playout_mode_changed.emit("delete_on_play", self._delete_on_play)

    def set_stop_after(self, on: bool) -> None:
        self._stop_after = bool(on)
        self.playout_mode_changed.emit("stop_after", self._stop_after)

    def _apply_duck(self) -> None:
        target = 1.0
        if self._manual_duck or self._auto_pisador:
            target = min(target, self.duck_level)
        if self._mic_ducking:                      # el mic del locutor también baja la música
            target = min(target, self._mic_deck_level)
        self._duck_val = target
        if self._deck is not None:
            self._deck.set_vol(target, self.duck_ms)

    def is_ducked(self) -> bool:
        return self._manual_duck

    # ----------------------------------------------------- micrófono / auto-duck
    def set_mic_duck(self, active: bool, deck_level: float = _DUCK_LEVEL,
                     carts_level: float = 1.0) -> None:
        """El locutor habla (active=True) -> baja la PRINCIPAL a `deck_level` y las
        CUÑAS a `carts_level`; al callar (False) las restaura, en rampa suave."""
        self._mic_ducking = bool(active)
        self._mic_deck_level = float(deck_level)
        self._apply_duck()
        cart_target = float(carts_level) if active else self._cart_volume
        for v in list(self._cart_voices.values()):
            v.set_vol(cart_target, self.duck_ms)

    def add_mic_voice(self, source) -> None:
        """Mezcla la voz del micrófono en la salida (al aire)."""
        self.remove_mic_voice()
        self._ensure_output()
        self._mic_voice = Voice(source, self.samplerate, vol=1.0, fade=1.0, tag="mic")
        self.mixer.add(self._mic_voice)

    def remove_mic_voice(self) -> None:
        if self._mic_voice is not None:
            self._mic_voice.set_fade(0.0, 150)
            self._mic_voice.stop_when_silent = True
            self._mic_voice = None

    def play_locution(self, kind: str) -> bool:
        path = self._locutions.make(kind, self._weather)
        return self.play_voiceover(path) if path else False

    def locutions_available(self) -> bool:
        return self._locutions.available()

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
        self.levels_changed.emit(self.mixer.level_l, self.mixer.level_r)
        # Cuñas (cartwall) que terminaron solas -> apagar su resaltado en la UI.
        if self._cart_voices:
            live = self.mixer.voices("cart")
            for slot, v in list(self._cart_voices.items()):
                if v.finished or v not in live:
                    self._cart_voices.pop(slot, None)
                    self.cart_finished.emit(slot)
        # fin del pisador automático -> subir la música suave (en el hilo Qt)
        if self._auto_pisador and (self._pisador_voice is None
                                   or self._pisador_voice.finished
                                   or self._pisador_voice not in self.mixer.voices("pisador")):
            self._auto_pisador = False
            self._pisador_voice = None
            if not self._manual_duck:
                self._apply_duck()

        if self._paused or self._deck is None:
            return
        src = self._deck.source
        total = src.duration or 0.0
        elapsed = src.frames_read / self.samplerate
        remaining = max(0.0, total - elapsed) if total > 0 else 0.0
        self.position_changed.emit(remaining, total)

        # El crossfade termina cuando el mixer ya quitó la deck saliente (queda 1).
        if self._crossfading and len(self.mixer.voices("deck")) <= 1:
            self._crossfading = False
        if self._crossfading:
            return
        acf = self.auto_crossfade_ms / 1000.0
        items = self._items()
        # Los modos especiales (cíclico/borrar/parar-tras-actual) se resuelven en el
        # FIN NATURAL, así que en esos modos NO se dispara el crossfade automático.
        special = self._cyclic or self._stop_after or self._delete_on_play
        # Auto-avance: el crossfade automático empieza `auto_crossfade_ms` (1,75 s)
        # antes de acabar el jingle (petición del operador, solo para el automático).
        if not special and total > 0 and acf > 0 and 0 < remaining <= acf:
            nxt = self._next_to_play()
            if 0 <= nxt < len(items) and items[nxt].type in _CROSSFADE_TYPES:
                self._start_auto_crossfade(nxt)
                return
        # Fin natural: decide según los modos (parar / repetir / borrar / siguiente).
        if src.finished or (total > 0 and remaining <= 0.05):
            self._handle_end()

    def _handle_end(self) -> None:
        items = self._items()
        finished = self.current_index
        if self._stop_after:
            self.set_stop_after(False)   # se autodesactiva y avisa a la UI
            self.stop()
            return
        if self._cyclic and 0 <= finished < len(items):
            self.play_index(finished)    # repite la misma cuña
            return
        nxt = self._next_to_play()
        if self._delete_on_play and 0 <= finished < len(items) and self.model:
            self.model.remove_rows([finished])
            if nxt > finished:
                nxt -= 1                 # los índices se corrieron al borrar
            items = self._items()
        if 0 <= nxt < len(items):
            self.play_index(nxt)
        else:
            self.stop()

    def _start_auto_crossfade(self, nxt: int) -> None:
        items = self._items()
        path, title = self._resolve(items[nxt])
        if not path:
            return
        incoming = self._make_deck(path, fade=0.0)
        incoming.set_fade(1.0, self.auto_crossfade_ms)
        self.mixer.add(incoming)
        if self._deck is not None:
            self._deck.set_fade(0.0, self.auto_crossfade_ms)
            self._deck.stop_when_silent = True
        self._deck = incoming
        if nxt == self._forced_next:
            self._forced_next = -1
        self.current_index = nxt
        self._emit_track(nxt, title)
        self._begin_crossfade_window()

    # ------------------------------------------------------------------ cierre
    def release(self) -> None:
        self._timer.stop()
        self._pause_timer.stop()
        try:
            self._output.stop()
        except Exception:
            pass
        self.mixer.clear()
