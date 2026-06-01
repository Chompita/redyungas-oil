"""
core/fftools.py — Localiza ffmpeg / ffprobe de forma robusta (Linux y Windows).

El emisor (`stream_encoder`), el medidor (`stream_meter`), el grabador
(`recorder`) y el sondeo de duración (`probe`) invocan `ffmpeg`/`ffprobe` por su
nombre, asumiendo que están en el PATH. En las esclavas Windows NO suelen estarlo
(p. ej. quedan en `%USERPROFILE%\\ffmpeg\\`), lo que rompía la emisión y dejaba las
duraciones en "--:--".

`ensure_on_path()` busca los binarios (config → PATH → junto al .exe → ubicaciones
típicas) y antepone su carpeta al PATH del proceso, de modo que TODAS las llamadas
`subprocess(["ffmpeg", ...])` funcionen sin tocar cada sitio de uso.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):                 # .exe PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]         # .../RED YUNGAS OIL


def _candidates(name: str) -> list[Path]:
    exe = name + (".exe" if sys.platform.startswith("win") else "")
    base = _base_dir()
    cands = [base / exe, base / "ffmpeg" / exe, base / "ffmpeg" / "bin" / exe]
    if sys.platform.startswith("win"):
        home = Path(os.environ.get("USERPROFILE", ""))
        cands += [home / "ffmpeg" / exe, home / "ffmpeg" / "bin" / exe,
                  Path(r"C:\ffmpeg\bin") / exe, Path(r"C:\ffmpeg") / exe]
    return cands


def resolve(name: str, config: dict | None = None) -> str:
    """Devuelve la ruta a ffmpeg/ffprobe, o el nombre pelado si no se encuentra."""
    if config:
        override = (config.get("paths", {}) or {}).get(name)
        if override and Path(override).exists():
            return str(override)
    found = shutil.which(name)
    if found:
        return found
    for c in _candidates(name):
        if c.exists():
            return str(c)
    return name


def ensure_on_path(config: dict | None = None) -> dict[str, str]:
    """Antepone al PATH la carpeta de ffmpeg/ffprobe encontrada. Idempotente."""
    resolved: dict[str, str] = {}
    parts = os.environ.get("PATH", "").split(os.pathsep)
    for name in ("ffmpeg", "ffprobe"):
        path = resolve(name, config)
        resolved[name] = path
        folder = os.path.dirname(path)
        if folder and folder not in parts:
            os.environ["PATH"] = folder + os.pathsep + os.environ.get("PATH", "")
            parts.insert(0, folder)
    return resolved


def available(name: str, config: dict | None = None) -> bool:
    p = resolve(name, config)
    return os.path.isabs(p) or shutil.which(p) is not None
