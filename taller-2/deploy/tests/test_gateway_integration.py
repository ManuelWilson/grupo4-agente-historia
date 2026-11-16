"""Integración real: habla con los `langgraph dev` locales si están levantados."""

import os

import httpx
import pytest

from gateway.a2a_client import A2AClient, AgentTarget

AGENTES = (
    ("Historia", "http://127.0.0.1:2025", "agente_profesor_historia", "En una frase: ¿qué fue la Ilustración?"),
    ("Geografía", "http://127.0.0.1:2026", "agente_profesor_geografia", "En una frase: ¿qué es un delta fluvial?"),
)


def _arriba(base: str) -> bool:
    try:
        return httpx.get(f"{base}/ok", timeout=3).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.parametrize("label,base,graph,pregunta", AGENTES)
def test_agente_local_responde(label, base, graph, pregunta):
    if not _arriba(base):
        pytest.skip(f"{base} no está corriendo (langgraph dev)")

    target = AgentTarget(label, base, graph)
    # Los agentes pueden exigir el token compartido; el test usa el mismo entorno.
    reply = A2AClient(
        timeout=60,
        shared_token=os.environ.get("A2A_SHARED_TOKEN", ""),
    ).send_text(target, pregunta)

    assert reply.state == "completed"
    assert len(reply.text) > 20
