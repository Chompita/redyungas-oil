"""
REDYUNGAS OIL — Carga y guardado de configuración (TOML).

La config define el perfil de operación (estudio/esclava/standalone), rutas,
puertos, umbrales y los datos de los adaptadores opcionales (Telegram, JARVIS).
Se lee con `tomllib` (nativo en Python 3.11+) y se escribe con `tomli_w`.

Punto de entrada: `load_config()` devuelve un dict con los valores efectivos
(defaults fusionados con el archivo del usuario).

>>> NOTA IA: los adaptadores (telegram/jarvis) están aquí pero VACÍOS por
    defecto -> el software funciona standalone sin tocar JARVIS. Se activan
    rellenando esta config. <<<
"""

from __future__ import annotations

import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any

import tomli_w

from . import constants as C

# Ubicación por defecto del config del usuario (junto al proyecto).
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .../RED YUNGAS OIL
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.toml"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.example.toml"

# Valores por defecto (espejo de config.example.toml; única fuente de defaults).
DEFAULTS: dict[str, Any] = {
    "general": {
        "profile": C.PROFILE_STANDALONE,   # estudio | esclava | standalone
        "station_name": "Red Yungas",
        "language": "es",
    },
    "paths": {
        "music_root": str(Path.home()),
        "emergency_folder": "",      # carpeta de emergencia (failover por silencio)
        "recordings_folder": str(PROJECT_ROOT / "grabaciones"),
        "logs_folder": str(PROJECT_ROOT / "logs"),
    },
    "audio": {
        "crossfade_ms": C.CROSSFADE_MS,
        "output_device": "",         # "" = dispositivo por defecto del SO
    },
    "network": {
        # Receptor (perfil esclava): de dónde se escucha la señal del estudio.
        "stream_url": "http://stream.example.com:8032/",
        "reconnect_timeout_s": C.RECONNECT_TIMEOUT_S,
        "silence_timeout_s": C.SILENCE_TIMEOUT_S,
        "stall_seconds": 8,          # señal "congelada" antes de declararla caída
        "offline_folder": "",        # carpeta de cuñas para el protocolo offline (PUBLI H:MM)
        # Emisor (perfil estudio): a dónde se empuja la señal.
        "icecast_host": "stream.example.com",
        "icecast_port": C.DEFAULT_ICECAST_PORT,
        "icecast_mount": "/live",
        "icecast_password": "",      # se rellena en cada despliegue
        "icecast_bitrate": 128,      # kbps del MP3 emitido
        "capture_device": "",        # "" = auto (monitor del sink); o "pulse:..."/"dshow:audio=..."
    },
    # --- Emisor público estilo Opticodec (panel "PUERTO") ---
    # Reemplaza a Orban Opticodec-PC: empuja el bus de programa al SHOUTcast público.
    "stream": {
        "enabled": False,
        "server_type": "shoutcast",   # shoutcast | icecast
        "host": "stream.example.com",
        "port": C.DEFAULT_ICECAST_PORT,   # 8032
        "mount": "/stream",          # SHOUTcast v2: punto de montaje del source
        "user": "source",
        "password": "",              # se rellena en config.toml por despliegue (NO al repo)
        "bitrate": 128,              # kbps
        "codec": "mp3",              # mp3 (compatible) | aac (LC). HE-AAC pide libfdk_aac.
        "sample_rate": 44100,
        "channels": 2,
        "gain_db": 0.0,              # ganancia/saturación independiente del volumen de playout
        "stream_name": "RED YUNGAS",
        "genre": "Various",
        "website": "http://www.redyungas.com.bo",
        "description": "Hi-Fi Internet Audio",
        "connect_on_start": False,   # emitir automáticamente al arrancar
    },
    "recording": {
        "segment_seconds": C.RECORDING_SEGMENT_S,   # 30 min
        "format": "mp3",
        "bitrate": 192,
        "send_to_jarvis": False,
    },
    "mcp": {
        "enabled": False,
        "host": "127.0.0.1",         # en producción: IP Tailscale 100.x
        "port": C.DEFAULT_MCP_PORT,
        "token": "",                 # token obligatorio si enabled=True
    },
    "rest": {
        "enabled": False,
        "host": "127.0.0.1",
        "port": C.DEFAULT_REST_PORT,
        "token": "",
    },
    # --- Adaptadores opcionales hacia JARVIS (vacíos = desacoplado) ---
    "telegram": {
        "enabled": False,
        "bot_token": "",             # token del bot MARCUS (o el que se use)
        "chat_id": "",               # ej. operador ***REMOVED***
    },
    "jarvis": {
        "enabled": False,
        # Modo de entrega de grabaciones: "api" (POST) o "folder" (carpeta vigilada).
        "delivery_mode": "folder",
        "transcription_api": "http://127.0.0.1:9120/api/transcription/jobs",
        "watch_folder": "",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Fusiona `override` sobre `base` de forma recursiva (no muta `base`)."""
    out = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    """Carga la config del usuario fusionada con los defaults.

    Si el archivo no existe, devuelve los defaults (modo standalone).
    """
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if cfg_path.exists():
        with cfg_path.open("rb") as fh:
            user_cfg = tomllib.load(fh)
        return _deep_merge(DEFAULTS, user_cfg)
    return deepcopy(DEFAULTS)


def save_config(config: dict[str, Any], path: Path | str | None = None) -> Path:
    """Guarda la config en TOML y devuelve la ruta escrita."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("wb") as fh:
        tomli_w.dump(config, fh)
    return cfg_path
