"""
audio/recorder.py — Grabación de la transmisión con segmentación (FASE 6).

Graba el "bus de programa" (lo que sale al aire = monitor del sink, igual que el
emisor) con ffmpeg y el muxer `segment`, cerrando un MP3 nuevo cada
`recording.segment_seconds` (30 min por defecto). Cada vez que un segmento se
cierra emite `segment_closed(path)`; la ventana principal lo entrega a JARVIS
(integrations/jarvis_adapter.py) para transcripción + diarización.

    ffmpeg -f <fmt> -i <captura> -f segment -segment_time 1800 -reset_timestamps 1 \
           -strftime 1 -c:a libmp3lame -b:a 192k "grab_%Y%m%d_%H%M%S.mp3"

Los segmentos se nombran con su marca de tiempo (orden cronológico = orden léxico).
Un segmento se considera CERRADO cuando ffmpeg ya abrió el siguiente, o al detener.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .capture import resolve_input

log = logging.getLogger("redyungas_oil.recorder")

_WATCH_MS = 1000


class Recorder(QObject):
    state_changed = pyqtSignal(str)      # "recording" | "stopped"
    segment_closed = pyqtSignal(str)     # ruta de un segmento ya cerrado

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        rec = (config.get("recording", {}) or {})
        self.segment_seconds = int(rec.get("segment_seconds", 1800))
        self.bitrate = int(rec.get("bitrate", 192))
        self.fmt, self.device = resolve_input(config)
        self.folder = Path((config.get("paths", {}) or {}).get("recordings_folder", "grabaciones"))

        logs_folder = (config.get("paths", {}) or {}).get("logs_folder", ".")
        self._log_path = Path(logs_folder) / "recorder_ffmpeg.log"
        self._proc: subprocess.Popen | None = None
        self._preexisting: set[str] = set()
        self._appeared: list[str] = []
        self._delivered: set[str] = set()
        self._watch = QTimer(self)
        self._watch.timeout.connect(self._tick)

    def is_recording(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        if self.is_recording():
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        self._preexisting = set(self._current_files())
        self._appeared = []
        self._delivered = set()
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", self.fmt, "-i", self.device,
            "-f", "segment", "-segment_time", str(self.segment_seconds),
            "-reset_timestamps", "1", "-strftime", "1",
            "-c:a", "libmp3lame", "-b:a", f"{self.bitrate}k",
            str(self.folder / "grab_%Y%m%d_%H%M%S.mp3"),
        ]
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        logf = open(self._log_path, "ab")
        self._proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=logf)
        log.info("Grabando (segmentos de %s s) en %s", self.segment_seconds, self.folder)
        self._watch.start(_WATCH_MS)
        self.state_changed.emit("recording")

    def stop(self) -> None:
        self._watch.stop()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        # El último segmento (el que estaba escribiéndose) ahora está cerrado.
        self._tick(final=True)
        self.state_changed.emit("stopped")

    # --------------------------------------------------------------- interno
    def _current_files(self) -> list[str]:
        if not self.folder.is_dir():
            return []
        return sorted(str(p) for p in self.folder.glob("grab_*.mp3"))

    def _tick(self, final: bool = False) -> None:
        for f in self._current_files():
            if f not in self._preexisting and f not in self._appeared:
                self._appeared.append(f)
        # Todos los aparecidos menos el último siguen escribiéndose -> los previos están cerrados.
        # Al detener (final=True), también el último se considera cerrado.
        closed = self._appeared if final else self._appeared[:-1]
        for f in closed:
            if f not in self._delivered and Path(f).exists():
                self._delivered.add(f)
                log.info("Segmento cerrado: %s", Path(f).name)
                self.segment_closed.emit(f)
