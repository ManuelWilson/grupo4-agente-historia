"""Cliente A2A del gateway: JSON-RPC, descubrimiento y errores tipados.

Regla de oro: un fallo **nunca** se devuelve como texto de respuesta exitosa.
Cada problema se traduce a una excepción con dos mensajes: uno apto para el
usuario (`str(exc)`) y un detalle técnico para los logs (`exc.detail`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace

import httpx

CARD_PATH = "/.well-known/agent-card.json"
A2A_PATH = "/a2a/{assistant_id}"
ROLES_AGENTE = {"agent", "assistant"}
ESTADOS_FINALES_FALLIDOS = {"failed", "canceled", "cancelled", "rejected"}


class A2AError(RuntimeError):
    """Fallo al hablar con un agente A2A."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


class A2AConnectionError(A2AError):
    """No se pudo abrir conexión con el agente."""


class A2ATimeoutError(A2AError):
    """El agente no respondió dentro del tiempo configurado."""


class A2AProtocolError(A2AError):
    """Respuesta inválida: HTTP raro, JSON-RPC con error, card inaccesible."""


class A2ATaskFailed(A2AError):
    """El agente recibió la consulta pero la tarea terminó en error."""


@dataclass(frozen=True)
class AgentTarget:
    label: str
    base_url: str
    graph_id: str
    assistant_id: str = ""

    @property
    def endpoint(self) -> str:
        return self.base_url + A2A_PATH.format(assistant_id=self.assistant_id)


@dataclass(frozen=True)
class AgentReply:
    label: str
    state: str
    text: str
    task_id: str = ""


def _parts_text(parts: list[dict] | None) -> str:
    textos = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        if part.get("kind") == "text" or part.get("type") == "text":
            texto = (part.get("text") or "").strip()
            if texto:
                textos.append(texto)
    return "\n".join(textos)


def extract_reply_text(result: dict) -> str:
    """Extrae el texto del agente probando las formas que usa A2A/LangGraph."""
    for message in reversed(result.get("history") or []):
        if isinstance(message, dict) and message.get("role") in ROLES_AGENTE:
            texto = _parts_text(message.get("parts"))
            if texto:
                return texto

    for artifact in result.get("artifacts") or []:
        if isinstance(artifact, dict):
            texto = _parts_text(artifact.get("parts"))
            if texto:
                return texto

    status = result.get("status") or {}
    texto = _parts_text((status.get("message") or {}).get("parts"))
    if texto:
        return texto

    for message in reversed(result.get("messages") or []):
        if isinstance(message, dict) and message.get("role") in ROLES_AGENTE:
            texto = _parts_text(message.get("parts"))
            if texto:
                return texto

    return ""


class A2AClient:
    """Habla con los agentes por A2A y resuelve sus `assistant_id`."""

    def __init__(
        self,
        timeout: float = 45.0,
        transport: httpx.BaseTransport | None = None,
        shared_token: str = "",
    ):
        self._timeout = timeout
        self._transport = transport
        self._shared_token = (shared_token or "").strip()
        self._assistant_ids: dict[str, str] = {}

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, transport=self._transport)

    def _auth_headers(self) -> dict[str, str]:
        """El token A2A viaja como Bearer; si no está configurado, no se envía."""
        if not self._shared_token:
            return {}
        return {"Authorization": f"Bearer {self._shared_token}"}

    def _request_json(self, method: str, url: str, **kwargs):
        headers = dict(self._auth_headers())
        headers.update(kwargs.pop("headers", None) or {})
        if headers:
            kwargs["headers"] = headers
        try:
            with self._client() as client:
                response = client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise A2ATimeoutError(
                "El agente tardó demasiado en responder.",
                detail=f"timeout de {self._timeout}s en {url}",
            ) from exc
        except httpx.HTTPError as exc:
            raise A2AConnectionError(
                "No pude conectarme con el agente.",
                detail=f"{type(exc).__name__} en {url}: {exc}",
            ) from exc

        if response.status_code in (401, 403):
            raise A2AProtocolError(
                "El agente rechazó la autenticación.",
                detail=(
                    f"HTTP {response.status_code} en {url}: "
                    "revisá A2A_SHARED_TOKEN (debe ser el mismo en gateway y agente). "
                    f"{response.text[:200]}"
                ),
            )

        if response.status_code != 200:
            raise A2AProtocolError(
                "El agente respondió con un error.",
                detail=f"HTTP {response.status_code} en {url}: {response.text[:300]}",
            )

        try:
            return response.json()
        except ValueError as exc:
            raise A2AProtocolError(
                "El agente devolvió una respuesta que no es JSON.",
                detail=f"{url}: {response.text[:300]}",
            ) from exc

    def discover_assistant(self, base_url: str, graph_id: str) -> str:
        """`langgraph dev` asigna un UUID por grafo y puede cambiar al reiniciar."""
        url = f"{base_url}/assistants/search"
        payload = self._request_json("POST", url, json={"graph_id": graph_id})
        if isinstance(payload, dict) and payload.get("assistants"):
            payload = payload["assistants"]
        if not isinstance(payload, list) or not payload:
            raise A2AProtocolError(
                "El agente no está registrado en el servidor.",
                detail=f"{url}: sin assistants para el grafo {graph_id}",
            )
        assistant_id = (payload[0] or {}).get("assistant_id")
        if not assistant_id:
            raise A2AProtocolError(
                "El servidor del agente devolvió un identificador vacío.",
                detail=f"{url}: {str(payload[0])[:300]}",
            )
        return assistant_id

    def get_agent_card(self, target: AgentTarget) -> dict:
        params = {"assistant_id": target.assistant_id} if target.assistant_id else None
        card = self._request_json("GET", target.base_url + CARD_PATH, params=params)
        if not isinstance(card, dict):
            raise A2AProtocolError(
                "La Agent Card del agente no es un objeto JSON.",
                detail=f"{target.base_url}: {str(card)[:300]}",
            )
        return card

    def resolve(self, target: AgentTarget) -> AgentTarget:
        """Completa el `assistant_id` (del entorno o por descubrimiento) una sola vez."""
        if target.assistant_id:
            return target
        cached = self._assistant_ids.get(target.label)
        if cached:
            return replace(target, assistant_id=cached)
        assistant_id = self.discover_assistant(target.base_url, target.graph_id)
        self._assistant_ids[target.label] = assistant_id
        return replace(target, assistant_id=assistant_id)

    def send_text(
        self,
        target: AgentTarget,
        text: str,
        context_id: str | None = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> AgentReply:
        """Envía una consulta y devuelve la respuesta, o lanza una excepción tipada."""
        target = self.resolve(target)
        body = {
            "jsonrpc": "2.0",
            "id": uuid.uuid4().hex,
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "messageId": uuid.uuid4().hex,
                    "contextId": context_id or str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": text}],
                }
            },
        }
        payload = self._request_json(
            "POST",
            target.endpoint,
            json=body,
            headers={"Accept": "application/json", **(headers or {})},
        )

        error = payload.get("error")
        if error:
            message = (error or {}).get("message") or "error JSON-RPC"
            raise A2AProtocolError(
                "El agente rechazó la consulta.",
                detail=f"{target.label}: {message}",
            )

        result = payload.get("result")
        if not isinstance(result, dict):
            raise A2AProtocolError(
                "El agente devolvió una respuesta sin resultado.",
                detail=f"{target.label}: {str(payload)[:300]}",
            )

        status = result.get("status") or {}
        state = str(status.get("state") or "completed")
        texto = extract_reply_text(result)

        if state in ESTADOS_FINALES_FALLIDOS:
            raise A2ATaskFailed(
                "El agente no pudo completar la consulta.",
                detail=f"{target.label}: state={state} status={str(status)[:300]}",
            )

        if not texto:
            raise A2AProtocolError(
                "El agente devolvió una respuesta vacía.",
                detail=f"{target.label}: state={state} keys={sorted(result)}",
            )

        return AgentReply(
            label=target.label,
            state=state,
            text=texto,
            task_id=str(result.get("id") or status.get("taskId") or ""),
        )
