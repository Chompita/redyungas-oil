"""
ui/widgets/lcd_clock.py — Barra de reloj + fecha + temperatura + humedad.

Es la franja informativa bajo el panel "Siguiente" (ver capturas). Reloj en vivo
(QTimer cada segundo) con fecha en español, y placeholders de temperatura/humedad
que en una fase futura se alimentarán de una fuente de clima.
"""

from __future__ import annotations

from PyQt6.QtCore import QDateTime, Qt, QTimer
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

_DIAS = ["lun.", "mar.", "mié.", "jue.", "vie.", "sáb.", "dom."]
_MESES = ["ene.", "feb.", "mar.", "abr.", "may.", "jun.",
          "jul.", "ago.", "sep.", "oct.", "nov.", "dic."]


class ClockBar(QWidget):
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

        # Temperatura
        self.temp_label = QLabel("🌡  0 °C")
        self.temp_label.setObjectName("weather")
        layout.addWidget(self.temp_label)

        # Humedad
        self.hum_label = QLabel("☁  0 %")
        self.hum_label.setObjectName("weather")
        layout.addWidget(self.hum_label)

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

    def set_weather(self, temp_c: float, humidity_pct: int) -> None:
        self.temp_label.setText(f"🌡  {temp_c:.0f} °C")
        self.hum_label.setText(f"☁  {humidity_pct} %")
