"""
audio/capture.py — Resolución de la fuente de captura del "bus de programa".

Lo que sale al aire = la mezcla final del sistema (monitor del sink). Tanto el
emisor (encoder.py) como el grabador (recorder.py) capturan de la misma fuente,
así que la lógica vive aquí (DRY).

Fuente (config [network].capture_device):
    - "" (auto): Linux -> monitor del sink por defecto (pactl); otro SO -> "default".
    - "fmt:dispositivo": "pulse:NOMBRE.monitor" | "alsa:hw:0" | "dshow:audio=Cable Output".
"""

from __future__ import annotations

import sys

from ..core import proc

_KNOWN_FORMATS = {"pulse", "alsa", "dshow", "avfoundation", "lavfi"}


def default_format() -> str:
    if sys.platform.startswith("linux"):
        return "pulse"
    if sys.platform == "darwin":
        return "avfoundation"
    return "dshow"   # Windows


def default_monitor() -> str:
    try:
        sink = proc.run(["pactl", "get-default-sink"],
                        capture_output=True, text=True, timeout=5).stdout.strip()
        return f"{sink}.monitor" if sink else "default"
    except Exception:
        return "default"


def resolve_input(config: dict, capture: str | None = None) -> tuple[str, str]:
    """Resuelve (formato, dispositivo) de captura. `capture` (p. ej. el del emisor
    [stream].capture_device) tiene prioridad sobre [network].capture_device."""
    cap = (capture or (config.get("network", {}) or {}).get("capture_device", "") or "").strip()
    if cap:
        prefix = cap.split(":", 1)[0]
        if prefix in _KNOWN_FORMATS and ":" in cap:
            fmt, dev = cap.split(":", 1)
            return fmt, dev
        return default_format(), cap
    if sys.platform.startswith("linux"):
        return "pulse", default_monitor()
    return default_format(), "default"
