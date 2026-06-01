"""
ui/widgets/playlist_view.py — Lista de reproducción central (FASE 2).

QTableView respaldado por PlaylistModel: columnas Título / Duración, fila roja =
sonando, verde = siguiente, "Duración Total" en vivo, y DROP de archivos desde el
árbol o desde cualquier ventana externa (text/uri-list). El reordenamiento se hace
con las flechas ▲▼ de la ventana principal (model.move_row).
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...core.timefmt import fmt_mmss_tenths
from ...playlist.model import PlaylistModel


class PlaylistView(QWidget):
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
        root.addWidget(self.view, 1)

        self.model.total_changed.connect(self._update_total)

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
