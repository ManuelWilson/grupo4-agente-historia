"""Servicio: rutas, contexto por agente, fallos parciales y control de acceso."""

import uuid

import pytest

from gateway.a2a_client import A2AConnectionError, AgentReply
from gateway.config import Settings
from gateway.service import TEXTO_GENERICA, GatewayService

ENV = {
    "A2A_HISTORIA_URL": "http://127.0.0.1:2025",
    "A2A_GEOGRAFIA_URL": "http://127.0.0.1:2026",
    "TELEGRAM_ALLOW_ALL": "true",
}


class FakeClient:
    def __init__(self, respuestas: dict):
        self.respuestas = respuestas
        self.llamadas: list[tuple[str, str]] = []

    def send_text(self, target, text, context_id=None, headers=None):
        self.llamadas.append((target.label, context_id or ""))
        respuesta = self.respuestas.get(target.label, "respuesta")
        if isinstance(respuesta, Exception):
            raise respuesta
        return AgentReply(target.label, "completed", respuesta)


def servicio(respuestas=None, llm_router=None, env=None) -> GatewayService:
    settings = Settings.from_env({**ENV, **(env or {})})
    return GatewayService(settings, client=FakeClient(respuestas or {}), llm_router=llm_router)


def test_historia_usa_su_agente():
    gw = servicio({"Historia": "La Ilustración fue un movimiento del siglo XVIII."})
    reply = gw.handle("¿Qué fue la Ilustración?")
    assert reply.ok is True
    assert reply.route == "historia"
    assert reply.agents == ("historia",)
    assert "siglo XVIII" in reply.text
    assert [llamada[0] for llamada in gw.client.llamadas] == ["Historia"]


def test_geografia_usa_su_agente():
    gw = servicio({"Geografía": "Un delta se forma por sedimentación."})
    reply = gw.handle("¿Cómo se forma un delta fluvial?")
    assert reply.route == "geografia"
    assert reply.agents == ("geografia",)


def test_mixta_consulta_los_dos_con_contexto_distinto():
    gw = servicio({"Historia": "parte histórica", "Geografía": "parte geográfica"})
    reply = gw.handle("Compará la Revolución Francesa con el relieve de los Andes", "ctx-1")

    assert reply.route == "mixta"
    assert set(reply.agents) == {"historia", "geografia"}
    assert "Historia:" in reply.text and "Geografía:" in reply.text

    contextos = {label: contexto for label, contexto in gw.client.llamadas}
    assert len(set(contextos.values())) == 2
    assert contextos["Historia"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "ctx-1:historia"))
    assert contextos["Geografía"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "ctx-1:geografia"))


def test_mixta_con_un_fallo_lo_dice_y_no_inventa():
    gw = servicio({"Historia": "parte histórica", "Geografía": A2AConnectionError("sin conexión")})
    reply = gw.handle("Compará la Revolución Francesa con el relieve de los Andes")

    assert reply.ok is True  # una mitad respondió
    assert "parte histórica" in reply.text
    assert "No pude consultar al agente de Geografía" in reply.text


def test_mixta_con_ambos_fallos_es_error():
    gw = servicio(
        {"Historia": A2AConnectionError("sin conexión"), "Geografía": A2AConnectionError("sin conexión")}
    )
    reply = gw.handle("Compará la Revolución Francesa con el relieve de los Andes")
    assert reply.ok is False
    assert "Historia" in reply.text and "Geografía" in reply.text


def test_generica_pide_tema():
    gw = servicio(llm_router=lambda _texto: "generica")
    reply = gw.handle("contame un chiste")
    assert reply.route == "generica"
    assert reply.text == TEXTO_GENERICA
    assert gw.client.llamadas == []


def test_sin_clasificar_no_llama_agentes():
    gw = servicio(llm_router=lambda _texto: None)
    reply = gw.handle("contame un chiste")
    assert reply.route == "sin_clasificar"
    assert reply.ok is False
    assert gw.client.llamadas == []


def test_seguimiento_hereda_el_agente_del_contexto():
    gw = servicio({"Historia": "respuesta histórica"}, llm_router=lambda _texto: "generica")

    primera = gw.handle("¿Qué fue la Ilustración?", "ctx-A")
    segunda = gw.handle("¿De qué te pregunté antes?", "ctx-A")

    assert primera.route == "historia"
    assert segunda.route == "historia"
    assert segunda.ok is True
    assert [label for label, _ in gw.client.llamadas] == ["Historia", "Historia"]


def test_seguimiento_sin_contexto_previo_no_inventa():
    gw = servicio(llm_router=lambda _texto: "generica")
    reply = gw.handle("contame un chiste", "ctx-nuevo")
    assert reply.route == "generica"
    assert gw.client.llamadas == []


def test_texto_vacio():
    gw = servicio()
    assert gw.handle("   ").ok is False
    assert gw.client.llamadas == []


def test_texto_demasiado_largo():
    gw = servicio()
    reply = gw.handle("historia " * 400)
    assert reply.ok is False
    assert "demasiado larga" in reply.text


def test_allowlist_falla_cerrado():
    gw = servicio(env={"TELEGRAM_ALLOW_ALL": "false"})
    reply = gw.handle("¿Qué fue la Ilustración?", chat_id=42, user_id=7)
    assert reply.ok is False
    assert "No estoy autorizado" in reply.text
    assert gw.client.llamadas == []


def test_allowlist_autoriza_por_chat():
    gw = servicio(env={"TELEGRAM_ALLOW_ALL": "false", "TELEGRAM_ALLOWED_CHAT_IDS": "42"})
    assert gw.is_allowed(42, None) == (True, "chat autorizado")
    assert gw.is_allowed(43, None)[0] is False


def test_allow_all_para_desarrollo():
    gw = servicio()
    assert gw.is_allowed(999, 999)[0] is True
