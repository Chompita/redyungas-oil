"""
ui/widgets/stream_settings.py — Ajustes del emisor "PUERTO" (estilo Opticodec).

Edita la sección [stream] del config.toml: servidor (SHOUTcast/Icecast), URL,
puerto, montaje, usuario/contraseña, bitrate, códec, sample rate y los metadatos
del stream (nombre, género, web). Equivale a las pestañas "Destination Server",
"Audio" y "Stream Description" de Opticodec-PC.
"""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...core.config import save_config


class StreamSettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ajustes del emisor — PUERTO (REDYUNGAS OIL)")
        self.resize(520, 420)
        self._cfg = deepcopy(config)
        self._cfg.setdefault("stream", {})
        self._fields: dict[tuple[str, str], object] = {}

        tabs = QTabWidget()
        tabs.addTab(self._tab(self._build_server), "Servidor")
        tabs.addTab(self._tab(self._build_audio), "Audio")
        tabs.addTab(self._tab(self._build_desc), "Descripción")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --------------------------------------------------------------- helpers
    def _line(self, form, key, label, password=False):
        edit = QLineEdit(str(self._cfg["stream"].get(key, "")))
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._fields[("stream", key)] = edit
        form.addRow(label, edit)

    def _check(self, form, key, label):
        cb = QCheckBox()
        cb.setChecked(bool(self._cfg["stream"].get(key)))
        self._fields[("stream", key)] = cb
        form.addRow(label, cb)

    def _combo(self, form, key, label, options):
        combo = QComboBox()
        combo.addItems(options)
        cur = str(self._cfg["stream"].get(key, ""))
        if cur in options:
            combo.setCurrentText(cur)
        self._fields[("stream", key)] = combo
        form.addRow(label, combo)

    def _tab(self, build) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        build(form)
        return w

    # --------------------------------------------------------------- pestañas
    def _build_server(self, form) -> None:
        self._combo(form, "server_type", "Servidor", ["shoutcast", "icecast"])
        self._check(form, "enabled", "Emisor habilitado")
        self._line(form, "host", "URL / host")
        self._line(form, "port", "Puerto")
        self._line(form, "mount", "Montaje (mount)")
        self._line(form, "user", "Usuario")
        self._line(form, "password", "Contraseña", password=True)
        self._check(form, "connect_on_start", "Emitir al arrancar")

    def _build_audio(self, form) -> None:
        self._line(form, "bitrate", "Bitrate (kbps)")
        self._combo(form, "codec", "Códec", ["mp3", "aac"])
        self._line(form, "sample_rate", "Sample rate (Hz)")
        self._line(form, "channels", "Canales (1=mono, 2=estéreo)")
        self._line(form, "capture_device", "Captura (Windows: dshow:audio=Mezcla estéreo ...)")

    def _build_desc(self, form) -> None:
        self._line(form, "stream_name", "Nombre del stream")
        self._line(form, "genre", "Género")
        self._line(form, "website", "Sitio web")
        self._line(form, "description", "Descripción")

    # --------------------------------------------------------------- guardar
    def _collect(self) -> dict:
        for (section, key), widget in self._fields.items():
            old = self._cfg[section].get(key)
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            else:
                value = widget.text()
                if isinstance(old, int):
                    try:
                        value = int(value)
                    except ValueError:
                        value = old
            self._cfg[section][key] = value
        return self._cfg

    def _on_save(self) -> None:
        save_config(self._collect())
        self.accept()

    def result_config(self) -> dict:
        return self._cfg
