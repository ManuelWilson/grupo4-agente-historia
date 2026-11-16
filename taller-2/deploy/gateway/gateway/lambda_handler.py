"""Adaptador delgado para AWS Lambda.

El entrypoint sigue siendo `lambda_handler.lambda_handler` (el archivo del mismo
nombre en la raíz de `deploy/gateway` reexporta esta función), así no hay que
tocar la configuración de la función en AWS.
"""

from __future__ import annotations

import base64
import json
import logging
import secrets

from gateway.config import ConfigError, Settings
from gateway.logging_setup import configure as configure_logging
from gateway.observability import end_request, set_message_context
from gateway.service import GatewayService
from gateway.telegram_client import TelegramClient, TelegramError
from gateway.telegram_update import parse_update

logger = logging.getLogger("gateway.lambda_handler")

_settings: Settings | None = None
_service: GatewayService | None = None
_telegram: TelegramClient | None = None


def _bootstrap() -> None:
    """Construye los objetos una sola vez por contenedor (cold start)."""
    global _settings, _service, _telegram
    if _service is not None:
        return
    settings = Settings.from_env()
    configure_logging(settings.log_level, settings.log_format)
    for warning in settings.warnings:
        logger.warning(warning)
    _settings = settings
    _service = GatewayService(settings)
    _telegram = TelegramClient(settings.telegram_token, enabled=settings.telegram_send_enabled)


def _header(event: dict, name: str) -> str | None:
    headers = event.get("headers") or {}
    for key, value in headers.items():
        if key.lower() == name:
            return value
    return None


def _body(event: dict) -> dict | None:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8", errors="replace")
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def handle_event(event: dict, context=None) -> dict:
    try:
        _bootstrap()
    except ConfigError as exc:
        logger.error("config_invalida", extra={"detail": str(exc)})
        return {"statusCode": 500, "body": json.dumps({"error": "configuración inválida"})}

    expected = _settings.telegram_secret  # type: ignore[union-attr]
    provided = _header(event, "x-telegram-bot-api-secret-token")
    if not expected or not provided or not secrets.compare_digest(provided, expected):
        logger.warning("webhook_rechazado", extra={"secret_configured": bool(expected)})
        return {"statusCode": 403, "body": "Forbidden"}

    update = _body(event)
    if update is None:
        return {"statusCode": 400, "body": "Bad request"}
    message = parse_update(update)
    if message is None:
        return {"statusCode": 200, "body": "OK"}

    tokens = set_message_context(message.update_id, message.chat_id)
    try:
        reply = _service.handle_chat(  # type: ignore[union-attr]
            message.chat_id,
            message.user_id,
            message.text,
            media_type=message.media_type,
        )
        try:
            enviados = _telegram.send_message(message.chat_id, reply.text)  # type: ignore[union-attr]
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

    # Telegram siempre recibe 200 para no reintentar el mismo update en bucle.
    return {"statusCode": 200, "body": "OK"}


def lambda_handler(event, context=None):
    return handle_event(event, context)
