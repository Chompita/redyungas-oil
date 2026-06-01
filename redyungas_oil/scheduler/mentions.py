"""
scheduler/mentions.py — Menciones programadas que "brillan" (FASE 7).

Gestiona el texto de menciones con su horario. Un QTimer de 1 s comprueba cuándo
llega la hora de cada mención y emite `mention_due`, para que la ventana de
menciones (ui/widgets/mentions_window.py) ILUMINE esa fila y el locutor la lea.

Las menciones entran desde JARVIS/Telegram (Fase 7) vía el servidor MCP
(tool `set_mention`) o el endpoint REST `/mention`. Hora en "HH:MM" o "HH:MM:SS".
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject, QTime, QTimer, pyqtSignal


@dataclass
class Mention:
    text: str
    when: str            # "HH:MM" o "HH:MM:SS"
    source: str = ""     # "telegram" | "jarvis" | "mcp" | "manual"
    read: bool = False


class MentionManager(QObject):
    mention_added = pyqtSignal(object)   # Mention
    mention_due = pyqtSignal(object)     # Mention

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.mentions: list[Mention] = []
        self._fired: dict[int, str] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(1000)

    def add(self, text: str, when: str, source: str = "manual") -> Mention:
        m = Mention(text=text, when=when.strip(), source=source)
        self.mentions.append(m)
        self.mention_added.emit(m)
        return m

    def mark_read(self, index: int) -> None:
        if 0 <= index < len(self.mentions):
            self.mentions[index].read = True

    def _check(self) -> None:
        now = QTime.currentTime().toString("HH:mm:ss")
        for m in self.mentions:
            if m.read:
                continue
            matches = (now == m.when) or (len(m.when) == 5 and now[:5] == m.when)
            if matches and self._fired.get(id(m)) != m.when:
                self._fired[id(m)] = m.when
                self.mention_due.emit(m)
