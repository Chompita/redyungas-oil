"""
ui/widgets/file_tree.py — Explorador de carpetas (réplica ZaraRadio).

QTreeView sobre QFileSystemModel mostrando el árbol de carpetas del usuario, con
las carpetas conocidas (Inicio, Descargas, Documentos, Escritorio, Imágenes,
Música, Vídeos). En Fase 2 será origen de drag & drop hacia la lista.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QDir
from PyQt6.QtGui import QFileSystemModel
from PyQt6.QtWidgets import QTreeView


class FileTree(QTreeView):
    def __init__(self, root_path: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("fileTree")
        model = QFileSystemModel(self)
        root = root_path or str(Path.home())
        model.setRootPath(root)
        model.setFilter(QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot)
        self.setModel(model)
        self.setRootIndex(model.index(root))
        # Solo el nombre (ocultar tamaño/tipo/fecha) para parecerse a ZaraRadio.
        for col in range(1, model.columnCount()):
            self.hideColumn(col)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)            # Fase 2: drag&drop a la lista
        self.setAnimated(False)
        self.setIndentation(14)
