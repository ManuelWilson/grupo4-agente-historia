"""Configuración del gateway, validada al arrancar.

Una variable faltante o inválida debe fallar con un mensaje que diga *cuál* es y
dónde mirar, no con un `KeyError` a mitad de una consulta.

El `.env` es opcional: si existe se carga, pero las variables reales del entorno
tienen prioridad (comportamiento por defecto de `python-dotenv`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:  # el .env es una comodidad local; en Lambda no existe
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv está en requirements
    pass

TRUE_VALUES = {"1", "true", "yes", "si", "sí", "on"}
FALSE_VALUES = {"0", "false", "no", "off"}


class ConfigError(RuntimeError):
    """Configuración incompleta o inválida."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        detail = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(
            "Configuración inválida del gateway:\n"
            f"{detail}\n"
            "Revisá `.env.example` y el README; las variables reales van en tu .env local "
            "(nunca en el repositorio)."
        )


def _text(env: dict[str, str], name: str, default: str = "") -> str:
    return (env.get(name) or default).strip()


def _number(
    env: dict[str, str],
    name: str,
    default: float,
    problems: list[str],
    minimum: float | None = None,
) -> float:
    raw = _text(env, name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        problems.append(f"{name} debe ser numérico (recibido: {raw!r}).")
        return default
    if minimum is not None and value < minimum:
        problems.append(f"{name} debe ser mayor o igual a {minimum} (recibido: {raw!r}).")
    return value


def _flag(
    env: dict[str, str], name: str, default: bool, problems: list[str]
) -> bool:
    raw = _text(env, name).lower()
    if not raw:
        return default
    if raw in TRUE_VALUES:
        return True
    if raw in FALSE_VALUES:
        return False
    problems.append(f"{name} debe ser true o false (recibido: {raw!r}).")
    return default


def _ids(env: dict[str, str], name: str) -> frozenset[str]:
    raw = _text(env, name)
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


@dataclass(frozen=True)
class Settings:
    """Configuración completa y ya validada."""

    google_api_key: str
    model: str
    a2a_timeout: float
    max_input_chars: int
    historia_url: str
    historia_graph: str
    historia_assistant_id: str
    geografia_url: str
    geografia_graph: str
    geografia_assistant_id: str
    a2a_shared_token: str
    telegram_token: str
    telegram_secret: str
    telegram_allowed_chat_ids: frozenset[str]
    telegram_allowed_user_ids: frozenset[str]
    telegram_allow_all: bool
    telegram_send_enabled: bool
    rate_limit_per_minute: int
    rate_limit_per_day: int
    local_api_token: str
    host: str
    port: int
    log_level: str
    log_format: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def llm_enabled(self) -> bool:
        return bool(self.google_api_key)

    @classmethod
    def from_env(
        cls,
        env: dict[str, str] | None = None,
        *,
        needs_local_api: bool = False,
    ) -> "Settings":
        env = dict(os.environ) if env is None else env
        problems: list[str] = []
        warnings: list[str] = []

        historia_url = _text(env, "A2A_HISTORIA_URL")
        geografia_url = _text(env, "A2A_GEOGRAFIA_URL")
        for name, value in (
            ("A2A_HISTORIA_URL", historia_url),
            ("A2A_GEOGRAFIA_URL", geografia_url),
        ):
            if not value:
                problems.append(f"Falta {name} (por ejemplo http://127.0.0.1:2025).")
            elif not value.startswith(("http://", "https://")):
                problems.append(f"{name} debe empezar con http:// o https:// (recibido: {value!r}).")

        historia_graph = _text(env, "A2A_HISTORIA_GRAPH", "agente_profesor_historia")
        geografia_graph = _text(env, "A2A_GEOGRAFIA_GRAPH", "agente_profesor_geografia")

        google_api_key = _text(env, "GOOGLE_API_KEY")
        if not google_api_key:
            warnings.append(
                "Sin GOOGLE_API_KEY: el router usa solo palabras clave "
                "(sin clasificación por LLM)."
            )

        a2a_shared_token = _text(env, "A2A_SHARED_TOKEN")
        if not a2a_shared_token:
            warnings.append(
                "Sin A2A_SHARED_TOKEN: el gateway no autentica contra los agentes. "
                "En producción configurá el mismo token en gateway y agentes."
            )

        local_api_token = _text(env, "LOCAL_API_TOKEN")
        if needs_local_api and not local_api_token:
            problems.append(
                "Falta LOCAL_API_TOKEN: protege POST /v1/chat. "
                'Generá uno con python -c "import secrets; print(secrets.token_urlsafe(32))".'
            )

        allow_all = _flag(env, "TELEGRAM_ALLOW_ALL", False, problems)
        allowed_chats = _ids(env, "TELEGRAM_ALLOWED_CHAT_IDS")
        allowed_users = _ids(env, "TELEGRAM_ALLOWED_USER_IDS")
        if not allow_all and not allowed_chats and not allowed_users:
            warnings.append(
                "Sin TELEGRAM_ALLOWED_CHAT_IDS/USER_IDS y con TELEGRAM_ALLOW_ALL=false: "
                "el canal de Telegram rechaza a todos (falla cerrado)."
            )

        port = int(_number(env, "PORT", 8000, problems, minimum=1))
        a2a_timeout = _number(env, "A2A_TIMEOUT_SECONDS", 45.0, problems, minimum=1)
        max_input_chars = int(_number(env, "MAX_INPUT_CHARS", 2000, problems, minimum=1))
        # Límite de uso por chat/usuario. 0 desactiva ese límite (útil en pruebas).
        rate_limit_per_minute = int(
            _number(env, "RATE_LIMIT_PER_MINUTE", 6, problems, minimum=0)
        )
        rate_limit_per_day = int(
            _number(env, "RATE_LIMIT_PER_DAY", 100, problems, minimum=0)
        )
        telegram_send_enabled = _flag(env, "TELEGRAM_SEND_ENABLED", True, problems)
        log_format = _text(env, "LOG_FORMAT", "json").lower()
        if log_format not in ("json", "text"):
            problems.append(f"LOG_FORMAT debe ser json o text (recibido: {log_format!r}).")

        if problems:
            raise ConfigError(problems)

        return cls(
            google_api_key=google_api_key,
            model=_text(env, "MODELO", "gemini-3.5-flash-lite"),
            a2a_timeout=a2a_timeout,
            max_input_chars=max_input_chars,
            historia_url=historia_url.rstrip("/"),
            historia_graph=historia_graph,
            historia_assistant_id=_text(env, "A2A_HISTORIA_ASSISTANT_ID"),
            geografia_url=geografia_url.rstrip("/"),
            geografia_graph=geografia_graph,
            geografia_assistant_id=_text(env, "A2A_GEOGRAFIA_ASSISTANT_ID"),
            a2a_shared_token=a2a_shared_token,
            telegram_token=_text(env, "TELEGRAM_TOKEN"),
            telegram_secret=_text(env, "TELEGRAM_SECRET"),
            telegram_allowed_chat_ids=allowed_chats,
            telegram_allowed_user_ids=allowed_users,
            telegram_allow_all=allow_all,
            telegram_send_enabled=telegram_send_enabled,
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_day=rate_limit_per_day,
            local_api_token=local_api_token,
            host=_text(env, "HOST", "127.0.0.1"),
            port=port,
            log_level=_text(env, "LOG_LEVEL", "INFO").upper(),
            log_format=log_format,
            warnings=tuple(warnings),
        )

    def summary(self) -> dict:
        """Resumen seguro para `/health` y logs: nunca incluye tokens."""
        return {
            "model": self.model,
            "llm_enabled": self.llm_enabled,
            "a2a_timeout": self.a2a_timeout,
            "agents": {
                "historia": self.historia_url,
                "geografia": self.geografia_url,
            },
            "max_input_chars": self.max_input_chars,
            "rate_limit_per_minute": self.rate_limit_per_minute,
            "rate_limit_per_day": self.rate_limit_per_day,
            "telegram_send_enabled": self.telegram_send_enabled,
            "telegram_allow_all": self.telegram_allow_all,
            "telegram_allowlist": len(self.telegram_allowed_chat_ids)
            + len(self.telegram_allowed_user_ids),
            "a2a_auth_enabled": bool(self.a2a_shared_token),
        }
