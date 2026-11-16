"""Router de consultas: palabras clave primero, LLM como fallback.

Determinista y explicable: cada decisión trae `method` (`keywords`, `llm`,
`fallback`) y un `reason` que se puede loguear. Si no se puede clasificar, la
ruta es `sin_clasificar` y el servicio lo dice; nunca se disfraza de respuesta
genérica exitosa.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Literal

RouteName = Literal["historia", "geografia", "mixta", "generica", "sin_clasificar"]

HISTORIA_KEYWORDS = (
    "historia", "historico", "historica", "prehistoria", "edad media", "medieval",
    "antiguo regimen", "ilustracion", "revolucion francesa", "1789", "revolucion industrial",
    "primera guerra", "segunda guerra", "guerra fria", "guerra", "guerras",
    "independencia", "independencias", "colonial", "colonia", "colonizacion",
    "imperio", "imperios", "imperio romano", "roma", "romano", "griego", "grecia",
    "atenas", "esparta", "egipto", "faraon", "mesopotamia", "incas", "mayas", "aztecas",
    "feudalismo", "cruzadas", "renacimiento", "reforma protestante", "lutero",
    "monarquia", "republica", "dictadura", "dictaduras", "totalitarismo",
    "nazismo", "fascismo", "hitler", "mussolini", "stalin", "peron", "peronismo",
    "san martin", "bolivar", "belgrano", "sarmiento", "rosas",
    "constitucion", "tratado", "armisticio", "crisis de 1929", "muro de berlin",
    "conquista", "virreinato", "esclavitud", "ilustrados", "enciclopedia",
)

GEOGRAFIA_KEYWORDS = (
    "geografia", "geografico", "geografica", "territorio", "territorios",
    "relieve", "clima", "climatico", "climatica", "hidrografia", "cuenca",
    "rio", "rios", "delta", "valle", "montaña", "montañas", "cordillera", "volcan",
    "terremoto", "sismo", "placas tectonicas", "erosion", "sedimentos", "sedimentacion",
    "latitud", "longitud", "hemisferio", "ecuador", "tropico", "desierto", "selva",
    "bosque", "tundra", "estepa", "bioma", "ecosistema", "ecorregion",
    "poblacion", "densidad", "migracion", "migraciones", "urbanizacion", "rural",
    "ciudad", "ciudades", "region", "regiones", "frontera", "fronteras",
    "mapa", "mapas", "coordenadas", "atmosfera", "precipitaciones", "monzon",
    "corriente marina", "corrientes marinas", "cambio climatico", "calentamiento global",
    "nilo", "amazonas", "andes", "pampa", "patagonia", "altiplano", "delta fluvial",
)

# Las frases pesan más que una palabra suelta: menos falsos positivos.
PESO_FRASE = 2.0
PESO_PALABRA = 1.0
# Si la consulta toca los dos temas, se consulta a los dos agentes: no se adivina
# cuál "predomina". Cada mención de cada tema alcanza para la ruta mixta.
UMBRAL_MIXTA = 1.0


@dataclass(frozen=True)
class Route:
    name: RouteName
    reason: str
    method: str


def normalize(text: str) -> str:
    """Minúsculas y sin acentos, para comparar palabras clave de forma estable."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return re.sub(r"\s+", " ", "".join(c for c in decomposed if not unicodedata.combining(c))).strip()


def _pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(normalize(keyword))}(?![a-z0-9])")


_PATRONES_HISTORIA = tuple(
    (_pattern(k), PESO_FRASE if " " in k else PESO_PALABRA, normalize(k)) for k in HISTORIA_KEYWORDS
)
_PATRONES_GEOGRAFIA = tuple(
    (_pattern(k), PESO_FRASE if " " in k else PESO_PALABRA, normalize(k)) for k in GEOGRAFIA_KEYWORDS
)


def _score(texto: str, patrones) -> tuple[float, list[str]]:
    encontrados = [(peso, palabra) for patron, peso, palabra in patrones if patron.search(texto)]
    return sum(peso for peso, _ in encontrados), [palabra for _, palabra in encontrados]


def classify(text: str, llm_router: Callable[[str], str | None] | None = None) -> Route:
    texto = normalize(text)
    if not texto:
        return Route("sin_clasificar", "consulta vacía", "fallback")

    score_historia, terminos_historia = _score(texto, _PATRONES_HISTORIA)
    score_geografia, terminos_geografia = _score(texto, _PATRONES_GEOGRAFIA)

    if score_historia and score_geografia:
        return Route(
            "mixta",
            f"toca ambos temas ({', '.join(terminos_historia[:3])} / {', '.join(terminos_geografia[:3])})",
            "keywords",
        )

    if score_historia:
        return Route("historia", f"palabras clave: {', '.join(terminos_historia[:3])}", "keywords")
    if score_geografia:
        return Route("geografia", f"palabras clave: {', '.join(terminos_geografia[:3])}", "keywords")

    if llm_router is None:
        return Route("sin_clasificar", "sin palabras clave y sin clasificador LLM", "fallback")

    try:
        decision = llm_router(text)
    except Exception as exc:  # el router nunca debe tumbar la consulta
        return Route("sin_clasificar", f"el clasificador LLM falló ({type(exc).__name__})", "fallback")

    if decision in ("historia", "geografia", "generica"):
        return Route(decision, "clasificación por LLM", "llm")
    return Route("sin_clasificar", f"el clasificador LLM devolvió {decision!r}", "fallback")


def build_llm_router(settings) -> Callable[[str], str | None] | None:
    """Crea el clasificador LLM solo si hay clave; si no, el router sigue siendo por palabras."""
    if not settings.llm_enabled:
        return None

    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI
    from pydantic import BaseModel, Field

    class Decision(BaseModel):
        ruta: Literal["historia", "geografia", "generica"] = Field(
            description="Tema de la consulta del usuario."
        )
        motivo: str = Field(description="Una frase breve: por qué esa ruta.")

    modelo = ChatGoogleGenerativeAI(model=settings.model, api_key=settings.google_api_key)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "Clasificá la consulta del usuario. Respondé 'historia' si trata de historia, "
                "'geografia' si trata de geografía, y 'generica' si no es de ninguna de las dos. "
                "Si menciona las dos cosas, elegí la que predomine.",
            ),
            ("human", "{texto}"),
        ]
    )
    cadena = prompt | modelo.with_structured_output(Decision)

    def router(text: str) -> str | None:
        return cadena.invoke({"texto": text}).ruta

    return router
