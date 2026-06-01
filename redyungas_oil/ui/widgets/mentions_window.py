"""
ui/widgets/mentions_window.py — Ventana de menciones que BRILLA (FASE 1 + FASE 7).

Muestra las menciones (de un MentionManager) con su horario. Cuando llega la hora
de una mención, su fila se ILUMINA/parpadea para que el locutor la recuerde y la
lea. Las menciones entran desde JARVIS/Telegram vía MCP/REST (Fase 7); también se
puede usar autónoma con datos demo.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


class MentionsWindow(QWidget):
    def __init__(self, manager=None, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setWindowTitle("Menciones — REDYUNGAS OIL")
        self.resize(580, 340)
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 4)
        self.table.setObjectName("mentionsTable")
        self.table.setHorizontalHeaderLabels(["Hora", "Mención", "Origen", "Estado"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self._mark_btn = QPushButton("Marcar como leída")
        self._mark_btn.clicked.connect(self._mark_selected_read)
        layout.addWidget(self._mark_btn)

        self._blink_row = -1
        self._blink_on = False
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink_tick)

        if self.manager is not None:
            for m in self.manager.mentions:
                self._append(m)
            self.manager.mention_added.connect(self._append)
        else:
            self._append_demo()

    # ------------------------------------------------------------------ filas
    def _append(self, mention) -> int:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(mention.when))
        self.table.setItem(row, 1, QTableWidgetItem(mention.text))
        self.table.setItem(row, 2, QTableWidgetItem(mention.source))
        self.table.setItem(row, 3, QTableWidgetItem("Leída" if mention.read else "Pendiente"))
        return row

    def _append_demo(self) -> None:
        from ...scheduler.mentions import Mention
        for hora, texto in (("07:30", "Saludo de apertura: 'Buenos días, Yungas…'"),
                            ("09:00", "Mención EMAPA: campaña de ahorro de agua."),
                            ("10:15", "Cumpleaños de doña Rosa (Coroico).")):
            self._append(Mention(text=texto, when=hora, source="demo"))

    # --------------------------------------------------------------- brillo
    def highlight_mention(self, mention) -> None:
        if self.manager is not None and mention in self.manager.mentions:
            self.highlight_row(self.manager.mentions.index(mention))

    def highlight_row(self, row: int) -> None:
        self._blink_row = row
        self._blink_on = False
        if 0 <= row < self.table.rowCount() and self.table.item(row, 3):
            self.table.item(row, 3).setText("¡AL AIRE!")
        self._blink_timer.start(500)

    def _mark_selected_read(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        if self.manager is not None:
            self.manager.mark_read(row)
        if self.table.item(row, 3):
            self.table.item(row, 3).setText("Leída")
        if row == self._blink_row:
            self._blink_timer.stop()
            self._set_row_bg(row, None)
            self._blink_row = -1

    def _blink_tick(self) -> None:
        if self._blink_row < 0:
            return
        self._blink_on = not self._blink_on
        self._set_row_bg(self._blink_row, QColor("#fff04d") if self._blink_on else QColor("#fff8c0"))

    def _set_row_bg(self, row: int, color) -> None:
        if not (0 <= row < self.table.rowCount()):
            return
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color if color else QColor(Qt.GlobalColor.white))
