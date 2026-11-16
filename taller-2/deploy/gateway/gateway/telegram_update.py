"""Lectura de un update de Telegram: remitente, texto y tipo de contenido.

Compartido por el webhook local (`app.py`) y por el adaptador de Lambda, para
que ambos traten igual los mensajes sin texto (foto, voz, documento, sticker).
"""

from __future__ import annotations

from dataclasses import dataclass

# Lo que Telegram puede mandar en lugar de (o además de) texto.
MEDIA_KEYS = (
    "photo",
    "voice",
    "audio",
    "video",
    "video_note",
    "document",
    "sticker",
    "location",
    "contact",
    "poll",
    "animation",
)


@dataclass(frozen=True)
class IncomingMessage:
    chat_id: int | str | None
    user_id: int | str | None
    text: str
    media_type: str | None = None
    update_id: int | str | None = None


def parse_update(update: dict) -> IncomingMessage | None:
    """Devuelve el mensaje del update, o `None` si no hay nada que responder."""
    if not isinstance(update, dict):
        return None
    message = update.get("message") or update.get("edited_message") or {}
    if not isinstance(message, dict):
        return None

    chat_id = (message.get("chat") or {}).get("id")
    if chat_id is None:
        return None
    user_id = (message.get("from") or {}).get("id")
    media_type = next((clave for clave in MEDIA_KEYS if message.get(clave)), None)
    texto = (message.get("text") or message.get("caption") or "").strip()
    return IncomingMessage(chat_id, user_id, texto, media_type, update.get("update_id"))
