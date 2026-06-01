"""
playlist/model.py — Modelo de la lista de reproducción (FASE 2).

QAbstractTableModel que respalda la tabla central: columnas Título / Duración,
fila ROJA = sonando, fila VERDE = siguiente, "Duración Total", y drop de archivos
(text/uri-list) desde el árbol o desde cualquier ventana externa.

El motor de audio (audio/engine.py) marca quién suena con set_playing(); los
marcadores siguen al ÍTEM (por identidad), así que sobreviven a reordenamientos.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QThreadPool,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QColor

from ..audio.probe import ProbeSignals, ProbeTask
from ..core import constants as C
from ..core.timefmt import fmt_mmss_tenths
from .item_types import ItemType, PlaylistItem, is_audio

_SPECIAL_TITLES = {
    ItemType.STOP: "Comando stop",
    ItemType.TIME: "Locución de hora",
    ItemType.TEMPERATURE: "Locución de temperatura",
    ItemType.HUMIDITY: "Locución de humedad",
}


class PlaylistModel(QAbstractTableModel):
    HEADERS = ("Título de la canción", "Duración")
    total_changed = pyqtSignal(float)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.items: list[PlaylistItem] = []
        self.current_index = -1
        self.next_index = -1
        self._current_item: PlaylistItem | None = None
        self._next_item: PlaylistItem | None = None
        self._probe = ProbeSignals(self)
        self._probe.probed.connect(self._on_probed)
        self._pool = QThreadPool.globalInstance()

    # ---------------------------------------------------------------- Qt API
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 2

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:
                return f"{item.glyph}  {item.title}"
            return fmt_mmss_tenths(item.duration) if item.duration > 0 else "--:--"
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 1:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role in (Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole):
            row = index.row()
            is_bg = role == Qt.ItemDataRole.BackgroundRole
            if row == self.current_index:
                return QColor(C.COLOR_PLAYING_BG if is_bg else C.COLOR_PLAYING_FG)
            if row == self.next_index:
                return QColor(C.COLOR_NEXT_BG if is_bg else C.COLOR_NEXT_FG)
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.HEADERS[section]
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.isValid():
            return base | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        return base | Qt.ItemFlag.ItemIsDropEnabled

    # ----------------------------------------------------------- drag & drop
    def supportedDropActions(self):
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def mimeTypes(self):
        return ["text/uri-list"]

    def canDropMimeData(self, data, action, row, col, parent):
        return data.hasUrls()

    def dropMimeData(self, data, action, row, col, parent):
        if not data.hasUrls():
            return False
        if row >= 0:
            at = row
        elif parent.isValid():
            at = parent.row()
        else:
            at = len(self.items)
        paths = [u.toLocalFile() for u in data.urls() if u.isLocalFile()]
        self.add_paths(paths, at)
        return True

    # -------------------------------------------------------------- mutación
    def add_paths(self, paths, at_row: int | None = None) -> int:
        """Inserta archivos (o el contenido de audio de una carpeta). Devuelve cuántos."""
        expanded: list[str] = []
        for p in paths:
            pp = Path(p)
            if pp.is_dir():
                for f in sorted(pp.iterdir()):
                    if f.is_file() and is_audio(str(f)):
                        expanded.append(str(f))
            elif is_audio(p):
                expanded.append(p)
        if not expanded:
            return 0
        at = len(self.items) if at_row is None or at_row < 0 else min(at_row, len(self.items))
        new_items = [PlaylistItem(path=p) for p in expanded]
        self.beginInsertRows(QModelIndex(), at, at + len(new_items) - 1)
        self.items[at:at] = new_items
        self.endInsertRows()
        self._recompute_markers()
        for it in new_items:
            self._pool.start(ProbeTask(it.path, self._probe))
        self._emit_total()
        return len(new_items)

    def insert_item(self, item: PlaylistItem, at_row: int | None = None) -> int:
        """Inserta un ítem ya construido (especial o pista). Devuelve su posición."""
        at = len(self.items) if at_row is None or at_row < 0 else min(at_row, len(self.items))
        self.beginInsertRows(QModelIndex(), at, at)
        self.items.insert(at, item)
        self.endInsertRows()
        self._recompute_markers()
        if item.type == ItemType.TRACK and item.duration <= 0 and item.path:
            self._pool.start(ProbeTask(item.path, self._probe))
        self._emit_total()
        return at

    def add_random_folder(self, folder: str, at_row: int | None = None) -> int:
        """Añade una carpeta como ítem 'rotativa' (pista al azar en cada pasada)."""
        item = PlaylistItem(path=folder, title=f"[Aleatoria] {Path(folder).name}",
                            type=ItemType.RANDOM)
        return self.insert_item(item, at_row)

    def add_special(self, item_type: ItemType, at_row: int | None = None,
                    seconds: int = 0) -> int:
        """Añade un comando especial: STOP, PAUSE(seconds), TIME, TEMPERATURE, HUMIDITY."""
        if item_type == ItemType.PAUSE:
            item = PlaylistItem(title=f"Pausa {seconds}s", duration=float(seconds),
                                type=ItemType.PAUSE, meta={"seconds": seconds})
        else:
            item = PlaylistItem(title=_SPECIAL_TITLES.get(item_type, item_type.value),
                                type=item_type)
        return self.insert_item(item, at_row)

    def set_items(self, items) -> None:
        """Reemplaza toda la lista (p. ej. al cargar un .lst) y sondea duraciones."""
        self.beginResetModel()
        self.items = list(items)
        self._current_item = self._next_item = None
        self.current_index = self.next_index = -1
        self.endResetModel()
        self._recompute_markers()
        for it in self.items:
            if it.type == ItemType.TRACK and it.duration <= 0 and it.path:
                self._pool.start(ProbeTask(it.path, self._probe))
        self._emit_total()

    def remove_rows(self, rows) -> None:
        for r in sorted(set(rows), reverse=True):
            if 0 <= r < len(self.items):
                self.beginRemoveRows(QModelIndex(), r, r)
                del self.items[r]
                self.endRemoveRows()
        self._recompute_markers()
        self._emit_total()

    def clear(self) -> None:
        self.beginResetModel()
        self.items.clear()
        self._current_item = self._next_item = None
        self.current_index = self.next_index = -1
        self.endResetModel()
        self._emit_total()

    def move_row(self, src: int, dst: int) -> int:
        """Mueve una fila; devuelve la nueva posición (para mantener la selección)."""
        if not (0 <= src < len(self.items)) or not (0 <= dst < len(self.items)) or src == dst:
            return src
        self.beginResetModel()
        item = self.items.pop(src)
        self.items.insert(dst, item)
        self.endResetModel()
        self._recompute_markers()
        return dst

    # ----------------------------------------------------------- marcadores
    def set_playing(self, current: int, nxt: int) -> None:
        self._current_item = self.items[current] if 0 <= current < len(self.items) else None
        self._next_item = self.items[nxt] if 0 <= nxt < len(self.items) else None
        self._recompute_markers()

    def _index_of(self, obj) -> int:
        for i, it in enumerate(self.items):
            if it is obj:
                return i
        return -1

    def _recompute_markers(self) -> None:
        self.current_index = self._index_of(self._current_item)
        self.next_index = self._index_of(self._next_item)
        if self.items:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.items) - 1, 1),
                [Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole],
            )

    # --------------------------------------------------------------- helpers
    def total_duration(self) -> float:
        return sum(it.duration for it in self.items)

    def _emit_total(self) -> None:
        self.total_changed.emit(self.total_duration())

    def _on_probed(self, path: str, duration: float) -> None:
        changed = False
        for row, it in enumerate(self.items):
            if it.path == path and it.duration <= 0:
                it.duration = duration
                self.dataChanged.emit(self.index(row, 1), self.index(row, 1),
                                      [Qt.ItemDataRole.DisplayRole])
                changed = True
        if changed:
            self._emit_total()
