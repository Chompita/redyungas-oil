"""
audio/locutions.py — Locuciones de hora / temperatura / humedad (FASE 3).

Genera el archivo de audio a reproducir para una locución. Dos estrategias, en
orden de preferencia:
    1) FRAGMENTOS pregrabados (estilo ZaraRadio / voz de JARVIS): si se configura
       una carpeta de fragmentos, se ensamblan (calidad de radio). [gancho futuro]
    2) TTS de respaldo (espeak-ng / pico2wave): voz robótica pero funcional, para
       que la función opere sin depender de nada más.
Si no hay ninguna vía disponible, devuelve None y el motor lo omite con aviso.

>>> IA: la voz de calidad la proveerá JARVIS; aquí queda el gancho. <<<
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path


def _tts_tool() -> str | None:
    for tool in ("espeak-ng", "espeak", "pico2wave"):
        if shutil.which(tool):
            return tool
    return None


def _synth(text: str, out_path: str, tool: str, lang: str = "es") -> bool:
    try:
        if tool in ("espeak-ng", "espeak"):
            subprocess.run([tool, "-v", lang, "-s", "150", "-w", out_path, text],
                           check=True, capture_output=True, timeout=15)
            return True
        if tool == "pico2wave":
            subprocess.run(["pico2wave", "-l", "es-ES", "-w", out_path, text],
                           check=True, capture_output=True, timeout=15)
            return True
    except Exception:
        return False
    return False


class LocutionMaker:
    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.cache_dir = Path(tempfile.gettempdir()) / "redyungas_oil_loc"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.tool = _tts_tool()
        # Carpeta de fragmentos pregrabados (vacía = usar TTS). Gancho para Fase futura.
        self.fragments_dir = (self.config.get("paths", {}) or {}).get("locutions_folder", "")

    def available(self) -> bool:
        return bool(self.tool) or bool(self.fragments_dir)

    def make(self, kind: str, weather: tuple[float, float] = (0.0, 0.0)) -> str | None:
        text, name = self._text(kind, weather)
        if not text:
            return None
        # (1) Fragmentos pregrabados -> Fase futura (assemble). Por ahora, TTS.
        if not self.tool:
            return None
        out = self.cache_dir / f"{name}.wav"
        return str(out) if _synth(text, str(out), self.tool) else None

    @staticmethod
    def _text(kind: str, weather: tuple[float, float]):
        if kind == "time":
            now = datetime.now()
            h = now.hour % 12 or 12
            m = now.minute
            text = f"Son las {h} en punto." if m == 0 else f"Son las {h} y {m} minutos."
            return text, "loc_time"
        if kind == "temperature":
            return f"Temperatura, {int(weather[0])} grados.", "loc_temp"
        if kind == "humidity":
            return f"Humedad, {int(weather[1])} por ciento.", "loc_hum"
        return None, None
