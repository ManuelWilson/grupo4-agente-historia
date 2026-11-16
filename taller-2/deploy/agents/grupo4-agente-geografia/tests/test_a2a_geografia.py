"""Pruebas del agente profesor de geografia expuesto por A2A nativo. Requiere `langgraph dev --port 2026` corriendo."""
import os, uuid, httpx, pytest

BASE = os.environ.get("A2A_GEOGRAFIA_URL", "http://127.0.0.1:2026")
GRAPH = os.environ.get("A2A_GEOGRAFIA_GRAPH", "agente_profesor_geografia")
# `langgraph dev` crea el assistant con el graph_id como nombre: ese es el valor real que
# publica la Agent Card. El env var solo existe para probar un assistant renombrado.
NOMBRE = os.environ.get("A2A_GEOGRAFIA_NOMBRE", GRAPH)


def assistant_id() -> str:
    """El servidor identifica cada grafo con un assistant_id UUID; se obtiene buscando por graph_id."""
    r = httpx.post(f"{BASE}/assistants/search", json={"graph_id": GRAPH}, timeout=10).json()
    return r[0]["assistant_id"]


def _servidor_arriba():
    try:
        return httpx.get(f"{BASE}/ok", timeout=3).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _servidor_arriba(), reason="langgraph dev no esta corriendo")


def test_agent_card():
    aid = assistant_id()
    card = httpx.get(f"{BASE}/.well-known/agent-card.json", params={"assistant_id": aid}, timeout=10).json()
    esperado = f"{BASE.rstrip('/')}/a2a/{aid}"
    assert card["name"] == NOMBRE
    assert card["url"] == esperado
    # El middleware reescribe tambien las interfaces: un cliente A2A usa esa URL para hablar.
    assert [i["url"] for i in card["supportedInterfaces"]] == [esperado]
    assert "geograf" in card["description"].lower()
    assert isinstance(card.get("skills"), list)


def test_message_send():
    cuerpo = {"jsonrpc": "2.0", "id": "1", "method": "message/send", "params": {"message": {
        "role": "user", "messageId": uuid.uuid4().hex, "contextId": str(uuid.uuid4()),
        "parts": [{"kind": "text", "text": "Explica el clima del valle del Nilo"}]}}}
    r = httpx.post(f"{BASE}/a2a/{assistant_id()}", json=cuerpo, timeout=90).json()
    assert r["result"]["status"]["state"] == "completed"
    assert "Nilo" in str(r["result"]) or "clima" in str(r["result"])
