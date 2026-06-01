"""
core/proc.py — Lanzar procesos externos SIN ventana de consola (clave en Windows).

En Windows, cada `subprocess.run`/`subprocess.Popen` lanzado sin los flags
adecuados abre (y cierra) una **ventana de consola negra** parpadeante. Como el
software invoca ffmpeg/ffprobe/git/espeak/pactl en muchos sitios —y algunos en
bucle (el medidor del emisor, el sondeo de duración por cada audio)— el efecto
era una lluvia de ventanas que aparecían y desaparecían, dando la sensación de
que el software "no abre" o haciéndolo inusable.

Aquí se centralizan los flags para ocultarlas. En Linux/macOS `no_window_kwargs()`
devuelve `{}` (sin efecto). Úsese `proc.run(...)` y `proc.popen(...)` en lugar de
`subprocess.run`/`subprocess.Popen` en TODO el código que llame binarios externos.
"""

from __future__ import annotations

import subprocess
import sys

__all__ = ["no_window_kwargs", "run", "popen"]


def no_window_kwargs() -> dict:
    """kwargs para que un proceso hijo no muestre ventana de consola en Windows."""
    if sys.platform.startswith("win"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        # CREATE_NO_WINDOW evita la consola incluso si el padre no tiene una.
        return {
            "creationflags": subprocess.CREATE_NO_WINDOW,
            "startupinfo": startupinfo,
        }
    return {}


def run(cmd, **kwargs):
    """`subprocess.run` con la consola oculta en Windows."""
    merged = no_window_kwargs()
    merged.update(kwargs)
    return subprocess.run(cmd, **merged)


def popen(cmd, **kwargs):
    """`subprocess.Popen` con la consola oculta en Windows."""
    merged = no_window_kwargs()
    merged.update(kwargs)
    return subprocess.Popen(cmd, **merged)
