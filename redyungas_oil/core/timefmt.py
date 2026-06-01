"""
core/timefmt.py — Formato de tiempos al estilo ZaraRadio.

ZaraRadio muestra duraciones/tiempo restante como MM:SS.s (ej. 00:17.7, 13:58.9)
y "Acaba a las" como HH:MM:SS.
"""

from __future__ import annotations


def fmt_mmss_tenths(seconds: float | None) -> str:
    """Formatea segundos como 'MM:SS.s' (minutos sin límite de 60)."""
    if not seconds or seconds < 0:
        seconds = 0.0
    minutes = int(seconds // 60)
    rest = seconds - minutes * 60
    return f"{minutes:02d}:{rest:04.1f}"
