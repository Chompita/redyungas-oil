"""
ui/widgets/tuner_window.py — "Recibir señal" (sintonizador manual, estilo Winamp).

Permite ESCUCHAR un stream en cualquier perfil (no solo "esclava") sin tocar
config ni reiniciar: pega/confirma la URL y pulsa Escuchar. Reutiliza el
`StreamReceiver` (VLC + watchdog). Pensado para que el locutor reciba la señal
del estudio / del emisor "PUERTO" en las esclavas Windows con un clic.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ...audio.receiver import StreamReceiver


class TunerWindow(QWidget):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("Recibir señal — REDYUNGAS OIL")
        self.resize(440, 150)
        self._config = config or {}
        self._receiver: StreamReceiver | None = None

        net = (self._config.get("network", {}) or {})
        default_url = net.get("stream_url") or "http://stream.example.com:8032/stream"

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        root.addWidget(QLabel("URL del stream a escuchar:"))
        self.url_edit = QLineEdit(default_url)
        root.addWidget(self.url_edit)

        btns = QHBoxLayout()
        self.btn_listen = QPushButton("▶ Escuchar")
        self.btn_stop = QPushButton("■ Detener")
        self.btn_stop.setEnabled(False)
        btns.addWidget(self.btn_listen, 1)
        btns.addWidget(self.btn_stop, 1)
        root.addLayout(btns)

        vol = QHBoxLayout()
        vol.addWidget(QLabel("Volumen"))
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(90)
        vol.addWidget(self.volume, 1)
        root.addLayout(vol)

        self.status = QLabel("● Detenido")
        self.status.setObjectName("streamStatusOff")
        root.addWidget(self.status)

        self.btn_listen.clicked.connect(self._listen)
        self.btn_stop.clicked.connect(self._stop)
        self.volume.valueChanged.connect(self._on_volume)

    # ------------------------------------------------------------------ acciones
    def _listen(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            return
        self._stop()
        cfg = {"network": {"stream_url": url,
                           "stall_seconds": (self._config.get("network", {}) or {}).get("stall_seconds", 8)}}
        self._receiver = StreamReceiver(cfg, self)
        self._receiver.health_changed.connect(self._on_health)
        self._receiver.set_volume(self.volume.value())
        self._receiver.start()
        self.btn_listen.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def _stop(self) -> None:
        if self._receiver is not None:
            self._receiver.stop()
            self._receiver = None
        self.btn_listen.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self._set_status("● Detenido", "streamStatusOff")

    def _on_volume(self, value: int) -> None:
        if self._receiver is not None:
            self._receiver.set_volume(value)

    def _on_health(self, health: str) -> None:
        if health == "on_air":
            self._set_status("● EN VIVO — recibiendo señal", "streamStatusOn")
        elif health == "connecting":
            self._set_status("● Conectando…", "streamStatusWarn")
        else:  # lost
            self._set_status("● Señal perdida — reintentando…", "streamStatusWarn")

    def _set_status(self, text: str, obj: str) -> None:
        self.status.setText(text)
        self.status.setObjectName(obj)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._stop()
        super().closeEvent(event)
