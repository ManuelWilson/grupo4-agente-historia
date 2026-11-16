"""Publica la URL real del agente dentro de la Agent Card y protege `/a2a/*`.

`langgraph dev` arma la Agent Card con el host de bind, que en Heroku es
`0.0.0.0` y en un contenedor puede ser un puerto interno. Este middleware
reescribe solo el campo `url` de la card (y de sus `supportedInterfaces`)
usando `PUBLIC_BASE_URL`. El resto de las rutas pasa sin cambios.

Además exige `Authorization: Bearer <A2A_SHARED_TOKEN>` en `/a2a/*` cuando el
token está configurado. La Agent Card y `/assistants/search` quedan públicos
para que un cliente pueda descubrir el agente antes de autenticarse.
"""

from __future__ import annotations

import json
import os
import secrets

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

CARD_PATHS = ("/.well-known/agent-card.json", "/.well-known/agent.json")
A2A_MARKER = "/a2a/"
A2A_PREFIX = "/a2a/"
BEARER_PREFIX = "bearer "


def _shared_token() -> str:
    return os.environ.get("A2A_SHARED_TOKEN", "").strip()


def _bearer_token(request) -> str:
    header = request.headers.get("authorization", "").strip()
    if not header.lower().startswith(BEARER_PREFIX):
        return ""
    return header[len(BEARER_PREFIX) :].strip()


def _base_url(request) -> str:
    configured = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = (
        request.headers.get("x-forwarded-host")
        or request.headers.get("host")
        or request.url.netloc
    )
    return f"{scheme}://{host.split(',')[0].strip()}"


def _rewrite_url(value: str, base: str) -> str:
    if A2A_MARKER in value:
        return base + A2A_MARKER + value.split(A2A_MARKER, 1)[1]
    return value


class A2AAuthMiddleware(BaseHTTPMiddleware):
    """Exige Bearer en `/a2a/*` si `A2A_SHARED_TOKEN` está configurado.

    Sin token configurado no se exige nada: así el entorno local sigue
    funcionando sin variables extra. En producción se configura en ambos lados.
    """

    async def dispatch(self, request, call_next):
        if not request.url.path.startswith(A2A_PREFIX):
            return await call_next(request)

        expected = _shared_token()
        if not expected:
            return await call_next(request)

        provided = _bearer_token(request)
        if not provided or not secrets.compare_digest(provided, expected):
            return JSONResponse(
                {"error": "unauthorized", "detail": "Token A2A inválido o ausente."},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            )
        return await call_next(request)


class AgentCardUrlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not request.url.path.endswith(CARD_PATHS):
            return await call_next(request)

        response = await call_next(request)
        if response.status_code != 200:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            card = json.loads(body)
        except (TypeError, ValueError):
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(
                body,
                status_code=response.status_code,
                headers=headers,
                media_type=response.media_type,
            )

        base = _base_url(request)
        if isinstance(card, dict):
            if isinstance(card.get("url"), str):
                card["url"] = _rewrite_url(card["url"], base)
            interfaces = card.get("supportedInterfaces")
            if isinstance(interfaces, list):
                for interface in interfaces:
                    if isinstance(interface, dict) and isinstance(interface.get("url"), str):
                        interface["url"] = _rewrite_url(interface["url"], base)
            if _shared_token():
                card.setdefault(
                    "securitySchemes",
                    {"bearer": {"type": "http", "scheme": "bearer"}},
                )
                card.setdefault("security", [{"bearer": []}])

        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-length", "content-type"}
        }
        return Response(
            json.dumps(card).encode("utf-8"),
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )


app = Starlette(
    middleware=[
        Middleware(AgentCardUrlMiddleware),
        Middleware(A2AAuthMiddleware),
    ]
)
