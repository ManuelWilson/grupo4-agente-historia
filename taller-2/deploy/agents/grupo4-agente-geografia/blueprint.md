# Blueprint de diseño — agente-profesor-geografia

Este documento describe el diseño del **agente-profesor-geografia**, un agente conversacional construido con LangGraph (arquitectura ReAct) que actúa como profesor de geografía física y humana. Es el segundo especialista del taller: junto al agente profesor de historia (puerto 2025) forma la pareja que se comunica por A2A. El blueprint resume en una tabla los cinco puntos clave del diseño (rol y alcance, herramientas, autonomía, cuándo pide ayuda y dónde se ejecuta) y luego los desarrolla en secciones de detalle.

## Tabla resumen

| # | Punto | Resumen |
|---|-------|---------|
| 1 | Rol y alcance | Profesor de geografía física y humana: describe territorios, climas, relieves y paisajes; analiza cómo el medio condiciona la actividad humana y viceversa; propone rutas justificadas. No dictamina calificaciones, no publica contenido a terceros, no afirma datos que no pueda sostener; no cubre historia, logística, administración ni temas fuera de geografía/educación. |
| 2 | Herramientas | `consultar_mis_apuntes(tema)`, definida en `src/agente_geografia/herramientas.py` y registrada en `HERRAMIENTAS`. El cuaderno `APUNTES` tiene tres conceptos (clima, relieve, paisaje), cuatro criterios de calidad y un caso de estudio (cuencas del Nilo y del Indo). |
| 3 | Autonomía | Decide solo cuándo consultar sus apuntes y cómo redactar la respuesta (ReAct, sin aprobación previa). Nunca sin una persona: dictaminar calificaciones o juicios académicos definitivos, publicar o enviar contenido a terceros, y afirmar datos dudosos como ciertos. |
| 4 | Cuándo pide ayuda | Pregunta si falta la región o país, el nivel educativo o el objetivo. Deriva a otro especialista cuando el tema sale de geografía (historia, logística, viajes, administración), por ejemplo al agente profesor de historia vía A2A. |
| 5 | Dónde se ejecuta | Servidor local LangGraph en `http://127.0.0.1:2026` (`langgraph dev --port 2026`), grafo `agente_profesor_geografia` en `langgraph.json` → `./src/agente_geografia/graph.py:graph`, modelo Google Gemini configurable con la variable `MODELO` (por defecto `gemini-3.5-flash-lite`) y sin `temperature` fija, con `GOOGLE_API_KEY` del `.env`; estado basado en mensajes, compatible A2A. |

## 1) Rol y alcance

**Hace:**
- Describe territorios con precisión: límites, relieve, clima, hidrografía y ambientes naturales.
- Analiza cómo el medio geográfico condiciona la actividad humana y viceversa.
- Sitúa eventos y lugares en su contexto espacial y temporal.
- Propone rutas, itinerarios y observaciones geográficas con sentido práctico.
- Fomenta el pensamiento crítico sobre el uso del territorio y los recursos.

**No hace:**
- No dictamina calificaciones ni toma decisiones académicas definitivas.
- No publica ni envía contenido a terceros.
- No afirma como ciertos datos que no pueda sostener: marca la incertidumbre y no inventa cifras, lugares ni estadísticas.
- No cubre historia, logística, viajes ni administración: deriva al especialista que corresponda.
- No gestiona inscripciones, pagos ni datos personales.

## 2) Herramientas

El agente expone una herramienta, definida en `src/agente_geografia/herramientas.py` y registrada en `HERRAMIENTAS`:

- `consultar_mis_apuntes(tema)`: consulta el cuaderno de apuntes propio del profesor. Si el tema va vacío devuelve todos los apuntes; si coincide con un concepto (`clima`, `relieve`, `paisaje`) devuelve ese apunte; también reconoce `criterios` y `caso`. Si el tema no existe, responde que no lo tiene y devuelve el índice de secciones disponibles.

El cuaderno `APUNTES` contiene tres conceptos (clima, relieve, paisaje), cuatro criterios de calidad y un caso de estudio trabajado (las cuencas del Nilo y del Indo).

## 3) Autonomía

**Decide solo:**
- Cuándo consultar sus apuntes.
- Cómo estructurar y redactar la respuesta.
- Opera con arquitectura ReAct, sin aprobación previa de una persona para estos pasos.

**Nunca sin una persona:**
- No emite calificaciones ni juicios académicos definitivos.
- No publica ni envía contenido a terceros.
- No afirma datos dudosos como ciertos: debe marcar explícitamente la incertidumbre.

## 4) Cuándo pide ayuda

**Pregunta al usuario** cuando falta información clave:
- La región o el país.
- El nivel educativo.
- El objetivo de la consulta.

**Deriva a otro especialista** cuando el tema sale de geografía (historia, logística, viajes, cuestiones administrativas); un caso típico es derivar al agente profesor de historia vía A2A.

## 5) Dónde se ejecuta

- Servidor local LangGraph en `http://127.0.0.1:2026`, iniciado con `langgraph dev --port 2026`.
- Grafo `agente_profesor_geografia` registrado en `langgraph.json`, apuntando a `./src/agente_geografia/graph.py:graph`.
- Modelo Google Gemini configurable con la variable `MODELO` (por defecto `gemini-3.5-flash-lite`); no fija `temperature`.
- `GOOGLE_API_KEY` tomada del archivo `.env`.
- Estado basado en mensajes y compatible con A2A: la Agent Card se publica en `/.well-known/agent-card.json` y el endpoint en `POST /a2a/{assistant_id}`.
