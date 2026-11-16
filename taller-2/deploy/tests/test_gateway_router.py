"""Router determinista: palabras clave primero, LLM solo como fallback."""

import pytest

from gateway.router import classify, normalize


def test_normaliza_acentos_y_mayusculas():
    assert normalize("  Geografía  DEL  Río  ") == "geografia del rio"


@pytest.mark.parametrize(
    "consulta",
    [
        "¿Cuáles fueron las causas de la Revolución Francesa?",
        "Contame sobre la independencia y San Martín",
        "¿Qué fue el feudalismo?",
    ],
)
def test_ruta_historia(consulta):
    route = classify(consulta)
    assert route.name == "historia"
    assert route.method == "keywords"


@pytest.mark.parametrize(
    "consulta",
    [
        "¿Cómo se forma un delta fluvial?",
        "Explicá el relieve de los Andes",
        "¿Qué es la latitud y la longitud?",
    ],
)
def test_ruta_geografia(consulta):
    route = classify(consulta)
    assert route.name == "geografia"
    assert route.method == "keywords"


def test_ruta_mixta_cuando_pesa_los_dos():
    route = classify("Compará la Revolución Francesa con el relieve de los Andes")
    assert route.name == "mixta"
    assert route.method == "keywords"


def test_ruta_mixta_por_mencionar_ambos_temas():
    # Regresión: una sola mención de cada tema ya es mixta; no se adivina
    # cuál "predomina" y se termina consultando a un solo agente.
    route = classify("¿Cómo influyó el relieve de los Andes en la independencia de Chile?")
    assert route.name == "mixta"


def test_generica_solo_la_decide_el_llm():
    route = classify("contame un chiste", llm_router=lambda _texto: "generica")
    assert route.name == "generica"
    assert route.method == "llm"


def test_sin_clasificar_si_no_hay_llm():
    route = classify("contame un chiste")
    assert route.name == "sin_clasificar"
    assert route.method == "fallback"


def test_sin_clasificar_si_el_llm_falla():
    def roto(_texto):
        raise RuntimeError("cuota agotada")

    route = classify("contame un chiste", llm_router=roto)
    assert route.name == "sin_clasificar"
    assert "RuntimeError" in route.reason


def test_no_inventa_ruta_con_respuesta_rara():
    route = classify("contame un chiste", llm_router=lambda _texto: "astronomia")
    assert route.name == "sin_clasificar"
    assert "astronomia" in route.reason


def test_texto_vacio():
    assert classify("   ").name == "sin_clasificar"
