"""Adaptador de Lambda: secreto del webhook, updates sin texto y envío a Telegram."""

import json
from types import SimpleNamespace

import gateway.lambda_handler as adaptador
from gateway.service import Reply


class FakeService:
    def __init__(self, reply=None):
        self.reply = reply or Reply("respuesta", "historia", ("historia",))
        self.llamadas = []

    def handle_chat(self, chat_id, user_id, text="", *, media_type=None):
        self.llamadas.append((chat_id, user_id, text, media_type))
        return self.reply


class FakeTelegram:
    def __init__(self):
        self.enviados = []

    def send_message(self, chat_id, text):
        self.enviados.append((chat_id, text))
        return [1]


def preparar(monkeypatch, reply=None):
    servicio = FakeService(reply)
    telegram = FakeTelegram()
    monkeypatch.setattr(adaptador, "_settings", SimpleNamespace(telegram_secret="secreto", log_level="INFO"))
    monkeypatch.setattr(adaptador, "_service", servicio)
    monkeypatch.setattr(adaptador, "_telegram", telegram)
    return servicio, telegram


def evento(texto="¿Qué fue la Ilustración?", secreto="secreto", **extra):
    headers = {"X-Telegram-Bot-Api-Secret-Token": secreto} if secreto else {}
    mensaje = {
        "message_id": 1,
        "chat": {"id": 42},
        "from": {"id": 7},
    }
    if texto is not None:
        mensaje["text"] = texto
    mensaje.update(extra)
    body = json.dumps({"message": mensaje})
    return {"headers": headers, "body": body}


def test_secreto_incorrecto_es_403(monkeypatch):
    servicio, telegram = preparar(monkeypatch)
    assert adaptador.handle_event(evento(secreto="otro"))["statusCode"] == 403
    assert servicio.llamadas == []
    assert telegram.enviados == []


def test_sin_secreto_es_403(monkeypatch):
    servicio, _ = preparar(monkeypatch)
    assert adaptador.handle_event(evento(secreto=None))["statusCode"] == 403
    assert servicio.llamadas == []


def test_consulta_valida_responde_y_envia(monkeypatch):
    servicio, telegram = preparar(monkeypatch)
    respuesta = adaptador.handle_event(evento())
    assert respuesta["statusCode"] == 200
    assert servicio.llamadas == [(42, 7, "¿Qué fue la Ilustración?", None)]
    assert telegram.enviados == [(42, "respuesta")]


def test_update_sin_texto_igual_recibe_ayuda(monkeypatch):
    servicio, telegram = preparar(monkeypatch)
    assert adaptador.handle_event(evento(texto=None))["statusCode"] == 200
    assert servicio.llamadas == [(42, 7, "", None)]
    assert telegram.enviados == [(42, "respuesta")]


def test_foto_se_deriva_como_media(monkeypatch):
    servicio, _ = preparar(monkeypatch)
    evento_foto = evento(texto=None, photo=[{"file_id": "abc"}])
    assert adaptador.handle_event(evento_foto)["statusCode"] == 200
    assert servicio.llamadas == [(42, 7, "", "photo")]


def test_body_invalido_es_400(monkeypatch):
    preparar(monkeypatch)
    payload = {"headers": {"x-telegram-bot-api-secret-token": "secreto"}, "body": "{no es json"}
    assert adaptador.handle_event(payload)["statusCode"] == 400


def test_fallo_del_agente_igual_responde_200(monkeypatch):
    preparar(monkeypatch, reply=Reply("No pude consultar.", "historia", ("historia",), ok=False, error="A2AError"))
    respuesta = adaptador.handle_event(evento())
    assert respuesta["statusCode"] == 200
