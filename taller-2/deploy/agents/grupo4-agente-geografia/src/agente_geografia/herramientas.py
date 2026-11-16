"""Herramientas del agente profesor de geografía.

El agente expone un cuaderno de apuntes propio (APUNTES) y la herramienta
`consultar_mis_apuntes` para consultarlo, tal como pide la rúbrica del taller.
"""

from langchain_core.tools import tool

APUNTES = {
    "conceptos": {
        "clima": (
            "Clima es el conjunto de condiciones atmosféricas habituales de un lugar, "
            "medidas durante al menos 30 años. Se describe con temperatura media anual, "
            "amplitud térmica, régimen de lluvias y estacionalidad. No es lo mismo que "
            "tiempo, que es el estado atmosférico de un momento concreto. Un mismo lugar "
            "puede tener un clima templado y un día de calor extremo."
        ),
        "relieve": (
            "Relieve es la forma de la superficie terrestre: llanuras, mesetas, sierras, "
            "cordilleras, valles y depresiones. Determina el drenaje, la erosión y la "
            "transitabilidad, y actúa como barrera que aísla poblaciones, cultivos y "
            "lenguas. Una llanura llana favorece los desplazamientos y el cultivo "
            "extensivo; una cordillera los encarece y los protege."
        ),
        "paisaje": (
            "Paisaje es la porción visible del territorio, resultado de la interacción "
            "entre elementos naturales (relieve, clima, vegetación, agua) y humanos "
            "(cultivos, ciudades, caminos). El paisaje geográfico es el que la naturaleza "
            "predomina; el paisajístico, el que la actividad humana transformó. Cambiar "
            "el paisaje es un proceso lento y, a veces, irreversible."
        ),
    },
    "criterios": [
        "Una buena descripción geográfica distingue el clima (largo plazo) del tiempo "
        "(un día) y da al menos un dato cuantitativo por región o periodo.",
        "Un análisis geográfico bien hecho explica la relación causal entre el territorio "
        "y la actividad humana, en vez de listar rasgos sin relación entre sí.",
        "Toda afirmación sobre un lugar debe poder ubicarse: límites, país, región y "
        "período. Un dato sin ubicación no es un dato geográfico.",
        "Cuando se comparan lugares, se comparan las mismas variables en los mismos "
        "términos; si no, la comparación es engañosa.",
    ],
    "caso": (
        "Caso de estudio: el valle del Nilo y el valle del Indo. En ambos casos el "
        "poblamiento se concentró junto al río porque el relieve y el clima lo permitían: "
        "las crecidas anuales depositaban limo fértil en un desierto por lo demás "
        "estéril. Aprendizaje: el agua y el relieve explican la localización del "
        "poblamiento y de la agricultura intensiva mucho mejor que la distancia al mar, "
        "y esa diferencia es clave para entender por qué ciertas civilizaciones se "
        "organizaron en cuencas y no en costas."
    ),
}


@tool
def consultar_mis_apuntes(tema: str = "") -> str:
    """Consulta el cuaderno de apuntes propio del profesor de geografía.

    Args:
        tema: El tema o sección a consultar ('clima', 'relieve', 'paisaje',
            'criterios' o 'caso'). Si va vacío, devuelve todos los apuntes.

    Returns:
        Los apuntes del tema pedido, o todos si el tema va vacío. Si el tema no existe
        en el cuaderno, lo dice y devuelve el índice de conceptos disponibles.
    """
    if not tema or not tema.strip():
        partes = []
        for nombre, texto in APUNTES["conceptos"].items():
            partes.append(f"[{nombre}]\n{texto}")
        partes.append("[criterios]\n" + "\n".join(f"- {c}" for c in APUNTES["criterios"]))
        partes.append("[caso]\n" + APUNTES["caso"])
        return "APUNTES COMPLETOS\n\n" + "\n\n".join(partes)

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
        f"Si tu consulta no encaja en ninguna de ellas, la responderé desde mi conocimiento "
        f"general y te lo aclararé."
    )


# Lista de herramientas disponibles para el agente
HERRAMIENTAS = [
    consultar_mis_apuntes,
]
