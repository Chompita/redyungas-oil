"""
playlist/lst_io.py — Import/Export de listas .lst (FASE 3).

Objetivo principal: que los locutores reusen sus listas existentes (ZaraRadio
guarda listas como texto con una ruta por línea). Leemos eso y, además, nuestros
propios marcadores para ítems especiales (@STOP, @PAUSE:n, @TIME, @TEMP, @HUM).

Limitación: los tokens de comando exactos de ZaraRadio no están estandarizados
aquí; las rutas de audio/carpeta sí son 100% compatibles (lo que importa para
reutilizar listas). ZaraRadio ignoraría nuestros marcadores como pistas perdidas.
"""

from __future__ import annotations

from pathlib import Path

from .item_types import ItemType, PlaylistItem, is_audio

_MARKERS = {
    "@STOP": ItemType.STOP,
    "@TIME": ItemType.TIME,
    "@TEMP": ItemType.TEMPERATURE,
    "@HUM": ItemType.HUMIDITY,
}
_TITLES = {
    ItemType.STOP: "Comando stop",
    ItemType.TIME: "Locución de hora",
    ItemType.TEMPERATURE: "Locución de temperatura",
    ItemType.HUMIDITY: "Locución de humedad",
}


def _read_text(path: str | Path) -> str:
    data = Path(path).read_bytes()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def load_lst(path: str | Path) -> list[PlaylistItem]:
    items: list[PlaylistItem] = []
    for raw in _read_text(path).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.upper().startswith("@PAUSE:"):
            try:
                secs = int(line.split(":", 1)[1])
            except ValueError:
                secs = 3
            items.append(PlaylistItem(title=f"Pausa {secs}s", duration=float(secs),
                                      type=ItemType.PAUSE, meta={"seconds": secs}))
            continue
        marker = _MARKERS.get(line.upper())
        if marker:
            items.append(PlaylistItem(title=_TITLES[marker], type=marker))
            continue
        p = Path(line)
        if p.is_dir():
            items.append(PlaylistItem(path=line, title=f"[Aleatoria] {p.name}",
                                      type=ItemType.RANDOM))
        elif is_audio(line):
            items.append(PlaylistItem(path=line, type=ItemType.TRACK))
    return items


def save_lst(items: list[PlaylistItem], path: str | Path) -> None:
    lines: list[str] = []
    for it in items:
        if it.type in (ItemType.TRACK, ItemType.RANDOM):
            lines.append(it.path)
        elif it.type == ItemType.PAUSE:
            lines.append(f"@PAUSE:{int(it.meta.get('seconds', it.duration or 3))}")
        elif it.type == ItemType.STOP:
            lines.append("@STOP")
        elif it.type == ItemType.TIME:
            lines.append("@TIME")
        elif it.type == ItemType.TEMPERATURE:
            lines.append("@TEMP")
        elif it.type == ItemType.HUMIDITY:
            lines.append("@HUM")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
