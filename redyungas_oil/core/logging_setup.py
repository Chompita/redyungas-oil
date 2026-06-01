"""
REDYUNGAS OIL — Configuración de logging.

Un único `setup_logging()` que escribe a consola y a un archivo rotativo en la
carpeta de logs. El "Explorador del registro" de la UI (Fase 8) leerá estos
archivos, igual que ZaraRadio.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_CONFIGURED = False


def setup_logging(logs_folder: str | Path, level: int = logging.INFO) -> logging.Logger:
    """Inicializa el logging global (idempotente). Devuelve el logger raíz RYO."""
    global _CONFIGURED
    logger = logging.getLogger("redyungas_oil")
    if _CONFIGURED:
        return logger

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    try:
        folder = Path(logs_folder)
        folder.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            folder / "redyungas_oil.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except OSError as exc:  # carpeta no escribible: seguimos solo con consola
        logger.warning("No se pudo crear el log de archivo: %s", exc)

    _CONFIGURED = True
    return logger
