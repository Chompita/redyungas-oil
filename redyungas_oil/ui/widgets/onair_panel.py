"""
ui/widgets/onair_panel.py — Paneles "En el aire" y "Siguiente" (réplica ZaraRadio).

OnAirPanel: badge "Reproduciendo ahora" (rojo) + título grande de la pista actual
            + "Tiempo restante" (LCD) + barras VU L/R + "Acaba a las".
NextPanel:  etiqueta "Siguiente" + título grande de la próxima pista.

Los valores son demo hasta la Fase 2, cuando el motor de audio los alimenta.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from .vu_widget import VuMeterWidget


class _TitleDisplay(QFrame):
    """Recuadro blanco hundido con el título grande, como los displays de ZaraRadio."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("titleDisplay")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        self.label = QLabel(text)
        self.label.setObjectName("titleText")
        self.label.setWordWrap(True)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.label)

    def set_title(self, text: str) -> None:
        self.label.setText(text)


class OnAirPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(3)

        # Badges superiores
        top = QHBoxLayout()
        air = QLabel("En el aire")
        air.setObjectName("sectionTag")
        playing = QLabel("Reproduciendo ahora")
        playing.setObjectName("badgePlaying")
        top.addWidget(air)
        top.addWidget(playing)
        top.addStretch(1)
        root.addLayout(top)

        # Título grande de la pista actual
        self.title = _TitleDisplay("00000001 FELIZ NAVIDAD-RED YUNGAS")
        root.addWidget(self.title, 1)

        # Fila inferior: tiempo restante | VU | acaba a las
        bottom = QGridLayout()
        bottom.setHorizontalSpacing(12)

        rem_tag = QLabel("Tiempo restante")
        rem_tag.setObjectName("sectionTag")
        self.remaining = QLabel("00:15.5")
        self.remaining.setObjectName("lcd")
        bottom.addWidget(rem_tag, 0, 0)
        bottom.addWidget(self.remaining, 1, 0)

        self.vu = VuMeterWidget()
        bottom.addWidget(self.vu, 0, 1, 2, 1)

        ends_tag = QLabel("Acaba a las")
        ends_tag.setObjectName("sectionTag")
        self.ends_at = QLabel("23:46:01")
        self.ends_at.setObjectName("lcdSmall")
        bottom.addWidget(ends_tag, 0, 2, alignment=Qt.AlignmentFlag.AlignRight)
        bottom.addWidget(self.ends_at, 1, 2, alignment=Qt.AlignmentFlag.AlignRight)

        bottom.setColumnStretch(1, 1)
        root.addLayout(bottom)

    # API que usará el motor de audio (Fase 2)
    def set_now_playing(self, title: str) -> None:
        self.title.set_title(title)

    def set_remaining(self, text: str) -> None:
        self.remaining.setText(text)

    def set_ends_at(self, text: str) -> None:
        self.ends_at.setText(text)


class NextPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 2, 4, 2)
        root.setSpacing(3)
        tag = QLabel("Siguiente")
        tag.setObjectName("sectionTag")
        root.addWidget(tag)
        self.title = _TitleDisplay("0000001 aaaaaaCuña 2 narcotráfico 52 segundos")
        root.addWidget(self.title, 1)

    def set_next(self, title: str) -> None:
        self.title.set_title(title)
