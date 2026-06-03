"""
ui/widgets/aux_panel.py — Planilla AUXILIAR "Aux 1" (réplica del reproductor auxiliar
de ZaraRadio, botón >1).

Es una segunda planilla con LA MISMA funcionalidad que la principal: su lista, su
barra de transporte (con la regleta de POSICIÓN que reproduce desde donde se suelta)
y, además, un **control de volumen VERDE horizontal**. La reproducción es
INDEPENDIENTE de la principal (un segundo motor de audio), así que pueden sonar a la
vez si el operador lo desea.

El panel se desliza desde el borde derecho (lo anima MainWindow cambiando su ancho).
Las operaciones de archivo (nuevo/abrir/guardar/añadir) las maneja el propio panel
sobre SU modelo de lista, para no acoplarlo a la ventana principal.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...playlist.lst_io import load_lst, save_lst
from .playlist_view import PlaylistView
from .transport_bar import TransportBar


class AuxPlaylistPanel(QWidget):
    PANEL_W = 360

    closed = pyqtSignal()
    volume_changed = pyqtSignal(int)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        self.config = config or {}
        self.setObjectName("auxPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(0)
        self.setMaximumWidth(self.PANEL_W)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        # --- Cabecera: marca "Aux 1" + mini-toolbar + cierre ---
        head = QHBoxLayout(); head.setSpacing(4)
        banner = QLabel("Aux 1"); banner.setObjectName("auxBanner")
        head.addWidget(banner)
        head.addStretch(1)
        for glyph, tip, slot in (
            ("🗋", "Nuevo", self._new),
            ("📂", "Abrir lista…", self._open),
            ("💾", "Guardar lista…", self._save),
            ("➕", "Añadir pistas…", self._add),
        ):
            b = QToolButton(); b.setText(glyph); b.setToolTip(tip); b.setAutoRaise(True)
            b.clicked.connect(slot)
            head.addWidget(b)
        self.btn_close = QToolButton(); self.btn_close.setText("«")
        self.btn_close.setObjectName("auxClose")
        self.btn_close.setToolTip("Cerrar la planilla auxiliar")
        self.btn_close.clicked.connect(self.closed)
        head.addWidget(self.btn_close)
        root.addLayout(head)

        self.now_label = QLabel("—")
        self.now_label.setObjectName("auxNow")
        self.now_label.setWordWrap(True)
        root.addWidget(self.now_label)

        # --- Lista (misma vista que la principal) ---
        self.playlist = PlaylistView()
        root.addWidget(self.playlist, 1)

        # --- Transporte (reutiliza la barra; apilada: la regleta de POSICIÓN va en
        # su propia fila a todo lo ancho, para manipularla bien en el panel estrecho) ---
        self.transport = TransportBar(stacked=True)
        root.addWidget(self.transport)

        # --- Volumen VERDE horizontal (extra de la auxiliar) ---
        vol_row = QHBoxLayout(); vol_row.setSpacing(6)
        vtag = QLabel("Volumen"); vtag.setObjectName("sectionTag")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("auxVolume")
        self.volume.setRange(0, 100); self.volume.setValue(80)
        self.volume.valueChanged.connect(self.volume_changed)
        vol_row.addWidget(vtag, 0)
        vol_row.addWidget(self.volume, 1)
        root.addLayout(vol_row)

    # ------------------------------------------------------------- operaciones
    def _music_root(self) -> str:
        return (self.config.get("paths", {}) or {}).get("music_root") or str(Path.home())

    def _new(self) -> None:
        self.playlist.model.clear()

    def _open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Abrir lista (Aux 1)", self._music_root(),
                                              "Listas (*.lst);;Todos (*)")
        if path:
            self.playlist.model.set_items(load_lst(path))

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Guardar lista (Aux 1)", self._music_root(),
                                              "Listas (*.lst)")
        if path:
            if not path.lower().endswith(".lst"):
                path += ".lst"
            save_lst(self.playlist.model.items, path)

    def _add(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "Añadir pistas (Aux 1)", self._music_root(),
            "Audio (*.mp3 *.wav *.ogg *.flac *.m4a *.aac *.opus *.wma);;Todos (*)")
        if files:
            self.playlist.add_paths(files)

    def set_now_playing(self, title: str) -> None:
        self.now_label.setText(title or "—")
