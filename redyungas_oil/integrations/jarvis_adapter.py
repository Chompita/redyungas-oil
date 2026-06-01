"""
integrations/jarvis_adapter.py — Entrega de grabaciones a JARVIS (FASE 6).

Toma cada segmento MP3 (30 min) que cierra el grabador y lo entrega a JARVIS para
transcripción + diarización (WhisperX/pyannote), por una de sus interfaces PÚBLICAS
(NO modifica JARVIS):

    - "folder": copia el MP3 a una carpeta vigilada por JARVIS (lo más desacoplado).
    - "api":    POST multipart a transcription_api (`:9120/api/transcription/jobs`).

La entrega corre en un hilo del QThreadPool (no bloquea la UI) con reintentos. Si
JARVIS no está disponible, el archivo queda en disco para reintentar/recuperar.
"""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

import httpx
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

log = logging.getLogger("redyungas_oil.jarvis")


class _DeliverSignals(QObject):
    done = pyqtSignal(str, bool)     # (ruta, ok)


class _DeliverTask(QRunnable):
    def __init__(self, path: str, mode: str, api: str, watch_folder: str,
                 signals: _DeliverSignals) -> None:
        super().__init__()
        self.path = path
        self.mode = mode
        self.api = api
        self.watch_folder = watch_folder
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        ok = False
        for attempt in range(3):
            try:
                if self.mode == "api":
                    ok = self._post()
                else:
                    ok = self._copy()
                if ok:
                    break
            except Exception as exc:
                log.warning("Entrega a JARVIS falló (intento %s): %s", attempt + 1, exc)
            time.sleep(2 * (attempt + 1))
        self.signals.done.emit(self.path, ok)

    def _copy(self) -> bool:
        dest = Path(self.watch_folder)
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(self.path, dest / Path(self.path).name)
        log.info("Grabación copiada a carpeta JARVIS: %s", dest)
        return True

    def _post(self) -> bool:
        with open(self.path, "rb") as fh:
            files = {"file": (Path(self.path).name, fh, "audio/mpeg")}
            resp = httpx.post(self.api, files=files, timeout=60.0)
        if resp.status_code in (200, 201, 202):
            log.info("Grabación enviada a la API de JARVIS: %s", resp.status_code)
            return True
        log.warning("API JARVIS respondió %s: %s", resp.status_code, resp.text[:160])
        return False


class JarvisAdapter(QObject):
    delivered = pyqtSignal(str, bool)    # (ruta, ok)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        j = (config or {}).get("jarvis", {}) or {}
        self.enabled = bool(j.get("enabled"))
        self.mode = j.get("delivery_mode", "folder")
        self.api = j.get("transcription_api", "")
        self.watch_folder = j.get("watch_folder", "")
        self._signals = _DeliverSignals(self)
        self._signals.done.connect(self.delivered.emit)
        self._pool = QThreadPool.globalInstance()

    def deliver_recording(self, mp3_path: str) -> bool:
        """Encola la entrega de un MP3. Devuelve True si se intentará entregar."""
        if not self.enabled:
            log.info("JARVIS desactivado; grabación guardada en disco: %s", Path(mp3_path).name)
            return False
        if self.mode == "folder" and not self.watch_folder:
            log.warning("delivery_mode=folder pero watch_folder vacío; no se entrega.")
            return False
        if self.mode == "api" and not self.api:
            log.warning("delivery_mode=api pero transcription_api vacío; no se entrega.")
            return False
        self._pool.start(_DeliverTask(mp3_path, self.mode, self.api, self.watch_folder, self._signals))
        return True
