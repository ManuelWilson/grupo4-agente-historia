"""Auth A2A de los agentes: `/a2a/*` cerrado con token, card y descubrimiento públicos.

Se cargan los dos `http_app.py` reales por ruta para que el test falle si los
agentes divergen (hoy son iguales, pero son paquetes separados).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

DEPLOY = Path(__file__).resolve().parents[1]
AGENTS = (
    ("historia", DEPLOY / "agents" / "grupo4-agente-historia" / "src" / "agente_profesor" / "http_app.py"),
    ("geografia", DEPLOY / "agents" / "grupo4-agente-geografia" / "src" / "agente_geografia" / "http_app.py"),
)
TOKEN = "token-a2a-de-prueba"


def _cargar(nombre: str, path: Path):
    modulo_id = f"http_app_{nombre}"
    spec = importlib.util.spec_from_file_location(modulo_id, path)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[modulo_id] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def _app(modulo) -> Starlette:
    async def a2a(_request):
        return JSONResponse({"ok": True})

    async def card(_request):
        return JSONResponse(
            {
                "name": "agente",
                "url": "http://0.0.0.0:2025/a2a/aid-1",
                "supportedInterfaces": [{"url": "http://0.0.0.0:2025/a2a/aid-1"}],
            }
        )

    async def search(_request):
        return JSONResponse([])

    return Starlette(
        routes=[
            Route("/a2a/{rest:path}", a2a, methods=["GET", "POST"]),
            Route("/.well-known/agent-card.json", card),
            Route("/assistants/search", search, methods=["POST"]),
        ],
        middleware=[
            Middleware(modulo.AgentCardUrlMiddleware),
            Middleware(modulo.A2AAuthMiddleware),
        ],
    )


@pytest.fixture(params=AGENTS, ids=[nombre for nombre, _ in AGENTS])
def agente(request):
    nombre, path = request.param
    return _cargar(nombre, path)


@pytest.fixture
def cliente(agente) -> TestClient:
    return TestClient(_app(agente))


def test_a2a_sin_token_es_401(cliente, monkeypatch):
    monkeypatch.setenv("A2A_SHARED_TOKEN", TOKEN)
    respuesta = cliente.post("/a2a/aid-1", json={})
    assert respuesta.status_code == 401
    assert respuesta.headers["www-authenticate"] == "Bearer"
    assert respuesta.json()["error"] == "unauthorized"


def test_a2a_con_token_incorrecto_es_401(cliente, monkeypatch):
    monkeypatch.setenv("A2A_SHARED_TOKEN", TOKEN)
    respuesta = cliente.post(
        "/a2a/aid-1", json={}, headers={"Authorization": "Bearer otro-token"}
    )
    assert respuesta.status_code == 401


def test_a2a_con_token_correcto_pasa(cliente, monkeypatch):
    monkeypatch.setenv("A2A_SHARED_TOKEN", TOKEN)
    respuesta = cliente.post(
        "/a2a/aid-1", json={}, headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json() == {"ok": True}


def test_sin_token_configurado_no_se_exige(cliente, monkeypatch):
    monkeypatch.delenv("A2A_SHARED_TOKEN", raising=False)
    assert cliente.post("/a2a/aid-1", json={}).status_code == 200


def test_card_y_descubrimiento_siguen_publicos(cliente, monkeypatch):
    monkeypatch.setenv("A2A_SHARED_TOKEN", TOKEN)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://agente.test")

    card = cliente.get("/.well-known/agent-card.json")
    assert card.status_code == 200
    cuerpo = card.json()
    assert cuerpo["url"] == "https://agente.test/a2a/aid-1"
    assert cuerpo["supportedInterfaces"][0]["url"] == "https://agente.test/a2a/aid-1"
    assert cuerpo["security"] == [{"bearer": []}]
    assert cuerpo["securitySchemes"]["bearer"] == {"type": "http", "scheme": "bearer"}

    assert cliente.post("/assistants/search", json={}).status_code == 200


def test_card_sin_token_no_declara_seguridad(cliente, monkeypatch):
    monkeypatch.delenv("A2A_SHARED_TOKEN", raising=False)
    cuerpo = cliente.get("/.well-known/agent-card.json").json()
    assert "security" not in cuerpo
    assert "securitySchemes" not in cuerpo
