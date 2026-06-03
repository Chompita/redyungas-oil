"""
ui/widgets/cartwall.py — Cartwall de 9 cuñas (réplica ZaraRadio) + controles.

Nueve botones (①..⑨) para lanzar cuñas rápidas + selector de banco, un botón de
**fundido general** y un **volumen general** pequeño para todas las cuñas. Cada botón:
    - clic izquierdo  -> dispara/silencia la cuña (toggle suave, lo decide el motor)
    - soltar un audio -> asigna esa cuña al slot (cart_assigned)
    - teclas 1..9     -> equivalen a un clic en el botón correspondiente

Detalles pedidos por el operador:
* El botón **NO cambia de tamaño** al asignarle una cuña: el texto se **elide** y el
  ancho lo reparte el layout por igual (no crece para mostrar el nombre completo).
* El **segundo clic NO reproduce de nuevo**: silencia la cuña con un pisador suave
  (el motor hace el fundido). El estado activo se muestra resaltado en el botón.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QWidget,
)

from ...core import constants as C
from ...playlist.item_types import is_audio


class _CartButton(QPushButton):
    dropped = pyqtSignal(str)        # ruta de audio soltada

    def __init__(self, text: str, parent=None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setAcceptDrops(True)
        # Ancho repartido por el layout (no por el texto): así NO crece con el nombre.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(40)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full_text = text
        self._apply_elided()

    def full_text(self) -> str:
        return self._full_text

    def _apply_elided(self) -> None:
        fm = QFontMetrics(self.font())
        elided = fm.elidedText(self._full_text, Qt.TextElideMode.ElideRight,
                               max(10, self.width() - 16))
        super().setText(elided)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elided()

    def set_active(self, active: bool) -> None:
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)

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
    cart_triggered = pyqtSignal(int)         # slot disparado/silenciado (toggle)
    cart_assigned = pyqtSignal(int, str)     # slot, ruta asignada
    fade_all_requested = pyqtSignal()        # fundido general de todas las cuñas
    volume_changed = pyqtSignal(int)         # volumen general de las cuñas 0..100

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
            btn.set_active(False)
            btn.clicked.connect(lambda _=False, n=i: self.cart_triggered.emit(n))
            btn.dropped.connect(lambda path, n=i: self._assign(n, path))
            self.buttons.append(btn)
            layout.addWidget(btn, 1)

        # --- Fundido general de todas las cuñas ---
        self.btn_fade_all = QToolButton()
        self.btn_fade_all.setObjectName("cartFadeAll")
        self.btn_fade_all.setText("≈")
        self.btn_fade_all.setToolTip("Fundido general de todas las cuñas")
        self.btn_fade_all.clicked.connect(self.fade_all_requested)
        layout.addWidget(self.btn_fade_all, 0)

        # --- Volumen general (pequeño) de todas las cuñas ---
        vlab = QLabel("Vol")
        vlab.setObjectName("sectionTag")
        layout.addWidget(vlab, 0)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setObjectName("cartVolume")
        self.volume.setRange(0, 100)
        self.volume.setValue(100)
        self.volume.setFixedWidth(70)
        self.volume.setToolTip("Volumen general de las cuñas")
        self.volume.valueChanged.connect(self.volume_changed)
        layout.addWidget(self.volume, 0)

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

    def set_active(self, slot: int, active: bool) -> None:
        """Resalta el botón mientras su cuña suena (lo dirige el motor)."""
        if 0 <= slot < len(self.buttons):
            self.buttons[slot].set_active(active)

    def activate_slot(self, slot: int) -> None:
        """Equivalente a pulsar el botón (lo usan las teclas 1..9)."""
        if 0 <= slot < len(self.buttons):
            self.cart_triggered.emit(slot)
