# Empaquetado y despliegue — REDYUNGAS OIL (Fase 8)

## Desarrollo (Linux, esta máquina)
```bash
cd "/home/redyungas/RED YUNGAS OIL"
source .venv/bin/activate
python -m redyungas_oil            # arranca la app
```
El look Windows 7 se emula con `ui/style/win7.qss`. En Windows sale nativo.

## Build para Windows (en una máquina Windows)
Las 9 esclavas son Windows; el ejecutable se genera EN Windows (PyInstaller no hace
cross-compile).

1. Instalar **Python 3.11+** y **VLC** oficial (64-bit) — aporta libVLC.
2. Crear venv e instalar dependencias:
   ```bat
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r redyungas_oil\requirements.txt
   pip install pyinstaller
   ```
3. (Opcional) si VLC no está en la ruta típica:
   ```bat
   set VLC_DIR=C:\Program Files\VideoLAN\VLC
   ```
4. Empaquetar:
   ```bat
   pyinstaller redyungas_oil\packaging\redyungas_oil.spec
   ```
   Resultado: `dist\REDYUNGAS OIL\REDYUNGAS OIL.exe` (carpeta autocontenida con libVLC).

## Requisitos extra en cada esclava
- **ffmpeg** en el PATH (grabación y emisión). Incluir `ffmpeg.exe` en la carpeta del
  programa o instalarlo en el sistema.
- Para **emitir/grabar** en Windows: un dispositivo de captura de la salida (loopback)
  — p. ej. un cable de audio virtual (VB-Audio) — y configurar en `config.toml`:
  `capture_device = "dshow:audio=CABLE Output (VB-Audio Virtual Cable)"`.
- `espeak-ng` (opcional) para locuciones por TTS, o configurar fragmentos de voz.

## Configuración por emisora
Copiar `redyungas_oil\config.example.toml` a `config.toml` (junto al .exe o en la raíz
del proyecto) y ajustar:
- `[general].profile`: `estudio` (la que emite) o `esclava` (las que reciben).
- `[network].stream_url` (esclava) e `icecast_*` (estudio).
- `[network].offline_folder`: carpeta de cuñas para el protocolo offline.
- `[telegram]`, `[jarvis]`, `[mcp]` según se quiera conectar a JARVIS / control IA.

## Despliegue a las esclavas (Tailscale)
Copiar la carpeta `dist\REDYUNGAS OIL\` + su `config.toml` a cada PC (SCP/robocopy por
Tailscale, como ya hace el agente-red-yungas). Crear acceso directo / inicio automático.
El control remoto por MCP debe ir SIEMPRE por la IP Tailscale (100.x) + token.
