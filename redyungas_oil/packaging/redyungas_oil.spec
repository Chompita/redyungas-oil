# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
#  PyInstaller spec — REDYUNGAS OIL (FASE 8). Empaquetado para esclavas Windows.
#
#  Lo delicado: incluir el runtime de libVLC (libvlc.dll, libvlccore.dll y la
#  carpeta de plugins) y los recursos. Este spec intenta localizar VLC en la
#  máquina de build (variable de entorno VLC_DIR o rutas típicas de Windows).
#
#  Uso (en Windows, dentro del venv, desde la raíz "RED YUNGAS OIL"):
#      pip install pyinstaller
#      set VLC_DIR=C:\Program Files\VideoLAN\VLC      (si VLC no está en la ruta típica)
#      pyinstaller redyungas_oil\packaging\redyungas_oil.spec
#  El resultado queda en dist\REDYUNGAS OIL\.
# ============================================================================

import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))     # .../RED YUNGAS OIL
PKG = os.path.join(ROOT, "redyungas_oil")

# --- Recursos propios ---
datas = [
    (os.path.join(PKG, "ui", "style", "win7.qss"), "redyungas_oil/ui/style"),
    (os.path.join(PKG, "resources", "branding"), "redyungas_oil/resources/branding"),
    (os.path.join(PKG, "config.example.toml"), "redyungas_oil"),
]
binaries = []

# --- Runtime de libVLC (solo Windows) ---
def _find_vlc():
    candidates = [os.environ.get("VLC_DIR", "")]
    candidates += [
        r"C:\Program Files\VideoLAN\VLC",
        r"C:\Program Files (x86)\VideoLAN\VLC",
    ]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "libvlc.dll")):
            return c
    return None

if sys.platform.startswith("win"):
    vlc_dir = _find_vlc()
    if vlc_dir:
        for dll in ("libvlc.dll", "libvlccore.dll"):
            binaries.append((os.path.join(vlc_dir, dll), "."))
        plugins = os.path.join(vlc_dir, "plugins")
        if os.path.isdir(plugins):
            datas.append((plugins, "plugins"))
    else:
        print("AVISO: no se encontró VLC; define VLC_DIR. El empaquetado puede no "
              "reproducir audio sin libVLC.")

hiddenimports = [
    "vlc",
    "uvicorn", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols",
    "anyio", "starlette",
]

block_cipher = None

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[os.path.join(SPECPATH, "rthook_vlc.py")],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="REDYUNGAS OIL",
    console=False,
    icon=None,   # FASE 8+: icono .ico propio
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    name="REDYUNGAS OIL",
)
