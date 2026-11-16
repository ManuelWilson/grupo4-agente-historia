"""Observabilidad: logs JSON correlacionados y sin datos personales.

Cada línea de log es un objeto JSON con:

    ts, level, logger, event, request_id, update_id, chat_id_hash,
    route, agents, a2a_task_id, status, latency_ms, error_code

Reglas:
- **Nunca** se registra el texto del mensaje ni el `chat_id` en claro: solo un hash.
- `request_id` identifica una solicitud; `update_id` la ata al update de Telegram.
- El hash usa `LOG_HASH_SALT`; si falta, se usa una sal aleatoria por proceso (los
  hashes no se pueden comparar entre reinicios, que es lo correcto para privacidad).
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone

REQUEST_ID: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
UPDATE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("update_id", default="")
CHAT_HASH: contextvars.ContextVar[str] = contextvars.ContextVar("chat_id_hash", default="")

_SALT = os.environ.get("LOG_HASH_SALT") or uuid.uuid4().hex

_RESERVED = set(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {
    "message",
    "asctime",
    "extra_fields",
}


def chat_id_hash(chat_id: int | str | None) -> str:
    """Hash corto y estable por proceso: permite agrupar sin identificar a nadie."""
    if chat_id is None or chat_id == "":
        return ""
    return hashlib.sha256(f"{_SALT}:{chat_id}".encode()).hexdigest()[:12]


def start_request(update_id: int | str | None = None, chat_id: int | str | None = None) -> list:
    """Abre el contexto de una solicitud y devuelve los tokens para cerrarlo."""
    return [
        REQUEST_ID.set(uuid.uuid4().hex[:12]),
        UPDATE_ID.set(str(update_id) if update_id is not None else ""),
        CHAT_HASH.set(chat_id_hash(chat_id)),
    ]


def set_message_context(update_id: int | str | None, chat_id: int | str | None) -> list:
    """Completa update_id y hash del chat sin pisar el request_id de la petición."""
    return [
        UPDATE_ID.set(str(update_id) if update_id is not None else ""),
        CHAT_HASH.set(chat_id_hash(chat_id)),
    ]


def end_request(tokens: list) -> None:
    for token in reversed(tokens):
        try:
            token.var.reset(token)
        except ValueError:  # pragma: no cover - contexto de otro hilo
            pass


def current_request_id() -> str:
    return REQUEST_ID.get()


class JsonFormatter(logging.Formatter):
    """Una línea JSON por evento, con los campos de correlación siempre presentes."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
            "request_id": REQUEST_ID.get(),
            "update_id": UPDATE_ID.get(),
            "chat_id_hash": CHAT_HASH.get(),
        }
        for key, value in vars(record).items():
            if key in _RESERVED:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                payload[key] = value
            else:
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)
