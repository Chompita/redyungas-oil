# -*- mode: python ; coding: utf-8 -*-
# ============================================================================
#  PyInstaller spec — REDYUNGAS OIL para LINUX (servidor/estudio Ubuntu).
#
#  A diferencia del de Windows, NO empaqueta libVLC: usa el del sistema
#  (libvlc.so de VLC instalado). ffmpeg también se toma del sistema (PATH).
#  Resultado: dist/redyungas-oil/redyungas-oil (carpeta autocontenida).
#
#  Uso (Linux, dentro del venv, desde la raíz "RED YUNGAS OIL"):
#      pip install pyinstaller
#      pyinstaller redyungas_oil/packaging/redyungas_oil_linux.spec
# ============================================================================

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))     # .../RED YUNGAS OIL
PKG = os.path.join(ROOT, "redyungas_oil")

datas = [
    (os.path.join(PKG, "ui", "style", "win7.qss"), "redyungas_oil/ui/style"),
    (os.path.join(PKG, "resources", "branding"), "redyungas_oil/resources/branding"),
    (os.path.join(PKG, "config.example.toml"), "redyungas_oil"),
]

hiddenimports = [
    "vlc",
    "uvicorn", "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols",
    "anyio", "starlette",
]

block_cipher = None

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[ROOT],
    binaries=[],
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
    name="redyungas-oil",
    console=False,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    name="redyungas-oil",
)
