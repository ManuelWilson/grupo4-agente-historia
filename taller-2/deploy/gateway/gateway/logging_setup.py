"""Configuración de logs común al gateway y al bot local.

Dos formatos:
- `json` (default): una línea JSON por evento, con request_id/update_id/chat hash.
  Es el que se usa para las evidencias.
- `text`: formato legible mientras se desarrolla.

Los clientes HTTP (httpx/httpcore) registran la URL completa en nivel INFO. En
Telegram esa URL incluye el token del bot (`/bot<token>/sendMessage`), así que ese
logger se deja en WARNING: el token nunca debe llegar a un archivo de log.
"""

from __future__ import annotations

import logging

from gateway.observability import JsonFormatter

# Librerías que escriben la URL completa de cada request.
NOISY_LOGGERS = ("httpx", "httpx2", "httpcore", "urllib3")
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s :: %(message)s"


def configure(level: str = "INFO", fmt: str = "json") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter(TEXT_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
