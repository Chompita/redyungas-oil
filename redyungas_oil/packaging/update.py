"""
packaging/update.py — Actualización sin GUI de REDYUNGAS OIL en una esclava.

Pensado para lanzarse por SSH (desde el servidor / MARCUS) o como tarea
programada en cada esclava. Hace `git pull --ff-only` si hay versión nueva.

    python -m redyungas_oil.packaging.update      # o: python packaging/update.py

Equivale a `python -m redyungas_oil.core.updater`. Para actualizar TODAS las
esclavas a la vez, itera las IPs Tailscale y ejecuta este módulo por SSH (igual
que MARCUS distribuye la publicidad).
"""

from __future__ import annotations

from redyungas_oil.core.updater import _cli

if __name__ == "__main__":
    raise SystemExit(_cli())
