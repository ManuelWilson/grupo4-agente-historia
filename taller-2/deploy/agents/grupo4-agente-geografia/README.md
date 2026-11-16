# Agente Profesor de Geografía 🌍🗺️

Agente conversacional especializado en geografía, construido con LangChain 1.x + LangGraph y Google Gemini,
expuesto por **A2A nativo** con `langgraph dev`.

Es el **segundo agente del proyecto** del taller: junto a `agente-profesor-historia` (puerto 2025) forma la
pareja de especialistas que se comunican entre sí por A2A (consigna del taller, etapa 3).

**Autoría:** colectiva del **Grupo 4** — Karen García, Sebastian Garrido, Leonel Carrasco y
Manuel Wilson.

## Descripción

Este agente actúa como un profesor de geografía que puede:

- Describir territorios con precisión: límites, relieve, clima, hidrografía y ambientes naturales
- Analizar cómo el medio geográfico condiciona la actividad humana y viceversa
- Situar eventos y lugares en su contexto espacial y temporal
- Proponer rutas e itinerarios con su componente geográfico justificado

## Características

- **Modelo**: Gemini (configurable con la variable `MODELO`, por defecto `gemini-3.5-flash-lite`)
- **Framework**: `create_agent` de LangChain 1.x (agente ReAct) sobre LangGraph
- **Herramientas**: `consultar_mis_apuntes` (cuaderno propio con conceptos, criterios y un caso de estudio)
- **Puerto**: 2026 (historia usa 2025)
- **Grafo**: `agente_profesor_geografia`
- **A2A nativo**: el servidor de LangGraph publica la Agent Card y el endpoint `/a2a/{assistant_id}`

## Requisitos

- Python **3.12** (probado con 3.12.10; el repo fija `3.12` en `.python-version`)
- Clave API de Google Gemini (https://aistudio.google.com/app/apikey)

## Instalación (entorno virtual propio)

```bash
cd agente-profesor-geografia
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / Mac
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

Solo runtime + servidor + SDK A2A (sin pytest/notebooks):

```bash
pip install -r requirements-core.txt
```

> **Windows**: si `pip install` falla con un error de ruta demasiado larga al instalar `jedi`,
> instalá solo lo necesario y usá el intérprete compartido del workspace para los notebooks:
> `.venv\Scripts\python.exe -m pip install nbformat nbclient ipykernel --no-deps`.

## Variables de entorno

Copiá `.env.example` a `.env` y completá los valores:

```env
GOOGLE_API_KEY=tu_clave
MODELO=gemini-3.5-flash-lite
A2A_GEOGRAFIA_URL=http://127.0.0.1:2026
A2A_GEOGRAFIA_GRAPH=agente_profesor_geografia
PUBLIC_BASE_URL=http://127.0.0.1:2026
```

`PUBLIC_BASE_URL` es la base que el middleware `http_app.py` publica dentro de la Agent Card.
Si falta, el middleware intenta reconstruirla desde `Host`/`X-Forwarded-*`; en Heroku eso puede
dar el host interno, así que se configura explícitamente con la URL pública de la app.

## Ejecución

```bash
langgraph dev --port 2026
```

Esto levanta el grafo declarado en `langgraph.json`
(`./src/agente_geografia/graph.py:graph`) y expone automáticamente:

- Agent Card: `GET http://127.0.0.1:2026/.well-known/agent-card.json?assistant_id=<uuid>`
- Endpoint A2A: `POST http://127.0.0.1:2026/a2a/<assistant_id>` (`message/send`, `message/stream`, `tasks/get`, `tasks/cancel`)

El `assistant_id` (UUID) se obtiene con:

```bash
curl -X POST http://127.0.0.1:2026/assistants/search -H "Content-Type: application/json" -d '{"graph_id":"agente_profesor_geografia"}'
```

El `contextId` de A2A se mapea al `thread_id`, por lo que la memoria por conversación es automática.

## Tests

Con el servidor corriendo en otra terminal (`langgraph dev --port 2026`):

```bash
pytest -q
```

Si el servidor no está arriba, los tests se omiten (skip) automáticamente.

## Estructura del proyecto

```
agente-profesor-geografia/
├── blueprint.md                 # blueprint del agente (tabla de 5 puntos)
├── src/
│   └── agente_geografia/
│       ├── __init__.py
│       ├── graph.py             # create_agent + ChatGoogleGenerativeAI
│       ├── prompts.py           # NOMBRE, ESPECIALIDAD, PERSONALIDAD, SOBRE_MI, SKILLS, SYSTEM_GEOGRAFIA
│       └── herramientas.py      # APUNTES, consultar_mis_apuntes, HERRAMIENTAS
├── notebooks/
│   ├── a2a-test.ipynb           # pruebas A2A (con outputs)
│   └── a2a-test.run.log         # salida completa de esa corrida
├── tests/
│   ├── __init__.py
│   └── test_a2a_geografia.py    # Agent Card + message/send
├── langgraph.json
├── pyproject.toml
├── requirements.txt
├── requirements-core.txt
├── .env.example
├── .gitignore
└── README.md
```

## Cómo se conecta con el agente de historia

El notebook de evidencia del taller es `agente-profesor-historia/notebooks/a2a-test.ipynb`
(descubrimiento de ambos servidores, supervisor y diálogo A → B → A). El `notebooks/a2a-test.ipynb`
de este proyecto queda como prueba complementaria del agente de geografía.

1. Los dos servidores tienen que estar arriba: `langgraph dev --port 2025` (historia) y
   `langgraph dev --port 2026` (geografía).
2. Las tarjetas se pueden presentar con nombre y descripción reales para que el supervisor
   elija a quién consultar:
   ```bash
   curl -X PATCH "http://127.0.0.1:2026/assistants/$AID" -H "Content-Type: application/json" \
     -d '{"name": "Agente Profesor de Geografía", "description": "Especialista en geografía física y humana..."}'
   ```
3. El intercambio A → B → A está en la sección 9 de
   `agente-profesor-historia/notebooks/agente_profesor_historia.ipynb`.

## Solución de problemas

- **Falta GOOGLE_API_KEY**: verificá el `.env`.
- **`langgraph dev` no arranca con `ValueError: Unable to configure formatter 'simple'`**:
  instalá `colorama` (Windows lo necesita para los logs con color):
  `pip install colorama`.
- **Puerto 2026 ocupado**: `langgraph dev --port 3000` (y ajustá `A2A_GEOGRAFIA_URL`).
- **`ModuleNotFoundError: No module named 'agente_geografia'`**: falta `pip install -e .`.
