"""
audio/encoder.py — Emisor a Icecast, modo ESTUDIO (FASE 5).

Empuja al servidor Icecast remoto (`...:8032`, ya existe) la señal que REALMENTE
sale al aire — la mezcla final del sistema (playout + crossfades + cuñas + pisador
+ locuciones) — capturando el monitor del dispositivo de salida con ffmpeg:

    ffmpeg -f <fmt> -i <captura> -c:a libmp3lame -b:a 128k \
           -content_type audio/mpeg -f mp3 icecast://source:<pass>@<host>:<port><mount>

Fuente de captura (config [network].capture_device):
    - "" (auto): Linux -> monitor del sink por defecto (PipeWire/Pulse); otro -> "default".
    - "fmt:dispositivo": p.ej. "pulse:mi_sink.monitor", "alsa:hw:0",
      "dshow:audio=Cable Output" (Windows con cable de audio virtual).

El proceso ffmpeg se vigila: si muere (caída de red, etc.) se reintenta solo.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from ..core import proc
from .capture import resolve_input

log = logging.getLogger("redyungas_oil.encoder")

_RETRY_MS = 5000


class IcecastEncoder(QObject):
    state_changed = pyqtSignal(str)     # "emitting" | "stopped" | "reconnecting"

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        net = (config.get("network", {}) or {})
        self.host = net.get("icecast_host", "")
        self.port = int(net.get("icecast_port", 8032))
        self.mount = net.get("icecast_mount", "/live")
        self.password = net.get("icecast_password", "")
        self.bitrate = int(net.get("icecast_bitrate", 128))
        self.fmt, self.device = resolve_input(config)

        logs_folder = (config.get("paths", {}) or {}).get("logs_folder", ".")
        self._log_path = Path(logs_folder) / "encoder_ffmpeg.log"
        self._proc: subprocess.Popen | None = None
        self._want_running = False
        self._monitor = QTimer(self)
        self._monitor.timeout.connect(self._check)

    # --------------------------------------------------------------- comando
    def source_url(self) -> str:
        return f"icecast://source:{self.password}@{self.host}:{self.port}{self.mount}"

    def build_cmd(self) -> list[str]:
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "warning",
            "-f", self.fmt, "-i", self.device,
            "-c:a", "libmp3lame", "-b:a", f"{self.bitrate}k",
            "-content_type", "audio/mpeg", "-f", "mp3",
            self.source_url(),
        ]

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        self._want_running = True
        self._spawn()
        self._monitor.start(_RETRY_MS)

    def stop(self) -> None:
        self._want_running = False
        self._monitor.stop()
        self._kill()
        self.state_changed.emit("stopped")

    def is_emitting(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _spawn(self) -> None:
        if self.is_emitting():
            return
        try:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            logf = open(self._log_path, "ab")
            self._proc = proc.popen(self.build_cmd(), stdout=subprocess.DEVNULL,
                                    stderr=logf)
            log.info("Encoder ffmpeg PID %s -> %s:%s%s",
                     self._proc.pid, self.host, self.port, self.mount)
            self.state_changed.emit("emitting")
        except Exception as exc:
            log.error("No se pudo lanzar ffmpeg: %s", exc)
            self._proc = None
            self.state_changed.emit("reconnecting")

    def _check(self) -> None:
        if not self._want_running:
            return
        if not self.is_emitting():
            log.warning("Encoder caído; reintentando (ver %s)", self._log_path.name)
            self.state_changed.emit("reconnecting")
            self._spawn()

    def _kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
