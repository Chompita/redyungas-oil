# REDYUNGAS OIL — Instalador todo‑en‑uno (Windows) + autoactualización

Instalador **un‑clic** que deja cada PC con todo lo necesario y se **autoactualiza**
cuando subimos funciones nuevas (sin re‑instalar). Estrategia elegida por el operador:
**Inno Setup + git** (la app corre desde un clon del repo y se actualiza con
`git fetch + reset --hard`, ver `redyungas_oil/core/updater.py`).

> El instalador hay que **compilarlo en Windows** (Inno Setup no corre en Linux). Aquí
> están todos los scripts ya listos; solo falta poner 4 binarios y pulsar *Compile*.

---

## 1. Qué hace el instalador
1. Instala **VLC** (silencioso) y **Python 3.11** (dentro de `…\RedYungasOil\python`).
2. Copia **git portátil (MinGit)** y **ffmpeg/ffprobe** a `…\RedYungasOil\tools`.
3. Pide un **token de SOLO LECTURA** del repo privado y **clona** el repositorio.
4. Crea el **venv** e instala las dependencias (`pip install -r requirements.txt`).
5. Deja un **`config.toml`** inicial (desde el ejemplo) en el clon.
6. Crea **accesos directos** (Escritorio + Inicio/autoarranque) que arrancan la app
   **sin consola** (`run_redyungas_oil.vbs` → `RedYungasOil.bat` → `pythonw -m redyungas_oil`).

**Actualizar después:** desde la app (Ayuda → Buscar actualizaciones, o el aviso al
arrancar) o por consola `…\venv\Scripts\python -m redyungas_oil.core.updater`. La app
hace `git fetch` + `reset --hard origin/master`, **verifica que la versión en disco
cambió** y, si hay dependencias nuevas, `pip install`. Luego ofrece **Reiniciar**.

---

## 2. Preparar la credencial (una vez)
El repo es privado → cada PC necesita leer el repo. Crea un **fine‑grained PAT**
(GitHub → Settings → Developer settings → *Fine‑grained tokens*) con:
- Repository access: solo `Chompita/redyungas-oil`.
- Permissions → **Contents: Read‑only**.

Ese token se pega en el instalador (queda cacheado en el clon para el self‑update).
No lo subas al repo. (Un deploy key SSH también vale; entonces usa la URL `git@…`.)

---

## 3. Preparar el payload (una vez, junto al .iss)
Descarga y coloca en `installer\payload\` (renombrando a estos nombres exactos):

| Archivo en `payload\`        | De dónde                                              |
|------------------------------|-------------------------------------------------------|
| `vlc-setup.exe`              | VLC oficial 64‑bit (videolan.org)                     |
| `python-setup.exe`           | `python-3.11.x-amd64.exe` (python.org)                |
| `git\` (carpeta)             | **MinGit** (github.com/git-for-windows/git, *MinGit*) extraído; debe quedar `payload\git\cmd\git.exe` |
| `ffmpeg\ffmpeg.exe`          | ffmpeg estático Windows (gyan.dev / BtbN)             |
| `ffmpeg\ffprobe.exe`         | idem                                                  |

(Estos binarios NO van al repo: `installer/payload/` está en `.gitignore`.)

---

## 4. Compilar
1. Instala **Inno Setup 6** (jrsoftware.org).
2. Abre `installer\redyungas_oil.iss` y pulsa **Compile** (o `iscc redyungas_oil.iss`).
3. Resultado: `installer\Output\RedYungasOil-Setup.exe`.

---

## 5. Desplegar en una esclava
1. Copia `RedYungasOil-Setup.exe` a la PC (por Tailscale/USB) y ejecútalo como admin.
2. Pega el **token de solo lectura** y confirma la URL cuando lo pida.
3. Al terminar, edita `…\RedYungasOil\repo\config.toml` (perfil `estudio`/`esclava`,
   `[stream]`, `[network]`, `[telegram]`, `[mcp]`, micrófono `[mic]`…) — hay un acceso
   directo "Editar configuración" en el menú Inicio.
4. La app ya queda en el Escritorio y en el autoarranque.

---

## 6. Actualizar TODAS las esclavas (de noche, por Telegram/MARCUS o SSH)
Como ya se reparte la publicidad por Tailscale, se puede lanzar en cada IP:
```
ssh <IP> "C:\Program Files\RedYungasOil\venv\Scripts\python.exe -m redyungas_oil.core.updater"
```
Devuelve `0` si quedó al día, `1` si falló (y dice por qué), `2` si no es clon git.
Después, reiniciar la app (cerrar y reabrir el acceso directo, o el watchdog).

---

## 7. Linux (servidor de desarrollo / pruebas)
El mismo self‑update funciona en el clon git de Linux:
```
cd "~/RED YUNGAS OIL" && source .venv/bin/activate
python -m redyungas_oil.core.updater          # fetch + reset --hard + verifica versión
```
(En la máquina de desarrollo con commits locales, el updater **se niega** a sobrescribir:
es intencional, para no perder trabajo. Usa git a mano allí.)

---

## 8. Notas
- El self‑update necesita que el clon tenga la credencial cacheada (lo deja el bootstrap
  con `credential.helper store`). Si rota el token, vuelve a clonar o re‑guarda la credencial.
- VLC/ffmpeg quedan disponibles; el lanzador añade `tools\git\cmd` y `tools\ffmpeg` al PATH
  del proceso para que el updater (git) y el audio (ffmpeg) los encuentren.
- Alternativa "sin Python/git en el PC" (.exe empaquetado + GitHub Releases) NO es esta vía;
  se documenta aparte si algún día se quiere para máquinas muy limitadas.
