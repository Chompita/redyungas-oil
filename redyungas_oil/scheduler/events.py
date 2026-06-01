"""
scheduler/events.py — Programador de eventos (FASE 3).

Dispara acciones a una hora exacta del día (ej. 10:00:00), igual que el módulo de
eventos de ZaraRadio, y alimenta el panel "Eventos próximos".

Implementado sobre un QTimer de 1 s (granularidad de segundos) en el hilo Qt: es
simple y 100% thread-safe con la UI (evita la complejidad de hilos de APScheduler).
Cada evento es diario (se repite cada día a su hora).
"""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QDateTime, QObject, QTime, QTimer, pyqtSignal


@dataclass
class Event:
    time: str                 # "HH:MM:SS"
    action: str               # "play_file" | "stop" | "load_list"
    target: str = ""          # ruta del archivo/lista (según acción)
    label: str = ""           # texto a mostrar
    enabled: bool = True


class EventScheduler(QObject):
    event_due = pyqtSignal(object)     # Event
    events_changed = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.events: list[Event] = []
        self._last_fired: dict[int, str] = {}
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check)
        self._timer.start(1000)

    # --------------------------------------------------------------- gestión
    def add_event(self, event: Event) -> None:
        self.events.append(event)
        self.events_changed.emit()

    def remove_event(self, index: int) -> None:
        if 0 <= index < len(self.events):
            del self.events[index]
            self.events_changed.emit()

    def clear(self) -> None:
        self.events.clear()
        self.events_changed.emit()

    # ----------------------------------------------------------------- disparo
    def _check(self) -> None:
        now = QTime.currentTime().toString("HH:mm:ss")
        for ev in self.events:
            if not ev.enabled:
                continue
            if ev.time == now and self._last_fired.get(id(ev)) != now:
                self._last_fired[id(ev)] = now
                self.event_due.emit(ev)

    # ----------------------------------------------------------------- próximos
    def upcoming(self, limit: int = 20) -> list[tuple[QDateTime, Event]]:
        """Lista ordenada de (próxima ocurrencia, evento) para el panel."""
        now = QDateTime.currentDateTime()
        out: list[tuple[QDateTime, Event]] = []
        for ev in self.events:
            if not ev.enabled:
                continue
            t = QTime.fromString(ev.time, "HH:mm:ss")
            if not t.isValid():
                continue
            dt = QDateTime(now.date(), t)
            if dt < now:
                dt = dt.addDays(1)
            out.append((dt, ev))
        out.sort(key=lambda pair: pair[0])
        return out[:limit]
