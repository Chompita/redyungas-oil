"""
ui/widgets/events_panel.py — Panel "Eventos próximos" (FASE 1 visual + FASE 3 funcional).

Barra de iconos (programar / quitar) sobre una tabla Hora | Comienzo | Fichero |
Duración. Se alimenta desde scheduler/events.py vía set_events(). Emite señales
para que la ventana principal programe o quite eventos.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


class EventsPanel(QWidget):
    schedule_requested = pyqtSignal()    # 🕓 programar
    remove_requested = pyqtSignal(int)   # ✕ quitar el evento seleccionado

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(2, 2, 2, 2)
        root.setSpacing(2)

        header = QHBoxLayout()
        tag = QLabel("Eventos próximos")
        tag.setObjectName("sectionTag")
        header.addWidget(tag)
        header.addStretch(1)
        self._btn_play = self._mk_btn(header, "▶", "Reproducir ahora")
        self._btn_remove = self._mk_btn(header, "✕", "Quitar evento")
        self._btn_check = self._mk_btn(header, "✔", "Activar/Desactivar")
        self._btn_sched = self._mk_btn(header, "🕓", "Programar evento")
        self._btn_remove.clicked.connect(self._on_remove)
        self._btn_sched.clicked.connect(self.schedule_requested.emit)
        root.addLayout(header)

        self.table = QTreeWidget()
        self.table.setObjectName("eventsTable")
        self.table.setColumnCount(4)
        self.table.setHeaderLabels(["Hora", "Comienzo", "Fichero", "Duración"])
        self.table.setRootIsDecorated(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setUniformRowHeights(True)
        self.table.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

    @staticmethod
    def _mk_btn(layout, glyph, tip) -> QToolButton:
        btn = QToolButton()
        btn.setText(glyph)
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        layout.addWidget(btn)
        return btn

    def _on_remove(self) -> None:
        idx = self.selected_index()
        if idx >= 0:
            self.remove_requested.emit(idx)

    def selected_index(self) -> int:
        item = self.table.currentItem()
        return self.table.indexOfTopLevelItem(item) if item else -1

    def set_events(self, upcoming) -> None:
        """upcoming: lista de (QDateTime, Event) ya ordenada (scheduler.upcoming())."""
        self.table.clear()
        for dt, ev in upcoming:
            target = ev.target or ev.label or ev.action
            from pathlib import Path
            shown = Path(target).name if ev.action != "stop" and target else target
            row = QTreeWidgetItem([ev.time, dt.toString("dd/MM HH:mm:ss"), shown, ""])
            self.table.addTopLevelItem(row)
