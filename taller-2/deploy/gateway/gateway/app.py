"""API local del gateway: `GET /health`, `POST /v1/chat` y webhook de Telegram.

Se levanta con `uvicorn gateway.app:app --port 8000` desde `deploy/gateway`.
No necesita AWS ni Heroku: alcanza con los dos `langgraph dev` locales.
"""

from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from functools import partial

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from gateway.config import ConfigError, Settings
from gateway.logging_setup import configure as configure_logging
from gateway.observability import (
    current_request_id,
    end_request,
    set_message_context,
    start_request,
)
from gateway.service import GatewayService
from gateway.telegram_client import TelegramClient, TelegramError
from gateway.telegram_update import parse_update

logger = logging.getLogger("gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        settings = Settings.from_env(needs_local_api=True)
    except ConfigError as exc:
        # Falla al arrancar y dice qué variable falta.
        raise RuntimeError(str(exc)) from exc

    configure_logging(settings.log_level, settings.log_format)
    for warning in settings.warnings:
        logger.warning(warning)
    app.state.settings = settings
    app.state.service = GatewayService(settings)
    app.state.telegram = TelegramClient(
        settings.telegram_token, enabled=settings.telegram_send_enabled
    )
    logger.info("gateway_listo", extra=settings.summary())
    yield


app = FastAPI(
    title="Gateway local del Taller 2",
    version="1.0.0",
    description="Orquesta las consultas hacia los agentes A2A de historia y geografía.",
    lifespan=lifespan,
)


@app.middleware("http")
async def correlacion(request: Request, call_next):
    """Cada petición tiene un `request_id`; se devuelve en `X-Request-ID`."""
    tokens = start_request(request.headers.get("x-request-id"))
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = current_request_id()
        return response
    finally:
        end_request(tokens)


class ChatRequest(BaseModel):
    message: str = Field(..., description="Consulta del usuario.")
    context_id: str | None = Field(
        default=None, description="ID de conversación; si falta se genera uno nuevo."
    )


class ChatResponse(BaseModel):
    reply: str
    route: str
    agents: list[str]
    request_id: str = ""
    task_ids: list[str] = []


def require_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    """`Authorization: Bearer <LOCAL_API_TOKEN>`; sin token válido responde 401."""
    expected = request.app.state.settings.local_api_token
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token or not secrets.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Token inválido o ausente.")


@app.get("/health")
def health(request: Request) -> dict:
    return request.app.state.service.health()


@app.post("/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_token)])
def chat(payload: ChatRequest, request: Request) -> ChatResponse:
    settings = request.app.state.settings
    texto = payload.message.strip()

    if not texto:
        raise HTTPException(status_code=422, detail="El mensaje está vacío.")
    if len(texto) > settings.max_input_chars:
        raise HTTPException(
            status_code=422,
            detail=f"El mensaje supera {settings.max_input_chars} caracteres.",
        )

    reply = request.app.state.service.handle(texto, payload.context_id)
    if not reply.ok:
        logger.warning("consulta_fallida", extra={"route": reply.route, "error": reply.error})
        raise HTTPException(status_code=502, detail=reply.text)

    return ChatResponse(
        reply=reply.text,
        route=reply.route,
        agents=list(reply.agents),
        request_id=current_request_id(),
        task_ids=list(reply.task_ids),
    )


def check_telegram_secret(request: Request, provided: str | None) -> None:
    expected = request.app.state.settings.telegram_secret
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict:
    """Webhook opcional para probar el flujo de Telegram en local."""
    check_telegram_secret(request, x_telegram_bot_api_secret_token)

    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="JSON inválido.")

    message = parse_update(update)
    if message is None:
        return {"ok": True}

    service: GatewayService = request.app.state.service
    telegram: TelegramClient = request.app.state.telegram

    # update_id y hash del chat quedan asociados a todo lo que se loguee abajo.
    tokens = set_message_context(message.update_id, message.chat_id)
    try:
        await run_in_threadpool(telegram.send_typing, message.chat_id)
        reply = await run_in_threadpool(
            partial(
                service.handle_chat,
                message.chat_id,
                message.user_id,
                message.text,
                media_type=message.media_type,
            )
        )
        try:
            enviados = await run_in_threadpool(
                telegram.send_message, message.chat_id, reply.text
            )
            logger.info(
                "telegram_enviado",
                extra={
                    "route": reply.route,
                    "status": "ok" if reply.ok else "error",
                    "mensajes": len(enviados),
                    "chars": len(reply.text),
                },
            )
        except TelegramError as exc:
            logger.error(
                "telegram_error",
                extra={"status": "error", "error_code": "telegram_error", "detail": exc.detail},
            )
    finally:
        end_request(tokens)
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    config = Settings.from_env(needs_local_api=True)
    uvicorn.run("gateway.app:app", host=config.host, port=config.port)
