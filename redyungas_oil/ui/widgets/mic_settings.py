"""
ui/widgets/mic_settings.py — Configuración del micrófono del locutor + auto-ducking.

Ventana que abre el botón de micrófono (donde antes estaba el clima). Permite:
  * Activar la entrada de micrófono y elegir el dispositivo.
  * Cuánto baja la música al hablar: planilla PRINCIPAL, AUXILIAR y CUÑAS.
  * Umbral de voz, ataque y liberación (ducking profesional).
  * Mandar la voz "al aire" por la misma salida (opcional).
Guarda en config.toml (sección [mic]).
"""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from ...core.config import save_config


def _input_devices() -> list[str]:
    try:
        import sounddevice as sd
        seen, out = set(), []
        for d in sd.query_devices():
            if d.get("max_input_channels", 0) > 0 and d["name"] not in seen:
                seen.add(d["name"]); out.append(d["name"])
        return out
    except Exception:
        return []


class MicSettingsDialog(QDialog):
    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Micrófono del locutor — REDYUNGAS OIL")
        self.resize(460, 420)
        self._cfg = deepcopy(config)
        mic = self._cfg.setdefault("mic", {})

        root = QVBoxLayout(self)
        intro = QLabel("Cuando el locutor habla, la música baja automáticamente "
                       "(como en las radios profesionales) y vuelve a subir al callar.")
        intro.setWordWrap(True)
        root.addWidget(intro)

        form = QFormLayout()

        self.enabled = QCheckBox("Activar entrada de micrófono")
        self.enabled.setChecked(bool(mic.get("enabled")))
        form.addRow(self.enabled)

        self.device = QComboBox()
        self.device.setEditable(True)
        devs = _input_devices()
        self.device.addItem("(dispositivo por defecto)")
        self.device.addItems(devs)
        cur = mic.get("device", "")
        self.device.setCurrentText(cur if cur else "(dispositivo por defecto)")
        form.addRow("Dispositivo:", self.device)

        self.to_air = QCheckBox("Mandar la voz al aire (mezclar en la salida)")
        self.to_air.setChecked(bool(mic.get("to_air")))
        form.addRow(self.to_air)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        form.addRow(sep)

        # Cuánto baja cada bus (en %): 100 = no baja, 0 = silencio total.
        self.duck_main = self._pct("Bajar la planilla PRINCIPAL a:", form, mic.get("duck_main", 0.30))
        self.duck_aux = self._pct("Bajar la planilla AUXILIAR a:", form, mic.get("duck_aux", 0.40))
        self.duck_carts = self._pct("Bajar las CUÑAS a:", form, mic.get("duck_carts", 0.50))

        sep2 = QFrame(); sep2.setFrameShape(QFrame.Shape.HLine)
        form.addRow(sep2)

        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(-90.0, 0.0); self.threshold.setSuffix(" dB")
        self.threshold.setValue(float(mic.get("threshold_db", -38.0)))
        form.addRow("Umbral de voz:", self.threshold)

        self.attack = QSpinBox(); self.attack.setRange(0, 2000); self.attack.setSuffix(" ms")
        self.attack.setValue(int(mic.get("attack_ms", 120)))
        form.addRow("Ataque (al hablar):", self.attack)

        self.release = QSpinBox(); self.release.setRange(0, 5000); self.release.setSuffix(" ms")
        self.release.setValue(int(mic.get("release_ms", 700)))
        form.addRow("Liberación (al callar):", self.release)

        self.mic_gain = QDoubleSpinBox()
        self.mic_gain.setRange(-24.0, 24.0); self.mic_gain.setSuffix(" dB")
        self.mic_gain.setValue(float(mic.get("mic_gain_db", 0.0)))
        form.addRow("Ganancia del micrófono:", self.mic_gain)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _pct(self, label: str, form: QFormLayout, value: float) -> QSpinBox:
        sb = QSpinBox(); sb.setRange(0, 100); sb.setSuffix(" %")
        sb.setValue(int(round(float(value) * 100)))
        form.addRow(label, sb)
        return sb

    def _on_save(self) -> None:
        mic = self._cfg.setdefault("mic", {})
        mic["enabled"] = self.enabled.isChecked()
        dev = self.device.currentText().strip()
        mic["device"] = "" if dev.startswith("(") else dev
        mic["to_air"] = self.to_air.isChecked()
        mic["duck_main"] = self.duck_main.value() / 100.0
        mic["duck_aux"] = self.duck_aux.value() / 100.0
        mic["duck_carts"] = self.duck_carts.value() / 100.0
        mic["threshold_db"] = self.threshold.value()
        mic["attack_ms"] = self.attack.value()
        mic["release_ms"] = self.release.value()
        mic["mic_gain_db"] = self.mic_gain.value()
        save_config(self._cfg)
        self.accept()

    def result_config(self) -> dict:
        return self._cfg
