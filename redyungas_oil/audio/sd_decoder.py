"""
audio/sd_decoder.py — Decodificación a PCM por ffmpeg, en STREAMING (motor audio-pro).

El motor de un solo grafo (sd_mixer/engine_sd) necesita las MUESTRAS de cada pista
para mezclarlas él mismo (no delega la mezcla al SO como VLC). `PcmStream` arranca
un ffmpeg que decodifica CUALQUIER formato a PCM float32 intercalado, a un
samplerate/canales fijos, y lo va leyendo en un hilo a una cola acotada
(back-pressure: ffmpeg se pausa solo cuando la cola se llena). El hilo de audio
consume con `read(frames)` sin bloquear.

    ffmpeg -ss <s> -i <file> -f f32le -ar <rate> -ac <ch> pipe:1

`read()` SIEMPRE devuelve `frames` muestras (rellena con ceros si aún no hay datos
o si la pista terminó), y expone `finished` cuando ya no queda nada por sonar.
"""

from __future__ import annotations

import queue
import subprocess
import threading

import numpy as np

from ..core import proc
from .probe import probe_duration

_BYTES_PER_SAMPLE = 4          # float32
_READ_BYTES = 16384            # ~ por lectura del pipe
_QUEUE_MAX = 96                # chunks en vuelo (~3-4 s); acota memoria


class PcmStream:
    def __init__(self, path: str, samplerate: int = 44100, channels: int = 2,
                 config: dict | None = None) -> None:
        self.path = path
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self._config = config
        self._frame_bytes = _BYTES_PER_SAMPLE * self.channels
        self._q: queue.Queue = queue.Queue(maxsize=_QUEUE_MAX)
        self._leftover = np.zeros((0, self.channels), dtype=np.float32)
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._stop = threading.Event()
        self._eof = False              # ffmpeg cerró el pipe (no quedan más datos por venir)
        self._exhausted = False        # además, ya se consumió todo lo bufferizado
        # blocking=False (vivo): el callback NUNCA bloquea (underrun -> ceros).
        # blocking=True: para render OFFLINE (el bucle no debe adelantar a ffmpeg).
        self.blocking = False
        self.frames_read = 0           # muestras realmente consumidas (posición de reproducción)
        self.duration = probe_duration(path)
        self._spawn(0.0)

    # ------------------------------------------------------------------ ffmpeg
    def _spawn(self, start_s: float) -> None:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error"]
        if start_s > 0.01:
            cmd += ["-ss", f"{start_s:.3f}"]
        cmd += ["-i", self.path, "-f", "f32le",
                "-ar", str(self.samplerate), "-ac", str(self.channels), "pipe:1"]
        self._proc = proc.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._stop.clear()
        self._eof = False
        self._exhausted = False
        self._reader = threading.Thread(target=self._read_loop, args=(self._proc,), daemon=True)
        self._reader.start()

    def _read_loop(self, p: subprocess.Popen) -> None:
        remainder = b""
        try:
            while not self._stop.is_set():
                buf = p.stdout.read(_READ_BYTES)        # type: ignore[union-attr]
                if not buf:
                    break
                data = remainder + buf
                n_full = len(data) // self._frame_bytes
                cut = n_full * self._frame_bytes
                remainder = data[cut:]
                if n_full:
                    arr = np.frombuffer(data[:cut], dtype=np.float32).reshape(-1, self.channels)
                    # put bloqueante = back-pressure (pausa a ffmpeg si vamos llenos)
                    while not self._stop.is_set():
                        try:
                            self._q.put(arr, timeout=0.2)
                            break
                        except queue.Full:
                            continue
        except Exception:
            pass
        finally:
            try:
                self._q.put(None, timeout=1.0)          # centinela de fin
            except Exception:
                pass

    # ------------------------------------------------------------------ lectura
    def read(self, frames: int) -> np.ndarray:
        """Devuelve EXACTAMENTE `frames` muestras (frames, ch), rellenando con
        ceros si hay underrun o si la pista terminó."""
        out = np.zeros((frames, self.channels), dtype=np.float32)
        filled = 0
        # 1) lo que sobró del bloque anterior
        if len(self._leftover):
            take = min(frames, len(self._leftover))
            out[:take] = self._leftover[:take]
            self._leftover = self._leftover[take:]
            filled += take
        # 2) sacar de la cola hasta completar
        while filled < frames and not self._eof:
            try:
                chunk = self._q.get(timeout=1.0) if self.blocking else self._q.get_nowait()
            except queue.Empty:
                break                                    # underrun: quedan ceros
            if chunk is None:
                self._eof = True
                break
            need = frames - filled
            if len(chunk) <= need:
                out[filled:filled + len(chunk)] = chunk
                filled += len(chunk)
            else:
                out[filled:frames] = chunk[:need]
                self._leftover = chunk[need:]
                filled = frames
        if self._eof and filled < frames and len(self._leftover) == 0:
            self._exhausted = True
        self.frames_read += filled
        return out

    @property
    def finished(self) -> bool:
        return self._exhausted

    # ------------------------------------------------------------------ control
    def seek(self, seconds: float) -> None:
        self._kill()
        # vaciar la cola y el remanente
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._leftover = np.zeros((0, self.channels), dtype=np.float32)
        self.frames_read = int(max(0.0, float(seconds)) * self.samplerate)
        self._spawn(max(0.0, float(seconds)))

    def close(self) -> None:
        self._kill()

    def _kill(self) -> None:
        self._stop.set()
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=2)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
        self._proc = None
