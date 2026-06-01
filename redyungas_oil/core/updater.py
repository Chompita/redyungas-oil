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
_VERSION_RE = re.compile(r'APP_VERSION\s*=\s*["\']([0-9]+(?:\.[0-9]+)*)["\']')


def _ver_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return (0,)


def is_newer(remote: str, local: str) -> bool:
    return _ver_tuple(remote) > _ver_tuple(local)


def _git(args: list[str], cwd: Path = REPO_ROOT, timeout: int = 30) -> tuple[int, str]:
    try:
        p = proc.run(["git", "-C", str(cwd), *args], capture_output=True,
                     text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as exc:
        return 1, str(exc)


def is_git_install(cwd: Path = REPO_ROOT) -> bool:
    rc, out = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    return rc == 0 and out.strip() == "true"


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
        if not is_git_install():
            self.applied.emit(False, "Instalación no-git: no se puede actualizar con git.")
            return
        rc, out = _git(["pull", "--ff-only", "origin", self.branch], timeout=120)
        if rc != 0:
            self.applied.emit(False, f"git pull falló: {out[:240]}")
            return
        self.applied.emit(True, "Actualizado. Reinicia REDYUNGAS OIL para aplicar los cambios.")


# --------------------------------------------------------------------------- CLI
def _cli() -> int:
    """Actualización sin GUI (para tareas programadas / despliegue por SSH)."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not is_git_install():
        print("Instalación no-git: actualiza por redepliegue o Release.")
        return 2
    branch = "master"
    rc, out = _git(["fetch", "--quiet", "origin", branch])
    if rc != 0:
        print(f"No se pudo contactar el repo: {out}")
        return 1
    rc, content = _git(["show", f"origin/{branch}:redyungas_oil/core/constants.py"])
    m = _VERSION_RE.search(content) if rc == 0 else None
    remote = m.group(1) if m else ""
    if remote and not is_newer(remote, C.APP_VERSION):
        print(f"Estás al día (v{C.APP_VERSION}).")
        return 0
    print(f"Actualizando v{C.APP_VERSION} -> v{remote or '?'} …")
    rc, out = _git(["pull", "--ff-only", "origin", branch], timeout=120)
    if rc != 0:
        print(f"git pull falló: {out}")
        return 1
    print("OK. Reinicia REDYUNGAS OIL para aplicar los cambios.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
