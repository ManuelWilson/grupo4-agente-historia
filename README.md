# Agente Profesor de Historia 🎓📚

Agente conversacional especializado en historia, construido con LangChain 1.x + LangGraph y
Google Gemini, expuesto por **A2A nativo** con `langgraph dev`. Es el primer especialista del
taller y conversa con el Agente Profesor de Geografía (puerto 2026).

**Autoría:** colectiva del **Grupo 4** — Karen García, Sebastian Garrido, Leonel Carrasco y
Manuel Wilson.

## Descripción

El agente actúa como un profesor de historia que:

- Explica eventos históricos de forma clara y contextualizada.
- Analiza causas y consecuencias, distinguiendo hecho documentado de interpretación.
- Construye cronologías y líneas de tiempo.
- Diseña actividades y sugiere recursos educativos.
- Consulta su cuaderno de apuntes propio cuando necesita precisión.

## Características

- **Modelo**: Gemini configurable con la variable `MODELO` (por defecto `gemini-3.5-flash-lite`).
- **Framework**: `create_agent` de LangChain 1.x (agente ReAct) sobre LangGraph.
- **Herramientas**: `consultar_mis_apuntes(tema)` con el cuaderno `APUNTES` (causas, contexto,
  fuentes, cuatro criterios y el caso de la caída del Imperio Romano de Occidente).
- **Puerto**: 2025.
- **A2A nativo**: el servidor publica la Agent Card y el endpoint `/a2a/{assistant_id}`.

## Requisitos

- Python >= 3.11 (probado con 3.12.10)
- `GOOGLE_API_KEY` de Google Gemini con cuota disponible

## Instalación

```powershell
cd agente-profesor-historia
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-core.txt
.venv\Scripts\python.exe -m pip install -e .
```

Para ejecutar los notebooks, agregá el tooling y registrá el kernel:

```powershell
.venv\Scripts\python.exe -m pip install nbformat nbclient ipykernel
.venv\Scripts\python.exe -m ipykernel install --user --name agente-historia
```

## Variables de entorno

Copiá `.env.example` a `.env` y completá los valores (el `.env` no se entrega):

```env
GOOGLE_API_KEY=tu_clave
MODELO=gemini-3.5-flash-lite
A2A_HISTORIA_URL=http://127.0.0.1:2025
A2A_HISTORIA_GRAPH=agente_profesor_historia
```

## Ejecución

```powershell
.venv\Scripts\python.exe -m langgraph_cli dev --port 2025
```

Esto levanta el grafo declarado en `langgraph.json` (`./src/agente_profesor/graph.py:graph`) y
expone:

- Agent Card: `GET http://127.0.0.1:2025/.well-known/agent-card.json?assistant_id=<uuid>`
- Endpoint A2A: `POST http://127.0.0.1:2025/a2a/<assistant_id>`

El `assistant_id` se obtiene con:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:2025/assistants/search `
  -ContentType application/json -Body '{"graph_id":"agente_profesor_historia"}'
```

El `contextId` de A2A se mapea al `thread_id`, así que la memoria por conversación es automática.

## Notebooks

- `notebooks/a2a-test.ipynb` — notebook de pruebas y evidencia del taller: descubrimiento, las 3
  pruebas clave, A2A, tarjetas, supervisor, diálogo A → B → A y checklist final (13/13).
- `notebooks/a2a-test.run.log` — salida íntegra de la corrida (18 celdas · 0 fallidas).

El kernel `agente-historia` apunta al `.venv` de este proyecto. No uses el Python de la Microsoft
Store: trae un `a2a-sdk` antiguo y falla al importar `TextPart`.

## Tests

Con el servidor arriba:

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Si el servidor no está corriendo, los tests se omiten automáticamente.

## Estructura

```
agente-profesor-historia/
├── src/agente_profesor/
│   ├── graph.py            # create_agent + ChatGoogleGenerativeAI
│   ├── prompts.py          # NOMBRE, ESPECIALIDAD, PERSONALIDAD, SOBRE_MI, SKILLS, SYSTEM_PROMPT
│   └── herramientas.py     # APUNTES + consultar_mis_apuntes
├── notebooks/
│   ├── a2a-test.ipynb
│   └── a2a-test.run.log
├── scripts/setup_entorno.py
├── tests/test_a2a_historia.py
├── langgraph.json
├── pyproject.toml
├── requirements.txt
├── requirements-core.txt
├── .env.example
└── README.md
```

El blueprint del agente está en el `blueprint.md` de la raíz del workspace.

## Solución de problemas

- **Falta `GOOGLE_API_KEY`**: verificá el `.env`.
- **`ValueError: Unable to configure formatter 'simple'`**: instalá `colorama` (ya está en
  `requirements-core.txt`).
- **`ModuleNotFoundError: No module named 'agente_profesor'`**: falta `pip install -e .`.
- **`402 RESOURCE_EXHAUSTED`**: la clave no tiene cuota; recargá créditos o usá otra clave.
  Quedó documentado en el documento de entrega (sección 4.6).
- **El `.venv` apunta a otra máquina**: corregí `home`/`executable` en `.venv/pyvenv.cfg` y el
  `.pth` editable de `site-packages`.
- **Puerto 2025 ocupado**: usá otro puerto y ajustá `A2A_HISTORIA_URL`.

Atajo de instalación: `python scripts/setup_entorno.py` crea el entorno y valida `langgraph.json`.
