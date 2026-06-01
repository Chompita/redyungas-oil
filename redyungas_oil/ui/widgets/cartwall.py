"""
ui/widgets/cartwall.py — Cartwall de 9 cuñas (réplica ZaraRadio).

Nueve botones (①..⑨) para lanzar cuñas rápidas + selector de banco. Cada botón:
    - clic izquierdo  -> dispara la cuña (cart_triggered)
    - soltar un audio -> asigna esa cuña al slot (cart_assigned)
El número de slots viene de core.constants.CARTWALL_SLOTS.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSpinBox, QWidget

from ...core import constants as C
from ...playlist.item_types import is_audio


class _CartButton(QPushButton):
    dropped = pyqtSignal(str)        # ruta de audio soltada

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile() and is_audio(url.toLocalFile()):
                self.dropped.emit(url.toLocalFile())
                event.acceptProposedAction()
                return


class Cartwall(QWidget):
    cart_triggered = pyqtSignal(int)         # slot disparado
    cart_assigned = pyqtSignal(int, str)     # slot, ruta asignada

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(3)

        self.buttons: list[_CartButton] = []
        for i in range(C.CARTWALL_SLOTS):
            btn = _CartButton(f"{chr(0x2460 + i)}  Vacío")
            btn.setObjectName("cartButton")
            btn.setMinimumHeight(26)
            btn.clicked.connect(lambda _=False, n=i: self.cart_triggered.emit(n))
            btn.dropped.connect(lambda path, n=i: self._assign(n, path))
            self.buttons.append(btn)
            layout.addWidget(btn, 1)

        self.bank = QSpinBox()
        self.bank.setObjectName("cartBank")
        self.bank.setRange(1, 99)
        self.bank.setFixedWidth(46)
        layout.addWidget(self.bank, 0, Qt.AlignmentFlag.AlignRight)

    def _assign(self, slot: int, path: str) -> None:
        self.set_cart(slot, Path(path).stem)
        self.cart_assigned.emit(slot, path)

    def set_cart(self, slot: int, label: str) -> None:
        if 0 <= slot < len(self.buttons):
            self.buttons[slot].setText(f"{chr(0x2460 + slot)}  {label}")
