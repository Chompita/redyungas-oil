"""
audio/mic_ducker.py — Entrada de micrófono del locutor + auto-ducking profesional.

Reemplaza el apartado de clima por una función de radio profesional: escucha el
micrófono y, cuando el locutor HABLA, baja automáticamente la música (planilla
principal, auxiliar y cuñas) con ataque/liberación suaves; al callar, la vuelve a
subir. Opcionalmente mezcla la voz "al aire" por la misma salida.

Detección de voz por nivel (RMS en dBFS) con histéresis:
  * `threshold_db`  — nivel a partir del cual se considera "hablando".
  * `attack_ms`     — debe mantenerse por encima este tiempo para abrir el gate.
  * `release_ms`    — tras callar, espera este tiempo antes de cerrar (no "chattering").

Si PortAudio/sounddevice no está disponible (servidor headless), `start()` no
rompe: simplemente no hay captura (igual que el resto del motor).
"""

from __future__ import annotations

import logging
import math
import threading

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

log = logging.getLogger("redyungas_oil.mic")


class MicSource:
    """Búfer en anillo para mandar la voz del mic al mixer (read() como PcmStream)."""

    def __init__(self, samplerate: int, channels: int = 2, max_blocks: int = 32) -> None:
        self.samplerate = samplerate
        self.channels = channels
        self._blocks: list[np.ndarray] = []
        self._max = max_blocks
        self._lock = threading.Lock()
        self.finished = False
        self.duration = 0.0

    def write(self, stereo_block: np.ndarray) -> None:
        with self._lock:
            self._blocks.append(stereo_block)
            if len(self._blocks) > self._max:        # acota latencia (descarta lo viejo)
                self._blocks = self._blocks[-self._max:]

    def read(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, self.channels), dtype=np.float32)
        filled = 0
        with self._lock:
            while filled < frames and self._blocks:
                blk = self._blocks[0]
                need = frames - filled
                if len(blk) <= need:
                    out[filled:filled + len(blk)] = blk
                    filled += len(blk)
                    self._blocks.pop(0)
                else:
                    out[filled:frames] = blk[:need]
                    self._blocks[0] = blk[need:]
                    filled = frames
        return out

    def close(self) -> None:
        with self._lock:
            self._blocks.clear()


class MicDucker(QObject):
    speaking_changed = pyqtSignal(bool)     # True = el locutor está hablando
    level_changed = pyqtSignal(float)       # nivel en dBFS (para un VU opcional)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config
        mic = (config.get("mic", {}) or {})
        self.samplerate = int((config.get("audio", {}) or {}).get("samplerate", 44100))
        self.blocksize = int((config.get("audio", {}) or {}).get("blocksize", 1024))
        self.threshold_db = float(mic.get("threshold_db", -38.0))
        self.attack_ms = float(mic.get("attack_ms", 120))
        self.release_ms = float(mic.get("release_ms", 700))
        self.to_air = bool(mic.get("to_air", False))
        self.mic_gain = 10 ** (float(mic.get("mic_gain_db", 0.0)) / 20.0)
        self.device = mic.get("device") or None

        self.speaking = False
        self.level_db = -120.0
        self._loud_ms = 0.0
        self._quiet_ms = 0.0
        self._stream = None
        self.mic_source = MicSource(self.samplerate, 2)

    # --------------------------------------------------------------- control
    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> bool:
        if self._stream is not None:
            return True
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(
                samplerate=self.samplerate, channels=1, blocksize=self.blocksize,
                dtype="float32", device=self.device, callback=self._callback,
            )
            self._stream.start()
            log.info("Micrófono iniciado (device=%s)", self.device)
            return True
        except Exception as exc:                # sin PortAudio/sin mic: no romper
            log.warning("No se pudo abrir el micrófono: %s", exc)
            self._stream = None
            return False

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self.speaking:
            self.speaking = False
            self.speaking_changed.emit(False)
        self.mic_source.close()

    # ----------------------------------------------------------- callback PA
    def _callback(self, indata, frames, time_info, status) -> None:  # noqa: ARG002
        x = indata[:, 0] if indata.ndim > 1 else indata
        rms = float(np.sqrt(np.mean(x * x))) if frames else 0.0
        self.level_db = 20.0 * math.log10(rms) if rms > 1e-7 else -120.0
        block_ms = 1000.0 * frames / self.samplerate

        if self.level_db >= self.threshold_db:
            self._loud_ms += block_ms
            self._quiet_ms = 0.0
            if not self.speaking and self._loud_ms >= self.attack_ms:
                self.speaking = True
                self.speaking_changed.emit(True)
        else:
            self._quiet_ms += block_ms
            self._loud_ms = 0.0
            if self.speaking and self._quiet_ms >= self.release_ms:
                self.speaking = False
                self.speaking_changed.emit(False)

        if self.to_air:                          # voz al aire (estéreo, con ganancia)
            st = np.clip((x * self.mic_gain), -1.0, 1.0).astype(np.float32)
            self.mic_source.write(np.stack([st, st], axis=1))
