"""
REDYUNGAS OIL — Punto de entrada / orquestador.

Arranca la aplicación Qt, carga la config, inicializa el logging y muestra la
ventana principal. En fases posteriores también arrancará (según el perfil y la
config): el motor de audio, el receptor/emisor de red, el grabador, el
programador de eventos, el servidor MCP y los adaptadores (Telegram/JARVIS).

Uso:
    python -m redyungas_oil.app            # arranque normal
    RYO_SMOKE=1 python -m redyungas_oil.app  # smoke test (abre y cierra solo)

En Windows el estilo "windowsvista" da el look nativo de Win7; en Linux se usa
"Fusion" + la hoja de estilos ui/style/win7.qss (emulación).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QStyleFactory

from .core import constants as C
from .core.config import load_config
from .core.logging_setup import setup_logging


def _apply_style(app: QApplication) -> None:
    """Aplica el look ZaraRadio de forma IDÉNTICA en Linux y Windows.

    Se fuerza el estilo **Fusion + win7.qss** en TODAS las plataformas (no el
    estilo nativo Win11), para que el aspecto sea exactamente el mismo que se
    desarrolla/ajusta en Linux y se vea igual en las esclavas Windows
    (pixel-perfect controlado por la hoja de estilos, no por el SO).
    """
    if "Fusion" in set(QStyleFactory.keys()):
        app.setStyle("Fusion")
    qss = Path(__file__).resolve().parent / "ui" / "style" / "win7.qss"
    if qss.exists():
        app.setStyleSheet(qss.read_text(encoding="utf-8"))


def _install_excepthook(logger) -> None:
    """Registra cualquier excepción no controlada (no morir en silencio)."""
    def _hook(exc_type, exc, tb):
        logger.error("Excepción no controlada", exc_info=(exc_type, exc, tb))
        sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = _hook


def main() -> int:
    config = load_config()
    logger = setup_logging(config["paths"]["logs_folder"])
    _install_excepthook(logger)

    # Asegura que ffmpeg/ffprobe sean invocables (PATH) — clave en Windows, donde
    # no suelen estar en el PATH y rompían la emisión y el sondeo de duración.
    from .core.fftools import ensure_on_path
    ff = ensure_on_path(config)
    logger.info("ffmpeg=%s ffprobe=%s", ff.get("ffmpeg"), ff.get("ffprobe"))

    app = QApplication(sys.argv)
    app.setApplicationName(C.APP_NAME)
    app.setOrganizationName(C.ORG_NAME)
    _apply_style(app)

    # Import diferido para que el smoke test no falle si faltan widgets de fases futuras.
    from .ui.main_window import MainWindow

    window = MainWindow(config)
    window.show()

    if os.environ.get("RYO_SMOKE"):
        # Smoke test: procesa eventos, confirma que la ventana montó y cierra.
        QTimer.singleShot(800, app.quit)
        app.exec()
        print(f"SMOKE OK: {C.APP_NAME} v{C.APP_VERSION} arrancó y montó la ventana.")
        return 0

    shot = os.environ.get("RYO_SHOT")
    if shot:
        # Captura la ventana a un PNG (verificación visual durante el desarrollo).
        def _grab():
            window.grab().save(shot)
            print(f"SHOT OK: {shot}")
            app.quit()
        QTimer.singleShot(700, _grab)
        return app.exec()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
