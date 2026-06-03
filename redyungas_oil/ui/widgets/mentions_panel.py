"""
ui/widgets/mentions_panel.py — Riel + panel de MENCIONES en el borde IZQUIERDO.

Equivalente al panel "PUERTO" (derecha) pero a la izquierda: una pestaña vertical
"MENCIONES" siempre visible; al pulsarla, el panel se DESLIZA mostrando las menciones
del horario. Cuando llega la hora de una mención, su fila se ILUMINA/parpadea para
que el locutor la lea (alimentado por scheduler/mentions.MentionManager).
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

RAIL_W = 26


class MentionsRail(QWidget):
    """Pestaña vertical 'MENCIONES' del borde IZQUIERDO (abre/cierra el panel)."""

    toggled = pyqtSignal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._open = False
        self._hover = False
        self.setFixedWidth(RAIL_W)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Menciones del horario — clic para abrir/cerrar")
        self.setObjectName("mentionsRail")

    def set_open(self, is_open: bool) -> None:
        self._open = is_open
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._open = not self._open
        self.toggled.emit(self._open)
        self.update()

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hover = True; self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hover = False; self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        w, h = self.width(), self.height()
        base = QColor("#1f7a52") if not self._hover else QColor("#249162")
        p.fillRect(0, 0, w, h, base)
        p.setPen(QColor("#11503a"))
        p.drawLine(w - 1, 0, w - 1, h)
        # Flecha: » (cerrado, abrir hacia la derecha) / « (abierto)
        p.setPen(QColor("#ffffff"))
        af = QFont(); af.setPointSize(11); af.setBold(True); p.setFont(af)
        arrow = "«" if self._open else "»"
        p.drawText(0, 4, w, 18, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, arrow)
        # Texto "MENCIONES" vertical, de ABAJO hacia ARRIBA.
        p.save()
        p.translate(w // 2 + 5, h - 8)
        p.rotate(-90)
        tf = QFont(); tf.setPointSize(9); tf.setBold(True); p.setFont(tf)
        p.setPen(QColor("#ffffff"))
        p.drawText(0, 0, "MENCIONES")
        p.restore()
        p.end()


class MentionsPanel(QWidget):
    """Panel desplegable con las menciones (tabla + parpadeo de la que está al aire)."""

    PANEL_W = 320

    def __init__(self, manager=None, parent=None) -> None:
        super().__init__(parent)
        self.manager = manager
        self.setObjectName("mentionsPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumWidth(0)
        self.setMaximumWidth(self.PANEL_W)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(5)

        banner = QLabel("MENCIONES"); banner.setObjectName("mentionsBanner")
        root.addWidget(banner)
        hint = QLabel("Brillan al llegar su hora para que el locutor las lea.")
        hint.setObjectName("mentionsHint"); hint.setWordWrap(True)
        root.addWidget(hint)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine); sep.setObjectName("mentionsSep")
        root.addWidget(sep)

        self.table = QTableWidget(0, 3)
        self.table.setObjectName("mentionsTable")
        self.table.setHorizontalHeaderLabels(["Hora", "Mención", "Estado"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self._mark_btn = QPushButton("Marcar como leída")
        self._mark_btn.clicked.connect(self._mark_selected_read)
        root.addWidget(self._mark_btn)

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
        self.table.setItem(row, 2, QTableWidgetItem("Leída" if mention.read else "Pendiente"))
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
        if 0 <= row < self.table.rowCount() and self.table.item(row, 2):
            self.table.item(row, 2).setText("¡AL AIRE!")
        self._blink_timer.start(500)

    def _mark_selected_read(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        if self.manager is not None:
            self.manager.mark_read(row)
        if self.table.item(row, 2):
            self.table.item(row, 2).setText("Leída")
        if row == self._blink_row:
            self._blink_timer.stop()
            self._set_row_bg(row, None)
            self._blink_row = -1

    def _blink_tick(self) -> None:
        if self._blink_row < 0:
            return
        self._blink_on = not self._blink_on
        self._set_row_bg(self._blink_row,
                         QColor("#fff04d") if self._blink_on else QColor("#fff8c0"))

    def _set_row_bg(self, row: int, color) -> None:
        if not (0 <= row < self.table.rowCount()):
            return
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color if color else QColor(Qt.GlobalColor.white))
