# REDYUNGAS OIL

Automatización radial para la red **Red Yungas** (10 PCs por Tailscale: 1 estudio +
9 esclavas Windows). Por fuera es un **clon visual de ZaraRadio v1.6.2** (look
Windows 7) para que locutores y periodistas no sufran curva de aprendizaje; por
dentro es un backend moderno **controlable por IA vía MCP** y Telegram (MARCUS).

> Repositorio **privado** de uso interno. Reemplaza a ZaraRadio (playout) y a
> Orban Opticodec-PC (emisor de stream).

## Qué incluye

- **Playout** estilo ZaraRadio: lista, rotativas, cuñas (cartwall de 9), locuciones,
  pisador/ducking, eventos a hora exacta, crossfade, grabación por segmentos.
- **Panel emisor "PUERTO"** (estilo Opticodec): pestaña vertical en el borde
  derecho que despliega un visualizador de **decibelios L/R en vivo** y un control
  de **volumen/saturación independiente**; emite al **SHOUTcast** público
  (protocolo v1 nativo) o a Icecast2.
- **Red estudio↔esclava**: receptor con watchdog + protocolo offline (cuña de
  publicidad) + avisos por Telegram.
- **MCP**: servidor con herramientas para que la IA (JARVIS / MARCUS) controle el
  playout, lance cuñas/menciones y emita, de forma remota por Tailscale.
- **Auto-actualización** desde este repositorio (ver `core/updater.py`).

## Arranque (desarrollo, Linux)

```bash
cd "RED YUNGAS OIL"
python -m venv .venv && source .venv/bin/activate
pip install -r redyungas_oil/requirements.freeze.txt
python -m redyungas_oil                 # arranca la app
```

## Configuración

Copia `redyungas_oil/config.example.toml` a `config.toml` (en la raíz) y ajusta
perfil, rutas, `[stream]` (SHOUTcast), `[network]`, `[telegram]`, `[jarvis]`,
`[mcp]`. **`config.toml` NO se versiona** (lleva contraseñas/tokens).

## Empaquetado

- **Windows:** `packaging/redyungas_oil.spec` (PyInstaller, en una esclava).
- **Linux:** `packaging/redyungas_oil_linux.spec`.
- Guía: `packaging/README_BUILD.md`.

## Estado

Ver `CHECKPOINTS/REDYUNGAS_OIL_MASTER_CHECKPOINT_*.md` y `CHECKPOINTS/REDYUNGAS_OIL_TODO.md`.
