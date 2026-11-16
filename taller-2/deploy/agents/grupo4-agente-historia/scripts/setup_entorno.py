"""Deja operativo el proyecto agente-profesor-historia.

- Crea .venv (si no existe) con el Python actual (requiere 3.11+).
- Actualiza pip.
- Instala dependencias con 'pip install -r requirements.txt' (el extra [inmem]
  se interpreta desde el archivo, evitando el error de especificacion invalida).
- Si falta langgraph-cli, lo instala como argumento de pip: 'langgraph-cli[inmem]>=0.4'.
- Verifica 'langgraph --version' y que langgraph.json sea JSON valido.

No modifica src/agente_profesor/graph.py ni langgraph.json.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROYECTO = Path(__file__).resolve().parent.parent
VENV = PROYECTO / ".venv"


def ejecutable(nombre: str) -> Path:
    if os.name == "nt":
        return VENV / "Scripts" / f"{nombre}.exe"
    return VENV / "bin" / nombre


def correr(cmd: list[str]) -> int:
    print("\n>>", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.call([str(c) for c in cmd], cwd=str(PROYECTO))


def main() -> int:
    if sys.version_info < (3, 11):
        print(f"ERROR: se requiere Python 3.11+ (actual {sys.version.split()[0]}).")
        return 1

    py = ejecutable("python")
    if not py.exists():
        print("Creando entorno virtual .venv ...")
        if correr([sys.executable, "-m", "venv", str(VENV)]) != 0:
            print("ERROR: no se pudo crear .venv")
            return 1
    else:
        print(".venv ya existe, se reutiliza.")

    if correr([py, "-m", "pip", "install", "--upgrade", "pip"]) != 0:
        print("ERROR: no se pudo actualizar pip")
        return 1

    if correr([py, "-m", "pip", "install", "-r", "requirements.txt"]) != 0:
        print("ERROR: fallo 'pip install -r requirements.txt'")
        return 1

    langgraph = ejecutable("langgraph")
    if not langgraph.exists():
        print("langgraph no encontrado; instalando extra puntual ...")
        correr([py, "-m", "pip", "install", "langgraph-cli[inmem]>=0.4"])
        langgraph = ejecutable("langgraph")

    problemas: list[str] = []

    if langgraph.exists():
        if correr([langgraph, "--version"]) != 0:
            problemas.append("'langgraph --version' devolvio un codigo de error.")
    else:
        problemas.append("El ejecutable 'langgraph' no quedo disponible en .venv.")

    cfg = PROYECTO / "langgraph.json"
    try:
        datos = json.loads(cfg.read_text(encoding="utf-8"))
        if "graphs" not in datos or not datos["graphs"]:
            problemas.append("langgraph.json no declara 'graphs'.")
        else:
            for nombre, destino in datos["graphs"].items():
                ruta = destino.split(":")[0]
                if not (PROYECTO / ruta).exists():
                    problemas.append(f"grafo '{nombre}': no existe {ruta}")
            print("langgraph.json valido:", list(datos["graphs"]))
    except Exception as exc:  # noqa: BLE001
        problemas.append(f"langgraph.json invalido: {exc}")

    print("\n=== RESULTADO ===")
    if problemas:
        for p in problemas:
            print("AVISO:", p)
        print("Revisar los avisos antes de ejecutar: langgraph dev --port 2025")
        return 1

    print("Entorno listo. Para iniciar el servidor (no se levanta aqui):")
    print(r"  .venv\Scripts\activate ; langgraph dev --port 2025")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
