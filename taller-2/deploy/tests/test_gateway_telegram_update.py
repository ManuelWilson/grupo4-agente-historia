"""Lectura de updates de Telegram: texto, foto, voz y mensajes incompletos."""

from gateway.telegram_update import parse_update


def update(**mensaje):
    base = {"message_id": 1, "chat": {"id": 42}, "from": {"id": 7}}
    base.update(mensaje)
    return {"update_id": 100, "message": base}


def test_mensaje_de_texto():
    mensaje = parse_update(update(text="  ¿Qué fue la Ilustración?  "))
    assert mensaje.chat_id == 42
    assert mensaje.user_id == 7
    assert mensaje.text == "¿Qué fue la Ilustración?"
    assert mensaje.media_type is None


def test_foto_con_epigrafe_sigue_siendo_media():
    mensaje = parse_update(update(photo=[{"file_id": "abc"}], caption="mirá esto"))
    assert mensaje.media_type == "photo"
    assert mensaje.text == "mirá esto"


def test_nota_de_voz():
    assert parse_update(update(voice={"file_id": "v"})).media_type == "voice"


def test_edited_message_tambien_cuenta():
    payload = {"edited_message": {"chat": {"id": 42}, "text": "corregido"}}
    assert parse_update(payload).text == "corregido"


def test_update_sin_chat_se_ignora():
    assert parse_update({"message": {"text": "hola"}}) is None


def test_update_que_no_es_dict_se_ignora():
    assert parse_update({}) is None
    assert parse_update({"message": "texto"}) is None
    assert parse_update(None) is None
