"""
ui/widgets/options_dialog.py — Diálogo de Opciones (FASE 8).

Edita la configuración principal y la guarda en config.toml (sin tocar archivos a
mano). Algunos cambios (perfil, puertos, MCP) requieren reiniciar la aplicación.
Réplica del espíritu de "Herramientas → Opciones" de ZaraRadio.
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

from ...core import constants as C
from ...core.config import save_config


class OptionsDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Opciones — REDYUNGAS OIL")
        self.resize(560, 440)
        self._cfg = deepcopy(config)
        self._fields: dict[tuple[str, str], object] = {}

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "General")
        tabs.addTab(self._tab_red(), "Red")
        tabs.addTab(self._tab_grabacion(), "Grabación / JARVIS")
        tabs.addTab(self._tab_ia(), "IA (MCP) / Telegram")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # --------------------------------------------------------------- helpers
    def _line(self, form, section, key, label, password=False):
        edit = QLineEdit(str(self._cfg.get(section, {}).get(key, "")))
        if password:
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._fields[(section, key)] = edit
        form.addRow(label, edit)

    def _check(self, form, section, key, label):
        cb = QCheckBox()
        cb.setChecked(bool(self._cfg.get(section, {}).get(key)))
        self._fields[(section, key)] = cb
        form.addRow(label, cb)

    def _combo(self, form, section, key, label, options):
        combo = QComboBox()
        combo.addItems(options)
        cur = str(self._cfg.get(section, {}).get(key, ""))
        if cur in options:
            combo.setCurrentText(cur)
        self._fields[(section, key)] = combo
        form.addRow(label, combo)

    def _tab(self, build) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        build(form)
        return w

    # --------------------------------------------------------------- pestañas
    def _tab_general(self) -> QWidget:
        def build(form):
            self._combo(form, "general", "profile", "Perfil", list(C.PROFILES))
            self._line(form, "general", "station_name", "Nombre de la emisora")
            self._line(form, "paths", "music_root", "Carpeta de música")
            self._line(form, "paths", "recordings_folder", "Carpeta de grabaciones")
            self._line(form, "paths", "emergency_folder", "Carpeta de emergencia (offline)")
        return self._tab(build)

    def _tab_red(self) -> QWidget:
        def build(form):
            self._line(form, "network", "stream_url", "URL del stream (esclava)")
            self._line(form, "network", "reconnect_timeout_s", "Reconexión (s)")
            self._line(form, "network", "icecast_host", "Icecast host (estudio)")
            self._line(form, "network", "icecast_port", "Icecast puerto")
            self._line(form, "network", "icecast_mount", "Icecast mount")
            self._line(form, "network", "icecast_password", "Icecast contraseña", password=True)
            self._line(form, "network", "offline_folder", "Carpeta de cuñas offline")
        return self._tab(build)

    def _tab_grabacion(self) -> QWidget:
        def build(form):
            self._line(form, "recording", "segment_seconds", "Segundo por trozo (s)")
            self._check(form, "recording", "send_to_jarvis", "Enviar grabaciones a JARVIS")
            self._check(form, "jarvis", "enabled", "JARVIS activado")
            self._combo(form, "jarvis", "delivery_mode", "Modo de entrega", ["folder", "api"])
            self._line(form, "jarvis", "watch_folder", "Carpeta vigilada por JARVIS")
            self._line(form, "jarvis", "transcription_api", "API de transcripción")
        return self._tab(build)

    def _tab_ia(self) -> QWidget:
        def build(form):
            self._check(form, "mcp", "enabled", "Servidor MCP activado")
            self._line(form, "mcp", "host", "MCP host (Tailscale)")
            self._line(form, "mcp", "port", "MCP puerto")
            self._line(form, "mcp", "token", "MCP token", password=True)
            self._check(form, "telegram", "enabled", "Telegram activado")
            self._line(form, "telegram", "bot_token", "Token del bot", password=True)
            self._line(form, "telegram", "chat_id", "Chat ID")
        return self._tab(build)

    # --------------------------------------------------------------- guardar
    def _collect(self) -> dict:
        for (section, key), widget in self._fields.items():
            self._cfg.setdefault(section, {})
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
