"""
playlist/item_types.py — Tipos de ítem de la lista, estilo ZaraRadio.

ItemType enumera los tipos (ver menú "Lista" en las capturas). PlaylistItem es la
estructura concreta que guarda cada fila. El motor de audio decide cómo reproducir
cada tipo. En Fase 2 se usa sobre todo TRACK; los demás se completan en Fase 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

AUDIO_EXTS = {
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac",
    ".wma", ".opus", ".aif", ".aiff",
}


def is_audio(path: str) -> bool:
    return Path(path).suffix.lower() in AUDIO_EXTS


class ItemType(str, Enum):
    TRACK = "track"              # pista de audio normal
    RANDOM = "random"           # rotativa: una pista al azar de una carpeta (Fase 3)
    STOP = "stop"               # comando stop
    PAUSE = "pause"             # pausa de N segundos
    TIME = "time"               # locución de hora
    TEMPERATURE = "temperature"  # locución de temperatura
    HUMIDITY = "humidity"       # locución de humedad
    SATELLITE = "satellite"     # conexión/desconexión de satélite
    INTERNET_RADIO = "internet_radio"  # radio de internet (stream)


# Glifo por tipo para la columna Título (réplica del icono de ZaraRadio).
TYPE_GLYPH = {
    ItemType.TRACK: "♪",
    ItemType.RANDOM: "🎲",
    ItemType.STOP: "⏹",
    ItemType.PAUSE: "⏸",
    ItemType.TIME: "🕓",
    ItemType.TEMPERATURE: "🌡",
    ItemType.HUMIDITY: "☁",
    ItemType.SATELLITE: "🛰",
    ItemType.INTERNET_RADIO: "📡",
}


@dataclass
class PlaylistItem:
    path: str = ""
    title: str = ""
    duration: float = 0.0                 # segundos; 0 = aún no sondeada
    type: ItemType = ItemType.TRACK
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title:
            self.title = Path(self.path).stem if self.path else self.type.value

    @property
    def glyph(self) -> str:
        return TYPE_GLYPH.get(self.type, "♪")
