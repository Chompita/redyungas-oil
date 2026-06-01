"""
ui/widgets/log_viewer.py — Explorador del registro (FASE 8).

Muestra el log de la aplicación (logs/redyungas_oil.log) con botón de recargar,
réplica del espíritu de "Herramientas → Explorador del registro" de ZaraRadio.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class LogViewer(QDialog):
    def __init__(self, log_path: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Explorador del registro — REDYUNGAS OIL")
        self.resize(720, 460)
        self._log_path = Path(log_path)

        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        header.addWidget(QLabel(str(self._log_path)))
        header.addStretch(1)
        reload_btn = QPushButton("Recargar")
        reload_btn.clicked.connect(self.reload)
        header.addWidget(reload_btn)
        layout.addLayout(header)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName("logView")
        layout.addWidget(self.text)
        self.reload()

    def reload(self) -> None:
        if self._log_path.exists():
            content = self._log_path.read_text(encoding="utf-8", errors="ignore")
            self.text.setPlainText(content[-100_000:])   # últimas líneas
            self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().maximum())
        else:
            self.text.setPlainText("(sin registro todavía)")
