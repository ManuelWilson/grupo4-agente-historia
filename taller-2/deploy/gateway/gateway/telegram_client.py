"""Envío de mensajes por Telegram: Markdown, chunking, 429 y verificación de errores.

`sendMessage` puede fallar con HTTP 200 y `ok: false`; eso también es un error.
El token nunca se imprime ni se incluye en los mensajes de excepción.

Markdown: los agentes responden con `**negrita**`, listas y encabezados, que
Telegram muestra literales si se envían como texto. Se traduce a un subconjunto
de HTML de Telegram (`<b>`, `<i>`, `<code>`, `<pre>`, `<a>`) y, si Telegram
rechaza las entidades, se reenvía el bloque como texto plano.
"""

from __future__ import annotations

import html
import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 4000
MAX_RETRIES = 3
MAX_RETRY_WAIT = 5.0
PARSE_ERRORS = ("can't parse entities", "can't find end", "unsupported start tag", "unclosed")


class TelegramError(RuntimeError):
    """No se pudo entregar el mensaje a Telegram."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail


def chunk_text(text: str, limit: int = MAX_MESSAGE_CHARS) -> list[str]:
    """Parte el texto en bloques <= limit, cortando en párrafo, línea o palabra."""
    texto = (text or "").strip()
    if not texto:
        return []
    if len(texto) <= limit:
        return [texto]

    bloques: list[str] = []
    resto = texto
    while len(resto) > limit:
        ventana = resto[:limit]
        corte = ventana.rfind("\n\n")
        if corte < limit // 2:
            corte = ventana.rfind("\n")
        if corte < limit // 2:
            corte = ventana.rfind(" ")
        if corte <= 0:
            corte = limit
        bloques.append(resto[:corte].strip())
        resto = resto[corte:].lstrip()
    if resto:
        bloques.append(resto)
    return [bloque for bloque in bloques if bloque]


def to_html(text: str) -> str:
    """Traduce el Markdown habitual de los agentes al HTML que acepta Telegram.

    Se convierte **cada bloque después de trocearlo**, así las etiquetas nunca
    quedan abiertas entre dos mensajes.
    """
    fragmentos: list[str] = []

    def guardar(fragmento: str) -> str:
        fragmentos.append(fragmento)
        return f"\x00{len(fragmentos) - 1}\x00"

    # Bloques ```...``` primero: su contenido no se interpreta como Markdown.
    texto = re.sub(
        r"```[a-zA-Z0-9+#-]*\n?(.*?)```",
        lambda m: guardar(f"<pre>{html.escape(m.group(1).strip(chr(10)), quote=False)}</pre>"),
        text,
        flags=re.S,
    )
    # Código en línea.
    texto = re.sub(
        r"`([^`\n]+)`",
        lambda m: guardar(f"<code>{html.escape(m.group(1), quote=False)}</code>"),
        texto,
    )

    texto = html.escape(texto, quote=False)

    def enlace(m: re.Match[str]) -> str:
        etiqueta, url = m.group(1), html.unescape(m.group(2))
        if not url.lower().startswith(("http://", "https://")):
            return m.group(0)
        return f'<a href="{html.escape(url, quote=True)}">{etiqueta}</a>'

    texto = re.sub(r"\[([^\]\n]+)\]\(([^)\s]+)\)", enlace, texto)
    texto = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texto, flags=re.S)
    texto = re.sub(r"__(.+?)__", r"<b>\1</b>", texto, flags=re.S)
    texto = re.sub(r"~~(.+?)~~", r"<s>\1</s>", texto, flags=re.S)
    # Cursiva con asteriscos o guiones bajos sueltos (nunca dentro de palabras).
    texto = re.sub(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", texto)
    texto = re.sub(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])", r"<i>\1</i>", texto)
    # Encabezados: Telegram no tiene <h1>, se muestran como negrita.
    texto = re.sub(r"(?m)^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", r"<b>\1</b>", texto)
    # Viñetas Markdown a un símbolo estable (sin romper tablas ni restas).
    texto = re.sub(r"(?m)^(\s*)[*-]\s+", r"\1• ", texto)

    for indice, fragmento in enumerate(fragmentos):
        texto = texto.replace(f"\x00{indice}\x00", fragmento)
    return texto.strip()


class TelegramClient:
    def __init__(
        self,
        token: str,
        *,
        enabled: bool = True,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ):
        self._token = token
        self._enabled = enabled
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.Client:
        return httpx.Client(timeout=self._timeout, transport=self._transport)

    def _post(self, method: str, payload: dict) -> dict:
        if not self._token:
            raise TelegramError(
                "Falta TELEGRAM_TOKEN: no se puede enviar nada a Telegram.",
                detail="token vacío",
            )
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        try:
            with self._client() as client:
                response = client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise TelegramError(
                "No pude conectarme con Telegram.",
                detail=f"{type(exc).__name__}: {exc}",
            ) from exc
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code == 429:
            retry_after = float((data.get("parameters") or {}).get("retry_after") or 1)
            raise _RateLimited(min(retry_after, MAX_RETRY_WAIT))
        if response.status_code != 200 or not data.get("ok"):
            description = data.get("description") or response.text[:200]
            raise TelegramError(
                "Telegram rechazó el mensaje.",
                detail=f"HTTP {response.status_code}: {description}",
            )
        return data

    def send_message(self, chat_id: int | str, text: str, *, reply_to: int | None = None) -> list[int]:
        """Envía el texto (partido si hace falta) y devuelve los message_id."""
        if not self._enabled:
            # El chat_id es dato personal: solo va su hash, que agrega el formatter.
            logger.info("telegram_send_disabled", extra={"chars": len(text or "")})
            return []

        return [
            self._send_block(chat_id, bloque, reply_to if indice == 0 else None)
            for indice, bloque in enumerate(chunk_text(text))
        ]

    def _send_block(self, chat_id: int | str, bloque: str, reply_to: int | None) -> int:
        base = {"chat_id": chat_id, "disable_web_page_preview": True}
        if reply_to:
            base["reply_to_message_id"] = reply_to
        try:
            return self._send_with_retry({**base, "text": to_html(bloque), "parse_mode": "HTML"})
        except TelegramError as exc:
            if not any(marca in exc.detail.lower() for marca in PARSE_ERRORS):
                raise
            logger.warning("markdown_rechazado", extra={"detail": exc.detail})
            return self._send_with_retry({**base, "text": bloque})

    def _send_with_retry(self, payload: dict) -> int:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                data = self._post("sendMessage", payload)
                return int((data.get("result") or {}).get("message_id") or 0)
            except _RateLimited as limited:
                if attempt == MAX_RETRIES:
                    raise TelegramError(
                        "Telegram está limitando el envío; probá en unos segundos.",
                        detail=f"429 tras {attempt} intentos",
                    ) from None
                time.sleep(limited.wait)
        raise TelegramError("Telegram no aceptó el mensaje.", detail="reintentos agotados")

    def send_typing(self, chat_id: int | str) -> None:
        """Aviso cosmético: si falla, no debe romper la consulta."""
        if not self._enabled:
            return
        try:
            self._post("sendChatAction", {"chat_id": chat_id, "action": "typing"})
        except (TelegramError, _RateLimited) as exc:
            logger.debug("telegram_typing_failed", extra={"error": str(exc)})


class _RateLimited(Exception):
    def __init__(self, wait: float):
        super().__init__(f"429: esperar {wait}s")
        self.wait = wait
