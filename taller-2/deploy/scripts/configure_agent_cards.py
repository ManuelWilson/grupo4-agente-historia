#!/usr/bin/env python3
"""Publica la URL real en cada Agent Card de los agentes desplegados en Heroku.

El middleware `http_app.py` de cada agente usa `PUBLIC_BASE_URL` para reescribir
la Agent Card. Sin esa variable la card puede publicar el host interno del
proceso (`0.0.0.0:<puerto>`), que no sirve para descubrir el agente.

Uso:
    python deploy/scripts/configure_agent_cards.py --dry-run
    python deploy/scripts/configure_agent_cards.py

Lee los secretos de %USERPROFILE%\\.config\\taller2\\.env y nunca los imprime.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from update_cloud_secrets import heroku_request, read_env, require  # noqa: E402

AGENTS = (
    {
        "label": "Historia",
        "app_var": "HEROKU_APP_HISTORIA",
        "assistant_var": "A2A_HISTORIA_ASSISTANT_ID",
        "graph_var": "A2A_HISTORIA_GRAPH",
    },
    {
        "label": "Geografia",
        "app_var": "HEROKU_APP_GEOGRAFIA",
        "assistant_var": "A2A_GEOGRAFIA_ASSISTANT_ID",
        "graph_var": "A2A_GEOGRAFIA_GRAPH",
    },
)


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.load(response)


def discover_assistant(base: str, graph_id: str) -> str:
    data = json.dumps({"graph_id": graph_id}).encode()
    request = urllib.request.Request(
        base + "/assistants/search",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        assistants = json.load(response)
    if not assistants:
        raise SystemExit(f"{base}: no hay assistants para el grafo {graph_id}")
    return assistants[0]["assistant_id"]


def wait_for_card(base: str, assistant_id: str, timeout: int = 180) -> dict:
    expected = f"{base}/a2a/{assistant_id}"
    card_url = f"{base}/.well-known/agent-card.json?assistant_id={assistant_id}"
    last_error = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            card = fetch_json(card_url)
            interfaces = [item.get("url") for item in card.get("supportedInterfaces") or []]
            if card.get("url") == expected and interfaces and all(url == expected for url in interfaces):
                return card
            last_error = f"url publicada: {card.get('url')} · interfaces: {interfaces}"
        except Exception as exc:
            last_error = type(exc).__name__
        time.sleep(4)
    raise SystemExit(f"{base}: la Agent Card no publico {expected} ({last_error})")


def main() -> int:
    parser = argparse.ArgumentParser(description="Configura LANGGRAPH_API_URL para las Agent Cards.")
    parser.add_argument("--dry-run", action="store_true", help="Mostrar los cambios sin tocar Heroku.")
    parser.add_argument(
        "--env-file",
        default=str(Path.home() / ".config" / "taller2" / ".env"),
        help="Archivo de secretos (por defecto, fuera del repositorio).",
    )
    parser.add_argument("--timeout", type=int, default=180, help="Segundos de espera por app.")
    args = parser.parse_args()

    env = read_env(Path(args.env_file))
    plan = []
    for agent in AGENTS:
        app = require(env, agent["app_var"])
        status, app_info = heroku_request(env, "GET", f"/apps/{app}")
        if status != 200 or not isinstance(app_info, dict):
            raise SystemExit(f"{app}: no se pudo leer la app en Heroku (HTTP {status})")
        base = (app_info.get("web_url") or "").rstrip("/")
        if not base.startswith("https://"):
            raise SystemExit(f"{app}: Heroku no devolvio una web_url https valida")
        plan.append((agent, app, base))

    if args.dry_run:
        for agent, app, base in plan:
            print(f"{agent['label']} ({app}): LANGGRAPH_API_URL={base}")
        print("Dry run: no se modifico nada.")
        return 0

    for agent, app, base in plan:
        status, _ = heroku_request(
            env,
            "PATCH",
            f"/apps/{app}/config-vars",
            {"PUBLIC_BASE_URL": base, "LANGGRAPH_API_URL": None},
        )
        if status not in (200, 201, 202):
            raise SystemExit(f"{app}: PATCH devolvio HTTP {status}")
        print(f"{agent['label']} ({app}): PUBLIC_BASE_URL={base} (HTTP {status})")

    for agent, app, base in plan:
        assistant_id = env.get(agent["assistant_var"], "").strip()
        if not assistant_id:
            assistant_id = discover_assistant(base, require(env, agent["graph_var"]))
        card = wait_for_card(base, assistant_id, timeout=args.timeout)
        print(f"{agent['label']}: card.url={card['url']} OK")

    print("OK: Agent Cards publicando la URL publica de cada agente.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"ERROR HTTP {exc.code}: {exc.read().decode(errors='replace')[:300]}", file=sys.stderr)
        raise SystemExit(1)
