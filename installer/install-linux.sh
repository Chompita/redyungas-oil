#!/usr/bin/env bash
# ============================================================================
#  REDYUNGAS OIL — lanzador Linux (ESTA PC es la única Linux).
#  Corre desde el CLON git (un solo lugar) y se autoactualiza por git
#  (Ayuda → Buscar actualizaciones, o el aviso al arrancar). NO usa el build
#  congelado de dist/ (ese no se puede autoactualizar).
#
#  Uso:  bash installer/install-linux.sh
# ============================================================================
set -e
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # raíz del clon (este repo)
echo "Repo (único lugar): $REPO"

# 1) venv + dependencias (idempotente).
if [ ! -x "$REPO/.venv/bin/python" ]; then
    python3 -m venv "$REPO/.venv"
fi
"$REPO/.venv/bin/python" -m pip install -q --upgrade pip
"$REPO/.venv/bin/python" -m pip install -q -r "$REPO/redyungas_oil/requirements.txt"

# 2) Lanzador en ~/.local/bin (ruta sin espacios, en el PATH).
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/redyungas-oil" <<EOF
#!/usr/bin/env bash
# Lanzador REDYUNGAS OIL — corre desde el clon git (autoactualizable).
cd "$REPO" || exit 1
source "$REPO/.venv/bin/activate"
exec python -m redyungas_oil "\$@"
EOF
chmod +x "$HOME/.local/bin/redyungas-oil"

# 3) Acceso directo (.desktop) en aplicaciones y Escritorio.
ICON="$REPO/redyungas_oil/resources/branding/logo.png"
mkdir -p "$HOME/.local/share/applications"
DESKTOP="$HOME/.local/share/applications/redyungas-oil.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=REDYUNGAS OIL
Comment=Automatización radial con IA
Exec=$HOME/.local/bin/redyungas-oil
Icon=$ICON
Terminal=false
Categories=AudioVideo;Audio;
EOF
chmod +x "$DESKTOP"
for d in "$HOME/Escritorio" "$HOME/Desktop" "$HOME/Escritorio/"; do
    if [ -d "$d" ]; then
        cp "$DESKTOP" "$d/redyungas-oil.desktop" && chmod +x "$d/redyungas-oil.desktop" 2>/dev/null || true
        # marcar como confiable en GNOME (evita el "Permitir el lanzamiento")
        gio set "$d/redyungas-oil.desktop" metadata::trusted true 2>/dev/null || true
    fi
done

echo "OK. Lanzador: ~/.local/bin/redyungas-oil  (+ acceso directo en el menú y el Escritorio)."
echo "El build congelado dist/redyungas-oil ya NO se usa (no se autoactualiza); puedes borrarlo."
