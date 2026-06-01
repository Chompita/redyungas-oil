"""
ui/widgets/playlist_view.py — Lista de reproducción central (FASE 2).

QTableView respaldado por PlaylistModel: columnas Título / Duración, fila roja =
sonando, verde = siguiente, "Duración Total" en vivo, y DROP de archivos desde el
árbol o desde cualquier ventana externa (text/uri-list). El reordenamiento se hace
con las flechas ▲▼ de la ventana principal (model.move_row).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.timefmt import fmt_mmss_tenths
from ...playlist.model import PlaylistModel

# (etiqueta, action_id, atajo)  — réplica del menú de click derecho de ZaraRadio
_CONTEXT_ITEMS = [
    ("Marcar como siguiente", "mark_next", None),
    ("Reproducir", "play", None),
    ("Renombrar", "rename", "F2"),
    ("Asignar pisador...", "assign_pisador", None),
    ("-", None, None),
    ("Cue", "cue", None),
    ("Ver la duración de la selección...", "sel_duration", "Ctrl+L"),
    ("Actualizar duración", "update_duration", "Ctrl+U"),
    ("-", None, None),
    ("Copiar", "copy", "Ctrl+C"),
    ("Pegar", "paste", "Ctrl+V"),
    ("-", None, None),
    ("Eliminar", "delete", "Del"),
]


class PlaylistView(QWidget):
    action_requested = pyqtSignal(str, int)   # (action_id, row)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.model = PlaylistModel(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        header = QHBoxLayout()
        self.total_label = QLabel("Duración Total: 00:00.0")
        self.total_label.setObjectName("durTotal")
        header.addWidget(self.total_label)
        header.addStretch(1)
        for glyph, tip in (("🖫", "Exportar lista"), ("⟳", "Actualizar")):
            btn = QToolButton()
            btn.setText(glyph)
            btn.setToolTip(tip)
            btn.setAutoRaise(True)
            header.addWidget(btn)
        root.addLayout(header)

        self.view = QTableView()
        self.view.setObjectName("playlist")
        self.view.setModel(self.model)
        self.view.verticalHeader().setVisible(False)
        self.view.setShowGrid(False)
        self.view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setAcceptDrops(True)
        self.view.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)
        self.view.setDropIndicatorShown(True)
        hh = self.view.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._context_menu)
        root.addWidget(self.view, 1)

        self.model.total_changed.connect(self._update_total)

    # ----------------------------------------------------------- menú contextual
    def _context_menu(self, pos) -> None:
        index = self.view.indexAt(pos)
        row = index.row() if index.isValid() else -1
        if row >= 0 and row not in self.selected_rows():
            self.view.selectRow(row)
        menu = QMenu(self)
        for label, action_id, shortcut in _CONTEXT_ITEMS:
            if label == "-":
                menu.addSeparator()
                continue
            act = menu.addAction(label)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.setEnabled(row >= 0 or action_id == "paste")
            act.triggered.connect(lambda _=False, a=action_id, r=row: self.action_requested.emit(a, r))
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _update_total(self, total: float) -> None:
        self.total_label.setText(f"Duración Total: {fmt_mmss_tenths(total)}")

    # API usada por la ventana principal
    def add_paths(self, paths) -> None:
        self.model.add_paths(paths)

    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.view.selectionModel().selectedRows()})

    def remove_selected(self) -> None:
        rows = self.selected_rows()
        if rows:
            self.model.remove_rows(rows)

    def move_selected(self, delta: int) -> None:
        rows = self.selected_rows()
        if len(rows) != 1:
            return
        new = self.model.move_row(rows[0], rows[0] + delta)
        self.view.selectRow(new)
