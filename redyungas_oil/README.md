# REDYUNGAS OIL

Software de automatización radial para la red de emisoras Red Yungas.
**Clon visual de ZaraRadio v1.6.2** (estilo Windows 7) por fuera, con un **backend
moderno** por dentro: resiliencia de señal, grabación con entrega a IA para
transcripción/diarización, menciones programadas y control por agentes de IA (MCP).

> Independiente de JARVIS. No modifica archivos de JARVIS. Se conecta a él de
> forma opcional mediante adaptadores (Telegram + API de transcripción).

## Estado
**v1.0.0 — todas las fases (0–8) completas.** Ver el checkpoint maestro en `../CHECKPOINTS/`.
Réplica visual de ZaraRadio + motor de audio (crossfade, rotativas, pisador, locuciones, eventos) +
red esclava (receptor + failover offline + Telegram) + estudio (emisor Icecast) + grabación con
entrega a JARVIS + servidor MCP + menciones que brillan. Empaquetado Windows: ver `packaging/`.

## Requisitos del sistema
- Python 3.11+ (probado en 3.12).
- **libVLC** del sistema:
  - Linux: `sudo apt install vlc libvlc-dev`
  - Windows: instalar VLC oficial (o se incluye en el empaquetado).
- ffmpeg / ffprobe en el PATH.

## Instalación (desarrollo)
```bash
cd "RED YUNGAS OIL"
python3 -m venv .venv
source .venv/bin/activate
pip install -r redyungas_oil/requirements.txt
```

## Ejecución
```bash
# arranque normal
python -m redyungas_oil.app

# smoke test (abre y cierra solo; útil en CI / verificación)
RYO_SMOKE=1 python -m redyungas_oil.app
```

## Configuración
Copia `redyungas_oil/config.example.toml` a `config.toml` (en la raíz del proyecto)
y ajusta el perfil (`estudio` / `esclava` / `standalone`), rutas, puertos y los
adaptadores opcionales. Sin `config.toml`, arranca en `standalone` con defaults.

## Arquitectura (resumen)
```
ui/        -> el "disfraz" (réplica de ZaraRadio en PyQt6)
audio/     -> motor VLC: playout, crossfade, VU, grabación, emisor, receptor
playlist/  -> modelo de lista, tipos de ítem, formato .lst
scheduler/ -> eventos a hora exacta + menciones que brillan
network/   -> failover offline + cliente Icecast
integrations/ -> adaptadores OPCIONALES a JARVIS (Telegram, transcripción)
mcp/       -> servidor MCP de control por IA
core/      -> constantes, config (TOML), logging
```
