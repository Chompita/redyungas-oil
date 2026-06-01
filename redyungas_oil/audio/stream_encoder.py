"""
audio/stream_encoder.py — Emisor público estilo Opticodec (panel "PUERTO").

Reemplaza a *Orban Opticodec-PC*: empuja al SHOUTcast/Icecast público
(`stream.example.com:8032`) el bus de programa REAL del sistema —la mezcla
final (playout + crossfades + cuñas + pisador + locuciones)— capturando el
monitor del dispositivo de salida con ffmpeg y aplicando una **ganancia
independiente** (control de saturación del panel).

Dos modos según `[stream].server_type`:

* **shoutcast** — protocolo NATIVO SHOUTcast v1 (el que usa Opticodec). Se
  descubrió en vivo contra el DNAS v2.5.5 de Red Yungas: ffmpeg NO habla este
  protocolo (su `-legacy_icecast` envía `SOURCE … HTTP/1.1`, que el DNAS
  rechaza). Aquí se implementa a mano, en Python puro (sin dependencias, va en
  Windows): socket → `"<pass>\\r\\nicy-name:…\\r\\n…\\r\\n\\r\\n"` → el server
  responde `OK2` → se bombea el MP3 de ffmpeg (stdout) al socket. La metadata
  "sonando ahora" se manda por `GET /admin.cgi?…&mode=updinfo&song=…`.

* **icecast** — Icecast2 nativo: ffmpeg empuja directo con su muxer `icecast://`
  (método PUT/SOURCE), sin socket intermedio.

Códec: `mp3` (libmp3lame, el más compatible) o `aac` (LC). HE-AAC/aacPlus exige
`libfdk_aac`, que el ffmpeg estándar NO trae; por eso por defecto sale en MP3
128k (lo escuchan igual todos los oyentes del DNAS).

El emisor se vigila: si ffmpeg muere o el socket se rompe, se reconecta solo. Al
cambiar la ganancia en vivo se relanza con el nuevo `volume`.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import threading
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .capture import resolve_input

log = logging.getLogger("redyungas_oil.stream")

_RETRY_MS = 5000
_CHUNK = 4096


class StreamEncoder(QObject):
    state_changed = pyqtSignal(str)     # "emitting" | "stopped" | "reconnecting"

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self._proc: subprocess.Popen | None = None
        self._sock: socket.socket | None = None
        self._pump: threading.Thread | None = None
        self._pump_alive = False
        self._want_running = False
        self._last_song = ""
        self._monitor = QTimer(self)
        self._monitor.timeout.connect(self._check)
        self._apply_config(config)

    def _apply_config(self, config: dict) -> None:
        self._config = config
        st = (config.get("stream", {}) or {})
        self.server_type = (st.get("server_type", "shoutcast") or "shoutcast").lower()
        self.host = st.get("host", "")
        self.port = int(st.get("port", 8032))
        self.mount = st.get("mount", "/stream") or "/stream"
        if not self.mount.startswith("/"):
            self.mount = "/" + self.mount
        self.user = st.get("user", "source") or "source"
        self.password = st.get("password", "")
        self.bitrate = int(st.get("bitrate", 128))
        self.codec = (st.get("codec", "mp3") or "mp3").lower()
        self.sample_rate = int(st.get("sample_rate", 44100))
        self.channels = int(st.get("channels", 2))
        self.gain_db = float(st.get("gain_db", 0.0))
        self.stream_name = st.get("stream_name", "RED YUNGAS")
        self.genre = st.get("genre", "Various")
        self.website = st.get("website", "")
        self.description = st.get("description", "")
        self.fmt, self.device = resolve_input(config)
        logs_folder = (config.get("paths", {}) or {}).get("logs_folder", ".")
        self._log_path = Path(logs_folder) / "stream_ffmpeg.log"

    def reconfigure(self, config: dict) -> None:
        """Reaplica la config (tras Ajustes). Relanza si estaba emitiendo."""
        running = self._want_running
        self._apply_config(config)
        if running:
            self._teardown()
            self._spawn()

    # ----------------------------------------------------------- ffmpeg args
    def public_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def _content_type(self) -> str:
        return "audio/aac" if self.codec == "aac" else "audio/mpeg"

    def _ffmpeg_base(self) -> list[str]:
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
        if self.fmt == "lavfi":               # fuente de test: necesita pacing
            cmd += ["-re"]
        cmd += ["-f", self.fmt, "-i", self.device]
        if abs(self.gain_db) > 0.01:
            cmd += ["-af", f"volume={self.gain_db}dB"]
        cmd += ["-ar", str(self.sample_rate), "-ac", str(self.channels)]
        if self.codec == "aac":
            cmd += ["-c:a", "aac", "-b:a", f"{self.bitrate}k", "-f", "adts"]
        else:
            cmd += ["-c:a", "libmp3lame", "-b:a", f"{self.bitrate}k", "-f", "mp3"]
        return cmd

    def build_cmd(self) -> list[str]:
        """Comando para modo Icecast (empuja directo) — útil para inspección/tests."""
        cmd = self._ffmpeg_base()[:-2]        # quita "-f mp3/adts"
        ct = self._content_type()
        cmd += ["-content_type", ct]
        if self.stream_name:
            cmd += ["-ice_name", self.stream_name]
        if self.genre:
            cmd += ["-ice_genre", self.genre]
        if self.website:
            cmd += ["-ice_url", self.website]
        fmt = "adts" if self.codec == "aac" else "mp3"
        cmd += ["-f", fmt,
                f"icecast://{self.user}:{self.password}@{self.host}:{self.port}{self.mount}"]
        return cmd

    # --------------------------------------------------------------- ajustes
    def set_gain_db(self, gain_db: float) -> None:
        if abs(gain_db - self.gain_db) < 0.01:
            return
        self.gain_db = float(gain_db)
        if self._want_running:
            self._teardown()
            self._spawn()

    def set_metadata(self, song: str) -> None:
        """Actualiza el 'sonando ahora' del DNAS (no bloquea la UI)."""
        if not song or song == self._last_song or self.server_type != "shoutcast":
            return
        self._last_song = song
        if not (self._want_running and self.password and self.host):
            return
        url = (f"http://{self.host}:{self.port}/admin.cgi?sid=1&pass="
               f"{quote(self.password)}&mode=updinfo&song={quote(song)}")
        threading.Thread(target=self._http_get, args=(url,), daemon=True).start()

    @staticmethod
    def _http_get(url: str) -> None:
        try:
            urlopen(url, timeout=6).read(64)
        except Exception as exc:
            log.debug("updinfo falló: %s", exc)

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        self._want_running = True
        self._spawn()
        self._monitor.start(_RETRY_MS)

    def stop(self) -> None:
        self._want_running = False
        self._monitor.stop()
        self._teardown()
        self.state_changed.emit("stopped")

    def is_emitting(self) -> bool:
        if self._proc is None or self._proc.poll() is not None:
            return False
        if self.server_type == "shoutcast":
            return self._pump_alive
        return True

    def _spawn(self) -> None:
        if self.is_emitting():
            return
        try:
            if self.server_type == "shoutcast":
                self._spawn_shoutcast()
            else:
                self._spawn_icecast()
            self.state_changed.emit("emitting")
        except Exception as exc:
            log.error("No se pudo iniciar el emisor: %s", exc)
            self._teardown()
            self.state_changed.emit("reconnecting")

    def _open_log(self):
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        return open(self._log_path, "ab")

    def _spawn_icecast(self) -> None:
        self._proc = subprocess.Popen(self.build_cmd(), stdout=subprocess.DEVNULL,
                                      stderr=self._open_log())
        log.info("Emisor Icecast ffmpeg PID %s -> %s%s", self._proc.pid,
                 self.public_url(), self.mount)

    def _spawn_shoutcast(self) -> None:
        # 1) Handshake nativo SHOUTcast v1.
        sock = socket.create_connection((self.host, self.port), timeout=8)
        handshake = (
            f"{self.password}\r\n"
            f"icy-name:{self.stream_name}\r\n"
            f"icy-genre:{self.genre}\r\n"
            f"icy-url:{self.website}\r\n"
            f"icy-br:{self.bitrate}\r\n"
            f"icy-pub:1\r\n"
            f"content-type:{self._content_type()}\r\n\r\n"
        ).encode("utf-8", "replace")
        sock.sendall(handshake)
        sock.settimeout(6)
        resp = sock.recv(100)
        if b"OK2" not in resp and not resp.startswith(b"OK"):
            sock.close()
            raise RuntimeError(f"DNAS rechazó el source: {resp!r}")
        sock.settimeout(None)
        self._sock = sock
        # 2) ffmpeg -> MP3/ADTS a stdout (pipe:1).
        self._proc = subprocess.Popen(self._ffmpeg_base() + ["pipe:1"],
                                      stdout=subprocess.PIPE, stderr=self._open_log())
        # 3) Hilo que bombea ffmpeg -> socket.
        self._pump_alive = True
        self._pump = threading.Thread(target=self._pump_loop,
                                      args=(self._proc, sock), daemon=True)
        self._pump.start()
        log.info("Emisor SHOUTcast PID %s -> %s%s (%s %sk, gain %+.1f dB)",
                 self._proc.pid, self.public_url(), self.mount,
                 self.codec, self.bitrate, self.gain_db)

    def _pump_loop(self, proc: subprocess.Popen, sock: socket.socket) -> None:
        try:
            while self._want_running:
                chunk = proc.stdout.read(_CHUNK)        # type: ignore[union-attr]
                if not chunk:
                    break
                sock.sendall(chunk)
        except Exception as exc:
            log.warning("Bomba SHOUTcast cortada: %s", exc)
        finally:
            self._pump_alive = False
            try:
                sock.close()
            except Exception:
                pass

    def _check(self) -> None:
        if not self._want_running:
            return
        if not self.is_emitting():
            log.warning("Emisor caído; reconectando (ver %s)", self._log_path.name)
            self.state_changed.emit("reconnecting")
            self._teardown()
            self._spawn()

    def _teardown(self) -> None:
        self._pump_alive = False
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._pump = None
