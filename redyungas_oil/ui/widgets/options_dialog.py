"""
ui/widgets/options_dialog.py — Diálogo de Opciones estilo ZaraRadio.

Réplica de "Herramientas → Opciones" de ZaraRadio v1.6.2 (imágenes 12–26): una
LISTA de secciones a la izquierda y el panel correspondiente a la derecha:

    Fundido · Satélite · Salidas · Registro · Contraseña · Detector de silencio ·
    Mezclador · HTH · DTMF · Explorador · Tags · Pisador · General

Cada control se guarda en config.toml. Las secciones que el motor usa de verdad
(Fundido, Detector de silencio, Pisador, Explorador, Registro, General) se aplican;
las demás se conservan para mantener la paridad funcional con ZaraRadio.
"""

from __future__ import annotations

from copy import deepcopy

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...core import constants as C
from ...core.config import save_config

_ALL_EXTS = ["WAV", "MP3", "OGG", "WMA", "FLAC", "M4A", "AAC", "OPUS",
             "LST", "M3U", "PLS", "SEQ", "ROT", "EVT"]


def _devices(output: bool) -> list[str]:
    try:
        import sounddevice as sd
        key = "max_output_channels" if output else "max_input_channels"
        seen, out = set(), []
        for d in sd.query_devices():
            if d.get(key, 0) > 0 and d["name"] not in seen:
                seen.add(d["name"]); out.append(d["name"])
        return out
    except Exception:
        return []


class OptionsDialog(QDialog):
    SECTIONS = ["Fundido", "Satélite", "Salidas", "Registro", "Contraseña",
                "Detector de silencio", "Mezclador", "HTH", "DTMF", "Explorador",
                "Tags", "Pisador", "General"]

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Opciones — REDYUNGAS OIL")
        self.resize(720, 520)
        self._cfg = deepcopy(config)
        self._fields: dict[tuple[str, str], object] = {}
        self._scale: dict[tuple[str, str], float] = {}
        self._out_devs = _devices(output=True)
        self._in_devs = _devices(output=False)

        # Lista de secciones (izquierda) + pila de paneles (derecha).
        self.list = QListWidget()
        self.list.setObjectName("optionsList")
        self.list.setFixedWidth(170)
        for name in self.SECTIONS:
            QListWidgetItem(name, self.list)
        self.stack = QStackedWidget()
        for builder in (self._fundido, self._satelite, self._salidas, self._registro,
                        self._contrasena, self._silencio, self._mezclador, self._hth,
                        self._dtmf, self._explorador, self._tags, self._pisador,
                        self._general):
            self.stack.addWidget(builder())
        self.list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.list.setCurrentRow(0)

        body = QHBoxLayout()
        body.addWidget(self.list)
        body.addWidget(self.stack, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Aceptar")
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)

        root = QVBoxLayout(self)
        root.addLayout(body, 1)
        root.addWidget(buttons)

    # ------------------------------------------------------------- helpers UI
    def _val(self, section, key, default=None):
        return (self._cfg.get(section, {}) or {}).get(key, default)

    def _check(self, label, section, key) -> QCheckBox:
        cb = QCheckBox(label)
        cb.setChecked(bool(self._val(section, key)))
        self._fields[(section, key)] = cb
        return cb

    def _line(self, section, key, password=False) -> QLineEdit:
        e = QLineEdit(str(self._val(section, key, "")))
        if password:
            e.setEchoMode(QLineEdit.EchoMode.Password)
        self._fields[(section, key)] = e
        return e

    def _spin(self, section, key, lo, hi, suffix="", scale=1.0, double=False, default=0):
        sb = QDoubleSpinBox() if double else QSpinBox()
        sb.setRange(lo, hi)
        if suffix:
            sb.setSuffix(" " + suffix)
        stored = self._val(section, key, default)
        try:
            sb.setValue((float(stored) / scale) if double else int(round(float(stored) / scale)))
        except (TypeError, ValueError):
            sb.setValue(default)
        self._fields[(section, key)] = sb
        self._scale[(section, key)] = scale
        return sb

    def _combo(self, section, key, options, default="") -> QComboBox:
        cb = QComboBox(); cb.addItems(options)
        cur = str(self._val(section, key, default))
        if cur in options:
            cb.setCurrentText(cur)
        elif cur:
            cb.insertItem(0, cur); cb.setCurrentIndex(0)
        self._fields[(section, key)] = cb
        return cb

    def _device_combo(self, section, key, devs, with_nosound=False) -> QComboBox:
        opts = (["No sound"] if with_nosound else []) + ["(dispositivo por defecto)"] + devs
        cb = QComboBox(); cb.addItems(opts); cb.setEditable(True)
        cur = str(self._val(section, key, ""))
        cb.setCurrentText(cur if cur else "(dispositivo por defecto)")
        self._fields[(section, key)] = cb
        return cb

    @staticmethod
    def _pane(title: str) -> tuple[QWidget, QVBoxLayout]:
        w = QWidget()
        lay = QVBoxLayout(w)
        head = QLabel(title); head.setObjectName("optionsHeader")
        lay.addWidget(head)
        return w, lay

    # ------------------------------------------------------------- secciones
    def _fundido(self) -> QWidget:
        w, lay = self._pane("Fundido")
        lay.addWidget(QLabel("Tiempos del fundido encadenado entre canciones."))
        g1 = QGroupBox("Superposición"); f1 = QFormLayout(g1)
        f1.addRow("Solapar pistas:", self._spin("audio", "auto_crossfade_ms", 0, 30,
                                                "segundos", scale=1000.0, double=True, default=1.75))
        lay.addWidget(g1)
        g2 = QGroupBox("Fundido"); f2 = QVBoxLayout(g2)
        ff = QFormLayout()
        ff.addRow("Fundir pistas:", self._spin("audio", "crossfade_ms", 0, 30,
                                               "segundos", scale=1000.0, double=True, default=3))
        f2.addLayout(ff)
        f2.addWidget(self._check("Fundido al solapar", "audio", "fade_on_overlap"))
        f2.addWidget(self._check("Fundido al parar", "audio", "fade_on_stop"))
        lay.addWidget(g2)
        g3 = QGroupBox("Detección de fin de canción"); f3 = QFormLayout(g3)
        f3.addRow(self._check("Detectar fin de canción", "audio", "detect_end"))
        f3.addRow("Umbral:", self._spin("audio", "detect_end_db", -60, 0, "dB", default=-26))
        lay.addWidget(g3)
        lay.addStretch(1)
        return w

    def _satelite(self) -> QWidget:
        w, lay = self._pane("Satélite")
        lay.addWidget(QLabel("Línea de la tarjeta usada como entrada del satélite."))
        lay.addWidget(self._device_combo("satellite", "input_device", self._in_devs))
        lay.addStretch(1)
        return w

    def _salidas(self) -> QWidget:
        w, lay = self._pane("Salidas")
        lay.addWidget(QLabel("Dispositivo de salida para la emisión y el canal de cue."))
        g1 = QGroupBox("Salida de emisión"); f1 = QFormLayout(g1)
        f1.addRow(self._device_combo("audio", "output_device", self._out_devs, with_nosound=True))
        lay.addWidget(g1)
        g2 = QGroupBox("Salida de cue"); f2 = QFormLayout(g2)
        f2.addRow(self._device_combo("audio", "cue_device", self._out_devs, with_nosound=True))
        lay.addWidget(g2)
        g3 = QGroupBox("Salidas de los reproductores auxiliares"); f3 = QFormLayout(g3)
        for i in range(1, 5):
            f3.addRow(f"Aux {i}:", self._device_combo("outputs", f"aux{i}", self._out_devs))
        lay.addWidget(g3)
        lay.addStretch(1)
        return w

    def _registro(self) -> QWidget:
        w, lay = self._pane("Registro")
        lay.addWidget(QLabel("Carpeta donde guardar los ficheros log (AA-MM-DD.log)."))
        g = QGroupBox("Carpeta de log"); f = QVBoxLayout(g)
        f.addWidget(self._check("Activar logs", "logging", "enabled"))
        ff = QFormLayout()
        ff.addRow("Carpeta:", self._browse_line("paths", "logs_folder", folder=True))
        f.addLayout(ff)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _contrasena(self) -> QWidget:
        w, lay = self._pane("Contraseña")
        lay.addWidget(QLabel("Proteja el diálogo de opciones y el de eventos con una contraseña."))
        g = QGroupBox("Contraseña"); f = QFormLayout(g)
        f.addRow(self._check("Activar protección", "security", "enabled"))
        f.addRow("Contraseña:", self._line("security", "password", password=True))
        lay.addWidget(g)
        g2 = QGroupBox("Elementos a proteger"); f2 = QVBoxLayout(g2)
        f2.addWidget(self._check("Diálogo de eventos", "security", "protect_events"))
        f2.addWidget(self._check("Descartar los eventos pendientes", "security", "discard_pending"))
        f2.addWidget(self._check("Reproducir los eventos pendientes manualmente",
                                 "security", "play_pending_manual"))
        f2.addWidget(self._check("Diálogo de opciones", "security", "protect_options"))
        f2.addWidget(self._check("Activar/Desactivar eventos", "security", "protect_enable_events"))
        lay.addWidget(g2)
        lay.addStretch(1)
        return w

    def _silencio(self) -> QWidget:
        w, lay = self._pane("Detector de silencio")
        lay.addWidget(QLabel("Detecta periodos de silencio en las canciones y actúa en consecuencia."))
        g = QGroupBox("Detector de silencio"); f = QFormLayout(g)
        f.addRow(self._check("Activar detector de silencio", "silence", "enabled"))
        f.addRow("Período de silencio:", self._spin("silence", "period_s", 1, 600,
                                                    "segundos", default=15))
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _mezclador(self) -> QWidget:
        w, lay = self._pane("Mezclador")
        lay.addWidget(QLabel("Programa que se usará como mezclador."))
        g = QGroupBox("Aplicación mezcladora"); f = QFormLayout(g)
        f.addRow("Mezclador:", self._browse_line("mixer", "app"))
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _hth(self) -> QWidget:
        w, lay = self._pane("HTH")
        lay.addWidget(QLabel("Configuración de temperatura y humedad para las locuciones."))
        g = QGroupBox("HTH"); f = QFormLayout(g)
        f.addRow("Temperatura:", self._spin("hth", "temperature", -60, 60, "°", default=0))
        f.addRow("Humedad:", self._spin("hth", "humidity", 0, 100, "%", default=0))
        lay.addWidget(g)
        g2 = QGroupBox("Importar"); f2 = QVBoxLayout(g2)
        f2.addWidget(self._check("Importar desde un fichero", "hth", "import_enabled"))
        ff = QFormLayout(); ff.addRow("Ruta del fichero:", self._browse_line("hth", "import_file"))
        f2.addLayout(ff)
        f2.addWidget(self._check("Desactivar las locuciones tras inactividad", "hth",
                                 "disable_after_enabled"))
        lay.addWidget(g2)
        g3 = QGroupBox("Unidades"); f3 = QFormLayout(g3)
        f3.addRow("Temperatura:", self._combo("hth", "units", ["Celsius", "Fahrenheit"],
                                              default="Celsius"))
        lay.addWidget(g3)
        lay.addStretch(1)
        return w

    def _dtmf(self) -> QWidget:
        w, lay = self._pane("DTMF")
        lay.addWidget(QLabel("Detector de tonos DTMF para sincronizar su radio con otra."))
        g = QGroupBox("Detector de tonos DTMF"); f = QVBoxLayout(g)
        f.addWidget(self._check("Activar el detector", "dtmf", "enabled"))
        lay.addWidget(g)
        g2 = QGroupBox("Desconexión"); f2 = QFormLayout(g2)
        f2.addRow("Tonos de desconexión:", self._line("dtmf", "disconnect_tones"))
        f2.addRow("Acción:", self._combo("dtmf", "disconnect_action",
                  ["Reproducir los eventos pendientes", "Parar", "Nada"],
                  default="Reproducir los eventos pendientes"))
        lay.addWidget(g2)
        g3 = QGroupBox("Conexión"); f3 = QFormLayout(g3)
        f3.addRow("Tono de conexión:", self._line("dtmf", "connect_tone"))
        f3.addRow("Conectar tras (s):", self._spin("dtmf", "connect_delay_s", 0, 3600,
                                                   "segundos", default=0))
        lay.addWidget(g3)
        lay.addStretch(1)
        return w

    def _explorador(self) -> QWidget:
        w, lay = self._pane("Explorador")
        lay.addWidget(QLabel("Carpeta raíz del explorador y tipos de fichero a mostrar."))
        g = QGroupBox("Carpeta raíz del árbol de ficheros"); f = QFormLayout(g)
        f.addRow("Carpeta:", self._browse_line("paths", "music_root", folder=True))
        f.addRow(self._check("Carpeta especial", "explorer", "use_special"))
        f.addRow("Especial:", self._combo("explorer", "special_folder",
                 ["Escritorio", "Música", "Documentos", "Inicio"], default="Escritorio"))
        lay.addWidget(g)
        g2 = QGroupBox("Extensiones"); f2 = QVBoxLayout(g2)
        self._ext_list = QListWidget()
        self._ext_list.setMaximumHeight(140)
        current = set(str(x).upper() for x in (self._val("explorer", "extensions") or []))
        for ext in _ALL_EXTS:
            it = QListWidgetItem(ext)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if ext in current else Qt.CheckState.Unchecked)
            self._ext_list.addItem(it)
        f2.addWidget(self._ext_list)
        lay.addWidget(g2)
        lay.addStretch(1)
        return w

    def _tags(self) -> QWidget:
        w, lay = self._pane("Tags")
        lay.addWidget(QLabel("Mostrar los tags en la lista de reproducción y su formato."))
        g = QGroupBox("Tags"); f = QFormLayout(g)
        f.addRow(self._check("Activar los tags", "tags", "enabled"))
        f.addRow("Formato:", self._line("tags", "format"))
        macros = QLabel("Macros: %ARTI (artista) · %TITL (título) · %ALBM (álbum) · "
                        "%GNRE (género) · %YEAR (año) · %CMNT (comentarios)")
        macros.setWordWrap(True); macros.setObjectName("sectionTag")
        f.addRow(macros)
        lay.addWidget(g)
        lay.addStretch(1)
        return w

    def _pisador(self) -> QWidget:
        w, lay = self._pane("Pisador")
        lay.addWidget(QLabel("Volumen al que baja la música durante las locuciones y la transición."))
        g = QGroupBox("Tiempo de transición"); f = QFormLayout(g)
        f.addRow("Variación de:", self._spin("audio", "duck_ms", 0, 5000, "milisegundos",
                                             default=C.DUCK_MS))
        lay.addWidget(g)
        g2 = QGroupBox("Volumen de locución (%)"); f2 = QFormLayout(g2)
        f2.addRow("Bajar la música a:", self._spin("audio", "duck_level", 0, 100, "%",
                                                   scale=0.01, double=False,
                                                   default=int(C.DUCK_LEVEL * 100)))
        lay.addWidget(g2)
        lay.addStretch(1)
        return w

    def _general(self) -> QWidget:
        w, lay = self._pane("General")
        g = QGroupBox("Nombre de la emisora"); f = QFormLayout(g)
        f.addRow("Nombre:", self._line("general", "station_name"))
        f.addRow("Idioma:", self._combo("general", "language", ["es", "en"], default="es"))
        f.addRow("Perfil:", self._combo("general", "profile", list(C.PROFILES)))
        lay.addWidget(g)
        g2 = QGroupBox("Carpeta de salida del fichero 'CurrentSong'"); f2 = QFormLayout(g2)
        f2.addRow("Carpeta:", self._browse_line("general", "currentsong_folder", folder=True))
        lay.addWidget(g2)
        g3 = QGroupBox("Otras opciones"); f3 = QVBoxLayout(g3)
        f3.addWidget(self._check("Activar autoarranque", "general", "autostart"))
        f3.addWidget(self._check("Activar AGC", "general", "agc"))
        f3.addWidget(self._check("Permitir la apertura de más de una instancia",
                                 "general", "allow_multiple"))
        f3.addWidget(self._check("Desactivar los eventos en las instancias secundarias",
                                 "general", "disable_events_secondary"))
        f3.addWidget(self._check("Abrir la última lista al arrancar", "general", "open_last_list"))
        f3.addWidget(self._check("Confirmación de cierre", "general", "confirm_close"))
        f3.addWidget(self._check("Reproducir las pistas haciendo doble clic",
                                 "general", "double_click_play"))
        lay.addWidget(g3)
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------- browse line
    def _browse_line(self, section, key, folder=False) -> QWidget:
        cont = QWidget(); h = QHBoxLayout(cont); h.setContentsMargins(0, 0, 0, 0)
        e = QLineEdit(str(self._val(section, key, "")))
        self._fields[(section, key)] = e
        btn = QPushButton("Examinar…"); btn.setFixedWidth(90)

        def pick():
            if folder:
                p = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta", e.text() or "")
            else:
                p, _ = QFileDialog.getOpenFileName(self, "Seleccionar fichero", e.text() or "")
            if p:
                e.setText(p)
        btn.clicked.connect(pick)
        h.addWidget(e, 1); h.addWidget(btn, 0)
        return cont

    # ------------------------------------------------------------- guardar
    def _collect(self) -> dict:
        for (section, key), widget in self._fields.items():
            self._cfg.setdefault(section, {})
            if isinstance(widget, QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
                if value.startswith("("):       # "(dispositivo por defecto)"
                    value = ""
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                scale = self._scale.get((section, key), 1.0)
                raw = widget.value() * scale
                value = raw if isinstance(widget, QDoubleSpinBox) or scale != 1.0 else int(raw)
                if (section, key) in (("audio", "auto_crossfade_ms"),
                                      ("audio", "crossfade_ms"), ("audio", "duck_ms")):
                    value = int(round(raw))
            else:
                value = widget.text()
            self._cfg[section][key] = value
        # Extensiones (lista con casillas)
        exts = [self._ext_list.item(i).text()
                for i in range(self._ext_list.count())
                if self._ext_list.item(i).checkState() == Qt.CheckState.Checked]
        self._cfg.setdefault("explorer", {})["extensions"] = exts
        return self._cfg

    def _on_save(self) -> None:
        save_config(self._collect())
        self.accept()

    def result_config(self) -> dict:
        return self._cfg
