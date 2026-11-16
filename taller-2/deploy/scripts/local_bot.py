#!/usr/bin/env python3
"""Bot de Telegram por *long polling*, solo para probar en local.

    python deploy/scripts/local_bot.py

Usa `TELEGRAM_TOKEN_LOCAL`, un bot de **prueba** distinto del de producción.
`getUpdates` borra el webhook, así que el script se niega a arrancar si el token
local coincide con `TELEGRAM_TOKEN` (el de la nube): si eso pasara, el bot que
responde en producción dejaría de recibir mensajes.

No necesita ngrok ni Function URL: habla con los agentes A2A directo, con el
mismo `GatewayService` que usan el webhook y `/v1/chat`. Requiere los dos
`langgraph dev` levantados.

Todo lo que muestra en consola es seguro: nunca imprime el token.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = REPO_ROOT / "deploy" / "gateway"
SECURE_ENV = Path.home() / ".config" / "taller2" / ".env"

logger = logging.getLogger("local_bot")


def load_env() -> None:
    """Carga el `.env` del proyecto y el `.env` seguro; el entorno real manda."""
    try:
        from dotenv import load_dotenv

        load_dotenv(REPO_ROOT / ".env", override=False)
        load_dotenv(SECURE_ENV, override=False)
    except ImportError:
        logger.warning("python-dotenv no está instalado: solo se usarán variables del entorno")


def telegram(method: str, token: str, payload: dict | None = None, timeout: float = 40):
    """Llama a la Bot API sin exponer el token en errores."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        detalle = exc.read().decode(errors="replace")[:200]
        raise TelegramAPIError(f"{method}: HTTP {exc.code} {detalle}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise TelegramAPIError(f"{method}: sin conexión ({type(exc).__name__})") from None


class TelegramAPIError(RuntimeError):
    """Fallo de la Bot API; el mensaje nunca incluye el token."""


def validar_token(local: str, produccion: str) -> None:
    if not local:
        raise SystemExit(
            "Falta TELEGRAM_TOKEN_LOCAL. Creá un bot de prueba en @BotFather y guardá su token "
            f"en {SECURE_ENV} (nunca en el proyecto)."
        )
    if ":" not in local:
        raise SystemExit("TELEGRAM_TOKEN_LOCAL no tiene forma de token de Telegram (<id>:<secreto>).")
    if produccion and local == produccion:
        raise SystemExit(
            "TELEGRAM_TOKEN_LOCAL es igual a TELEGRAM_TOKEN (el de producción). "
            "Long polling borraría el webhook del bot real. Usá un bot de prueba distinto."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Bot de Telegram local por long polling.")
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    load_env()

    # El paquete del gateway vive en deploy/gateway:
    if str(GATEWAY_DIR) not in sys.path:
        sys.path.insert(0, str(GATEWAY_DIR))

    from gateway.config import ConfigError, Settings
    from gateway.logging_setup import configure as configure_logging
    from gateway.observability import end_request, start_request
    from gateway.service import GatewayService
    from gateway.telegram_client import TelegramClient, TelegramError
    from gateway.telegram_update import parse_update

    # Nunca loguear la URL de los requests: incluye el token del bot.
    configure_logging(args.log_level)

    local = (os.environ.get("TELEGRAM_TOKEN_LOCAL") or "").strip()
    produccion = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    validar_token(local, produccion)

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        raise SystemExit(str(exc)) from None

    for aviso in settings.warnings:
        logger.warning(aviso)

    service = GatewayService(settings)
    cliente = TelegramClient(local, enabled=settings.telegram_send_enabled)

    # Solo afecta a este bot de prueba: se asegura de que no quede un webhook.
    try:
        telegram("deleteWebhook", local, {"drop_pending_updates": False})
        info = telegram("getWebhookInfo", local)
    except TelegramAPIError as exc:
        raise SystemExit(f"No pude preparar el bot de prueba: {exc}") from None
    if (info.get("result") or {}).get("url"):
        raise SystemExit("El bot de prueba todavía tiene un webhook configurado.")

    print("Bot local escuchando. Ctrl+C para detener.")
    print(f"  agentes: historia={settings.historia_url} geografia={settings.geografia_url}")
    print(f"  allowlist: {len(settings.telegram_allowed_chat_ids)} chat(s), "
          f"allow_all={settings.telegram_allow_all}")
    print(f"  enviar a Telegram: {settings.telegram_send_enabled}")
    print(f"  límites: {settings.rate_limit_per_minute}/min, {settings.rate_limit_per_day}/día, "
          f"máx {settings.max_input_chars} caracteres")

    offset = 0
    while True:
        try:
            data = telegram(
                "getUpdates",
                local,
                {"offset": offset, "timeout": 25, "allowed_updates": ["message", "edited_message"]},
                timeout=40,
            )
        except TelegramAPIError as exc:
            if "HTTP 401" in str(exc) or "HTTP 404" in str(exc):
                raise SystemExit(f"El token local fue rechazado: {exc}") from None
            logger.error("getUpdates falló: %s", exc)
            time.sleep(3)
            continue

        for update in data.get("result") or []:
            offset = max(offset, int(update.get("update_id") or 0) + 1)
            mensaje = parse_update(update)
            if mensaje is None:
                continue

            # Correlación: cada update tiene su request_id y su hash de chat.
            tokens = start_request(mensaje.update_id, mensaje.chat_id)
            try:
                cliente.send_typing(mensaje.chat_id)
                respuesta = service.handle_chat(
                    mensaje.chat_id,
                    mensaje.user_id,
                    mensaje.text,
                    media_type=mensaje.media_type,
                )
                try:
                    enviados = cliente.send_message(mensaje.chat_id, respuesta.text)
                    logger.info(
                        "telegram_enviado",
                        extra={
                            "route": respuesta.route,
                            "status": "ok" if respuesta.ok else "error",
                            "mensajes": len(enviados),
                            "chars": len(respuesta.text),
                        },
                    )
                except TelegramError as exc:
                    logger.error(
                        "telegram_error",
                        extra={"status": "error", "error_code": "telegram_error", "detail": exc.detail or str(exc)},
                    )
            finally:
                end_request(tokens)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nBot local detenido.")
