"""
audio/probe.py — Sondeo de duración con ffprobe (en segundo plano).

Añadir pistas a la lista debe ser instantáneo; la duración se resuelve después en
un hilo del QThreadPool y se emite por señal para actualizar la fila (sin congelar
la UI).
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from ..core import proc


def probe_duration(path: str) -> float:
    """Duración en segundos vía ffprobe; 0.0 si falla."""
    try:
        out = proc.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=20,
        )
        data = json.loads(out.stdout or "{}")
        return float(data.get("format", {}).get("duration", 0.0) or 0.0)
    except Exception:
        return 0.0


class ProbeSignals(QObject):
    probed = pyqtSignal(str, float)   # (path, duración)


class ProbeTask(QRunnable):
    def __init__(self, path: str, signals: ProbeSignals) -> None:
        super().__init__()
        self.path = path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        self.signals.probed.emit(self.path, probe_duration(self.path))
