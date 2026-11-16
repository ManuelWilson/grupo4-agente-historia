"""Validación de configuración: falla temprano y con mensajes útiles."""

import json

import pytest

from gateway.config import ConfigError, Settings

BASE = {
    "A2A_HISTORIA_URL": "http://127.0.0.1:2025",
    "A2A_GEOGRAFIA_URL": "http://127.0.0.1:2026",
}


def test_defaults_y_avisos():
    settings = Settings.from_env(dict(BASE))
    assert settings.a2a_timeout == 45.0
    assert settings.max_input_chars == 2000
    assert settings.historia_graph == "agente_profesor_historia"
    assert settings.geografia_graph == "agente_profesor_geografia"
    assert settings.llm_enabled is False
    assert any("GOOGLE_API_KEY" in aviso for aviso in settings.warnings)
    assert any("falla cerrado" in aviso for aviso in settings.warnings)


def test_faltantes_se_reportan_juntos():
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env({})
    mensaje = str(excinfo.value)
    assert "A2A_HISTORIA_URL" in mensaje
    assert "A2A_GEOGRAFIA_URL" in mensaje


def test_local_api_token_obligatorio_solo_para_la_api():
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env(dict(BASE), needs_local_api=True)
    assert "LOCAL_API_TOKEN" in str(excinfo.value)

    # El Lambda no necesita ese token: el canal es Telegram.
    assert Settings.from_env(dict(BASE), needs_local_api=False).local_api_token == ""


def test_valores_invalidos():
    env = dict(BASE, PORT="ocho mil", A2A_TIMEOUT_SECONDS="0")
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env(env)
    mensaje = str(excinfo.value)
    assert "PORT" in mensaje
    assert "A2A_TIMEOUT_SECONDS" in mensaje


def test_url_sin_esquema():
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env({**BASE, "A2A_HISTORIA_URL": "127.0.0.1:2025"})
    assert "A2A_HISTORIA_URL" in str(excinfo.value)


def test_summary_no_expone_secretos():
    env = dict(
        BASE,
        LOCAL_API_TOKEN="token-local-secreto",
        TELEGRAM_TOKEN="123456:token-telegram-secreto",
        TELEGRAM_SECRET="secreto-webhook",
        GOOGLE_API_KEY="clave-google-secreta",
        A2A_SHARED_TOKEN="token-a2a-secreto",
    )
    resumen = json.dumps(Settings.from_env(env, needs_local_api=True).summary())
    for secreto in (
        "token-local-secreto",
        "token-telegram-secreto",
        "secreto-webhook",
        "clave-google-secreta",
        "token-a2a-secreto",
    ):
        assert secreto not in resumen


def test_token_a2a_se_lee_y_se_reporta_como_activo():
    settings = Settings.from_env(dict(BASE, A2A_SHARED_TOKEN="token-a2a-secreto"))
    assert settings.a2a_shared_token == "token-a2a-secreto"
    assert settings.summary()["a2a_auth_enabled"] is True


def test_sin_token_a2a_avisa_y_queda_desactivado():
    settings = Settings.from_env(dict(BASE))
    assert settings.a2a_shared_token == ""
    assert settings.summary()["a2a_auth_enabled"] is False
    assert any("A2A_SHARED_TOKEN" in aviso for aviso in settings.warnings)


def test_allowlist_se_parsea_por_comas():
    env = dict(BASE, TELEGRAM_ALLOWED_CHAT_IDS="111, 222 ,,333")
    settings = Settings.from_env(env)
    assert settings.telegram_allowed_chat_ids == frozenset({"111", "222", "333"})


def test_limites_de_uso_por_defecto():
    settings = Settings.from_env(dict(BASE))
    assert settings.rate_limit_per_minute == 6
    assert settings.rate_limit_per_day == 100
    resumen = settings.summary()
    assert resumen["rate_limit_per_minute"] == 6
    assert resumen["max_input_chars"] == 2000


def test_limites_de_uso_se_leen_del_entorno():
    settings = Settings.from_env(
        dict(BASE, RATE_LIMIT_PER_MINUTE="2", RATE_LIMIT_PER_DAY="0", MAX_INPUT_CHARS="500")
    )
    assert settings.rate_limit_per_minute == 2
    assert settings.rate_limit_per_day == 0  # 0 desactiva el límite
    assert settings.max_input_chars == 500


def test_limites_invalidos_se_reportan():
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env(dict(BASE, RATE_LIMIT_PER_MINUTE="-1", RATE_LIMIT_PER_DAY="muchas"))
    mensaje = str(excinfo.value)
    assert "RATE_LIMIT_PER_MINUTE" in mensaje
    assert "RATE_LIMIT_PER_DAY" in mensaje


def test_flag_invalido_se_reporta():
    # Regresión: TELEGRAM_SEND_ENABLED se validaba después de lanzar ConfigError.
    with pytest.raises(ConfigError) as excinfo:
        Settings.from_env(dict(BASE, TELEGRAM_SEND_ENABLED="quizás"))
    assert "TELEGRAM_SEND_ENABLED" in str(excinfo.value)
