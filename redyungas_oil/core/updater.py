"""
core/updater.py — Auto-actualización desde el repositorio privado de GitHub.

Cada esclava se despliega como un **clon git** del repo privado
(`Chompita/redyungas-oil`). Para actualizar a la última versión basta con:

    git fetch  →  comparar APP_VERSION local vs origin/<branch>  →  git pull --ff-only

Se usa **git puro** a propósito: las credenciales quedan cacheadas en el clon
del despliegue, así que NO hace falta incrustar ningún token en el software (ni
subirlo al repo). Funciona igual en Linux y en Windows.

Uso:
* `Updater.check_async()` — comprueba en segundo plano y emite señales.
* `Updater.apply()` — hace `git pull --ff-only` y devuelve si hay que reiniciar.
* CLI sin GUI: `python -m redyungas_oil.core.updater` (ver `packaging/update.py`).

Instalaciones que NO son git (un .exe empaquetado suelto) no se autoactualizan
por aquí: se redepliegan o se bajan de una Release. `is_git_install()` lo indica.
"""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal

from . import constants as C
from . import proc

log = logging.getLogger("redyungas_oil.updater")

# Raíz del repo: .../RED YUNGAS OIL  (dos niveles sobre core/)
REPO_ROOT = Path(__file__).resolve().parents[2]
# El fichero de versión que CARGA el proceso al arrancar (lo que importa verificar).
CONSTANTS_FILE = Path(__file__).resolve().parent / "constants.py"
_VERSION_RE = re.compile(r'APP_VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+)*)["\']')


def _version_in_text(text: str) -> str:
    m = _VERSION_RE.search(text or "")
    return m.group(1) if m else ""


def _local_version_on_disk() -> str:
    """Lee APP_VERSION del fichero REAL en disco (el que cargará el próximo arranque)."""
    try:
        return _version_in_text(CONSTANTS_FILE.read_text(encoding="utf-8"))
    except OSError:
        return ""


def _ver_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return (0,)


def is_newer(remote: str, local: str) -> bool:
    return _ver_tuple(remote) > _ver_tuple(local)


def _git(args: list[str], cwd: Path | None = None, timeout: int = 30) -> tuple[int, str]:
    cwd = cwd or REPO_ROOT          # se resuelve EN LA LLAMADA (no en la definición)
    try:
        p = proc.run(["git", "-C", str(cwd), *args], capture_output=True,
                     text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


def is_git_install(cwd: Path | None = None) -> bool:
    rc, out = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    return rc == 0 and out.strip() == "true"


def _pip_install(requirements: Path) -> str:
    """Instala dependencias nuevas con el python del venv (best-effort)."""
    import sys
    if getattr(sys, "frozen", False):     # un .exe empaquetado no usa pip
        return ""
    try:
        p = proc.run([sys.executable, "-m", "pip", "install", "-q",
                      "-r", str(requirements)], capture_output=True, text=True, timeout=600)
        return " (deps actualizadas)" if p.returncode == 0 else " (¡revisa deps: pip falló!)"
    except Exception:
        return " (no se pudieron actualizar deps)"


class Updater(QObject):
    # (versión_remota, hay_update, mensaje)
    checked = pyqtSignal(str, bool, str)
    applied = pyqtSignal(bool, str)         # (ok, mensaje)

    def __init__(self, config: dict, parent=None) -> None:
        super().__init__(parent)
        up = (config.get("update", {}) or {})
        self.branch = up.get("branch", "master") or "master"
        self.local_version = C.APP_VERSION
        self.remote_version = ""

    # ------------------------------------------------------------- comprobar
    def check_async(self) -> None:
        threading.Thread(target=self._check, daemon=True).start()

    def _remote_version(self) -> tuple[str, str]:
        if not is_git_install():
            return "", "Instalación no-git: actualiza por redepliegue o Release."
        rc, out = _git(["fetch", "--quiet", "origin", self.branch])
        if rc != 0:
            return "", f"No se pudo contactar el repositorio: {out[:160]}"
        rc, content = _git(["show", f"origin/{self.branch}:redyungas_oil/core/constants.py"])
        if rc != 0:
            return "", f"No se pudo leer la versión remota: {content[:160]}"
        m = _VERSION_RE.search(content)
        if not m:
            return "", "No se encontró APP_VERSION en el repositorio remoto."
        return m.group(1), ""

    def _check(self) -> None:
        remote, err = self._remote_version()
        if err:
            self.checked.emit("", False, err)
            return
        self.remote_version = remote
        if is_newer(remote, self.local_version):
            self.checked.emit(remote, True,
                              f"Hay una versión nueva: v{remote} (tienes v{self.local_version}).")
        else:
            self.checked.emit(remote, False, f"Estás al día (v{self.local_version}).")

    # ------------------------------------------------------------- aplicar
    def apply_async(self) -> None:
        threading.Thread(target=self._apply, daemon=True).start()

    def _apply(self) -> None:
        """Sincroniza el clon al remoto y VERIFICA que la versión EN DISCO cambió.

        Antes hacía `git pull --ff-only` y reportaba éxito por el código de salida,
        aunque no aplicara nada (clon divergente/sucio, o sin avanzar la copia que
        carga el lanzador). Ahora: fetch → reset --hard a origin → re-leer la versión
        del fichero real y reportar el resultado HONESTO (vAntes → vDespués)."""
        if not is_git_install():
            self.applied.emit(False, "Instalación no-git: no se puede actualizar con git "
                                     "(usa el instalador/redepliegue).")
            return
        before = _local_version_on_disk()

        rc, out = _git(["fetch", "--all", "--prune", "--quiet"], timeout=120)
        if rc != 0:
            self.applied.emit(False, f"No se pudo contactar el repositorio (fetch): {out[:200]}")
            return

        # No pisar trabajo local: si el clon tiene commits propios NO en el remoto, abortar.
        rc, ahead = _git(["rev-list", "--count", f"origin/{self.branch}..HEAD"])
        if rc == 0 and ahead.strip().isdigit() and int(ahead.strip()) > 0:
            self.applied.emit(False,
                              "Este clon tiene cambios/commits locales que no están en el "
                              "servidor; no se sobrescriben. (Máquina de desarrollo: usa git a mano.)")
            return

        req = REPO_ROOT / "redyungas_oil" / "requirements.txt"
        req_before = req.read_text(encoding="utf-8") if req.exists() else ""

        # Forzar el árbol de trabajo a coincidir EXACTAMENTE con el remoto (idempotente,
        # no puede quedarse en un no-op silencioso como el pull --ff-only).
        rc, out = _git(["reset", "--hard", f"origin/{self.branch}"], timeout=120)
        if rc != 0:
            self.applied.emit(False, f"No se pudo aplicar la actualización (reset): {out[:200]}")
            return
        _git(["clean", "-df", "--", "redyungas_oil"], timeout=60)   # quita .py huérfanos del paquete

        # Si la nueva versión cambió las dependencias, instalarlas (clon git con venv).
        req_after = req.read_text(encoding="utf-8") if req.exists() else ""
        deps_msg = ""
        if req_after and req_after != req_before:
            deps_msg = _pip_install(req)

        after = _local_version_on_disk()
        if after and after != before:
            self.applied.emit(True, f"Actualizado: v{before or '?'} → v{after}.{deps_msg} "
                                    "Reinicia (o pulsa Reiniciar) para aplicar los cambios.")
        elif after and self.remote_version and after == self.remote_version:
            self.applied.emit(True, f"Ya estaba al día en disco (v{after}).")
        else:
            self.applied.emit(False,
                              f"El reset terminó pero la versión en disco sigue en "
                              f"v{after or '?'}. Salida: {out[:200] or 'sin cambios'}")


# --------------------------------------------------------------------------- CLI
def _cli() -> int:
    """Actualización sin GUI (para tareas programadas / despliegue por SSH).

    Misma lógica robusta que la GUI: fetch → reset --hard → verifica la versión en
    disco. Devuelve 0 si quedó al día, 1 si falló, 2 si no es un clon git.
    """
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not is_git_install():
        print("Instalación no-git: actualiza por redepliegue o instalador.")
        return 2
    branch = "master"
    before = _local_version_on_disk()
    rc, out = _git(["fetch", "--all", "--prune", "--quiet"], timeout=120)
    if rc != 0:
        print(f"No se pudo contactar el repo: {out}")
        return 1
    rc, content = _git(["show", f"origin/{branch}:redyungas_oil/core/constants.py"])
    remote = _version_in_text(content) if rc == 0 else ""
    rc, ahead = _git(["rev-list", "--count", f"origin/{branch}..HEAD"])
    if rc == 0 and ahead.strip().isdigit() and int(ahead.strip()) > 0:
        print("Clon con commits locales; no se sobrescribe. Usa git a mano.")
        return 1
    if remote and before and not is_newer(remote, before):
        print(f"Estás al día (v{before}).")
        return 0
    print(f"Actualizando v{before or '?'} -> v{remote or '?'} …")
    req = REPO_ROOT / "redyungas_oil" / "requirements.txt"
    req_before = req.read_text(encoding="utf-8") if req.exists() else ""
    rc, out = _git(["reset", "--hard", f"origin/{branch}"], timeout=120)
    if rc != 0:
        print(f"reset --hard falló: {out}")
        return 1
    _git(["clean", "-df", "--", "redyungas_oil"], timeout=60)
    req_after = req.read_text(encoding="utf-8") if req.exists() else ""
    if req_after and req_after != req_before:
        print("Dependencias cambiadas:" + _pip_install(req))
    after = _local_version_on_disk()
    if after and after != before:
        print(f"OK. v{before or '?'} -> v{after}. Reinicia REDYUNGAS OIL.")
        return 0
    print(f"El reset terminó pero la versión sigue en v{after or '?'}.")
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
