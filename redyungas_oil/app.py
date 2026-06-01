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

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen, QStyleFactory

from .core import constants as C
from .core.branding import logo_path
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


def _make_splash_pixmap(logo: str | None) -> QPixmap:
    """Compón la imagen de la pantalla de carga: fondo degradado + logo + textos."""
    w, h = 620, 380
    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Fondo degradado oscuro con borde redondeado.
    grad = QLinearGradient(0, 0, 0, h)
    grad.setColorAt(0.0, QColor("#222b38"))
    grad.setColorAt(1.0, QColor("#10151d"))
    painter.setBrush(grad)
    painter.setPen(QColor("#3c4858"))
    painter.drawRoundedRect(0, 0, w - 1, h - 1, 16, 16)

    # Logo centrado.
    if logo:
        src = QPixmap(logo)
        if not src.isNull():
            scaled = src.scaledToWidth(440, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap((w - scaled.width()) // 2, 56, scaled)

    # Subtítulo y versión.
    painter.setPen(QColor("#e8edf3"))
    painter.setFont(QFont("Arial", 15, QFont.Weight.Bold))
    painter.drawText(0, h - 92, w, 26, Qt.AlignmentFlag.AlignHCenter,
                     "Automatización radial con IA")
    painter.setPen(QColor("#9fb0c4"))
    painter.setFont(QFont("Arial", 10))
    painter.drawText(0, h - 64, w, 20, Qt.AlignmentFlag.AlignHCenter,
                     f"{C.APP_NAME}  ·  v{C.APP_VERSION}")
    painter.end()
    return pm


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

    logo = logo_path()
    if logo:
        app.setWindowIcon(QIcon(logo))
    _apply_style(app)

    # Pantalla de carga: aparece DE INMEDIATO para que se vea que el software está
    # abriendo, aunque la primera arranque (VLC, red, MCP) tarde unos segundos
    # (antes daba la impresión de que "no se abre"). Se omite en smoke/captura.
    splash = None
    if not (os.environ.get("RYO_SMOKE") or os.environ.get("RYO_SHOT")):
        splash = QSplashScreen(_make_splash_pixmap(logo))
        splash.show()
        splash.showMessage("Iniciando…",
                           Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                           QColor("#e8edf3"))
        app.processEvents()

    # Import diferido para que el smoke test no falle si faltan widgets de fases futuras.
    from .ui.main_window import MainWindow

    window = MainWindow(config)
    if logo:
        window.setWindowIcon(QIcon(logo))
    window.show()
    if splash is not None:
        splash.finish(window)

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
