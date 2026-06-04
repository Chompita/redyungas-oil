"""
REDYUNGAS OIL — Ventana principal.

FASE 1: réplica visual de ZaraRadio v1.6.2.
FASE 2: conectada al motor de audio (audio/engine.py). Ahora suena de verdad:
    - play/stop/pausa/siguiente/anterior desde menú, toolbar y barra de transporte
    - doble clic en la lista -> reproduce esa pista; auto-avance con crossfade
    - añadir pistas (diálogo + drop), eliminar, reordenar con ▲▼
    - volumen (slider horizontal y vertical sincronizados)
    - displays en vivo: título actual/siguiente, tiempo restante, "acaba a las", VU
    - cartwall: clic dispara la cuña; soltar un audio la asigna
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QDateTime,
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    Qt,
    QTime,
    QTimer,
    QUrl,
)
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QSlider,
    QTextEdit,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..audio.engine import AudioEngine
from ..audio.recorder import Recorder
from ..core import constants as C
from ..core.branding import logo_path
from ..core.timefmt import fmt_mmss_tenths
from ..integrations.jarvis_adapter import JarvisAdapter
from ..integrations.telegram_notifier import TelegramNotifier
from ..playlist.item_types import ItemType, PlaylistItem
from ..playlist.lst_io import load_lst, save_lst
from ..scheduler.events import Event, EventScheduler
from ..scheduler.mentions import MentionManager
from .widgets.aux_panel import AuxPlaylistPanel
from .widgets.cartwall import Cartwall
from .widgets.events_panel import EventsPanel
from .widgets.file_tree import FileTree
from .widgets.lcd_clock import ClockBar
from .widgets.mentions_panel import MentionsPanel, MentionsRail
from .widgets.log_viewer import LogViewer
from .widgets.onair_panel import NextPanel, OnAirPanel
from .widgets.options_dialog import OptionsDialog
from .widgets.playlist_view import PlaylistView
from .widgets.stream_panel import StreamPanel, StreamRail
from .widgets.transport_bar import TransportBar

_MEDIA_ACTIONS = {
    "media.play": "play", "media.stop": "stop", "media.pause": "pause",
    "media.next": "next", "media.rewind": "previous", "media.forward": "next",
}

# Toggles por-cuña: action_id de UI -> método del motor / nombre de modo del motor.
_MODE_SETTERS = {
    "media.cyclic": "set_cyclic",
    "media.delete_on_play": "set_delete_on_play",
    "media.stop_after": "set_stop_after",
}
_MODE_TO_ACTION = {
    "cyclic": "media.cyclic",
    "delete_on_play": "media.delete_on_play",
    "stop_after": "media.stop_after",
}


class MainWindow(QMainWindow):
    def __init__(self, config: dict | None = None) -> None:
        super().__init__()
        self.config = config or {}
        self.setWindowTitle(f"{C.APP_TITLE_DEFAULT} — {C.APP_NAME}")
        # La ventana abre YA con el ancho que tendría con el panel PUERTO desplegado,
        # así su ancho NO cambia al abrir/cerrar el PUERTO (el área central lo absorbe).
        self.resize(1336, 650)

        self._actions: dict[str, QAction] = {}
        # Gestor de menciones: se crea ya para alimentar el panel/riel de la izquierda.
        self.mentions_manager = MentionManager(self)

        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._setup_engine()
        self._setup_aux()
        self._setup_network()
        self._setup_recording()
        self._setup_mic()
        self._setup_mentions()
        self._setup_mcp()
        self._setup_stream()
        self._setup_update()

        # Teclas 1..9 -> disparan/silencian las cuñas del cartwall (como ZaraRadio),
        # excepto cuando se está escribiendo en un campo de texto.
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.KeyPress and not event.isAutoRepeat():
            fw = QApplication.focusWidget()
            editing = isinstance(fw, (QLineEdit, QAbstractSpinBox, QTextEdit)) or (
                isinstance(fw, QComboBox) and fw.isEditable())
            key = event.key()
            if not editing and Qt.Key.Key_1 <= key <= Qt.Key.Key_9:
                self.cartwall.activate_slot(key - Qt.Key.Key_1)
                return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ menús
    def _build_menus(self) -> None:
        menubar = self.menuBar()
        for menu_name in C.MENU_ORDER:
            menu = menubar.addMenu(menu_name)
            for label, shortcut, action_id in C.MENUS[menu_name]:
                if label == "-":
                    menu.addSeparator()
                    continue
                action = QAction(label, self)
                if shortcut:
                    action.setShortcut(QKeySequence(shortcut))
                if action_id:
                    action.setData(action_id)
                    action.triggered.connect(lambda _=False, a=action_id: self._on_action(a))
                    self._actions[action_id] = action
                menu.addAction(action)

    # ------------------------------------------------------------- toolbar
    def _build_toolbar(self) -> None:
        tb = QToolBar("Principal")
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        self.addToolBar(tb)

        def add_btn(glyph: str, action_id: str, tip: str) -> None:
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            btn.clicked.connect(lambda _=False, a=action_id: self._on_action(a))
            tb.addWidget(btn)

        add_btn("🗋", "file.new", "Nuevo")
        add_btn("📂", "file.open", "Abrir")
        add_btn("💾", "file.save", "Guardar")
        tb.addSeparator()
        add_btn("➕", "list.add_tracks", "Añadir pistas")
        add_btn("✕", "edit.delete", "Eliminar")
        tb.addSeparator()
        add_btn("✂", "edit.cut", "Cortar")
        add_btn("⧉", "edit.copy", "Copiar")
        add_btn("📋", "edit.paste", "Pegar")
        add_btn("🔍", "edit.find", "Buscar")
        tb.addSeparator()

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Normal", "Aleatorio", "Repetir lista", "Repetir pista"])
        self.mode_combo.setFixedWidth(120)
        tb.addWidget(self.mode_combo)
        tb.addSeparator()

        add_btn("🕓", "list.add_time", "Locución de hora")
        add_btn("🌡", "list.add_temp", "Locución de temperatura")
        add_btn("☁", "list.add_humidity", "Locución de humedad")
        add_btn("🎲", "list.add_random", "Pista aleatoria")
        tb.addSeparator()
        # Botón >1: despliega la planilla AUXILIAR (Aux 1). Como ZaraRadio, pero
        # solo una: al pulsarlo aparece el recuadro auxiliar (se desliza).
        self.aux_btn = QToolButton()
        self.aux_btn.setText("▶1")
        self.aux_btn.setObjectName("auxToolButton")
        self.aux_btn.setToolTip("Planilla auxiliar (Aux 1) — reproduce a la vez que la principal")
        self.aux_btn.setCheckable(True)
        self.aux_btn.setAutoRaise(True)
        self.aux_btn.toggled.connect(self._toggle_aux_panel)
        tb.addWidget(self.aux_btn)
        tb.addSeparator()
        add_btn("▶", "media.play", "Reproducir")
        add_btn("⏹", "media.stop", "Parar")
        add_btn("⏭", "media.next", "Siguiente")
        tb.addSeparator()
        self._record_btn = QToolButton()
        self._record_btn.setText("⏺")
        self._record_btn.setToolTip("Grabar / Detener grabación")
        self._record_btn.setObjectName("recordButton")
        self._record_btn.setAutoRaise(True)
        self._record_btn.clicked.connect(lambda: self._on_action("ryo.record"))
        tb.addWidget(self._record_btn)
        add_btn("📝", "ryo.mentions", "Menciones (REDYUNGAS OIL)")
        add_btn("❓", "help.contents", "Ayuda")

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)
        sec = QLabel("Copia secundaria")
        sec.setObjectName("secondaryCopy")
        tb.addWidget(sec)
        # Marca RED YUNGAS (donde ZaraRadio pone su logo): el logo real si está,
        # con respaldo a texto si faltara el recurso.
        brand = QLabel()
        brand.setObjectName("brandLogo")
        brand.setContentsMargins(6, 0, 8, 0)
        lp = logo_path()
        pm = QPixmap(lp) if lp else QPixmap()
        if not pm.isNull():
            brand.setPixmap(pm.scaledToHeight(30, Qt.TransformationMode.SmoothTransformation))
            brand.setToolTip(C.APP_NAME)
        else:
            brand.setText("🔴 REDYUNGAS OIL")
        tb.addWidget(brand)

    # ------------------------------------------------------------- central
    def _build_central(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # --- Fila superior ---
        top = QWidget()
        top.setObjectName("topZone")
        top.setFixedHeight(150)
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(2, 2, 2, 2)
        top_l.setSpacing(6)

        self.onair = OnAirPanel()
        top_l.addWidget(self.onair, 50)

        self.master_volume = QSlider(Qt.Orientation.Vertical)
        self.master_volume.setObjectName("masterVolume")
        self.master_volume.setRange(0, 100)
        self.master_volume.setValue(80)
        self.master_volume.setFixedWidth(20)
        top_l.addWidget(self.master_volume)

        right_top = QVBoxLayout()
        right_top.setSpacing(2)
        self.next_panel = NextPanel()
        self.clock = ClockBar()
        right_top.addWidget(self.next_panel, 1)
        right_top.addWidget(self.clock, 0)
        top_l.addLayout(right_top, 50)

        root.addWidget(top, 0)

        # --- Fila central ---
        mid = QHBoxLayout()
        mid.setSpacing(4)

        left_col = QWidget()
        left_col.setFixedWidth(322)
        left_l = QVBoxLayout(left_col)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(4)
        self.events = EventsPanel()
        music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
        self.tree = FileTree(music_root)
        left_l.addWidget(self.events, 4)
        left_l.addWidget(self.tree, 6)
        mid.addWidget(left_col, 0)

        arrows = QVBoxLayout()
        arrows.addStretch(1)
        self.up_btn = QToolButton(); self.up_btn.setText("▲"); self.up_btn.setToolTip("Subir")
        self.down_btn = QToolButton(); self.down_btn.setText("▼"); self.down_btn.setToolTip("Bajar")
        for b in (self.up_btn, self.down_btn):
            b.setAutoRaise(True)
            arrows.addWidget(b)
        arrows.addStretch(1)
        mid.addLayout(arrows, 0)

        self.playlist = PlaylistView()
        mid.addWidget(self.playlist, 1)

        root.addLayout(mid, 1)

        # --- Fila inferior ---
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("transportSep")
        root.addWidget(sep, 0)

        self.transport = TransportBar()
        root.addWidget(self.transport, 0)

        self.cartwall = Cartwall()
        root.addWidget(self.cartwall, 0)

        # --- Envoltura con el panel emisor "PUERTO" en el borde derecho ---
        outer = QWidget()
        outer_l = QHBoxLayout(outer)
        outer_l.setContentsMargins(0, 0, 0, 0)
        outer_l.setSpacing(0)
        # Riel + panel de MENCIONES en el borde IZQUIERDO (se desliza, como el PUERTO).
        self.mentions_rail = MentionsRail()
        outer_l.addWidget(self.mentions_rail, 0)
        self.mentions_panel = MentionsPanel(self.mentions_manager)
        self.mentions_panel.setMaximumWidth(0)   # arranca plegado
        self.mentions_panel.setVisible(False)
        outer_l.addWidget(self.mentions_panel, 0)
        outer_l.addWidget(central, 1)
        # Planilla AUXILIAR (botón >1): se desliza desde la derecha, junto al PUERTO.
        self.aux_panel = AuxPlaylistPanel(self.config)
        self.aux_panel.setMaximumWidth(0)        # arranca plegada
        self.aux_panel.setVisible(False)
        outer_l.addWidget(self.aux_panel, 0)
        self.stream_panel = StreamPanel(self.config)
        self.stream_panel.setMaximumWidth(0)     # arranca plegado (se desliza al abrir)
        self.stream_panel.setVisible(False)
        outer_l.addWidget(self.stream_panel, 0)
        self.stream_rail = StreamRail()
        outer_l.addWidget(self.stream_rail, 0)

        self.setCentralWidget(outer)

    # ------------------------------------------------------------ statusbar
    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        sb.showMessage(f"{C.APP_NAME} v{C.APP_VERSION} — listo")
        self._sb_time = QLabel("00:00.0")
        self._sb_time.setObjectName("statusTime")
        sb.addPermanentWidget(self._sb_time)

    # --------------------------------------------------------------- motor
    def _make_engine(self, model):
        """Crea un motor de audio según `[audio].engine` (sounddevice | vlc) para `model`."""
        name = ((self.config.get("audio", {}) or {}).get("engine", "vlc") or "vlc").lower()
        if name == "sounddevice":
            try:
                from ..audio.engine_sd import SoundDeviceEngine
                eng = SoundDeviceEngine(self.config, model=model, parent=self)
                self.statusBar().showMessage("Motor de audio: sounddevice (un solo grafo)", 4000)
                return eng
            except Exception as exc:   # si falta numpy/sounddevice, caer a VLC sin romper
                self.statusBar().showMessage(
                    f"Motor sounddevice no disponible ({exc}); usando VLC", 6000)
        return AudioEngine(self.config, model=model, parent=self)

    def _setup_engine(self) -> None:
        self.engine = self._make_engine(self.playlist.model)
        self._ends_anchor: float | None = None   # ancla de la hora "Acaba a las"

        # Señales del motor -> UI
        self.engine.now_playing_changed.connect(self._on_now_playing)
        self.engine.next_changed.connect(lambda _i, t: self.next_panel.set_next(t or "—"))
        self.engine.position_changed.connect(self._on_position)
        self.engine.levels_changed.connect(self.onair.vu.set_levels)
        self.engine.state_changed.connect(self._on_state)

        # Controles -> motor
        self.transport.action_triggered.connect(self._on_action)
        self.transport.seek_requested.connect(self.engine.set_position)
        self.transport.mode_toggled.connect(self._on_mode_toggled)
        self.engine.playout_mode_changed.connect(self._on_engine_mode_changed)
        self.master_volume.valueChanged.connect(self._on_volume)
        self.playlist.view.doubleClicked.connect(lambda idx: self.engine.play_index(idx.row()))
        self.playlist.action_requested.connect(self._on_playlist_action)
        self._clipboard: list = []
        self.up_btn.clicked.connect(lambda: self.playlist.move_selected(-1))
        self.down_btn.clicked.connect(lambda: self.playlist.move_selected(1))
        self.cartwall.cart_triggered.connect(self._on_cart)
        self.cartwall.cart_assigned.connect(self.engine.assign_cart)
        self.cartwall.fade_all_requested.connect(self.engine.fade_all_carts)
        self.cartwall.volume_changed.connect(self.engine.set_cart_volume)
        self.engine.cart_started.connect(lambda s: self.cartwall.set_active(s, True))
        self.engine.cart_finished.connect(lambda s: self.cartwall.set_active(s, False))

        # Programador de eventos
        self.scheduler = EventScheduler(self)
        self.scheduler.event_due.connect(self._on_event)
        self.scheduler.events_changed.connect(self._refresh_events)
        self.events.schedule_requested.connect(self._schedule_event)
        self.events.remove_requested.connect(self.scheduler.remove_event)
        self._events_refresh = QTimer(self)
        self._events_refresh.timeout.connect(self._refresh_events)
        self._events_refresh.start(15000)
        self._refresh_events()

        # Volumen inicial coherente
        self._on_volume(80)

    # --------------------------------------------------- planilla AUXILIAR (Aux 1)
    def _setup_aux(self) -> None:
        """Segundo motor INDEPENDIENTE para la planilla auxiliar (suena a la vez)."""
        self.aux_engine = self._make_engine(self.aux_panel.playlist.model)

        # Motor aux -> UI del panel aux
        self.aux_engine.now_playing_changed.connect(lambda _i, t: self.aux_panel.set_now_playing(t))
        self.aux_engine.position_changed.connect(
            lambda rem, total: self.aux_panel.transport.set_position(
                (total - rem) / total if total > 0 else 0.0))
        self.aux_engine.playout_mode_changed.connect(
            lambda mode, on: self.aux_panel.transport.set_mode_checked(
                _MODE_TO_ACTION.get(mode, ""), on))

        # Controles del panel aux -> motor aux
        self.aux_panel.transport.action_triggered.connect(self._on_aux_action)
        self.aux_panel.transport.seek_requested.connect(self.aux_engine.set_position)
        self.aux_panel.transport.mode_toggled.connect(self._on_aux_mode_toggled)
        self.aux_panel.volume_changed.connect(self.aux_engine.set_volume)
        self.aux_panel.playlist.view.doubleClicked.connect(
            lambda idx: self.aux_engine.play_index(idx.row()))
        self.aux_panel.playlist.action_requested.connect(self._on_aux_playlist_action)
        self.aux_panel.closed.connect(lambda: self.aux_btn.setChecked(False))
        self.aux_engine.set_volume(self.aux_panel.volume.value())

        # Animación de deslizamiento del panel auxiliar (igual que el PUERTO).
        self._aux_anim = QPropertyAnimation(self.aux_panel, b"maximumWidth", self)
        self._aux_anim.setDuration(240)
        self._aux_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _toggle_aux_panel(self, is_open: bool) -> None:
        anim = self._aux_anim
        anim.stop()
        try:
            anim.finished.disconnect()
        except TypeError:
            pass
        if is_open:
            self.aux_panel.setVisible(True)
            anim.setStartValue(self.aux_panel.maximumWidth())
            anim.setEndValue(self.aux_panel.PANEL_W)
        else:
            anim.setStartValue(self.aux_panel.maximumWidth())
            anim.setEndValue(0)
            anim.finished.connect(lambda: self.aux_panel.setVisible(False))
        anim.start()

    def _on_aux_action(self, action_id: str) -> None:
        if action_id in _MEDIA_ACTIONS:
            getattr(self.aux_engine, _MEDIA_ACTIONS[action_id])()
        elif action_id in _MODE_SETTERS:
            btn = self.aux_panel.transport.toggles.get(action_id)
            getattr(self.aux_engine, _MODE_SETTERS[action_id])(not (btn.isChecked() if btn else False))
        elif action_id == "media.duck":
            on = self.aux_engine.toggle_manual_duck()
            self.aux_panel.transport.set_ducked(on)
        elif action_id == "media.cue":
            pass

    def _on_aux_mode_toggled(self, action_id: str, on: bool) -> None:
        setter = _MODE_SETTERS.get(action_id)
        if setter:
            getattr(self.aux_engine, setter)(on)

    def _on_aux_playlist_action(self, action: str, row: int) -> None:
        model = self.aux_panel.playlist.model
        rows = self.aux_panel.playlist.selected_rows() or ([row] if row >= 0 else [])
        if action == "play" and row >= 0:
            self.aux_engine.play_index(row)
        elif action == "mark_next" and row >= 0:
            self.aux_engine.set_next(row)
        elif action == "cue" and row >= 0:
            self.aux_engine.play_index(row)
        elif action == "update_duration":
            model.reprobe(rows)
        elif action == "delete" and rows:
            model.remove_rows(rows)

    # --------------------------------------------------------------- red (esclava)
    def _setup_network(self) -> None:
        """Arranca la red según el perfil: 'esclava' recibe; 'estudio' emite."""
        self.failover = None
        self.encoder = None
        profile = (self.config.get("general", {}) or {}).get("profile")
        if profile == C.PROFILE_ESCLAVA:
            from ..network.failover import OfflineFailover
            self.failover = OfflineFailover(self.config, self)
            self.failover.state_changed.connect(self._on_failover_state)
            self.failover.receiver.health_changed.connect(self._on_stream_health)
            self.failover.start()
            self.statusBar().showMessage("Modo esclava: conectando a la señal del estudio…", 5000)
        elif profile == C.PROFILE_ESTUDIO:
            from ..audio.encoder import IcecastEncoder
            self.encoder = IcecastEncoder(self.config, self)
            self.encoder.state_changed.connect(self._on_encoder_state)
            self.encoder.start()
            self.statusBar().showMessage("Modo estudio: emitiendo señal al servidor…", 5000)

    def _setup_recording(self) -> None:
        """Grabador (segmentos 30 min) + entrega a JARVIS + avisos Telegram."""
        self.notifier = TelegramNotifier(self.config)
        self.recorder = Recorder(self.config, self)
        self.jarvis = JarvisAdapter(self.config, self)
        self.recorder.state_changed.connect(self._on_record_state)
        self.recorder.segment_closed.connect(self._on_segment)
        self.jarvis.delivered.connect(self._on_delivered)
        self.onair.record_requested.connect(self._toggle_record)
        self.onair.stop_requested.connect(self.recorder.stop)
        self.onair.rec_options_requested.connect(self._open_recording_settings)

    # ---------------------------------------------- micrófono (auto-ducking)
    def _setup_mic(self) -> None:
        self.mic_ducker = None
        self.clock.mic_clicked.connect(self._open_mic_settings)
        self.clock.set_mic_state(False)
        if (self.config.get("mic", {}) or {}).get("enabled"):
            self._apply_mic()

    def _open_mic_settings(self) -> None:
        from .widgets.mic_settings import MicSettingsDialog
        dlg = MicSettingsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            self._apply_mic()

    def _apply_mic(self) -> None:
        """(Re)construye el micrófono según la config y lo enciende si está activo."""
        if self.mic_ducker is not None:
            self.mic_ducker.stop()
            self.engine.remove_mic_voice()
            self.mic_ducker = None
        self.engine.set_mic_duck(False)
        mic = (self.config.get("mic", {}) or {})
        if not mic.get("enabled"):
            self.clock.set_mic_state(False)
            return
        from ..audio.mic_ducker import MicDucker
        self.mic_ducker = MicDucker(self.config, self)
        self.mic_ducker.speaking_changed.connect(self._on_mic_speaking)
        ok = self.mic_ducker.start()
        if ok and mic.get("to_air"):
            self.engine.add_mic_voice(self.mic_ducker.mic_source)
        self.clock.set_mic_state(enabled=ok)
        if ok:
            self.statusBar().showMessage("🎙 Micrófono activo (auto-ducking).", 4000)
        else:
            self.statusBar().showMessage(
                "No se pudo abrir el micrófono — revisa el dispositivo en sus ajustes.", 6000)

    def _on_mic_speaking(self, speaking: bool) -> None:
        mic = (self.config.get("mic", {}) or {})
        self.engine.set_mic_duck(speaking, float(mic.get("duck_main", 0.30)),
                                 float(mic.get("duck_carts", 0.50)))
        aux = getattr(self, "aux_engine", None)
        if aux is not None:
            aux.set_mic_duck(speaking, float(mic.get("duck_aux", 0.40)), 1.0)
        self.clock.set_mic_state(enabled=True, speaking=speaking)

    def _toggle_record(self) -> None:
        """Grabar/Pausar/Reanudar con el mismo botón (mismo archivo)."""
        if self.recorder.is_active():
            self.recorder.toggle_pause()
        else:
            self.recorder.start()

    def _open_recording_settings(self) -> None:
        from .widgets.recording_settings import RecordingSettingsDialog
        dlg = RecordingSettingsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            self.recorder.reconfigure(self.config)
            self.statusBar().showMessage("Opciones de grabación guardadas.", 4000)

    def _on_record_state(self, state: str) -> None:
        self.onair.set_record_state(state)
        if state == "recording":
            self._record_btn.setText("❚❚")
            self._record_btn.setStyleSheet("QToolButton { color: #e23b2e; }")
            self.statusBar().showMessage("⏺ GRABANDO", 4000)
        elif state == "paused":
            self._record_btn.setText("▶")
            self._record_btn.setStyleSheet("QToolButton { color: #c87f00; }")
            self.statusBar().showMessage("⏸ Grabación en pausa (mismo archivo)", 4000)
        else:  # stopped
            self._record_btn.setText("⏺")
            self._record_btn.setStyleSheet("")
            self.statusBar().showMessage("Grabación finalizada", 4000)

    def _on_segment(self, path: str) -> None:
        name = Path(path).name
        self.statusBar().showMessage(f"💾 Segmento guardado: {name}", 4000)
        if (self.config.get("recording", {}) or {}).get("send_to_jarvis"):
            self.jarvis.deliver_recording(path)

    def _on_delivered(self, path: str, ok: bool) -> None:
        name = Path(path).name
        if ok:
            self.notifier.notify(f"📝 Grabación enviada a JARVIS para transcripción: {name}")
            self.statusBar().showMessage(f"Enviado a JARVIS: {name}", 5000)
        else:
            self.statusBar().showMessage(f"⚠️ No se pudo enviar a JARVIS: {name}", 5000)

    def _on_encoder_state(self, state: str) -> None:
        msg = {"emitting": "🔴 EN VIVO — emitiendo al servidor",
               "reconnecting": "⚠️ Emisión interrumpida — reconectando…",
               "stopped": "Emisión detenida"}
        self.statusBar().showMessage(msg.get(state, state), 4000)

    def _on_failover_state(self, state: str) -> None:
        titles = {
            "stream": "🔵 SEÑAL DEL ESTUDIO (en vivo)",
            "grace": "⚠️ Reconectando con el estudio…",
            "offline": "🔴 PROTOCOLO OFFLINE — publicidad al aire",
        }
        self.onair.set_now_playing(titles.get(state, state))
        self.next_panel.set_next("—")

    def _on_stream_health(self, health: str) -> None:
        msg = {"connecting": "Conectando a la señal…", "on_air": "Recibiendo señal del estudio",
               "lost": "⚠️ Señal perdida"}
        self.statusBar().showMessage(msg.get(health, health), 4000)

    # --------------------------------------------------------------- handlers
    def _on_now_playing(self, _i: int, title: str) -> None:
        self.onair.set_now_playing(title)
        self._ends_anchor = None        # re-anclar "Acaba a las" en la nueva pista

    def _on_position(self, remaining: float, total: float) -> None:
        self.onair.set_remaining(fmt_mmss_tenths(remaining))
        self._sb_time.setText(fmt_mmss_tenths(remaining))
        self.transport.set_position((total - remaining) / total if total > 0 else 0.0)
        if remaining > 0:
            # "Acaba a las": se ANCLA la hora de fin absoluta y solo se recalcula si
            # cambia de verdad (>1.5 s = cambio de pista o seek). Así el indicador no
            # salta atrás/adelante por el jitter de VLC: se queda fijo en un número.
            now = QDateTime.currentMSecsSinceEpoch() / 1000.0
            candidate = now + remaining
            if self._ends_anchor is None or abs(candidate - self._ends_anchor) > 1.5:
                self._ends_anchor = candidate
            ends = QDateTime.fromSecsSinceEpoch(int(round(self._ends_anchor)))
            self.onair.set_ends_at(ends.toString("HH:mm:ss"))
        else:
            self._ends_anchor = None

    def _on_state(self, state: str) -> None:
        msg = {"playing": "Reproduciendo", "paused": "En pausa", "stopped": "Detenido"}
        self.statusBar().showMessage(msg.get(state, state), 3000)
        self.onair.set_playing_active(state == "playing")
        if state == "stopped":
            self.onair.set_remaining("00:00.0")
            self._ends_anchor = None

    def _on_volume(self, value: int) -> None:
        self.engine.set_volume(value)
        if self.master_volume.value() != value:
            self.master_volume.blockSignals(True)
            self.master_volume.setValue(value)
            self.master_volume.blockSignals(False)

    def _on_mode_toggled(self, action_id: str, on: bool) -> None:
        setter = _MODE_SETTERS.get(action_id)
        if setter:
            getattr(self.engine, setter)(on)

    def _on_engine_mode_changed(self, mode: str, on: bool) -> None:
        action_id = _MODE_TO_ACTION.get(mode)
        if action_id:
            self.transport.set_mode_checked(action_id, on)

    def _on_cart(self, slot: int) -> None:
        if not self.engine.fire_cart(slot):
            self.statusBar().showMessage(
                f"Cuña {chr(0x2460 + slot)} vacía — arrastra un audio sobre el botón para asignarla.",
                4000,
            )

    # ------------------------------------------------- menú contextual de la lista
    def _on_playlist_action(self, action: str, row: int) -> None:
        from copy import deepcopy
        model = self.playlist.model
        rows = self.playlist.selected_rows() or ([row] if row >= 0 else [])
        if action == "play" and row >= 0:
            self.engine.play_index(row)
        elif action == "mark_next" and row >= 0:
            self.engine.set_next(row)
            self.statusBar().showMessage(f"➡️ Marcada como siguiente: {model.items[row].title}", 4000)
        elif action == "rename" and row >= 0:
            cur = model.items[row].title
            text, ok = QInputDialog.getText(self, "Renombrar", "Nuevo título:", text=cur)
            if ok and text.strip():
                model.rename(row, text.strip())
        elif action == "assign_pisador" and row >= 0:
            music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
            path, _ = QFileDialog.getOpenFileName(
                self, "Asignar pisador a la pista", music_root,
                "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus);;Todos (*)")
            if path:
                model.set_pisador(row, path)
                self.statusBar().showMessage(f"🎙 Pisador asignado a: {model.items[row].title}", 4000)
        elif action == "cue" and row >= 0:
            self.engine.play_index(row)   # pre-escucha simple (al aire por ahora)
        elif action == "sel_duration":
            total = sum(model.items[r].duration for r in rows if 0 <= r < len(model.items))
            QMessageBox.information(self, "Duración de la selección",
                                    f"{len(rows)} pista(s)\nDuración total: {fmt_mmss_tenths(total)}")
        elif action == "update_duration":
            model.reprobe(rows)
        elif action == "copy":
            self._clipboard = [deepcopy(model.items[r]) for r in rows if 0 <= r < len(model.items)]
        elif action == "paste" and self._clipboard:
            at = (row + 1) if row >= 0 else None
            for it in self._clipboard:
                at = model.insert_item(deepcopy(it), at)
                at += 1
        elif action == "delete" and rows:
            model.remove_rows(rows)

    def _add_tracks(self) -> None:
        music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self, "Añadir pistas", music_root,
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus *.wma);;Todos los archivos (*)",
        )
        if files:
            self.playlist.add_paths(files)

    def _insert_at(self) -> int | None:
        rows = self.playlist.selected_rows()
        return (rows[-1] + 1) if rows else None

    def _add_random(self) -> None:
        music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Carpeta para pista aleatoria", music_root)
        if folder:
            self.playlist.model.add_random_folder(folder, self._insert_at())

    def _add_pause(self) -> None:
        secs, ok = QInputDialog.getInt(self, "Añadir pausa", "Segundos:", 3, 1, 3600)
        if ok:
            self.playlist.model.add_special(ItemType.PAUSE, self._insert_at(), seconds=secs)

    def _fire_locution(self, kind: str) -> None:
        if not self.engine.play_locution(kind):
            self.statusBar().showMessage(
                "No hay voz disponible (instala espeak-ng o configura fragmentos de locución).",
                5000,
            )

    def _pisador_dialog(self) -> None:
        music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "Pisador (voz superpuesta)", music_root,
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus);;Todos (*)",
        )
        if path:
            self.engine.play_voiceover(path)

    def _open_lst(self) -> None:
        music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(self, "Abrir lista", music_root,
                                              "Listas (*.lst);;Todos (*)")
        if path:
            self.playlist.model.set_items(load_lst(path))
            self.statusBar().showMessage(f"Lista cargada: {Path(path).name}", 4000)

    def _save_lst(self) -> None:
        music_root = (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())
        path, _ = QFileDialog.getSaveFileName(self, "Guardar lista", music_root,
                                              "Listas (*.lst)")
        if path:
            if not path.lower().endswith(".lst"):
                path += ".lst"
            save_lst(self.playlist.model.items, path)
            self.statusBar().showMessage(f"Lista guardada: {Path(path).name}", 4000)

    # ---------------------------------------------------------------- eventos
    def _refresh_events(self) -> None:
        self.events.set_events(self.scheduler.upcoming())

    def _schedule_event(self) -> None:
        default = QTime.currentTime().addSecs(60).toString("HH:mm:ss")
        time_str, ok = QInputDialog.getText(self, "Programar evento", "Hora (HH:MM:SS):", text=default)
        if not ok or not time_str.strip():
            return
        rows = self.playlist.selected_rows()
        if rows:
            item = self.playlist.model.items[rows[0]]
            ev = Event(time=time_str.strip(), action="play_file",
                       target=item.path, label=item.title)
        else:
            ev = Event(time=time_str.strip(), action="stop", label="Parar emisión")
        self.scheduler.add_event(ev)

    def _on_event(self, ev: Event) -> None:
        if ev.action == "stop":
            self.engine.stop()
        elif ev.action == "play_file" and ev.target:
            at = self.playlist.model.insert_item(PlaylistItem(path=ev.target, title=ev.label))
            self.engine.play_index(at)
        elif ev.action == "load_list" and ev.target:
            self.playlist.model.set_items(load_lst(ev.target))
            self.engine.play()
        self.statusBar().showMessage(f"⏰ Evento disparado: {ev.label or ev.action}", 5000)
        self._refresh_events()

    def _on_action(self, action_id: str) -> None:
        if action_id in _MEDIA_ACTIONS:
            getattr(self.engine, _MEDIA_ACTIONS[action_id])()
            return
        if action_id in _MODE_SETTERS:   # toggles desde el menú (p. ej. "Parar tras la actual")
            btn = self.transport.toggles.get(action_id)
            current = btn.isChecked() if btn else False
            getattr(self.engine, _MODE_SETTERS[action_id])(not current)
            return
        if action_id == "media.duck":
            on = self.engine.toggle_manual_duck()
            self.transport.set_ducked(on)
            self.statusBar().showMessage(
                "🔉 Pisador manual: música BAJADA" if on else "🔊 Pisador manual: música normal", 3000)
            return
        if action_id == "list.add_tracks":
            self._add_tracks()
            return
        if action_id == "edit.delete":
            self.playlist.remove_selected()
            return
        if action_id == "edit.delete_all":
            self.playlist.model.clear()
            return
        if action_id == "list.add_random":
            self._add_random()
            return
        if action_id == "list.add_stop":
            self.playlist.model.add_special(ItemType.STOP, self._insert_at())
            return
        if action_id == "list.add_pause":
            self._add_pause()
            return
        if action_id == "list.add_time":
            self.playlist.model.add_special(ItemType.TIME, self._insert_at())
            return
        if action_id == "list.add_temp":
            self.playlist.model.add_special(ItemType.TEMPERATURE, self._insert_at())
            return
        if action_id == "list.add_humidity":
            self.playlist.model.add_special(ItemType.HUMIDITY, self._insert_at())
            return
        if action_id in ("cue.time", "cue.temperature", "cue.humidity"):
            self._fire_locution(action_id.split(".", 1)[1])
            return
        if action_id == "media.voiceover":
            self._pisador_dialog()
            return
        if action_id == "file.open":
            self._open_lst()
            return
        if action_id in ("file.save", "file.save_as"):
            self._save_lst()
            return
        if action_id == "file.new":
            self.playlist.model.clear()
            return
        if action_id == "ryo.record":
            self._toggle_record()
            return
        if action_id == "tools.options":
            self._open_options()
            return
        if action_id in ("tools.log_explorer", "logs.today"):
            self._open_log_viewer()
            return
        if action_id == "logs.open_folder":
            folder = (self.config.get("paths", {}) or {}).get("logs_folder", ".")
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            return
        if action_id == "ryo.mentions":
            self._open_mentions()
            return
        if action_id == "help.update":
            self._check_updates(manual=True)
            return
        if action_id == "help.about":
            box = QMessageBox(self)
            box.setWindowTitle(f"Acerca de {C.APP_NAME}")
            box.setTextFormat(Qt.TextFormat.RichText)
            box.setText(
                f"<b>{C.APP_NAME}</b> v{C.APP_VERSION}<br><br>"
                "Automatización radial para Red Yungas.<br>"
                "Clon de ZaraRadio v1.6.2 con backend moderno e IA (MCP).")
            lp = logo_path()
            pm = QPixmap(lp) if lp else QPixmap()
            if not pm.isNull():
                box.setIconPixmap(pm.scaledToWidth(220, Qt.TransformationMode.SmoothTransformation))
            box.exec()
            return
        if action_id == "file.quit":
            self.close()
            return
        self.statusBar().showMessage(f"[{action_id}] — disponible en una fase posterior", 4000)

    # ------------------------------------------------------------- menciones
    def _setup_mentions(self) -> None:
        self.mentions_manager.mention_due.connect(self._on_mention_due)
        # Animación de deslizamiento del panel de menciones (riel izquierdo).
        self._mentions_anim = QPropertyAnimation(self.mentions_panel, b"maximumWidth", self)
        self._mentions_anim.setDuration(240)
        self._mentions_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.mentions_rail.toggled.connect(self._toggle_mentions_panel)

    def _toggle_mentions_panel(self, is_open: bool) -> None:
        anim = self._mentions_anim
        anim.stop()
        try:
            anim.finished.disconnect()
        except TypeError:
            pass
        if is_open:
            self.mentions_panel.setVisible(True)
            anim.setStartValue(self.mentions_panel.maximumWidth())
            anim.setEndValue(self.mentions_panel.PANEL_W)
        else:
            anim.setStartValue(self.mentions_panel.maximumWidth())
            anim.setEndValue(0)
            anim.finished.connect(lambda: self.mentions_panel.setVisible(False))
        anim.start()
        self.mentions_rail.set_open(is_open)

    def _on_mention_due(self, mention) -> None:
        self._toggle_mentions_panel(True)          # despliega el panel de menciones
        self.mentions_panel.highlight_mention(mention)
        self.statusBar().showMessage(f"📣 MENCIÓN AL AIRE: {mention.text}", 8000)

    # ------------------------------------------------------- opciones / log
    def _open_options(self) -> None:
        dlg = OptionsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            self._apply_audio_settings()
            QMessageBox.information(
                self, "Opciones guardadas",
                "Configuración guardada en config.toml.\n\n"
                "El fundido, el pisador y el volumen se aplican al instante; otros "
                "cambios (perfil, puertos, MCP, red, dispositivos) se aplican al reiniciar.",
            )

    def _apply_audio_settings(self) -> None:
        """Aplica EN VIVO los tiempos de audio (fundido/solape/pisador) a ambos motores."""
        au = (self.config.get("audio", {}) or {})
        for eng in (self.engine, getattr(self, "aux_engine", None)):
            if eng is None:
                continue
            eng.config = self.config            # el motor VLC lee la config en vivo
            if hasattr(eng, "crossfade_ms"):
                eng.crossfade_ms = int(au.get("crossfade_ms", eng.crossfade_ms))
            if hasattr(eng, "auto_crossfade_ms"):
                eng.auto_crossfade_ms = int(au.get("auto_crossfade_ms", eng.auto_crossfade_ms))
            if hasattr(eng, "duck_ms"):
                eng.duck_ms = int(au.get("duck_ms", eng.duck_ms))
            if hasattr(eng, "duck_level"):
                eng.duck_level = float(au.get("duck_level", eng.duck_level))

    def _open_log_viewer(self) -> None:
        folder = (self.config.get("paths", {}) or {}).get("logs_folder", ".")
        self._log_viewer = LogViewer(str(Path(folder) / "redyungas_oil.log"), self)
        self._log_viewer.show()
        self._log_viewer.raise_()

    def _open_mentions(self) -> None:
        # El botón 📝 y el menú abren el panel de menciones del borde izquierdo.
        self._toggle_mentions_panel(True)

    # ------------------------------------------------------------- MCP (IA)
    def _setup_mcp(self) -> None:
        self.mcp_server = None
        if not (self.config.get("mcp", {}) or {}).get("enabled"):
            return
        from ..mcp.server import MainThreadBridge, MCPServer
        from ..mcp.tools import RyoControl
        self._bridge = MainThreadBridge(self)
        control = RyoControl(self.engine, self.recorder, self.playlist.model,
                             self.mentions_manager, self.cartwall)
        try:
            self.mcp_server = MCPServer(self.config, control, self._bridge)
            self.mcp_server.start()
            port = (self.config.get("mcp", {}) or {}).get("port", 8770)
            self.statusBar().showMessage(f"Servidor MCP activo en el puerto {port}", 5000)
        except Exception as exc:  # nunca impedir que arranque la app
            self.statusBar().showMessage(f"MCP no disponible: {exc}", 6000)

    # ------------------------------------------------- auto-actualización
    def _setup_update(self) -> None:
        self.updater = None
        up = (self.config.get("update", {}) or {})
        if not up.get("enabled", True):
            return
        from ..core.updater import Updater
        self.updater = Updater(self.config, self)
        self.updater.checked.connect(self._on_update_checked)
        self.updater.applied.connect(self._on_update_applied)
        if up.get("check_on_start", True):
            QTimer.singleShot(4000, lambda: self._check_updates(manual=False))

    def _check_updates(self, manual: bool = True) -> None:
        if self.updater is None:
            from ..core.updater import Updater
            self.updater = Updater(self.config, self)
            self.updater.checked.connect(self._on_update_checked)
            self.updater.applied.connect(self._on_update_applied)
        self._update_manual = manual
        self.statusBar().showMessage("Buscando actualizaciones…", 3000)
        self.updater.check_async()

    def _on_update_checked(self, remote: str, has_update: bool, message: str) -> None:
        self.statusBar().showMessage(message, 6000)
        if has_update:
            resp = QMessageBox.question(
                self, "Actualización disponible",
                f"{message}\n\n¿Descargar e instalar ahora (git pull)?\n"
                "Tendrás que reiniciar la aplicación al terminar.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if resp == QMessageBox.StandardButton.Yes:
                self.updater.apply_async()
        elif getattr(self, "_update_manual", False):
            QMessageBox.information(self, "Actualizaciones", message)

    def _on_update_applied(self, ok: bool, message: str) -> None:
        self.statusBar().showMessage(message, 8000)
        if ok:
            resp = QMessageBox.question(
                self, "Actualización",
                f"{message}\n\n¿Reiniciar REDYUNGAS OIL ahora para aplicar la nueva versión?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if resp == QMessageBox.StandardButton.Yes:
                self._restart_app()
        else:
            QMessageBox.warning(self, "Actualización", message)

    def _restart_app(self) -> None:
        """Cierra recursos y RE-LANZA el proceso para cargar la versión nueva."""
        import os
        import sys
        self._shutdown_resources()
        try:
            if getattr(sys, "frozen", False):           # .exe empaquetado
                os.execv(sys.executable, [sys.executable])
            else:                                        # clon git: python -m redyungas_oil
                os.execv(sys.executable, [sys.executable, "-m", "redyungas_oil"])
        except Exception:
            # Si el re-exec falla, al menos cerrar para que el operador reabra.
            self.close()

    # ------------------------------------------------- emisor "PUERTO" (stream)
    def _setup_stream(self) -> None:
        """Panel emisor estilo Opticodec: medidor real + push a SHOUTcast/Icecast."""
        from ..audio.stream_encoder import StreamEncoder
        from ..audio.stream_meter import StreamMeter

        self.stream_encoder = StreamEncoder(self.config, self)
        self.stream_meter = StreamMeter(self.config, self)
        # "Al aire" SOLO parpadea si el PUERTO emite o recibe (si no, estático).
        self._air_emitting = False
        self._air_receiving = False

        # Animación de "deslizamiento" elegante del panel PUERTO (anima su ancho;
        # como la ventana ya abre ancha, el área central absorbe el cambio sin
        # mover el borde de la ventana).
        self._stream_anim = QPropertyAnimation(self.stream_panel, b"maximumWidth", self)
        self._stream_anim.setDuration(240)
        self._stream_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.stream_rail.toggled.connect(self._toggle_stream_panel)
        self.stream_panel.emit_requested.connect(self._stream_emit)
        self.stream_panel.stop_requested.connect(self.stream_encoder.stop)
        self.stream_panel.gain_changed.connect(self.stream_encoder.set_gain_db)
        self.stream_panel.settings_requested.connect(self._open_stream_settings)
        self.stream_meter.levels_changed.connect(self.stream_panel.set_levels_raw)
        self.stream_encoder.state_changed.connect(self._on_stream_state)
        # "Sonando ahora" del playout -> metadata del DNAS (como Opticodec).
        self.engine.now_playing_changed.connect(lambda _i, t: self.stream_encoder.set_metadata(t))

        # Receptor integrado al fondo del panel PUERTO (escuchar la transmisión).
        self.stream_receiver = None
        self.stream_recv_meter = None
        self.stream_panel.recv_listen.connect(self._recv_listen)
        self.stream_panel.recv_stop.connect(self._recv_stop)
        self.stream_panel.recv_volume.connect(self._recv_volume)

        if (self.config.get("stream", {}) or {}).get("connect_on_start"):
            self._stream_emit()

    def _recv_listen(self, url: str) -> None:
        if not url:
            return
        self._recv_stop()
        from ..audio.receiver import StreamReceiver
        from ..audio.stream_meter import StreamMeter
        cfg = {"network": {"stream_url": url}}
        self.stream_receiver = StreamReceiver(cfg, self)
        self.stream_receiver.health_changed.connect(self.stream_panel.set_recv_status)
        self.stream_receiver.health_changed.connect(self._on_recv_health)
        self.stream_receiver.set_volume(self.stream_panel.recv_vol.value())
        self.stream_receiver.start()
        # VU real del stream recibido (ffmpeg astats sobre la URL).
        self.stream_recv_meter = StreamMeter(self.config, self, source_url=url)
        self.stream_recv_meter.levels_changed.connect(self.stream_panel.set_recv_levels)
        self.stream_recv_meter.start()

    def _recv_stop(self) -> None:
        if self.stream_receiver is not None:
            self.stream_receiver.stop()
            self.stream_receiver = None
        if self.stream_recv_meter is not None:
            self.stream_recv_meter.stop()
            self.stream_recv_meter = None
        self.stream_panel.set_recv_status("stopped")
        self._air_receiving = False
        self._update_air()

    def _recv_volume(self, value: int) -> None:
        if self.stream_receiver is not None:
            self.stream_receiver.set_volume(value)

    def _toggle_stream_panel(self, is_open: bool) -> None:
        anim = self._stream_anim
        anim.stop()
        try:
            anim.finished.disconnect()
        except TypeError:
            pass
        if is_open:
            self.stream_panel.setVisible(True)
            anim.setStartValue(self.stream_panel.maximumWidth())
            anim.setEndValue(self.stream_panel.PANEL_W)
        else:
            anim.setStartValue(self.stream_panel.maximumWidth())
            anim.setEndValue(0)
            anim.finished.connect(lambda: self.stream_panel.setVisible(False))
        anim.start()
        self.stream_rail.set_open(is_open)
        self._update_meter_running()

    def _update_meter_running(self) -> None:
        want = self.stream_panel.isVisible() or self.stream_encoder.is_emitting()
        if want and not self.stream_meter.is_running():
            self.stream_meter.start()
        elif not want and self.stream_meter.is_running():
            self.stream_meter.stop()

    def _stream_emit(self) -> None:
        st = (self.config.get("stream", {}) or {})
        if not st.get("host") or not st.get("password"):
            QMessageBox.warning(
                self, "Emisor sin configurar",
                "Falta el servidor o la contraseña del stream.\n\n"
                "Ábrelo en ⚙ Ajustes del emisor (host, puerto, montaje, contraseña).",
            )
            self._open_stream_settings()
            return
        self.stream_encoder.set_gain_db(self.stream_panel.gain_db())
        self.stream_encoder.start()
        self._update_meter_running()

    def _on_stream_state(self, state: str) -> None:
        self.stream_panel.set_status(state)
        msg = {"emitting": "🟣 EN VIVO — emitiendo al stream público",
               "reconnecting": "⚠️ Stream interrumpido — reconectando…",
               "stopped": "Emisión de stream detenida"}
        self.statusBar().showMessage(msg.get(state, state), 4000)
        self._air_emitting = state in ("emitting", "reconnecting")
        self._update_air()
        if state == "stopped":
            self._update_meter_running()

    def _on_recv_health(self, health: str) -> None:
        self._air_receiving = (health == "on_air")
        self._update_air()

    def _update_air(self) -> None:
        """'Al aire' parpadea solo si el PUERTO emite o recibe señal."""
        self.onair.set_air_active(self._air_emitting or self._air_receiving)

    def _open_stream_settings(self) -> None:
        from .widgets.stream_settings import StreamSettingsDialog
        dlg = StreamSettingsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            self.stream_encoder.reconfigure(self.config)

    def _shutdown_resources(self) -> None:
        """Detiene motores, red, grabación, MCP, mic, etc. (cierre o reinicio)."""
        for attr, method in (("failover", "stop"), ("encoder", "stop"),
                             ("stream_encoder", "stop"), ("stream_meter", "stop"),
                             ("stream_receiver", "stop"), ("stream_recv_meter", "stop"),
                             ("mic_ducker", "stop"), ("mcp_server", "stop")):
            obj = getattr(self, attr, None)
            if obj is not None:
                try:
                    getattr(obj, method)()
                except Exception:
                    pass
        try:
            if getattr(self, "recorder", None) and self.recorder.is_recording():
                self.recorder.stop()
        except Exception:
            pass
        for eng_attr in ("aux_engine", "engine"):
            eng = getattr(self, eng_attr, None)
            if eng is not None:
                try:
                    eng.release()
                except Exception:
                    pass

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            self._shutdown_resources()
        finally:
            super().closeEvent(event)
