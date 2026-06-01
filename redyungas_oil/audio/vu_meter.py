"""
audio/vu_meter.py — Medición de niveles L/R para las barras VU (FASE 2).

Obtiene niveles del audio que suena (callback de audio de VLC o análisis RMS) y
emite valores 0..1 por canal para pintar las barras verdes del panel "En el aire".
"""

from __future__ import annotations


class VuMeter:
    """Fuente de niveles L/R. Implementación real en Fase 2."""

    def __init__(self) -> None:
        raise NotImplementedError("VuMeter se implementa en la Fase 2.")
