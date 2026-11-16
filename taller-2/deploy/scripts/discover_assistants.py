#!/usr/bin/env python3
"""Descubre los `assistant_id` que cada `langgraph dev` asigna a su grafo.

En `langgraph dev` el UUID puede cambiar al reiniciar, así que no conviene
hardcodearlo: el gateway lo descubre solo. Este script sirve para verlo y, si
hace falta, fijarlo en el `.env`.

    python deploy/scripts/discover_assistants.py
    python deploy/scripts/discover_assistants.py --json
    python deploy/scripts/discover_assistants.py --write-env .env

`--write-env` actualiza solo las líneas A2A_*_ASSISTANT_ID del archivo indicado.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

AGENTS = (
    ("Historia", "A2A_HISTORIA_URL", "A2A_HISTORIA_GRAPH", "agente_profesor_historia", "A2A_HISTORIA_ASSISTANT_ID"),
    ("Geografía", "A2A_GEOGRAFIA_URL", "A2A_GEOGRAFIA_GRAPH", "agente_profesor_geografia", "A2A_GEOGRAFIA_ASSISTANT_ID"),
)


def load_env(path: Path) -> dict[str, str]:
    env = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            env[key.strip()] = value.strip()
    return {**env, **os.environ}


def discover(base: str, graph: str) -> str:
    request = urllib.request.Request(
        f"{base}/assistants/search",
        data=json.dumps({"graph_id": graph}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        assistants = json.load(response)
    if not assistants:
        raise SystemExit(f"{base}: no hay assistants para el grafo {graph}")
    return assistants[0]["assistant_id"]


def write_env(path: Path, updates: dict[str, str]) -> None:
    lineas = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    pendientes = dict(updates)
    salida = []
    for linea in lineas:
        clave = linea.split("=", 1)[0].strip() if "=" in linea else ""
        if clave in pendientes:
            salida.append(f"{clave}={pendientes.pop(clave)}")
        else:
            salida.append(linea)
    salida.extend(f"{clave}={valor}" for clave, valor in pendientes.items())
    path.write_text("\n".join(salida) + "\n", encoding="utf-8")
    print(f"Actualizado: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Descubre los assistant_id locales.")
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env"), help="Archivo de variables.")
    parser.add_argument("--json", action="store_true", help="Salida JSON.")
    parser.add_argument("--write-env", metavar="ARCHIVO", help="Escribe los IDs en ese archivo.")
    args = parser.parse_args()

    env = load_env(Path(args.env_file))
    encontrados: dict[str, str] = {}

    for etiqueta, url_var, graph_var, graph_default, id_var in AGENTS:
        base = (env.get(url_var) or "").strip().rstrip("/")
        if not base:
            raise SystemExit(f"Falta {url_var}: copiá .env.example a .env y completalo.")
        graph = (env.get(graph_var) or graph_default).strip()
        try:
            assistant_id = discover(base, graph)
        except (urllib.error.URLError, OSError) as exc:
            raise SystemExit(f"{base}: no se pudo consultar ({type(exc).__name__}). ¿Está `langgraph dev` corriendo?")
        encontrados[id_var] = assistant_id
        if not args.json:
            print(f"{etiqueta}: {assistant_id}")
            print(f"  card: {base}/.well-known/agent-card.json?assistant_id={assistant_id}")

    if args.json:
        print(json.dumps(encontrados, indent=2, ensure_ascii=False))
    if args.write_env:
        write_env(Path(args.write_env), encontrados)
    return 0


if __name__ == "__main__":
    sys.exit(main())
