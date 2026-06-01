"""
REDYUNGAS OIL — Constantes globales (única fuente de verdad).

Aquí vive todo lo que se comparte entre módulos: branding, versión, estructura
de menús (réplica de ZaraRadio v1.6.2), colores de la lista, puertos por defecto
y umbrales de operación. NO poner lógica aquí, solo datos.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Identidad / branding  (el "disfraz" cambia ZaraRadio -> REDYUNGAS OIL)
# ---------------------------------------------------------------------------
APP_NAME = "REDYUNGAS OIL"
APP_VERSION = "1.1.1"           # v1.1.1 — sintonizador "Recibir señal" + config junto al .exe
APP_TITLE_DEFAULT = "Sin título 1"   # equivalente a "SinTítulo1" de ZaraRadio
ORG_NAME = "Red Yungas"

# ---------------------------------------------------------------------------
# Perfiles de operación
# ---------------------------------------------------------------------------
PROFILE_ESTUDIO = "estudio"      # emite señal hacia Icecast
PROFILE_ESCLAVA = "esclava"      # recibe señal + failover offline
PROFILE_STANDALONE = "standalone"  # playout local sin red
PROFILES = (PROFILE_ESTUDIO, PROFILE_ESCLAVA, PROFILE_STANDALONE)

# ---------------------------------------------------------------------------
# Colores de la lista de reproducción (ver capturas de ZaraRadio)
#   fila roja  = pista sonando ahora
#   fila verde = pista siguiente
# ---------------------------------------------------------------------------
COLOR_PLAYING_BG = "#FF0000"
COLOR_PLAYING_FG = "#FFFFFF"
COLOR_NEXT_BG = "#1FA01F"
COLOR_NEXT_FG = "#FFFFFF"
COLOR_VU_GREEN = "#22B14C"

# ---------------------------------------------------------------------------
# Estructura de menús — réplica EXACTA de ZaraRadio v1.6.2.
# Cada entrada: (etiqueta, atajo|None, action_id|None|"-" para separador).
# Las capturas 1..10 documentan cada submenú. Las acciones se conectan en Fase 1+.
# ---------------------------------------------------------------------------
MENUS = {
    "Archivo": [
        ("Nuevo", "Ctrl+N", "file.new"),
        ("Abrir...", "Ctrl+O", "file.open"),
        ("Guardar", "Ctrl+S", "file.save"),
        ("Guardar como...", None, "file.save_as"),
        ("-", None, None),
        ("Archivos recientes", None, "file.recent"),
        ("-", None, None),
        ("Salir", "Alt+F4", "file.quit"),
    ],
    "Edición": [
        ("Copiar", "Ctrl+C", "edit.copy"),
        ("Pegar", "Ctrl+V", "edit.paste"),
        ("Eliminar", "Del", "edit.delete"),
        ("-", None, None),
        ("Eliminar todo", "Ctrl+Del", "edit.delete_all"),
        ("-", None, None),
        ("Buscar...", "Ctrl+F", "edit.find"),
        ("Buscar en carpetas...", "Shift+Ctrl+F", "edit.find_folders"),
    ],
    "Ver": [
        ("Ruta completa", None, "view.full_path"),
        ("Fuente de la lista...", None, "view.list_font"),
        ("Cabecera en la lista", None, "view.header"),       # checkable
        ("Números de canciones", None, "view.song_numbers"),  # checkable
        ("-", None, None),
        ("Información del tiempo", None, "view.time_info"),    # checkable
        ("-", None, None),
        ("Actualizar árbol", None, "view.refresh_tree"),
    ],
    "Cuñas": [
        # 9 slots de cuñas (cartwall) + locuciones. Se generan dinámicos en Fase 1.
        ("Locución de hora", "H", "cue.time"),
        ("Temperatura", None, "cue.temperature"),
        ("Humedad", None, "cue.humidity"),
        ("-", None, None),
        ("Editar cuñas...", None, "cue.edit"),
    ],
    "Lista": [
        ("Añadir pistas...", "Ctrl+A", "list.add_tracks"),
        ("Añadir comando stop", "Ctrl+T", "list.add_stop"),
        ("Añadir locución de hora", "Ctrl+H", "list.add_time"),
        ("Añadir locución de temperatura", None, "list.add_temp"),
        ("Añadir locución de humedad", None, "list.add_humidity"),
        ("Añadir pista aleatoria...", None, "list.add_random"),
        ("Añadir pausa...", None, "list.add_pause"),
        ("Añadir satélite...", None, "list.add_satellite"),
        ("Añadir conexión de satélite", None, "list.sat_connect"),
        ("Añadir desconexión del satélite", None, "list.sat_disconnect"),
        ("Añadir activación de DTMF", None, "list.dtmf_on"),
        ("Añadir desactivación de DTMF", None, "list.dtmf_off"),
        ("Añadir radio de internet...", None, "list.add_internet_radio"),
        ("-", None, None),
        ("Barajar", "Ctrl+K", "list.shuffle"),
        ("Cue", "Ctrl+P", "list.cue"),
        ("-", None, None),
        ("Ver la duración de la selección...", "Ctrl+L", "list.selection_duration"),
        ("Actualizar duración", "Ctrl+U", "list.update_duration"),
        ("Actualizar todas las duraciones", None, "list.update_all_durations"),
    ],
    "Media": [
        ("Reproducir", "P", "media.play"),
        ("Parar", "S", "media.stop"),
        ("Siguiente", "N", "media.next"),
        ("Pisador", "T", "media.voiceover"),
        ("Parar tras la actual", "B", "media.stop_after"),
        ("-", None, None),
        ("Recibir señal...", "R", "media.tune"),
        ("-", None, None),
        ("Renombrar", "F2", "media.rename"),
    ],
    "Herramientas": [
        ("Mezclador...", "X", "tools.mixer"),
        ("Reproductores auxiliares", None, "tools.aux_players"),  # submenu
        ("Explorador del registro...", None, "tools.log_explorer"),
        ("Editor de pisadores...", None, "tools.voiceover_editor"),
        ("-", None, None),
        ("Opciones...", "O", "tools.options"),
    ],
    "Programas": [
        ("Fichero log de hoy", None, "logs.today"),
        ("Abrir carpeta de log", None, "logs.open_folder"),
        ("-", None, None),
        ("Editar...", None, "logs.edit"),
    ],
    "Ayuda": [
        ("Contenidos...", "F1", "help.contents"),
        ("Sugerencia del día", None, "help.tip"),
        ("-", None, None),
        ("Buscar actualizaciones...", None, "help.update"),
        ("-", None, None),
        ("Acerca de REDYUNGAS OIL", None, "help.about"),
    ],
}
MENU_ORDER = list(MENUS.keys())

# Número de slots del cartwall (ZaraRadio v1.6.2 muestra 9, ver capturas).
CARTWALL_SLOTS = 9

# ---------------------------------------------------------------------------
# Puertos por defecto (configurables en config.toml). Se enlazan a Tailscale.
# ---------------------------------------------------------------------------
DEFAULT_MCP_PORT = 8770          # servidor MCP (control IA) HTTP/SSE
DEFAULT_REST_PORT = 8771         # REST interno: menciones, cuñas, health
DEFAULT_ICECAST_PORT = 8032      # servidor de stream remoto (externo)

# ---------------------------------------------------------------------------
# Medidor del emisor (panel "PUERTO", estilo Opticodec). Escala en dBFS.
# Opticodec muestra de -30 a 0 dB; el riel pinta hasta -40 para dar margen.
# ---------------------------------------------------------------------------
STREAM_VU_MIN_DB = -40.0         # extremo izquierdo del riel (silencio)
STREAM_VU_MAX_DB = 0.0           # extremo derecho (saturación / clip)
STREAM_VU_TICKS = (-30, -24, -18, -12, -6, 0)   # marcas como en Opticodec
STREAM_GAIN_MIN_DB = -24.0       # rango del control de saturación independiente
STREAM_GAIN_MAX_DB = 12.0

# ---------------------------------------------------------------------------
# Umbrales de operación por defecto (segundos). Configurables.
# ---------------------------------------------------------------------------
RECONNECT_TIMEOUT_S = 15         # reintento de reconexión al caer la señal
SILENCE_TIMEOUT_S = 7            # silencio antes de saltar a emergencia
RECORDING_SEGMENT_S = 1800       # corte de grabación cada 30 minutos
CROSSFADE_MS = 3000              # duración del fundido por defecto
