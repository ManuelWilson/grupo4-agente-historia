"""Herramientas del agente profesor de historia.

El agente expone un cuaderno de apuntes propio (APUNTES) y la herramienta
`consultar_mis_apuntes` para consultarlo, tal como pide la rúbrica del taller.
"""

from langchain_core.tools import tool

APUNTES = {
    "conceptos": {
        "causas": (
            "Causa histórica es la condición que hace posible un proceso. Se distingue "
            "entre causas estructurales (economía, sociedad, instituciones, geografía) "
            "y coyunturales (decisiones, crisis, guerras). Un mismo hecho suele tener "
            "varias causas y no todas pesan igual: explicar historia es jerarquizarlas "
            "y mostrar cómo se combinan, no enumerarlas."
        ),
        "contexto": (
            "Contextualizar es situar un hecho en su tiempo y en su espacio, con las "
            "categorías de esa época y no con las actuales, para evitar el presentismo "
            "y el anacronismo. Un mismo acontecimiento cambia de sentido según la "
            "escala (local, regional o mundial) y según la duración (corto, medio o "
            "largo plazo)."
        ),
        "fuentes": (
            "Fuente primaria es el testimonio producido en la época (documentos, "
            "crónicas, restos materiales); secundaria, la interpretación posterior "
            "(libros, artículos). Toda fuente tiene autor, intención y límites. El "
            "hecho documentado se distingue de la interpretación historiográfica: dos "
            "historiadores pueden leer la misma fuente de forma distinta sin que eso "
            "convierta una lectura en un dato."
        ),
    },
    "criterios": [
        "Toda afirmación histórica debe poder ubicarse en tiempo y espacio: período, "
        "región y, cuando corresponda, fecha. Un dato sin contexto no es un dato "
        "histórico.",
        "Un buen análisis explica la multicausalidad y jerarquiza causas estructurales "
        "y coyunturales, en vez de enumerar hechos o atribuir el proceso a una sola "
        "causa.",
        "Toda respuesta distingue el hecho documentado de la interpretación, y marca "
        "la incertidumbre cuando las fuentes son discutidas o insuficientes.",
        "Las comparaciones usan las mismas variables y períodos, y evitan juzgar el "
        "pasado con categorías actuales.",
    ],
    "caso": (
        "Caso de estudio: la caída del Imperio Romano de Occidente (476 d.C.). "
        "Durante siglos se explicó por una sola causa —las invasiones bárbaras—, pero "
        "hoy se lee como un proceso multicausal: crisis fiscal y militar, agotamiento "
        "del modelo esclavista, inflación por devaluación monetaria, presión sostenida "
        "sobre las fronteras y pérdida de legitimidad política. Aprendizaje: la fecha "
        "de 476 es un hito convencional, no el fin instantáneo de un mundo; separar "
        "causas estructurales (siglos de desgaste) de coyunturales (invasiones, "
        "usurpaciones) evita explicaciones simplistas y muestra cómo se encadenan el "
        "corto y el largo plazo."
    ),
}


def _todos_los_apuntes() -> str:
    partes = []
    for nombre, texto in APUNTES["conceptos"].items():
        partes.append(f"[{nombre}]\n{texto}")
    partes.append("[criterios]\n" + "\n".join(f"- {c}" for c in APUNTES["criterios"]))
    partes.append("[caso]\n" + APUNTES["caso"])
    return "APUNTES COMPLETOS\n\n" + "\n\n".join(partes)


@tool
def consultar_mis_apuntes(tema: str = "") -> str:
    """Consulta el cuaderno de apuntes propio del profesor de historia.

    Args:
        tema: El tema o sección a consultar ('causas', 'contexto', 'fuentes',
            'criterios' o 'caso'). Si va vacío, devuelve todos los apuntes.

    Returns:
        Los apuntes del tema pedido, o todos si el tema va vacío. Si el tema no
        existe en el cuaderno, lo dice y devuelve el índice de secciones disponibles.
    """
    if not tema or not tema.strip():
        return _todos_los_apuntes()

    clave = tema.strip().lower()
    for nombre, texto in APUNTES["conceptos"].items():
        if nombre == clave or clave in nombre or nombre in clave:
            return f"APUNTE · {nombre}\n{texto}"

    if "criterio" in clave:
        return "CRITERIOS DE CALIDAD\n" + "\n".join(f"- {c}" for c in APUNTES["criterios"])

    if "caso" in clave:
        return "CASO DE ESTUDIO\n" + APUNTES["caso"]

    disponibles = ", ".join([*APUNTES["conceptos"], "criterios", "caso"])
    return (
        f"No tengo un apunte llamado '{tema}'.\n"
        f"Estas son las secciones disponibles de mi cuaderno: {disponibles}.\n"
        f"Si tu consulta no encaja en ninguna, la responderé desde mi conocimiento "
        f"general y te lo aclararé."
    )


# Lista de herramientas disponibles para el agente
HERRAMIENTAS = [
    consultar_mis_apuntes,
]
