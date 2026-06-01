"""
mcp/tools.py — Operaciones de control expuestas a la IA (FASE 7).

`RyoControl` es la fachada que opera sobre el motor / grabador / lista / menciones.
TODOS sus métodos se ejecutan en el HILO DE QT (el servidor MCP los invoca a través
del MainThreadBridge), así que aquí se puede tocar el engine/UI con seguridad.

Diseñado para que JARVIS inyecte cuñas y menciones "full automático".
"""

from __future__ import annotations

from ..playlist.lst_io import load_lst


class RyoControl:
    def __init__(self, engine, recorder, model, mentions, cartwall=None) -> None:
        self.engine = engine
        self.recorder = recorder
        self.model = model
        self.mentions = mentions
        self.cartwall = cartwall

    # --- transporte ---
    def play(self) -> str:
        self.engine.play()
        return "playing"

    def stop(self) -> str:
        self.engine.stop()
        return "stopped"

    def pause(self) -> str:
        self.engine.pause()
        return "toggled"

    def next(self) -> str:
        self.engine.next()
        return "next"

    def play_index(self, index: int) -> str:
        self.engine.play_index(int(index))
        return f"playing #{int(index)}"

    # --- lista / cuñas ---
    def add_track(self, path: str) -> str:
        n = self.model.add_paths([path])
        return f"added {n}"

    def load_list(self, path: str) -> str:
        items = load_lst(path)
        self.model.set_items(items)
        return f"loaded {len(items)}"

    def add_cue(self, slot: int, path: str) -> str:
        self.engine.assign_cart(int(slot), path)
        if self.cartwall is not None:
            from pathlib import Path
            self.cartwall.set_cart(int(slot), Path(path).stem)
        return f"cue {int(slot)} set"

    def fire_cart(self, slot: int) -> str:
        ok = self.engine.fire_cart(int(slot))
        return "fired" if ok else "empty"

    # --- menciones ---
    def set_mention(self, text: str, when: str) -> str:
        self.mentions.add(text, when, source="mcp")
        return "scheduled"

    # --- grabación ---
    def start_recording(self) -> str:
        self.recorder.start()
        return "recording"

    def stop_recording(self) -> str:
        self.recorder.stop()
        return "stopped"

    # --- estado (lectura) ---
    def get_now_playing(self) -> dict:
        i = self.engine.current_index
        items = self.model.items
        title = items[i].title if 0 <= i < len(items) else None
        return {"index": i, "title": title}

    def get_status(self) -> dict:
        return {
            "current_index": self.engine.current_index,
            "next_index": self.engine.next_index,
            "count": len(self.model.items),
            "recording": self.recorder.is_recording(),
            "total_duration": round(self.model.total_duration(), 1),
        }

    def get_playlist(self) -> list:
        return [
            {"index": k, "title": it.title, "type": it.type.value, "duration": round(it.duration, 1)}
            for k, it in enumerate(self.model.items)
        ]
