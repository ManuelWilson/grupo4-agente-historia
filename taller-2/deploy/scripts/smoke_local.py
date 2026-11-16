#!/usr/bin/env python3
"""Verifica el flujo local completo, sin AWS ni Heroku.

    python deploy/scripts/smoke_local.py          # agentes + cards + gateway
    python deploy/scripts/smoke_local.py --chat   # agrega una consulta real por /v1/chat

Solo usa la biblioteca estándar. Sale con código 1 si algo falla.
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
ENV_FILE = REPO_ROOT / ".env"
SECURE_ENV = Path.home() / ".config" / "taller2" / ".env"

AGENTS = (
    ("historia", "A2A_HISTORIA_URL", "A2A_HISTORIA_GRAPH", "agente_profesor_historia"),
    ("geografia", "A2A_GEOGRAFIA_URL", "A2A_GEOGRAFIA_GRAPH", "agente_profesor_geografia"),
)

fallos: list[str] = []


def load_env() -> dict[str, str]:
    """Variables reales > `.env` del proyecto > `.env` seguro (fuera del repo)."""
    env = dict(os.environ)
    for path in (ENV_FILE, SECURE_ENV):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    return env


def check(ok: bool, message: str) -> None:
    print(f"[{'OK   ' if ok else 'FALLO'}] {message}")
    if not ok:
        fallos.append(message)


def request(method: str, url: str, payload: dict | None = None, token: str | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, body
    except (urllib.error.URLError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def check_agents(env: dict[str, str]) -> None:
    for etiqueta, url_var, graph_var, graph_default in AGENTS:
        base = (env.get(url_var) or "").strip().rstrip("/")
        if not base:
            check(False, f"{etiqueta}: falta {url_var}")
            continue

        status, _ = request("GET", f"{base}/ok")
        check(status == 200, f"{etiqueta}: {base}/ok -> HTTP {status}")
        if status != 200:
            continue

        graph = (env.get(graph_var) or graph_default).strip()
        status, assistants = request("POST", f"{base}/assistants/search", {"graph_id": graph})
        if status != 200 or not isinstance(assistants, list) or not assistants:
            check(False, f"{etiqueta}: no se encontró el assistant del grafo {graph}")
            continue
        assistant_id = assistants[0]["assistant_id"]

        status, card = request(
            "GET", f"{base}/.well-known/agent-card.json?assistant_id={assistant_id}"
        )
        esperado = f"{base}/a2a/{assistant_id}"
        interfaces = [item.get("url") for item in (card.get("supportedInterfaces") or [])] if isinstance(card, dict) else []
        check(
            status == 200 and isinstance(card, dict) and card.get("url") == esperado,
            f"{etiqueta}: card.url={card.get('url') if isinstance(card, dict) else card}",
        )
        check(
            bool(interfaces) and all(url == esperado for url in interfaces),
            f"{etiqueta}: interfaces={interfaces}",
        )


def check_gateway(env: dict[str, str], gateway: str, chat: bool) -> None:
    status, health = request("GET", f"{gateway}/health")
    check(status == 200, f"gateway: {gateway}/health -> HTTP {status}")
    if status != 200:
        return

    if not chat:
        return

    token = (env.get("LOCAL_API_TOKEN") or "").strip()
    if not token:
        check(False, "gateway: falta LOCAL_API_TOKEN para probar /v1/chat")
        return

    status, _ = request("POST", f"{gateway}/v1/chat", {"message": "hola"})
    check(status == 401, f"gateway: /v1/chat sin token -> HTTP {status} (esperado 401)")

    status, body = request(
        "POST",
        f"{gateway}/v1/chat",
        {"message": "En una frase: ¿qué fue la Ilustración?"},
        token=token,
    )
    reply = body.get("reply") if isinstance(body, dict) else ""
    check(
        status == 200 and bool(reply),
        f"gateway: /v1/chat con token -> HTTP {status}, route={body.get('route') if isinstance(body, dict) else '?'}",
    )
    if reply:
        print(f"       respuesta: {reply[:180]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test local del Taller 2.")
    parser.add_argument("--gateway", default="http://127.0.0.1:8000", help="URL del gateway local.")
    parser.add_argument("--chat", action="store_true", help="Probar también POST /v1/chat (consume LLM).")
    args = parser.parse_args()

    env = load_env()
    check_agents(env)
    check_gateway(env, args.gateway.rstrip("/"), args.chat)

    print()
    if fallos:
        print(f"Resultado: {len(fallos)} fallo(s).")
        return 1
    print("Resultado: todo OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
