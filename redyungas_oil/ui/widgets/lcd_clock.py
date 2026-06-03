"""
ui/widgets/lcd_clock.py — Barra de reloj + fecha + MICRÓFONO del locutor.

Es la franja informativa bajo el panel "Siguiente" (ver capturas). Reloj en vivo
(QTimer cada segundo) con fecha en español. Donde antes estaba el clima ahora va
el botón de **micrófono** (auto-ducking): se enciende/apaga y abre su ventana de
ajustes. El estado encendido se ve resaltado (verde) y parpadea al detectar voz.
"""

from __future__ import annotations

from PyQt6.QtCore import QDateTime, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QToolButton, QVBoxLayout, QWidget

_DIAS = ["lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."]
_MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.",
          "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]


class ClockBar(QWidget):
    mic_clicked = pyqtSignal()        # abrir ajustes / activar el micrófono

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(16)

        # Bloque fecha + hora
        dt_block = QVBoxLayout()
        dt_block.setSpacing(0)
        self.date_label = QLabel("—")
        self.date_label.setObjectName("clockDate")
        self.time_label = QLabel("--:--:--")
        self.time_label.setObjectName("clockTime")
        dt_block.addWidget(self.date_label)
        dt_block.addWidget(self.time_label)
        layout.addWidget(QLabel("🕓"))
        layout.addLayout(dt_block)

        layout.addStretch(1)

        # Botón de MICRÓFONO (en lugar del antiguo clima): abre sus ajustes y
        # refleja el estado (apagado/encendido/hablando).
        self.mic_btn = QToolButton()
        self.mic_btn.setObjectName("micButton")
        self.mic_btn.setText("🎙  Micrófono")
        self.mic_btn.setToolTip("Entrada de micrófono y auto-ducking — clic para configurar/activar")
        self.mic_btn.clicked.connect(self.mic_clicked)
        layout.addWidget(self.mic_btn)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)
        self._tick()

    def _tick(self) -> None:
        now = QDateTime.currentDateTime()
        d = now.date()
        dow = _DIAS[d.dayOfWeek() - 1]
        self.date_label.setText(f"{dow}, {d.day():02d} {_MESES[d.month() - 1]}")
        t = now.time()
        h = t.hour()
        ampm = "a. m." if h < 12 else "p. m."
        h12 = h % 12 or 12
        self.time_label.setText(f"{h12}:{t.minute():02d}:{t.second():02d} {ampm}")

    def set_mic_state(self, enabled: bool, speaking: bool = False) -> None:
        """Apagado=gris · encendido=verde · hablando=verde brillante."""
        if not enabled:
            state, txt = "off", "🎙  Micrófono"
        elif speaking:
            state, txt = "speaking", "🎙  AL AIRE"
        else:
            state, txt = "on", "🎙  Micrófono ON"
        self.mic_btn.setText(txt)
        self.mic_btn.setProperty("micState", state)
        self.mic_btn.style().unpolish(self.mic_btn)
        self.mic_btn.style().polish(self.mic_btn)
