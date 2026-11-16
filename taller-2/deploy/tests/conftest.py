"""Deja importable el paquete `gateway` al correr pytest desde la raíz del repo."""

import sys
from pathlib import Path

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))
