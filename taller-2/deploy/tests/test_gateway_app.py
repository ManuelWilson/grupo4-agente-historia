"""API local: salud, 401 sin token, 422 de entrada y 502 cuando el agente falla."""

import pytest
from fastapi.testclient import TestClient

import gateway.app as app_module
from gateway.service import Reply

TOKEN = "token-de-prueba"
SECRET = "secreto-webhook"


class StubService:
    """Reemplaza el servicio real: estos tests no salen a la red."""

    def __init__(self, settings):
        self.settings = settings

    def health(self):
        return {"ok": True, "service": "gateway"}

    def handle(self, text, context_id=None, *, chat_id=None, user_id=None):
        if text == "falla":
            return Reply("No pude contactar al agente.", "historia", ("historia",), ok=False, error="A2AConnectionError")
        return Reply("respuesta de prueba", "historia", ("historia",))

    def handle_chat(self, chat_id, user_id, text="", *, media_type=None):
        if media_type:
            return Reply("Solo puedo leer texto.", "entrada_invalida", ok=False, error="tipo_no_soportado")
        if text == "/start":
            return Reply("Hola, soy el bot.", "comando")
        return Reply(f"respuesta a {text}", "historia", ("historia",))


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("A2A_HISTORIA_URL", "http://127.0.0.1:2025")
    monkeypatch.setenv("A2A_GEOGRAFIA_URL", "http://127.0.0.1:2026")
    monkeypatch.setenv("LOCAL_API_TOKEN", TOKEN)
    monkeypatch.setenv("TELEGRAM_SECRET", SECRET)
    monkeypatch.setenv("TELEGRAM_SEND_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(app_module, "GatewayService", StubService)
    with TestClient(app_module.app) as test_client:
        yield test_client


def test_health_sin_token(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_chat_sin_token_es_401(client):
    response = client.post("/v1/chat", json={"message": "¿Qué fue la Ilustración?"})
    assert response.status_code == 401


def test_chat_token_incorrecto_es_401(client):
    response = client.post(
        "/v1/chat",
        json={"message": "¿Qué fue la Ilustración?"},
        headers={"Authorization": "Bearer otro-token"},
    )
    assert response.status_code == 401


def test_chat_token_con_esquema_raro_es_401(client):
    response = client.post(
        "/v1/chat",
        json={"message": "¿Qué fue la Ilustración?"},
        headers={"Authorization": TOKEN},
    )
    assert response.status_code == 401


def test_chat_autorizado(client):
    response = client.post(
        "/v1/chat",
        json={"message": "¿Qué fue la Ilustración?"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "respuesta de prueba"
    assert body["route"] == "historia"
    assert body["agents"] == ["historia"]
    assert body["request_id"] and body["request_id"] == response.headers["X-Request-ID"]
    assert body["task_ids"] == []


def test_chat_mensaje_vacio_es_422(client):
    response = client.post(
        "/v1/chat",
        json={"message": "   "},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 422


def test_chat_mensaje_demasiado_largo_es_422(client, monkeypatch):
    response = client.post(
        "/v1/chat",
        json={"message": "historia " * 400},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 422


def test_fallo_del_agente_es_502(client):
    response = client.post(
        "/v1/chat",
        json={"message": "falla"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert response.status_code == 502
    assert "No pude contactar" in response.json()["detail"]


def test_webhook_sin_secreto_es_403(client):
    response = client.post("/telegram/webhook", json={"message": {"chat": {"id": 42}, "text": "/start"}})
    assert response.status_code == 403


def test_webhook_con_secreto_responde_y_no_filtra(monkeypatch, client):
    enviados = []
    monkeypatch.setattr(app_module.app.state.telegram, "send_message", lambda chat, text, **_: enviados.append((chat, text)) or [1])
    monkeypatch.setattr(app_module.app.state.telegram, "send_typing", lambda chat: None)

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 42}, "from": {"id": 7}, "text": "/start"}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200
    assert enviados == [(42, "Hola, soy el bot.")]


def test_webhook_con_foto_responde_sin_llamar_al_agente(monkeypatch, client):
    enviados = []
    monkeypatch.setattr(app_module.app.state.telegram, "send_message", lambda chat, text, **_: enviados.append((chat, text)) or [1])
    monkeypatch.setattr(app_module.app.state.telegram, "send_typing", lambda chat: None)

    response = client.post(
        "/telegram/webhook",
        json={"message": {"chat": {"id": 42}, "from": {"id": 7}, "photo": [{"file_id": "x"}]}},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200
    assert enviados == [(42, "Solo puedo leer texto.")]
