"""Cliente A2A: cada fallo se convierte en una excepción, nunca en texto exitoso."""

import httpx
import pytest

from gateway.a2a_client import (
    A2AClient,
    A2AConnectionError,
    A2AProtocolError,
    A2ATaskFailed,
    A2ATimeoutError,
    AgentTarget,
    extract_reply_text,
)

TARGET = AgentTarget("Historia", "http://agente.test", "agente_profesor_historia", "aid-1")


def cliente(handler, timeout: float = 5.0) -> A2AClient:
    return A2AClient(timeout=timeout, transport=httpx.MockTransport(handler))


def resultado(**extra) -> dict:
    base = {"status": {"state": "completed"}}
    base.update(extra)
    return base


def test_completed_devuelve_texto():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": resultado(
                    history=[{"role": "agent", "parts": [{"kind": "text", "text": "La Ilustración."}]}]
                ),
            },
        )

    reply = cliente(handler).send_text(TARGET, "¿Qué fue la Ilustración?")
    assert reply.text == "La Ilustración."
    assert reply.state == "completed"
    assert reply.label == "Historia"


def test_input_required_es_respuesta_valida():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {
                    "status": {
                        "state": "input-required",
                        "message": {
                            "role": "agent",
                            "parts": [{"kind": "text", "text": "¿De qué país hablamos?"}],
                        },
                    }
                },
            },
        )

    reply = cliente(handler).send_text(TARGET, "contame la independencia")
    assert reply.state == "input-required"
    assert reply.text == "¿De qué país hablamos?"


def test_failed_no_se_presenta_como_exito():
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"status": {"state": "failed", "message": {"parts": [{"kind": "text", "text": "boom"}]}}},
            },
        )

    with pytest.raises(A2ATaskFailed) as excinfo:
        cliente(handler).send_text(TARGET, "consulta")
    assert "no pudo completar" in str(excinfo.value)


def test_respuesta_vacia_es_error():
    def handler(_request):
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": "1", "result": resultado()})

    with pytest.raises(A2AProtocolError) as excinfo:
        cliente(handler).send_text(TARGET, "consulta")
    assert "vacía" in str(excinfo.value)


def test_http_500_es_error_de_protocolo():
    def handler(_request):
        return httpx.Response(500, text="kernel panic")

    with pytest.raises(A2AProtocolError) as excinfo:
        cliente(handler).send_text(TARGET, "consulta")
    assert "HTTP 500" in excinfo.value.detail


def test_error_jsonrpc_es_error_de_protocolo():
    def handler(_request):
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": "1", "error": {"code": -32602, "message": "params inválidos"}},
        )

    with pytest.raises(A2AProtocolError) as excinfo:
        cliente(handler).send_text(TARGET, "consulta")
    assert "params inválidos" in excinfo.value.detail


def test_timeout_es_error_de_timeout():
    def handler(request):
        raise httpx.ReadTimeout("sin respuesta", request=request)

    with pytest.raises(A2ATimeoutError):
        cliente(handler).send_text(TARGET, "consulta")


def test_conexion_rechazada_es_error_de_conexion():
    def handler(request):
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(A2AConnectionError):
        cliente(handler).send_text(TARGET, "consulta")


def test_descubre_assistant_id_y_reutiliza_la_cache():
    vistos = []

    def handler(request):
        vistos.append(request.url.path)
        if request.url.path.endswith("/assistants/search"):
            return httpx.Response(200, json=[{"assistant_id": "aid-9"}])
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": resultado(history=[{"role": "agent", "parts": [{"kind": "text", "text": "ok"}]}]),
            },
        )

    api = cliente(handler)
    target = AgentTarget("Historia", "http://agente.test", "agente_profesor_historia")
    assert api.send_text(target, "uno").text == "ok"
    assert api.send_text(target, "dos").text == "ok"

    assert vistos.count("/assistants/search") == 1
    assert vistos.count("/a2a/aid-9") == 2


def test_sin_grafo_registrado_falla_claro():
    def handler(_request):
        return httpx.Response(200, json=[])

    with pytest.raises(A2AProtocolError) as excinfo:
        cliente(handler).discover_assistant("http://agente.test", "grafo_inexistente")
    assert "no está registrado" in str(excinfo.value)


def test_agent_card_se_lee():
    def handler(request):
        assert request.url.path == "/.well-known/agent-card.json"
        return httpx.Response(200, json={"name": "agente", "url": "http://agente.test/a2a/aid-1"})

    card = cliente(handler).get_agent_card(TARGET)
    assert card["name"] == "agente"


def test_extrae_texto_de_artifacts_y_messages():
    assert extract_reply_text({"artifacts": [{"parts": [{"type": "text", "text": "desde artifact"}]}]}) == "desde artifact"
    assert extract_reply_text({"messages": [{"role": "assistant", "parts": [{"kind": "text", "text": "desde message"}]}]}) == "desde message"
    assert extract_reply_text({}) == ""


def test_envia_bearer_en_descubrimiento_card_y_consulta():
    vistos = []

    def handler(request):
        vistos.append((request.url.path, request.headers.get("authorization")))
        if request.url.path.endswith("/assistants/search"):
            return httpx.Response(200, json=[{"assistant_id": "aid-1"}])
        if request.url.path.startswith("/.well-known"):
            return httpx.Response(200, json={"name": "agente"})
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": resultado(history=[{"role": "agent", "parts": [{"kind": "text", "text": "ok"}]}]),
            },
        )

    api = A2AClient(
        transport=httpx.MockTransport(handler),
        shared_token="secreto-a2a",
    )
    target = AgentTarget("Historia", "http://agente.test", "agente_profesor_historia")

    api.get_agent_card(target)
    assert api.send_text(target, "consulta").text == "ok"

    assert [ruta for ruta, _ in vistos] == [
        "/.well-known/agent-card.json",
        "/assistants/search",
        "/a2a/aid-1",
    ]
    assert all(header == "Bearer secreto-a2a" for _, header in vistos)


def test_sin_token_no_envia_authorization():
    vistos = []

    def handler(request):
        vistos.append(request.headers.get("authorization"))
        return httpx.Response(200, json=[{"assistant_id": "aid-1"}])

    A2AClient(transport=httpx.MockTransport(handler)).discover_assistant(
        "http://agente.test", "agente_profesor_historia"
    )
    assert vistos == [None]


def test_401_explica_que_revisar_el_token():
    def handler(_request):
        return httpx.Response(401, text='{"error":"unauthorized"}')

    with pytest.raises(A2AProtocolError) as excinfo:
        cliente(handler).send_text(TARGET, "consulta")
    assert "autenticación" in str(excinfo.value)
    assert "A2A_SHARED_TOKEN" in excinfo.value.detail
