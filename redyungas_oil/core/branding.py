"""
core/branding.py — Localiza los recursos de marca (logo RED YUNGAS).

El logo vive en `redyungas_oil/resources/branding/logo.png` y se empaqueta con
PyInstaller (ver los .spec). Esta función devuelve su ruta tanto en desarrollo
como en el .exe congelado (la jerarquía de carpetas se conserva en ambos casos).
"""

from __future__ import annotations

from pathlib import Path

# .../redyungas_oil/resources/branding   (parents[1] = el paquete redyungas_oil)
_BRANDING_DIR = Path(__file__).resolve().parents[1] / "resources" / "branding"


def logo_path() -> str | None:
    """Ruta al logo PNG, o None si no está disponible."""
    p = _BRANDING_DIR / "logo.png"
    return str(p) if p.exists() else None
