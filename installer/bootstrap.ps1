# ============================================================================
#  REDYUNGAS OIL — bootstrap de instalación (lo llama el instalador Inno Setup).
#  Clona el repo PÚBLICO (sin credenciales), crea el venv, instala dependencias
#  y deja config.toml. La AUTOACTUALIZACIÓN la hace la app (git fetch + reset --hard).
#
#  Uso (lo invoca redyungas_oil.iss; también se puede a mano):
#    powershell -ExecutionPolicy Bypass -File bootstrap.ps1 `
#       -InstallDir "C:\Program Files\RedYungasOil" `
#       -RepoUrl "https://github.com/Chompita/redyungas-oil.git" `
#       -Branch master `
#       -PythonExe "C:\Program Files\RedYungasOil\python\python.exe" `
#       -GitExe "C:\Program Files\RedYungasOil\tools\git\cmd\git.exe"
# ============================================================================
param(
    [Parameter(Mandatory=$true)][string]$InstallDir,
    [Parameter(Mandatory=$true)][string]$RepoUrl,
    [string]$Branch = "master",
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$GitExe
)
$ErrorActionPreference = "Stop"
$repo = Join-Path $InstallDir "repo"
$venv = Join-Path $InstallDir "venv"
$log  = Join-Path $InstallDir "install.log"
function Log($m) { $line = "$(Get-Date -Format o)  $m"; Write-Host $line; Add-Content -Path $log -Value $line }

Log "Bootstrap REDYUNGAS OIL — InstallDir=$InstallDir Branch=$Branch"

# 1) Clonar (o actualizar si ya existía).
if (Test-Path (Join-Path $repo ".git")) {
    Log "El repo ya existe; actualizando (fetch + reset --hard)."
    & $GitExe -C $repo fetch --all --prune --quiet
    & $GitExe -C $repo reset --hard "origin/$Branch"
} else {
    Log "Clonando el repositorio…"
    if (Test-Path $repo) { Remove-Item $repo -Recurse -Force }
    & $GitExe clone --branch $Branch --depth 50 $RepoUrl $repo
    if ($LASTEXITCODE -ne 0) { throw "git clone falló (¿hay internet? el repo es público, no necesita credenciales)" }
}

# 2) Crear el venv e instalar dependencias.
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    Log "Creando entorno virtual…"
    & $PythonExe -m venv $venv
}
$venvPy = Join-Path $venv "Scripts\python.exe"
Log "Actualizando pip e instalando dependencias…"
& $venvPy -m pip install --upgrade pip --quiet
& $venvPy -m pip install -q -r (Join-Path $repo "redyungas_oil\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install de requirements falló." }

# 3) Dejar un config.toml inicial (junto al repo, donde la app lo lee) si no existe.
$cfg = Join-Path $repo "config.toml"
$example = Join-Path $repo "redyungas_oil\config.example.toml"
if ((-not (Test-Path $cfg)) -and (Test-Path $example)) {
    Copy-Item $example $cfg
    Log "config.toml creado desde el ejemplo (edítalo: perfil, stream, telegram…)."
}

Log "Bootstrap COMPLETADO. La app arranca con run_redyungas_oil.vbs."
