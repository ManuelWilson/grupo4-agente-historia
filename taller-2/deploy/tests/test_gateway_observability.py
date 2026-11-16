"""Logs JSON: campos de correlación, hash de chat y ausencia de datos personales."""

import io
import json
import logging

import pytest

from gateway import observability
from gateway.config import Settings
from gateway.observability import (
    JsonFormatter,
    chat_id_hash,
    current_request_id,
    end_request,
    set_message_context,
    start_request,
)
from gateway.service import GatewayService

ENV = {
    "A2A_HISTORIA_URL": "http://127.0.0.1:2025",
    "A2A_GEOGRAFIA_URL": "http://127.0.0.1:2026",
    "TELEGRAM_ALLOW_ALL": "true",
}


def capturar(level=logging.INFO, nombre="gateway.service"):
    """Handler JSON en memoria para inspeccionar las líneas que emite el servicio."""
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger(nombre)
    logger.addHandler(handler)
    logger.setLevel(level)
    return buffer, handler, logger


def eventos(buffer) -> list[dict]:
    return [json.loads(linea) for linea in buffer.getvalue().splitlines() if linea.strip()]


def test_hash_de_chat_es_estable_y_distinto_por_chat():
    assert chat_id_hash(42) == chat_id_hash("42")
    assert chat_id_hash(42) != chat_id_hash(43)
    assert chat_id_hash(None) == ""
    assert "42" not in chat_id_hash(42)


def test_campos_de_correlacion_se_adjuntan_a_cada_linea():
    buffer, handler, logger = capturar()
    tokens = start_request(update_id=777, chat_id=42)
    try:
        logger.info("prueba", extra={"route": "historia", "status": "ok"})
    finally:
        end_request(tokens)
        logger.removeHandler(handler)

    (evento,) = eventos(buffer)
    for campo in ("ts", "level", "logger", "event", "request_id", "update_id", "chat_id_hash"):
        assert campo in evento
    assert evento["event"] == "prueba"
    assert evento["update_id"] == "777"
    assert evento["chat_id_hash"] == chat_id_hash(42)
    assert evento["route"] == "historia"


def test_sin_contexto_los_campos_quedan_vacios():
    buffer, handler, logger = capturar()
    logger.info("suelto")
    logger.removeHandler(handler)

    (evento,) = eventos(buffer)
    assert evento["request_id"] == ""
    assert evento["update_id"] == ""
    assert evento["chat_id_hash"] == ""


def test_set_message_context_no_pisa_el_request_id():
    tokens = start_request(update_id=None, chat_id=None)
    try:
        request_id = current_request_id()
        extra = set_message_context(1234, 99)
        assert current_request_id() == request_id
        end_request(extra)
    finally:
        end_request(tokens)


def test_log_de_consulta_tiene_todos_los_campos_del_plan():
    settings = Settings.from_env({**ENV, "LOG_FORMAT": "json"})
    gw = GatewayService(settings, client=ClienteFalso(), llm_router=lambda _t: None)

    buffer, handler, logger = capturar()
    tokens = start_request(update_id=888, chat_id=42)
    try:
        reply = gw.handle_chat(42, 7, "¿Qué fue la Ilustración?")
    finally:
        end_request(tokens)
        logger.removeHandler(handler)

    assert reply.task_ids == ("task-123",)
    consulta = [evento for evento in eventos(buffer) if evento["event"] == "consulta"][-1]
    assert consulta["route"] == "historia"
    assert consulta["agents"] == "historia"
    assert consulta["a2a_task_id"] == "task-123"
    assert consulta["status"] == "ok"
    assert consulta["latency_ms"] >= 0
    assert consulta["update_id"] == "888"
    assert consulta["chat_id_hash"] == chat_id_hash(42)
    assert "error_code" in consulta


def test_log_no_contiene_el_texto_ni_el_chat_id():
    settings = Settings.from_env({**ENV, "LOG_FORMAT": "json"})
    gw = GatewayService(settings, client=ClienteFalso(), llm_router=lambda _t: None)

    buffer, handler, logger = capturar()
    tokens = start_request(update_id=1, chat_id=987654321)
    try:
        gw.handle_chat(987654321, 7, "mi pregunta secreta sobre la Ilustración")
    finally:
        end_request(tokens)
        logger.removeHandler(handler)

    crudo = buffer.getvalue()
    assert "mi pregunta secreta" not in crudo
    assert "987654321" not in crudo


def test_acceso_rechazado_no_loguea_el_chat_id():
    settings = Settings.from_env(
        {
            **ENV,
            "TELEGRAM_ALLOW_ALL": "false",
            "TELEGRAM_ALLOWED_CHAT_IDS": "111",
            "LOG_FORMAT": "json",
        }
    )
    gw = GatewayService(settings, client=ClienteFalso(), llm_router=lambda _t: None)

    buffer, handler, logger = capturar()
    tokens = start_request(update_id=2, chat_id=555)
    try:
        reply = gw.handle_chat(555, 9, "¿Qué fue la Ilustración?")
    finally:
        end_request(tokens)
        logger.removeHandler(handler)

    assert reply.ok is False
    crudo = buffer.getvalue()
    assert "555" not in crudo
    rechazo = [evento for evento in eventos(buffer) if evento["event"] == "acceso_rechazado"][0]
    assert rechazo["chat_id_hash"] == chat_id_hash(555)
    consulta = [evento for evento in eventos(buffer) if evento["event"] == "consulta"][-1]
    assert consulta["status"] == "error"
    assert consulta["error_code"] == "no_autorizado"


def test_limite_alcanzado_no_loguea_el_id():
    settings = Settings.from_env(
        {**ENV, "RATE_LIMIT_PER_MINUTE": "1", "LOG_FORMAT": "json"}
    )
    gw = GatewayService(settings, client=ClienteFalso(), llm_router=lambda _t: None)

    buffer, handler, logger = capturar()
    tokens = start_request(update_id=3, chat_id=777)
    try:
        gw.handle_chat(777, None, "¿Qué fue la Ilustración?")
        gw.handle_chat(777, None, "¿Y la Revolución Francesa?")
    finally:
        end_request(tokens)
        logger.removeHandler(handler)

    crudo = buffer.getvalue()
    assert "777" not in crudo
    limite = [evento for evento in eventos(buffer) if evento["event"] == "limite_alcanzado"][0]
    assert limite["chat_id_hash"] == chat_id_hash(777)
    assert limite["sujeto"] == "chat"


def test_dry_run_de_telegram_no_loguea_el_chat_id():
    from gateway.telegram_client import TelegramClient

    buffer, handler, logger = capturar(nombre="gateway.telegram_client")
    tokens = start_request(update_id=4, chat_id=123456)
    try:
        TelegramClient(token="123:abc", enabled=False).send_message(123456, "hola")
    finally:
        end_request(tokens)
        logger.removeHandler(handler)

    crudo = buffer.getvalue()
    assert "123456" not in crudo
    evento = eventos(buffer)[0]
    assert evento["event"] == "telegram_send_disabled"
    assert evento["chat_id_hash"] == chat_id_hash(123456)


class ClienteFalso:
    def __init__(self):
        self.llamadas = []

    def send_text(self, target, text, context_id=None, headers=None):
        from gateway.a2a_client import AgentReply

        self.llamadas.append((target.label, context_id))
        return AgentReply(target.label, "completed", "respuesta", task_id="task-123")


def test_log_format_se_valida():
    from gateway.config import ConfigError

    assert Settings.from_env(dict(ENV)).log_format == "json"
    assert Settings.from_env({**ENV, "LOG_FORMAT": "text"}).log_format == "text"
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env({**ENV, "LOG_FORMAT": "xml"})
    assert "LOG_FORMAT" in str(excinfo.value)
