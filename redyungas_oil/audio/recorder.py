"""
audio/recorder.py — Grabación de audio con PAUSA/REANUDAR en el MISMO archivo.

Graba el "bus de programa" (lo que sale al aire) con ffmpeg. Flujo pedido por el
operador, con TRES controles:

* **Grabar / Pausar-Reanudar** (un solo botón): el 1er clic empieza; el siguiente
  PAUSA (sin cortar el archivo final); el siguiente REANUDA en el MISMO archivo.
* **Detener**: termina la grabación y deja **un único archivo** (`grab_<fecha>.<ext>`).
* **Opciones**: carpeta de salida, formato (mp3 por defecto) y calidad.

Implementación: cada tramo entre pausas se graba en una parte temporal
(`<final>.partN.<ext>`); al **Detener** se **concatenan** (sin re-codificar) en el
archivo final → resulta UN archivo, sin huecos de silencio por las pausas. Al cerrar
emite `segment_closed(final)` para que JARVIS lo reciba (transcripción) como antes.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from ..core import proc
from .capture import resolve_input

log = logging.getLogger("redyungas_oil.recorder")

# Formato -> (extensión, args de códec para ffmpeg). 'q' = bitrate kbps (lossy).
_FORMATS = {
    "mp3":  ("mp3",  lambda q: ["-c:a", "libmp3lame", "-b:a", f"{q}k"]),
    "wav":  ("wav",  lambda q: ["-c:a", "pcm_s16le"]),
    "ogg":  ("ogg",  lambda q: ["-c:a", "libvorbis", "-b:a", f"{q}k"]),
    "aac":  ("m4a",  lambda q: ["-c:a", "aac", "-b:a", f"{q}k"]),
    "flac": ("flac", lambda q: ["-c:a", "flac"]),
}


class Recorder(QObject):
    state_changed = pyqtSignal(str)      # "recording" | "paused" | "stopped"
    segment_closed = pyqtSignal(str)     # ruta del archivo final ya cerrado

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self.reconfigure(config)
        logs_folder = (config.get("paths", {}) or {}).get("logs_folder", ".")
        self._log_path = Path(logs_folder) / "recorder_ffmpeg.log"
        self._proc: subprocess.Popen | None = None
        self._state = "stopped"
        self._parts: list[Path] = []      # partes del archivo final (una por tramo)
        self._final: Path | None = None   # archivo final de la sesión

    def reconfigure(self, config: dict) -> None:
        """Relee carpeta/formato/calidad (lo llama la ventana de opciones)."""
        self._config = config
        rec = (config.get("recording", {}) or {})
        self.bitrate = int(rec.get("bitrate", 192))
        fmt = str(rec.get("format", "mp3")).lower()
        self.fmt_name = fmt if fmt in _FORMATS else "mp3"
        self.fmt, self.device = resolve_input(config)
        self.folder = Path((config.get("paths", {}) or {}).get("recordings_folder", "grabaciones"))

    # --------------------------------------------------------------- estado
    def is_recording(self) -> bool:
        return self._state == "recording"

    def is_paused(self) -> bool:
        return self._state == "paused"

    def is_active(self) -> bool:
        return self._state in ("recording", "paused")

    def state(self) -> str:
        return self._state

    # --------------------------------------------------------------- ciclo
    def start(self) -> None:
        if self.is_active():
            return
        self.folder.mkdir(parents=True, exist_ok=True)
        ext, _ = _FORMATS.get(self.fmt_name, _FORMATS["mp3"])
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._final = self.folder / f"grab_{stamp}.{ext}"
        self._parts = []
        self._start_part()
        self.state_changed.emit("recording")

    def toggle_pause(self) -> None:
        """Pausa si está grabando; reanuda si está en pausa (mismo archivo)."""
        if self._state == "recording":
            self.pause()
        elif self._state == "paused":
            self.resume()

    def pause(self) -> None:
        if self._state != "recording":
            return
        self._stop_part()
        self._state = "paused"
        self.state_changed.emit("paused")

    def resume(self) -> None:
        if self._state != "paused":
            return
        self._start_part()
        self.state_changed.emit("recording")

    def stop(self) -> None:
        if not self.is_active():
            return
        self._stop_part()
        self._state = "stopped"
        final = self._finalize()
        self.state_changed.emit("stopped")
        if final and final.exists():
            log.info("Grabación finalizada: %s", final.name)
            self.segment_closed.emit(str(final))

    # --------------------------------------------------------------- interno
    def _start_part(self) -> None:
        ext, codec_args = _FORMATS.get(self.fmt_name, _FORMATS["mp3"])
        part = self.folder / f"{self._final.stem}.part{len(self._parts) + 1}.{ext}"
        self._parts.append(part)
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
               "-f", self.fmt, "-i", self.device, *codec_args(self.bitrate), str(part)]
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        logf = open(self._log_path, "ab")
        self._proc = proc.popen(cmd, stdout=subprocess.DEVNULL, stderr=logf)
        self._state = "recording"

    def _stop_part(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def _finalize(self) -> Path | None:
        """Une las partes en UN solo archivo final (sin re-codificar)."""
        parts = [p for p in self._parts if p.exists() and p.stat().st_size > 0]
        final = self._final
        self._parts = []
        self._final = None
        if not parts or final is None:
            return None
        if len(parts) == 1:
            parts[0].replace(final)
            return final
        listfile = final.with_suffix(final.suffix + ".concat.txt")
        listfile.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
               "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(final)]
        try:
            r = proc.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            if r.returncode == 0:
                for p in parts:
                    p.unlink(missing_ok=True)
                listfile.unlink(missing_ok=True)
                return final
        except Exception as exc:
            log.warning("No se pudo concatenar la grabación: %s", exc)
        # Si falla la unión, al menos conserva la primera parte como final.
        try:
            parts[0].replace(final)
        except Exception:
            return parts[0]
        return final
