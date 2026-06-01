"""
network/icecast_client.py — Utilidades del cliente Icecast (FASE 4/5).

Helpers para construir URLs de stream, comprobar disponibilidad del mount y
leer metadatos. El servidor Icecast es externo (ya existe).
"""

from __future__ import annotations


def build_source_url(host: str, port: int, mount: str, password: str) -> str:
    """URL de emisión (source) para ffmpeg. Implementación en Fase 5."""
    raise NotImplementedError("build_source_url se implementa en la Fase 5.")
