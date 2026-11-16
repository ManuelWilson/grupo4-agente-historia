"""Canal Telegram: comandos, entradas inválidas, contexto por chat y límites."""

from gateway.a2a_client import AgentReply
from gateway.config import Settings
from gateway.service import (
    GatewayService,
    TEXTO_AYUDA,
    TEXTO_RESET,
    TEXTO_START,
)

ENV = {
    "A2A_HISTORIA_URL": "http://127.0.0.1:2025",
    "A2A_GEOGRAFIA_URL": "http://127.0.0.1:2026",
    "TELEGRAM_ALLOW_ALL": "true",
}


class FakeClient:
    def __init__(self, respuestas: dict | None = None):
        self.respuestas = respuestas or {}
        self.llamadas: list[tuple[str, str]] = []

    def send_text(self, target, text, context_id=None, headers=None):
        self.llamadas.append((target.label, context_id or ""))
        return AgentReply(target.label, "completed", self.respuestas.get(target.label, "respuesta"))


def servicio(env=None, respuestas=None, llm_router=None) -> GatewayService:
    settings = Settings.from_env({**ENV, **(env or {})})
    return GatewayService(settings, client=FakeClient(respuestas), llm_router=llm_router)


def test_start_explica_el_bot_y_los_comandos():
    gw = servicio()
    reply = gw.handle_chat(42, 7, "/start")
    assert reply.ok is True
    assert reply.text == TEXTO_START
    assert "/reset" in reply.text
    assert gw.client.llamadas == []


def test_help_devuelve_ejemplos():
    gw = servicio()
    reply = gw.handle_chat(42, 7, "/help")
    assert reply.text == TEXTO_AYUDA
    assert "Revolución Francesa" in reply.text


def test_start_con_sufijo_de_grupo_se_reconoce():
    gw = servicio()
    assert gw.handle_chat(42, 7, "/start@history_teacher_taller_bot").text == TEXTO_START


def test_reset_rota_el_contexto_y_olvida_la_ruta():
    gw = servicio({"Historia": "respuesta histórica"}, llm_router=lambda _t: "generica")
    gw.handle_chat(42, 7, "¿Qué fue la Ilustración?")
    contexto_previo = gw.context_for_chat(42)
    gw.handle_chat(42, 7, "/reset")
    assert gw.handle_chat(42, 7, "/reset").text == TEXTO_RESET
    assert gw.context_for_chat(42) != contexto_previo

    # Sin contexto previo, un seguimiento ya no hereda historia: no inventa.
    reply = gw.handle_chat(42, 7, "¿De qué te pregunté antes?")
    assert reply.route == "generica"


def test_comando_desconocido_no_adivina():
    gw = servicio()
    reply = gw.handle_chat(42, 7, "/borrar")
    assert reply.ok is False
    assert reply.error == "comando_desconocido"
    assert "/help" in reply.text
    assert gw.client.llamadas == []


def test_foto_y_voz_se_rechazan_con_ejemplos():
    gw = servicio()
    for tipo, palabra in (("photo", "foto"), ("voice", "nota de voz"), ("document", "documento")):
        reply = gw.handle_chat(42, 7, "", media_type=tipo)
        assert reply.ok is False
        assert reply.error == "tipo_no_soportado"
        assert palabra in reply.text
        assert "Revolución Francesa" in reply.text
    assert gw.client.llamadas == []


def test_texto_vacio_pide_ejemplos():
    gw = servicio()
    reply = gw.handle_chat(42, 7, "   ")
    assert reply.ok is False
    assert reply.text == TEXTO_AYUDA


def test_texto_demasiado_largo_se_rechaza():
    gw = servicio({"MAX_INPUT_CHARS": "50"})
    reply = gw.handle_chat(42, 7, "historia " * 20)
    assert reply.ok is False
    assert "demasiado larga" in reply.text
    assert gw.client.llamadas == []


def test_acceso_rechazado_no_llama_al_agente_ni_con_comandos():
    gw = servicio({"TELEGRAM_ALLOW_ALL": "false", "TELEGRAM_ALLOWED_CHAT_IDS": "999"})
    for texto in ("/start", "/help", "¿Qué fue la Ilustración?"):
        reply = gw.handle_chat(42, 7, texto)
        assert reply.ok is False
        assert "No estoy autorizado" in reply.text
    assert gw.client.llamadas == []


def test_acceso_autorizado_por_usuario():
    gw = servicio({"TELEGRAM_ALLOW_ALL": "false", "TELEGRAM_ALLOWED_USER_IDS": "7"})
    reply = gw.handle_chat(42, 7, "¿Qué fue la Ilustración?")
    assert reply.ok is True
    assert reply.route == "historia"


def test_contexto_estable_por_chat_entre_mensajes():
    gw = servicio()
    gw.handle_chat(42, 7, "¿Qué fue la Ilustración?")
    gw.handle_chat(42, 7, "¿Y la Revolución Francesa?")
    contextos = [contexto for _, contexto in gw.client.llamadas]
    assert len(set(contextos)) == 1


def test_chats_distintos_no_comparten_contexto():
    gw = servicio()
    gw.handle_chat(42, 7, "¿Qué fue la Ilustración?")
    gw.handle_chat(43, 8, "¿Qué fue la Ilustración?")
    contextos = {contexto for _, contexto in gw.client.llamadas}
    assert len(contextos) == 2


def test_limite_por_minuto_no_gasta_cuota_con_entradas_invalidas():
    gw = servicio({"RATE_LIMIT_PER_MINUTE": "1", "RATE_LIMIT_PER_DAY": "0"})

    # Una foto no consume cupo: se rechaza antes de contar.
    assert gw.handle_chat(42, 7, "", media_type="photo").ok is False

    assert gw.handle_chat(42, 7, "¿Qué fue la Ilustración?").ok is True
    segunda = gw.handle_chat(42, 7, "¿Y la Revolución Francesa?")
    assert segunda.ok is False
    assert segunda.error == "limite_de_uso"
    assert "por minuto" in segunda.text
    assert len(gw.client.llamadas) == 1


def test_limite_diario():
    gw = servicio({"RATE_LIMIT_PER_MINUTE": "0", "RATE_LIMIT_PER_DAY": "1"})
    assert gw.handle_chat(42, 7, "¿Qué fue la Ilustración?").ok is True
    reply = gw.handle_chat(42, 7, "¿Y la Revolución Francesa?")
    assert reply.ok is False
    assert "diario" in reply.text


def test_limite_se_cuenta_por_usuario():
    gw = servicio({"RATE_LIMIT_PER_MINUTE": "1", "RATE_LIMIT_PER_DAY": "0"})
    assert gw.handle_chat(42, 7, "¿Qué fue la Ilustración?").ok is True
    assert gw.handle_chat(43, 7, "¿Qué fue la Ilustración?").ok is False
    assert gw.handle_chat(44, 8, "¿Qué fue la Ilustración?").ok is True


def test_comandos_no_consumen_cuota():
    gw = servicio({"RATE_LIMIT_PER_MINUTE": "1", "RATE_LIMIT_PER_DAY": "0"})
    gw.handle_chat(42, 7, "/help")
    gw.handle_chat(42, 7, "/help")
    assert gw.handle_chat(42, 7, "¿Qué fue la Ilustración?").ok is True
