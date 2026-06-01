"""
Launcher para PyInstaller (FASE 8).

Asegura que la raíz del proyecto esté en sys.path y arranca el paquete con
imports absolutos (los imports relativos de app.py funcionan al importarse como
parte del paquete).
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # .../redyungas_oil/..
sys.path.insert(0, ROOT)

from redyungas_oil.app import main  # noqa: E402

raise SystemExit(main())
