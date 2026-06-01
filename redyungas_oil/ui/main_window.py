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

from PyQt6.QtCore import QDateTime, Qt, QTime, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSlider,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..audio.engine import AudioEngine
from ..audio.recorder import Recorder
from ..core import constants as C
from ..core.timefmt import fmt_mmss_tenths
from ..integrations.jarvis_adapter import JarvisAdapter
from ..integrations.telegram_notifier import TelegramNotifier
from ..playlist.item_types import ItemType, PlaylistItem
from ..playlist.lst_io import load_lst, save_lst
from ..scheduler.events import Event, EventScheduler
from ..scheduler.mentions import MentionManager
from .widgets.cartwall import Cartwall
from .widgets.events_panel import EventsPanel
from .widgets.file_tree import FileTree
from .widgets.lcd_clock import ClockBar
from .widgets.mentions_window import MentionsWindow
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


class MainWindow(QMainWindow):
    def __init__(self, config: dict | None = None) -> None:
        super().__init__()
        self.config = config or {}
        self.setWindowTitle(f"{C.APP_TITLE_DEFAULT} — {C.APP_NAME}")
        self.resize(1024, 648)

        self._actions: dict[str, QAction] = {}
        self.mentions_window: MentionsWindow | None = None

        self._build_menus()
        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._setup_engine()
        self._setup_network()
        self._setup_recording()
        self._setup_mentions()
        self._setup_mcp()
        self._setup_stream()
        self._setup_update()

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
        add_btn("📻", "media.tune", "Recibir señal (escuchar un stream)")
        add_btn("❓", "help.contents", "Ayuda")

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)
        sec = QLabel("Copia secundaria")
        sec.setObjectName("secondaryCopy")
        tb.addWidget(sec)
        logo = QLabel("🔴 REDYUNGAS OIL")
        logo.setObjectName("brandLogo")
        tb.addWidget(logo)

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
        outer_l.addWidget(central, 1)
        self.stream_panel = StreamPanel(self.config)
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
    def _setup_engine(self) -> None:
        self.engine = AudioEngine(self.config, model=self.playlist.model, parent=self)

        # Señales del motor -> UI
        self.engine.now_playing_changed.connect(lambda _i, t: self.onair.set_now_playing(t))
        self.engine.next_changed.connect(lambda _i, t: self.next_panel.set_next(t or "—"))
        self.engine.position_changed.connect(self._on_position)
        self.engine.levels_changed.connect(self.onair.vu.set_levels)
        self.engine.state_changed.connect(self._on_state)

        # Controles -> motor
        self.transport.action_triggered.connect(self._on_action)
        self.transport.volume_changed.connect(self._on_volume)
        self.master_volume.valueChanged.connect(self._on_volume)
        self.playlist.view.doubleClicked.connect(lambda idx: self.engine.play_index(idx.row()))
        self.up_btn.clicked.connect(lambda: self.playlist.move_selected(-1))
        self.down_btn.clicked.connect(lambda: self.playlist.move_selected(1))
        self.cartwall.cart_triggered.connect(self._on_cart)
        self.cartwall.cart_assigned.connect(self.engine.assign_cart)

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

    def _toggle_record(self) -> None:
        if self.recorder.is_recording():
            self.recorder.stop()
        else:
            self.recorder.start()

    def _on_record_state(self, state: str) -> None:
        recording = state == "recording"
        self._record_btn.setText("⏹" if recording else "⏺")
        self._record_btn.setStyleSheet("QToolButton { color: #e23b2e; }" if recording else "")
        self.statusBar().showMessage("⏺ GRABANDO" if recording else "Grabación detenida", 4000)

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
    def _on_position(self, remaining: float, total: float) -> None:
        self.onair.set_remaining(fmt_mmss_tenths(remaining))
        self._sb_time.setText(fmt_mmss_tenths(remaining))
        if remaining > 0:
            ends = QDateTime.currentDateTime().addSecs(int(round(remaining)))
            self.onair.set_ends_at(ends.toString("HH:mm:ss"))

    def _on_state(self, state: str) -> None:
        msg = {"playing": "Reproduciendo", "paused": "En pausa", "stopped": "Detenido"}
        self.statusBar().showMessage(msg.get(state, state), 3000)
        if state == "stopped":
            self.onair.set_remaining("00:00.0")

    def _on_volume(self, value: int) -> None:
        self.engine.set_volume(value)
        for slider in (self.transport.slider, self.master_volume):
            if slider.value() != value:
                slider.blockSignals(True)
                slider.setValue(value)
                slider.blockSignals(False)

    def _on_cart(self, slot: int) -> None:
        if not self.engine.fire_cart(slot):
            self.statusBar().showMessage(
                f"Cuña {chr(0x2460 + slot)} vacía — arrastra un audio sobre el botón para asignarla.",
                4000,
            )

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
        if action_id == "media.tune":
            self._open_tuner()
            return
        if action_id == "help.update":
            self._check_updates(manual=True)
            return
        if action_id == "help.about":
            QMessageBox.about(
                self, f"Acerca de {C.APP_NAME}",
                f"{C.APP_NAME} v{C.APP_VERSION}\n\n"
                "Automatización radial para Red Yungas.\n"
                "Clon de ZaraRadio v1.6.2 con backend moderno e IA (MCP).",
            )
            return
        if action_id == "file.quit":
            self.close()
            return
        self.statusBar().showMessage(f"[{action_id}] — disponible en una fase posterior", 4000)

    # ------------------------------------------------------------- menciones
    def _setup_mentions(self) -> None:
        self.mentions_manager = MentionManager(self)
        self.mentions_manager.mention_due.connect(self._on_mention_due)

    def _on_mention_due(self, mention) -> None:
        self._open_mentions()
        self.mentions_window.highlight_mention(mention)
        self.statusBar().showMessage(f"📣 MENCIÓN AL AIRE: {mention.text}", 8000)

    # ------------------------------------------------------- opciones / log
    def _open_options(self) -> None:
        dlg = OptionsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            QMessageBox.information(
                self, "Opciones guardadas",
                "Configuración guardada en config.toml.\n\n"
                "Algunos cambios (perfil, puertos, MCP, red) se aplican al reiniciar.",
            )

    def _open_log_viewer(self) -> None:
        folder = (self.config.get("paths", {}) or {}).get("logs_folder", ".")
        self._log_viewer = LogViewer(str(Path(folder) / "redyungas_oil.log"), self)
        self._log_viewer.show()
        self._log_viewer.raise_()

    def _open_mentions(self) -> None:
        if self.mentions_window is None:
            self.mentions_window = MentionsWindow(self.mentions_manager, self)
            self.mentions_window.setWindowFlag(Qt.WindowType.Window, True)
        self.mentions_window.show()
        self.mentions_window.raise_()
        self.mentions_window.activateWindow()

    def _open_tuner(self) -> None:
        """Sintonizador manual: escuchar un stream sin cambiar de perfil ni reiniciar."""
        from .widgets.tuner_window import TunerWindow
        if getattr(self, "_tuner", None) is None:
            self._tuner = TunerWindow(self.config, self)
        self._tuner.show()
        self._tuner.raise_()
        self._tuner.activateWindow()

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
        icon = QMessageBox.information if ok else QMessageBox.warning
        icon(self, "Actualización", message)

    # ------------------------------------------------- emisor "PUERTO" (stream)
    def _setup_stream(self) -> None:
        """Panel emisor estilo Opticodec: medidor real + push a SHOUTcast/Icecast."""
        from ..audio.stream_encoder import StreamEncoder
        from ..audio.stream_meter import StreamMeter

        self.stream_encoder = StreamEncoder(self.config, self)
        self.stream_meter = StreamMeter(self.config, self)

        self.stream_rail.toggled.connect(self._toggle_stream_panel)
        self.stream_panel.emit_requested.connect(self._stream_emit)
        self.stream_panel.stop_requested.connect(self.stream_encoder.stop)
        self.stream_panel.gain_changed.connect(self.stream_encoder.set_gain_db)
        self.stream_panel.settings_requested.connect(self._open_stream_settings)
        self.stream_meter.levels_changed.connect(self.stream_panel.set_levels_raw)
        self.stream_encoder.state_changed.connect(self._on_stream_state)
        # "Sonando ahora" del playout -> metadata del DNAS (como Opticodec).
        self.engine.now_playing_changed.connect(lambda _i, t: self.stream_encoder.set_metadata(t))

        if (self.config.get("stream", {}) or {}).get("connect_on_start"):
            self._stream_emit()

    def _toggle_stream_panel(self, is_open: bool) -> None:
        self.stream_panel.setVisible(is_open)
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
        if state == "stopped":
            self._update_meter_running()

    def _open_stream_settings(self) -> None:
        from .widgets.stream_settings import StreamSettingsDialog
        dlg = StreamSettingsDialog(self.config, self)
        if dlg.exec():
            self.config = dlg.result_config()
            self.stream_encoder.reconfigure(self.config)

    def closeEvent(self, event) -> None:  # noqa: N802
        try:
            if getattr(self, "failover", None):
                self.failover.stop()
            if getattr(self, "encoder", None):
                self.encoder.stop()
            if getattr(self, "stream_encoder", None):
                self.stream_encoder.stop()
            if getattr(self, "stream_meter", None):
                self.stream_meter.stop()
            if getattr(self, "recorder", None) and self.recorder.is_recording():
                self.recorder.stop()
            if getattr(self, "mcp_server", None):
                self.mcp_server.stop()
            self.engine.release()
        finally:
            super().closeEvent(event)
