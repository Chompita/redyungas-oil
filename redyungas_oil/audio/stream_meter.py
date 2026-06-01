"""
audio/stream_meter.py — Medidor de decibelios L/R REAL del bus de programa.

Alimenta el visualizador del panel "PUERTO" (estilo Opticodec). A diferencia del
VU aproximado del motor, aquí se mide la señal de verdad: un ffmpeg ligero
captura la MISMA fuente que el emisor (monitor del sink) y, con el filtro
`astats`, publica el nivel RMS y de pico por canal en dBFS, ~20 veces/s:

    ffmpeg -f <fmt> -i <captura> \
      -af asetnsamples=n=2048:p=0,astats=metadata=1:reset=1,ametadata=mode=print:file=- \
      -f null -

Se lee la salida en un hilo y se emiten los niveles CRUDOS (sin ganancia). El
panel les suma la ganancia (saturación) para mostrar el efecto en vivo y avisar
de clip, sin tener que relanzar este proceso al mover el control.
"""

from __future__ import annotations

import logging
import math
import subprocess
import threading

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core import proc
from .capture import resolve_input

log = logging.getLogger("redyungas_oil.meter")

FLOOR_DB = -120.0
_CHECK_MS = 4000
_CHECK_MAX_MS = 30000   # tope del backoff cuando el medidor no logra arrancar


def _parse_db(value: str) -> float:
    v = value.strip()
    try:
        f = float(v)
    except ValueError:
        return FLOOR_DB
    if math.isinf(f) or math.isnan(f):
        return FLOOR_DB
    return f


class StreamMeter(QObject):
    # niveles CRUDOS en dBFS: (rms_L, rms_R, peak_L, peak_R)
    levels_changed = pyqtSignal(float, float, float, float)
    running_changed = pyqtSignal(bool)

    def __init__(self, config: dict, parent=None, source_url: str | None = None) -> None:
        super().__init__(parent)
        if source_url:                       # medir un stream recibido (URL)
            self._input = ["-i", source_url]
        else:                                # medir el bus de programa (captura)
            cap = (config.get("stream", {}) or {}).get("capture_device") or None
            fmt, device = resolve_input(config, cap)
            self._input = ["-f", fmt, "-i", device]
        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._want_running = False
        self._fail_count = 0
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._check)

    # --------------------------------------------------------------- comando
    def build_cmd(self) -> list[str]:
        return [
            "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "error",
            *self._input,
            "-af", ("asetnsamples=n=2048:p=0,"
                    "astats=metadata=1:reset=1,"
                    "ametadata=mode=print:file=-"),
            "-f", "null", "-",
        ]

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        if self._want_running:
            return
        self._want_running = True
        self._fail_count = 0
        self._spawn()
        self._watch.start(_CHECK_MS)

    def stop(self) -> None:
        self._want_running = False
        self._watch.stop()
        self._kill()
        self.running_changed.emit(False)

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self) -> None:
        if self.is_running():
            return
        try:
            self._proc = proc.popen(
                self.build_cmd(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, bufsize=1,
            )
        except Exception as exc:
            log.error("No se pudo lanzar el medidor ffmpeg: %s", exc)
            self._proc = None
            return
        self._reader = threading.Thread(target=self._read_loop, args=(self._proc,),
                                        daemon=True)
        self._reader.start()
        log.info("Medidor de stream PID %s sobre %s", self._proc.pid, " ".join(self._input))
        self.running_changed.emit(True)

    def _read_loop(self, proc: subprocess.Popen) -> None:
        """Hilo: parsea la metadata de astats y emite por canal y frame."""
        cur: dict[str, float] = {}

        def flush() -> None:
            if not cur:
                return
            rms_l = cur.get("1.RMS", FLOOR_DB)
            rms_r = cur.get("2.RMS", rms_l)        # mono -> R = L
            peak_l = cur.get("1.Peak", rms_l)
            peak_r = cur.get("2.Peak", rms_r)
            self.levels_changed.emit(rms_l, rms_r, peak_l, peak_r)

        try:
            for line in proc.stdout:               # type: ignore[union-attr]
                line = line.strip()
                if line.startswith("frame:"):
                    flush()
                    cur.clear()
                    continue
                if not line.startswith("lavfi.astats."):
                    continue
                key, _, val = line.partition("=")
                # key: lavfi.astats.<ch>.<Stat>
                parts = key.split(".")
                if len(parts) < 4:
                    continue
                ch, stat = parts[2], parts[3]
                if ch in ("1", "2"):
                    if stat == "RMS_level":
                        cur[f"{ch}.RMS"] = _parse_db(val)
                    elif stat == "Peak_level":
                        cur[f"{ch}.Peak"] = _parse_db(val)
            flush()
        except Exception as exc:                   # el proceso murió / pipe roto
            log.debug("Lector del medidor terminó: %s", exc)

    def _check(self) -> None:
        if not self._want_running:
            return
        if self.is_running():
            if self._fail_count:
                self._fail_count = 0
                self._watch.start(_CHECK_MS)     # vuelve al ritmo normal
            return
        # No logra arrancar (p. ej. dispositivo de captura inexistente): se reintenta
        # cada vez más espaciado para NO martillar ffmpeg en bucle.
        self._fail_count += 1
        log.debug("Medidor caído; reintento %s", self._fail_count)
        self._watch.start(min(_CHECK_MAX_MS, _CHECK_MS * self._fail_count))
        self._spawn()

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
