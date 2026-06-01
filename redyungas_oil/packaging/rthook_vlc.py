"""
Runtime hook de PyInstaller — localiza los plugins de libVLC en el .exe congelado.

Sin esto, `vlc.Instance()` devuelve None (no encuentra los plugins) y el motor de
audio no arranca. Fija `VLC_PLUGIN_PATH` si no está ya definido: en Windows a la
carpeta `plugins` empaquetada (o a la instalación de VLC); en Linux a la ruta del
sistema.
"""

import os
import sys


def _set_plugin_path() -> None:
    if os.environ.get("VLC_PLUGIN_PATH"):
        return
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(os.path.join(meipass, "plugins"))
    exe_dir = os.path.dirname(sys.executable)
    candidates.append(os.path.join(exe_dir, "plugins"))
    if sys.platform.startswith("win"):
        candidates += [
            r"C:\Program Files\VideoLAN\VLC\plugins",
            r"C:\Program Files (x86)\VideoLAN\VLC\plugins",
        ]
    else:
        candidates += [
            "/usr/lib/x86_64-linux-gnu/vlc/plugins",
            "/usr/lib/vlc/plugins",
            "/usr/lib64/vlc/plugins",
            "/usr/local/lib/vlc/plugins",
        ]
    for c in candidates:
        if c and os.path.isdir(c):
            os.environ["VLC_PLUGIN_PATH"] = c
            return


_set_plugin_path()
