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

try:                          # Python 3.11+ trae tomllib nativo
    import tomllib
except ModuleNotFoundError:   # Python 3.10 (p. ej. esclavas): respaldo con tomli
    import tomli as tomllib
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import tomli_w

from . import constants as C

# Ubicación del config del usuario:
#  - app empaquetada (.exe PyInstaller): JUNTO al ejecutable (config.toml al lado del .exe).
#  - desarrollo: junto al proyecto ".../RED YUNGAS OIL/config.toml".
PROJECT_ROOT = Path(__file__).resolve().parents[2]   # .../RED YUNGAS OIL
if getattr(sys, "frozen", False):                    # congelado por PyInstaller
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = PROJECT_ROOT
DEFAULT_CONFIG_PATH = BASE_DIR / "config.toml"
EXAMPLE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config.example.toml"

# Valores por defecto (espejo de config.example.toml; única fuente de defaults).
DEFAULTS: dict[str, Any] = {
    "general": {
        "profile": C.PROFILE_STANDALONE,   # estudio | esclava | standalone
        "station_name": "Red Yungas",
        "language": "es",
        "currentsong_folder": "",          # carpeta de salida del fichero 'CurrentSong'
        "autostart": False,                # activar autoarranque
        "agc": False,                      # activar AGC
        "allow_multiple": True,            # permitir abrir más de una instancia
        "disable_events_secondary": True,  # desactivar eventos en instancias secundarias
        "open_last_list": True,            # abrir la última lista al arrancar
        "confirm_close": False,            # confirmación de cierre
        "double_click_play": True,         # reproducir con doble clic
    },
    "paths": {
        "music_root": str(Path.home()),
        "emergency_folder": "",      # carpeta de emergencia (failover por silencio)
        "recordings_folder": str(PROJECT_ROOT / "grabaciones"),
        "logs_folder": str(PROJECT_ROOT / "logs"),
        "ffmpeg": "",                # ruta a ffmpeg (vacío = autodetectar/PATH)
        "ffprobe": "",               # ruta a ffprobe (vacío = autodetectar/PATH)
    },
    "audio": {
        # Motor de audio: "sounddevice" (un solo grafo, mezcla en numpy, sin tartamudeo
        # al solapar) o "vlc" (el clásico). En la rama audio-pro por defecto sounddevice.
        "engine": "sounddevice",
        "crossfade_ms": C.CROSSFADE_MS,            # solape MANUAL (Reproducir/click derecho)
        "auto_crossfade_ms": C.AUTO_CROSSFADE_MS,  # avance AUTOMÁTICO: empieza 1,75 s antes de acabar
        "fade_in_ms": C.FADE_IN_MS,  # fundido de entrada al Reproducir/click derecho (0 = sin fundido)
        "duck_ms": C.DUCK_MS,        # rapidez del pisador (bajar/subir música suave)
        "samplerate": 44100,
        "blocksize": 1024,           # tamaño de bloque del motor sounddevice (latencia/estabilidad)
        "output_device": "",         # "" = dispositivo por defecto del SO (Salida de emisión)
        "cue_device": "",            # salida de CUE (pre-escucha)
        "duck_level": C.DUCK_LEVEL,  # volumen de locución del pisador (0..1)
        "fade_on_overlap": True,     # "Fundido al solapar"
        "fade_on_stop": True,        # "Fundido al parar"
        "detect_end": True,          # "Detectar fin de canción"
        "detect_end_db": -26,        # umbral del detector de fin (dB)
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
        "capture_device": "",        # "" = auto. Windows: "dshow:audio=Mezcla estéreo (Realtek(R) Audio)"
        "gain_db": 0.0,              # ganancia/saturación independiente del volumen de playout
        "stream_name": "RED YUNGAS",
        "genre": "Various",
        "website": "http://www.redyungas.com.bo",
        "description": "Hi-Fi Internet Audio",
        "connect_on_start": False,   # emitir automáticamente al arrancar
    },
    # --- Micrófono del locutor + auto-ducking profesional (reemplaza el clima) ---
    # Cuando el locutor habla, baja AUTOMÁTICAMENTE la música (planilla principal,
    # auxiliar y cuñas) como en las radios profesionales, y vuelve a subir al callar.
    "mic": {
        "enabled": False,
        "device": "",                # "" = entrada por defecto del SO
        "to_air": False,             # mezclar la voz del mic en la salida (al aire)
        "threshold_db": -38.0,       # nivel a partir del cual se considera "hablando"
        "attack_ms": 120,            # rapidez en bajar la música al detectar voz
        "release_ms": 700,           # espera antes de volver a subir tras callar
        "duck_main": 0.30,           # nivel al que baja la planilla PRINCIPAL (0..1)
        "duck_aux": 0.40,            # nivel al que baja la planilla AUXILIAR (0..1)
        "duck_carts": 0.50,          # nivel al que bajan las CUÑAS (0..1)
        "mic_gain_db": 0.0,          # ganancia de la voz si se manda al aire
    },
    # --- Secciones del diálogo de Opciones (réplica ZaraRadio) ---
    "silence": {                     # Detector de silencio
        "enabled": True,
        "period_s": 15,
    },
    "security": {                    # Contraseña (proteger diálogos)
        "enabled": False,
        "password": "",
        "protect_events": True,
        "discard_pending": False,
        "play_pending_manual": False,
        "protect_options": True,
        "protect_enable_events": True,
    },
    "mixer": {                       # Aplicación mezcladora externa
        "app": "",
    },
    "hth": {                         # Temperatura / Humedad para locuciones
        "temperature": 0,
        "humidity": 0,
        "import_enabled": False,
        "import_file": "",
        "disable_after_min": 60,
        "disable_after_enabled": False,
        "units": "Celsius",          # Celsius | Fahrenheit
    },
    "dtmf": {                        # Detector de tonos DTMF
        "enabled": False,
        "disconnect_tones": "",
        "disconnect_action": "Reproducir los eventos pendientes",
        "connect_mode": "manual",    # tone | delay | manual
        "connect_tone": "",
        "connect_delay_s": 0,
    },
    "explorer": {                    # Explorador de ficheros (árbol)
        "root": "",
        "special_folder": "Escritorio",
        "use_special": True,
        "extensions": ["WAV", "MP3", "OGG", "WMA"],
    },
    "tags": {                        # Tags en la lista
        "enabled": False,
        "format": "%TITL - %ARTI",
    },
    "satellite": {                   # Entrada de satélite
        "input_device": "",
    },
    "outputs": {                     # Salidas de reproductores auxiliares
        "aux1": "", "aux2": "", "aux3": "", "aux4": "",
    },
    "recording": {
        "segment_seconds": C.RECORDING_SEGMENT_S,   # 30 min
        "format": "mp3",
        "bitrate": 192,
        "send_to_jarvis": False,
    },
    "update": {
        "enabled": True,             # auto-actualización desde el repo privado
        "branch": "master",
        # Por defecto NO se busca al arrancar: las esclavas están EN VIVO de día.
        # La actualización se dispara de noche por Telegram/MARCUS (git pull),
        # o a mano desde Ayuda → Buscar actualizaciones.
        "check_on_start": False,
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
        "chat_id": "",               # ej. el chat_id del operador
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
