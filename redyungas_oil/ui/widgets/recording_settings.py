"""
ui/widgets/recording_settings.py — Ventana de opciones de la GRABACIÓN.

La abre el botón ⚙ de la sección de grabación. Permite elegir:
  * Carpeta de salida (dónde se guardan los `grab_*.…`).
  * Formato de grabación (mp3 por defecto · wav · ogg · aac · flac).
  * Calidad (kbps; solo aplica a formatos con pérdida: mp3/ogg/aac).
Guarda en config.toml (`[paths].recordings_folder`, `[recording].format/bitrate`).
"""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from ...core.config import save_config

_FORMATS = ["mp3", "wav", "ogg", "aac", "flac"]
_QUALITIES = ["128", "192", "256", "320"]
_LOSSLESS = {"wav", "flac"}


class RecordingSettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Grabación de audio — REDYUNGAS OIL")
        self.resize(480, 220)
        self._cfg = deepcopy(config)
        rec = self._cfg.setdefault("recording", {})
        paths = self._cfg.setdefault("paths", {})

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Opciones de la grabación de audio."))
        form = QFormLayout()

        # Carpeta de salida + Examinar
        from PyQt6.QtWidgets import QWidget
        row = QWidget(); h = QHBoxLayout(row); h.setContentsMargins(0, 0, 0, 0)
        self.folder = QLineEdit(str(paths.get("recordings_folder", "")))
        btn = QPushButton("Examinar…"); btn.setFixedWidth(90)
        btn.clicked.connect(self._pick_folder)
        h.addWidget(self.folder, 1); h.addWidget(btn, 0)
        form.addRow("Carpeta de grabaciones:", row)

        self.format = QComboBox(); self.format.addItems(_FORMATS)
        cur = str(rec.get("format", "mp3")).lower()
        self.format.setCurrentText(cur if cur in _FORMATS else "mp3")
        self.format.currentTextChanged.connect(self._on_format)
        form.addRow("Formato (predeterminado mp3):", self.format)

        self.quality = QComboBox(); self.quality.addItems(_QUALITIES)
        self.quality.setCurrentText(str(rec.get("bitrate", 192)))
        form.addRow("Calidad de audio (kbps):", self.quality)

        root.addLayout(form)
        self._note = QLabel(""); self._note.setObjectName("sectionTag")
        root.addWidget(self._note)
        self._on_format(self.format.currentText())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Aceptar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pick_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta de grabaciones", self.folder.text() or "")
        if d:
            self.folder.setText(d)

    def _on_format(self, fmt: str) -> None:
        lossless = fmt in _LOSSLESS
        self.quality.setEnabled(not lossless)
        self._note.setText("Formato sin pérdida: la calidad (kbps) no aplica."
                           if lossless else "")

    def _on_save(self) -> None:
        self._cfg["paths"]["recordings_folder"] = self.folder.text().strip()
        self._cfg["recording"]["format"] = self.format.currentText()
        try:
            self._cfg["recording"]["bitrate"] = int(self.quality.currentText())
        except ValueError:
            self._cfg["recording"]["bitrate"] = 192
        save_config(self._cfg)
        self.accept()

    def result_config(self) -> dict:
        return self._cfg
