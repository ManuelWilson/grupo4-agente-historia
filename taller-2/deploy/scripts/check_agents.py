#!/usr/bin/env python3
"""Preflight de los agentes A2A: `/ok` + Agent Card + una consulta real.

    python deploy/scripts/check_agents.py
    python deploy/scripts/check_agents.py --historia https://... --geografia https://...

Sirve tanto para los agentes locales (`langgraph dev`) como para los de la nube
(Heroku). Solo usa la biblioteca estándar, así que corre con cualquier Python 3.10+.

Para cada agente verifica, en este orden:

1. `GET /ok` responde 200.
2. El grafo está registrado (`/assistants/search`) y la Agent Card publica la URL
   A2A de ese `assistant_id` (la misma en `url` y en `supportedInterfaces`).
3. Si `A2A_SHARED_TOKEN` está definido, `message/send` sin token responde 401.
4. `message/send` con token (o sin token si no está configurado) devuelve una tarea
   `completed` con texto no vacío.

Sale con código 0 si los dos agentes pasan y 1 si algo falla. Nunca imprime tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILES = (Path.home() / ".config" / "taller2" / ".env", REPO_ROOT / ".env")

AGENTS = (
    ("historia", "A2A_HISTORIA_URL", "A2A_HISTORIA_GRAPH", "agente_profesor_historia"),
    ("geografia", "A2A_GEOGRAFIA_URL", "A2A_GEOGRAFIA_GRAPH", "agente_profesor_geografia"),
)

PREGUNTAS = {
    "historia": "En una frase: ¿qué fue la Ilustración?",
    "geografia": "En una frase: ¿qué es la placa tectónica?",
}

ROLES_AGENTE = {"agent", "assistant"}
ESTADOS_FALLIDOS = {"failed", "canceled", "cancelled", "rejected"}

fallos: list[str] = []


def load_env() -> dict[str, str]:
    """Variables reales > `.env` del proyecto > `.env` seguro."""
    env = dict(os.environ)
    for path in ENV_FILES:
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


def request(
    method: str,
    url: str,
    payload: dict | None = None,
    timeout: float = 180,
    headers: dict[str, str] | None = None,
):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, body
    except (urllib.error.URLError, OSError) as exc:
        return 0, {"error": f"{type(exc).__name__}"}


def parts_text(parts: list[dict] | None) -> str:
    textos = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        if part.get("kind") == "text" or part.get("type") == "text":
            texto = (part.get("text") or "").strip()
            if texto:
                textos.append(texto)
    return "\n".join(textos)


def reply_text(result: dict) -> str:
    """Mismo orden que el cliente del gateway: history, artifacts, status."""
    for message in reversed(result.get("history") or []):
        if isinstance(message, dict) and message.get("role") in ROLES_AGENTE:
            texto = parts_text(message.get("parts"))
            if texto:
                return texto
    for artifact in result.get("artifacts") or []:
        if isinstance(artifact, dict):
            texto = parts_text(artifact.get("parts"))
            if texto:
                return texto
    return parts_text(((result.get("status") or {}).get("message") or {}).get("parts"))


def check_agent(
    etiqueta: str,
    base: str,
    graph: str,
    assistant_id: str,
    timeout: float,
    token: str = "",
) -> None:
    if not base:
        check(False, f"{etiqueta}: falta la URL del agente")
        return
    base = base.rstrip("/")

    status, _ = request("GET", f"{base}/ok", timeout=timeout)
    check(status == 200, f"{etiqueta}: GET {base}/ok -> HTTP {status}")
    if status != 200:
        return

    if not assistant_id:
        status, encontrados = request(
            "POST", f"{base}/assistants/search", {"graph_id": graph}, timeout=timeout
        )
        if status != 200 or not isinstance(encontrados, list) or not encontrados:
            check(False, f"{etiqueta}: no encontré el assistant del grafo {graph} (HTTP {status})")
            return
        assistant_id = str(encontrados[0].get("assistant_id") or "")
        if not assistant_id:
            check(False, f"{etiqueta}: el servidor devolvió un assistant_id vacío")
            return

    status, card = request(
        "GET",
        f"{base}/.well-known/agent-card.json?assistant_id={assistant_id}",
        timeout=timeout,
    )
    if status != 200 or not isinstance(card, dict):
        check(False, f"{etiqueta}: Agent Card -> HTTP {status}")
        return

    sufijo = f"/a2a/{assistant_id}"
    url_card = str(card.get("url") or "")
    interfaces = [
        str(item.get("url") or "")
        for item in (card.get("supportedInterfaces") or [])
        if isinstance(item, dict)
    ]
    check(
        url_card.endswith(sufijo),
        f"{etiqueta}: card.url={url_card or '(vacía)'}",
    )
    check(
        bool(interfaces) and all(url.endswith(sufijo) for url in interfaces),
        f"{etiqueta}: interfaces={interfaces or '(vacías)'}",
    )
    check(
        bool(card.get("name")) and bool(card.get("description")),
        f"{etiqueta}: card con nombre y descripción",
    )

    body = {
        "jsonrpc": "2.0",
        "id": uuid.uuid4().hex,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": uuid.uuid4().hex,
                "contextId": str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": PREGUNTAS[etiqueta]}],
            }
        },
    }
    status, payload = request("POST", f"{base}{sufijo}", body, timeout=timeout)
    if token:
        check(
            status == 401,
            f"{etiqueta}: sin token -> HTTP {status} (esperado 401)",
        )
        status, payload = request(
            "POST",
            f"{base}{sufijo}",
            body,
            timeout=timeout,
            headers={"Authorization": f"Bearer {token}"},
        )
    if status != 200 or not isinstance(payload, dict):
        check(False, f"{etiqueta}: message/send -> HTTP {status}")
        return
    if payload.get("error"):
        detalle = str((payload.get("error") or {}).get("message") or "")[:120]
        check(False, f"{etiqueta}: JSON-RPC error: {detalle}")
        return

    result = payload.get("result")
    if not isinstance(result, dict):
        check(False, f"{etiqueta}: respuesta sin `result`")
        return

    state = str((result.get("status") or {}).get("state") or "completed")
    texto = reply_text(result)
    task_id = str(result.get("id") or (result.get("status") or {}).get("taskId") or "")
    check(
        state not in ESTADOS_FALLIDOS and bool(texto),
        f"{etiqueta}: consulta A2A -> state={state}, {len(texto)} chars, task_id={task_id or '(sin id)'}",
    )
    if texto:
        print(f"       respuesta: {texto[:160]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight de los agentes A2A del Taller 2.")
    parser.add_argument("--historia", help="URL base del agente de historia (pisa el entorno).")
    parser.add_argument("--geografia", help="URL base del agente de geografía (pisa el entorno).")
    parser.add_argument("--timeout", type=float, default=120.0, help="Timeout por request, en segundos.")
    args = parser.parse_args()

    env = load_env()
    overrides = {"historia": args.historia, "geografia": args.geografia}
    token = (env.get("A2A_SHARED_TOKEN") or "").strip()

    for etiqueta, url_var, graph_var, graph_default in AGENTS:
        base = (overrides[etiqueta] or env.get(url_var) or "").strip().rstrip("/")
        graph = (env.get(graph_var) or graph_default).strip()
        # Siempre se descubre el assistant: es el mismo camino que usa el gateway
        # y evita arrastrar un UUID viejo guardado en el entorno.
        check_agent(etiqueta, base, graph, "", args.timeout, token)

    print()
    if fallos:
        print(f"Resultado: {len(fallos)} fallo(s).")
        return 1
    print("Resultado: agentes OK (/ok + card + consulta A2A).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
