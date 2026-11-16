"""Envío a Telegram: Markdown→HTML, troceado, reintentos 429 y errores `ok:false`."""

import json

import httpx
import pytest

import gateway.telegram_client as modulo
from gateway.telegram_client import TelegramClient, TelegramError, chunk_text, to_html


def cliente(handler, *, enabled=True) -> TelegramClient:
    return TelegramClient(
        "123:token-de-prueba",
        enabled=enabled,
        transport=httpx.MockTransport(handler),
    )


def ok(message_id=1):
    return httpx.Response(200, json={"ok": True, "result": {"message_id": message_id}})


# ---------- Markdown ----------


def test_negrita_se_convierte_en_html():
    assert to_html("Esto es **importante**.") == "Esto es <b>importante</b>."


def test_cursiva_con_asteriscos_y_guiones_bajos():
    assert to_html("*uno* y _dos_") == "<i>uno</i> y <i>dos</i>"


def test_codigo_en_linea_y_en_bloque():
    assert to_html("Usá `pip install`") == "Usá <code>pip install</code>"
    html = to_html("```python\nprint('hola')\n```")
    assert html == "<pre>print('hola')</pre>"


def test_el_contenido_de_codigo_no_se_interpreta():
    assert to_html("`a **b** c`") == "<code>a **b** c</code>"


def test_encabezado_y_vinetas():
    assert to_html("## Causas") == "<b>Causas</b>"
    assert to_html("- uno\n- dos") == "• uno\n• dos"


def test_enlace_solo_si_es_http():
    assert to_html("[AI Studio](https://aistudio.google.com)") == (
        '<a href="https://aistudio.google.com">AI Studio</a>'
    )
    assert to_html("[raro](javascript:alert(1))") == "[raro](javascript:alert(1))"


def test_se_escapa_html_del_modelo():
    assert to_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_markdown_no_rompe_palabras_con_guion_bajo():
    assert to_html("agente_profesor_historia") == "agente_profesor_historia"


def test_tachado():
    assert to_html("~~viejo~~") == "<s>viejo</s>"


# ---------- troceado ----------


def test_texto_corto_un_bloque():
    assert chunk_text("hola") == ["hola"]


def test_texto_vacio_no_es_un_bloque():
    assert chunk_text("   ") == []


def test_trocea_por_parrafos_y_respeta_el_limite():
    parrafos = ["palabra " * 20 for _ in range(30)]
    bloques = chunk_text("\n\n".join(parrafos), limit=500)
    assert len(bloques) > 1
    assert all(len(bloque) <= 500 for bloque in bloques)


def test_una_palabra_gigante_se_corta_igual():
    bloques = chunk_text("x" * 250, limit=100)
    assert all(len(bloque) <= 100 for bloque in bloques)
    assert "".join(bloques) == "x" * 250


def test_cada_bloque_tiene_html_balanceado():
    texto = "\n\n".join(f"**Párrafo {i}** con *cursiva* y `código`" for i in range(50))
    for bloque in chunk_text(texto, limit=300):
        html = to_html(bloque)
        assert html.count("<b>") == html.count("</b>")
        assert html.count("<i>") == html.count("</i>")


# ---------- envío ----------


def test_envia_con_parse_mode_html():
    enviados = []

    def handler(request):
        enviados.append(json.loads(request.content))
        return ok()

    ids = cliente(handler).send_message(42, "**Hola**")
    assert ids == [1]
    assert enviados[0]["parse_mode"] == "HTML"
    assert enviados[0]["text"] == "<b>Hola</b>"
    assert enviados[0]["chat_id"] == 42


def test_respuesta_larga_se_parte_en_varios_mensajes():
    enviados = []

    def handler(request):
        enviados.append(json.loads(request.content))
        return ok(len(enviados))

    ids = cliente(handler).send_message(42, "palabra " * 1000)
    assert len(ids) == len(enviados) > 1
    assert all(len(payload["text"]) <= 4000 for payload in enviados)


def test_si_telegram_rechaza_el_markdown_se_reenvia_plano():
    enviados = []

    def handler(request):
        payload = json.loads(request.content)
        enviados.append(payload)
        if len(enviados) == 1:
            return httpx.Response(
                400,
                json={"ok": False, "description": "Bad Request: can't parse entities"},
            )
        return ok()

    cliente(handler).send_message(42, "**Hola**")
    assert enviados[0]["parse_mode"] == "HTML"
    assert "parse_mode" not in enviados[1]
    assert enviados[1]["text"] == "**Hola**"


def test_429_espera_y_reintenta(monkeypatch):
    esperas = []
    monkeypatch.setattr(modulo.time, "sleep", esperas.append)
    respuestas = [
        httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 2}}),
        ok(9),
    ]

    def handler(_request):
        return respuestas.pop(0)

    assert cliente(handler).send_message(42, "hola") == [9]
    assert esperas == [2.0]


def test_429_agotado_es_error_claro(monkeypatch):
    monkeypatch.setattr(modulo.time, "sleep", lambda _s: None)

    def handler(_request):
        return httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 1}})

    with pytest.raises(TelegramError) as excinfo:
        cliente(handler).send_message(42, "hola")
    assert "limitando" in str(excinfo.value)


def test_ok_false_con_http_200_es_error():
    def handler(_request):
        return httpx.Response(200, json={"ok": False, "description": "chat not found"})

    with pytest.raises(TelegramError) as excinfo:
        cliente(handler).send_message(42, "hola")
    assert "chat not found" in excinfo.value.detail


def test_dry_run_no_envia_nada():
    llamadas = []

    def handler(request):
        llamadas.append(request)
        return ok()

    assert cliente(handler, enabled=False).send_message(42, "hola") == []
    assert llamadas == []


def test_sin_token_falla_antes_de_la_red():
    with pytest.raises(TelegramError) as excinfo:
        TelegramClient("").send_message(42, "hola")
    assert "TELEGRAM_TOKEN" in str(excinfo.value)


def test_error_de_red_es_telegram_error():
    def handler(request):
        raise httpx.ConnectError("sin red", request=request)

    with pytest.raises(TelegramError) as excinfo:
        cliente(handler).send_message(42, "hola")
    assert "conectarme" in str(excinfo.value)
    assert "token-de-prueba" not in excinfo.value.detail
