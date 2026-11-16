# Taller 2 — Agentes A2A de Historia y Geografía

Dos agentes docentes especializados (**Historia** y **Geografía**) que se comunican
por el protocolo **A2A** y se usan desde **Telegram**. El proyecto incluye el
recorrido local completo, un gateway FastAPI, pruebas automatizadas y un despliegue
opcional en AWS Lambda + Heroku como punto extra (+1).

**Opción elegida:** Opción 2, canal **Telegram**.

## Integrantes y aportes

**Grupo 4:** Karen García, Sebastian Garrido, Leonel Carrasco y Manuel Wilson.

La autoría es colectiva. El trabajo se organizó en cuatro frentes, revisados por
los cuatro integrantes:

| Frente | Qué incluye |
|---|---|
| Agentes A2A | Prompts, herramientas, cuadernos de apuntes, grafos de Historia y Geografía y Agent Cards |
| Gateway y canal | Router, cliente A2A, gateway FastAPI, webhook de Telegram, comandos, allowlist, límites y logs |
| Calidad y seguridad | Pruebas (143), manejo de errores, autenticación Bearer, escaneo de secretos y sanitización |
| Despliegue y evidencias | Lambda, Heroku, webhook, capturas, casos de prueba y documentación de reproducción |

## Problema que resuelve

Un estudiante o docente necesita respuestas fundamentadas de Historia y Geografía,
muchas veces sobre un mismo tema (por ejemplo, cómo influyó el clima del Nilo en el
Egipto antiguo). Un solo asistente generalista mezcla datos y no distingue entre
hecho documentado e interpretación. Este proyecto separa el conocimiento en dos
especialistas A2A, enruta cada consulta y, cuando el tema es mixto, consulta a los
dos en paralelo y etiqueta cada aporte.

El canal Telegram permite usarlo sin instalar nada, con control de acceso por chat
y con trazabilidad de cada solicitud.

## Qué se reutiliza del taller A2A

- El patrón **A2A nativo** de LangGraph: Agent Card en
  `/.well-known/agent-card.json` y endpoint JSON-RPC en `/a2a/{assistant_id}`.
- El uso del `contextId` de A2A como `thread_id`, que da memoria por conversación.
- La estructura de agente ReAct de LangChain 1.x con Gemini y una herramienta
  propia (`consultar_mis_apuntes`).
- El notebook de pruebas A2A del agente de Historia.

Se agrega el segundo agente, el router, el gateway, el canal Telegram, la
autenticación entre gateway y agentes y el despliegue reproducible.

## Arquitectura

```text
Local:
  Telegram (bot de prueba, long polling) ─┐
  POST /v1/chat                          ─┼─→ gateway FastAPI :8000
                                          │        │
                                          │        ├─→ A2A → Historia  :2025
                                          │        └─→ A2A → Geografía :2026
Nube (+1):
  Telegram → AWS Lambda (gateway) → A2A HTTPS + Bearer → Heroku (dos agentes)
```

| Componente | Ruta | Función |
|---|---|---|
| Agente Historia | `deploy/agents/grupo4-agente-historia` | Grafo `agente_profesor_historia`, puerto 2025 |
| Agente Geografía | `deploy/agents/grupo4-agente-geografia` | Grafo `agente_profesor_geografia`, puerto 2026 |
| Gateway | `deploy/gateway/gateway` | Router, A2A, Telegram, `/v1/chat`, allowlist y logs |
| Scripts | `deploy/scripts` | Arranque, preflight, despliegue, empaquetado y escaneo |

El gateway elige la ruta por palabras clave y, si no alcanza, por una clasificación
con LLM. Las rutas posibles son `historia`, `geografia`, `mixta`, `generica` y
`sin_clasificar`.

## Requisitos

- **Python 3.12** (probado con 3.12.10). El repo fija `3.12` en `.python-version`.
- Una **`GOOGLE_API_KEY`** de Google AI Studio con cuota de Gemini.
- Para el canal local: un bot de Telegram de prueba creado en **@BotFather**.
- Para el +1: cuenta de AWS, Docker, Heroku y un bot de producción.
- No hace falta AWS CLI: los scripts de despliegue usan boto3.

## Preparación manual

### 1. Google AI Studio

1. Entrar a <https://aistudio.google.com/app/apikey>.
2. Crear una API key y guardarla en el `.env` local (nunca en el repo).
3. Verificar que la cuenta tenga cuota para el modelo configurado en `MODELO`
   (por defecto `gemini-3.5-flash-lite`).

### 2. Bot de Telegram

1. Hablar con **@BotFather** y ejecutar `/newbot`.
2. Elegir nombre y usuario; guardar el token que devuelve.
3. Para el taller se usan dos bots:
   - uno de **producción**, apuntado al webhook de la Lambda;
   - uno de **prueba**, para `local_bot.py` por long polling.
4. Abrir el bot desde la cuenta que va a probarlo y enviar `/start`. Sin ese paso
   Telegram devuelve `chat not found` cuando el bot intenta responder.
5. Obtener el `chat_id` con `@userinfobot` o con `getUpdates`, y ponerlo en
   `TELEGRAM_ALLOWED_CHAT_IDS`.

`local_bot.py` se niega a arrancar si el token de prueba es igual al de producción:
`getUpdates` borra el webhook y el bot de la nube dejaría de responder.

### 3. Heroku y AWS (solo +1)

- **Heroku:** dos apps con dyno **Basic** (siempre activas). Config Vars:
  `GOOGLE_API_KEY`, `MODELO`, `PUBLIC_BASE_URL` y `A2A_SHARED_TOKEN`.
- **AWS:** imagen Docker del gateway en ECR, función Lambda
  `gateway-telegram` con handler `lambda_handler.lambda_handler`, timeout
  **120 s** y Function URL. No se necesita AWS CLI.
- El detalle paso a paso, los comandos y el rollback están en
  [`deploy/DEPLOYMENT.md`](deploy/DEPLOYMENT.md).

## Instalación

Desde la raíz del repo (o de la carpeta descomprimida del ZIP):

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install -e deploy/agents/grupo4-agente-historia `
                     -e deploy/agents/grupo4-agente-geografia
```

```bash
# Linux / macOS
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock
python -m pip install -e deploy/agents/grupo4-agente-historia \
                     -e deploy/agents/grupo4-agente-geografia
```

`requirements.lock` fija las versiones exactas verificadas el **2026-11-16**. Si se
prefiere el rango abierto de cada componente, también se pueden instalar
`deploy/gateway/requirements.txt` y los `requirements-core.txt` de cada agente.

## Configuración

Copiar `.env.example` a `.env` en la raíz y completar como mínimo:

```env
GOOGLE_API_KEY=...
MODELO=gemini-3.5-flash-lite
LOCAL_API_TOKEN=...          # generar con secrets.token_urlsafe(32)
TELEGRAM_ALLOW_ALL=true      # solo para la prueba local por /v1/chat
```

Para probar el canal con un bot real, completar además `TELEGRAM_TOKEN_LOCAL`,
`TELEGRAM_SECRET` (solo si se usa webhook) y `TELEGRAM_ALLOWED_CHAT_IDS`.

Variables principales:

| Variable | Default | Para qué |
|---|---|---|
| `GOOGLE_API_KEY` | — | Clave de Gemini; sin ella el router usa solo palabras clave y los agentes no pueden responder |
| `MODELO` | `gemini-3.5-flash-lite` | Modelo de los agentes |
| `A2A_HISTORIA_URL` / `A2A_GEOGRAFIA_URL` | `http://127.0.0.1:2025` / `:2026` | URLs de los agentes |
| `A2A_SHARED_TOKEN` | vacío | Token Bearer compartido gateway ↔ agentes |
| `A2A_TIMEOUT_SECONDS` | `45` | Espera máxima por agente |
| `LOCAL_API_TOKEN` | — | Bearer de `POST /v1/chat` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | vacío | Allowlist de chats autorizados |
| `TELEGRAM_ALLOW_ALL` | `false` | Abre el canal a cualquier chat; solo para pruebas |
| `TELEGRAM_SEND_ENABLED` | `true` | `false` = dry-run, no envía a Telegram |
| `MAX_INPUT_CHARS` | `2000` | Corta entradas gigantes antes de gastar cuota |
| `RATE_LIMIT_PER_MINUTE` | `6` | Límite por chat/usuario en memoria |
| `RATE_LIMIT_PER_DAY` | `100` | Tope diario por chat/usuario |
| `MAX_OUTPUT_TOKENS` | `1024` | Tope de salida del modelo |
| `LOG_FORMAT` | `json` | `text` para logs legibles |

El `.env` es opcional: las variables reales del entorno tienen prioridad. Nunca se
sube al repositorio, al ZIP ni a las capturas.

## Arranque local

Se necesitan tres terminales. Los agentes leen el `.env` de la raíz al arrancar.

**Terminal 1 — Historia**

```powershell
cd deploy/agents/grupo4-agente-historia
langgraph dev --port 2025 --no-browser
```

**Terminal 2 — Geografía**

```powershell
cd deploy/agents/grupo4-agente-geografia
langgraph dev --port 2026 --no-browser
```

**Terminal 3 — Gateway**

```powershell
cd deploy/gateway
uvicorn gateway.app:app --host 127.0.0.1 --port 8000
```

Endpoints:

| Método | Ruta | Protección |
|---|---|---|
| `GET` | `http://127.0.0.1:8000/health` | ninguna |
| `POST` | `http://127.0.0.1:8000/v1/chat` | `Authorization: Bearer <LOCAL_API_TOKEN>` |
| `POST` | `http://127.0.0.1:8000/telegram/webhook` | `X-Telegram-Bot-Api-Secret-Token` |
| `GET` | `http://127.0.0.1:2025/.well-known/agent-card.json?assistant_id=<uuid>` | ninguna |
| `POST` | `http://127.0.0.1:2025/a2a/<uuid>` | Bearer si `A2A_SHARED_TOKEN` está definido |

Probar una consulta real:

```powershell
$token = (Get-Content .env | Where-Object { $_ -match '^LOCAL_API_TOKEN=' }) -replace '^LOCAL_API_TOKEN=', ''
Invoke-RestMethod -Method Post http://127.0.0.1:8000/v1/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType 'application/json' `
  -Body '{"message":"¿Cuáles fueron las causas de la Revolución Francesa?"}'
```

Sin token, `/v1/chat` responde **401**. Si el agente falla, responde **502** con un
mensaje claro: un fallo nunca se devuelve como respuesta exitosa.

`/v1/chat` acepta `message` y, opcionalmente, `context_id`. Reenviar el mismo
`context_id` mantiene el hilo. Una entrada vacía o mayor a `MAX_INPUT_CHARS`
responde **422**.

### Canal Telegram local (opcional)

```powershell
python deploy/scripts/local_bot.py
```

Usa `TELEGRAM_TOKEN_LOCAL` y el mismo `GatewayService` que el webhook y
`/v1/chat`: comandos, allowlist, límites, Markdown y troceado incluidos.

Comandos del bot:

| Comando | Qué hace |
|---|---|
| `/start` | Presentación y ejemplos |
| `/help` | Ejemplos de uso |
| `/reset` | Empieza una conversación nueva |

## Pruebas

```powershell
# Tests del gateway y de los agentes (sin red)
python -m pytest deploy/tests -q

# Con los agentes levantados, además corre la integración A2A real
python -m pytest deploy/tests -q

# Preflight de los agentes: /ok + Agent Card + 401/200 + consulta A2A
python deploy/scripts/check_agents.py `
  --historia http://127.0.0.1:2025 `
  --geografia http://127.0.0.1:2026

# Smoke del recorrido local completo
python deploy/scripts/smoke_local.py
python deploy/scripts/smoke_local.py --chat
```

Con los dos agentes arriba, la corrida de referencia da **143 tests OK**. Si no
están arriba, los tests de integración se omiten y el resto sigue corriendo.
`smoke_local.py --chat` hace una consulta real por `/v1/chat` y falla con código 1
si algo no responde.

## Uso por Telegram

1. Abrir el bot y enviar `/start`.
2. Escribir una consulta de Historia, de Geografía o mixta.
3. Si el tema toca las dos áreas, el gateway llama a los dos agentes en paralelo y
   devuelve bloques `Historia:` y `Geografía:`.
4. Si falta un dato (región, período, nivel), el agente lo pide antes de responder.
5. Si el chat no está en la allowlist, el bot responde “No estoy autorizado…” y no
   llama a ningún agente.

Límites de costo: `MAX_INPUT_CHARS`, `RATE_LIMIT_PER_MINUTE`,
`RATE_LIMIT_PER_DAY` y `MAX_OUTPUT_TOKENS`. Los contadores viven en memoria del
proceso; en Lambda cada contenedor tiene los suyos.

## Detención

1. `Ctrl+C` en la terminal del gateway y en la de cada agente.
2. Bot local: `Ctrl+C`; opcionalmente
   `deleteWebhook?drop_pending_updates=true` sobre el bot de prueba.
3. Nube: `heroku ps:scale web=0 --app <app>` en cada app, o poner la concurrencia
   reservada de la Lambda en **0**.
4. Para cortar el gasto de modelos: revocar la `GOOGLE_API_KEY` en AI Studio.

## Datos y privacidad

- Los agentes y el gateway guardan el contexto **en memoria**. Al reiniciar se
  pierde el hilo de la conversación; no hay base de datos ni persistencia.
- Los logs guardan metadatos: `request_id`, `update_id`, `chat_id_hash`, ruta,
  agentes, `a2a_task_id`, estado, latencia y longitud de la respuesta. **No**
  guardan el texto de la consulta, el `chat_id` en claro ni tokens.
- `chat_id_hash` es un SHA-256 truncado con una sal. Sin `LOG_HASH_SALT` fija, la
  sal es aleatoria por proceso y el hash cambia al reiniciar.
- Los archivos `docs/evidence/logs/api_*.json` son capturas de respuesta e incluyen
  pregunta y respuesta a propósito; no son logs de producción.
- Las capturas de Telegram no muestran tokens ni datos de la cuenta; la captura
  remota 11 se recortó para excluir el sidebar de contactos.

## Seguridad

- **Secretos fuera del repo:** el `.env` vive en la raíz (ignorado por
  `.gitignore`) y, para el despliegue, en un archivo aparte fuera del proyecto
  (en este equipo, `%USERPROFILE%\.config\taller2\.env`).
- **Webhook:** la Lambda valida `X-Telegram-Bot-Api-Secret-Token`.
- **API local:** `/v1/chat` exige `LOCAL_API_TOKEN`.
- **A2A:** el gateway envía `Authorization: Bearer <A2A_SHARED_TOKEN>` y los agentes
  lo exigen en `/a2a/*`. Sin token configurado no se exige auth, para no romper el
  modo local; en la nube el token es obligatorio.
- **Allowlist:** si no hay chats autorizados y `TELEGRAM_ALLOW_ALL` es `false`, el
  gateway falla cerrado.
- **Escaneo:** `python deploy/scripts/check_no_secrets.py` bloquea el empaquetado si
  encuentra claves, `.env` o rutas absolutas de usuario.
- **Credenciales viejas:** el token anterior de `@history_teacher_001_bot` y la
  `GOOGLE_API_KEY` anterior deben revocarse en BotFather / AI Studio; no se pueden
  revocar desde este repositorio. Ver [`docs/security/ROTATION.md`](docs/security/ROTATION.md).

## Límites conocidos

- **Idempotencia:** no hay deduplicación persistente por `update_id`
  (DynamoDB/SQS). Si Telegram reintenta un update, el bot puede responder dos veces.
- **Contexto:** es en memoria; en Lambda se pierde al reciclar el contenedor.
- **Límites:** `RATE_LIMIT_*` es por instancia, no global.
- **Entrada:** el bot solo lee texto; fotos, voz y documentos reciben un aviso.
- **Router:** si el clasificador falla, la consulta cae en `generica`; no se
  inventa una respuesta de Historia o Geografía.
- **Dynos:** Basic no duerme; Eco sí, y el primer mensaje paga cold start.
- **`assistant_id`:** puede cambiar si se recrea una app de Heroku. El gateway lo
  descubre solo; los IDs fijados en la Lambda son una optimización.
- **Una sola instancia local:** los puertos 2025, 2026 y 8000 deben estar libres.

## Evidencias y casos de prueba

- Índice de capturas y logs: [`docs/evidence/README.md`](docs/evidence/README.md).
- Tabla de 18 casos (LOCAL y REMOTE): [`docs/casos_prueba.md`](docs/casos_prueba.md).
- Guía de despliegue, costos y rollback: [`deploy/DEPLOYMENT.md`](deploy/DEPLOYMENT.md).
- Guía técnica local y de nube: [`deploy/README.md`](deploy/README.md).
- Rotación de credenciales: [`docs/security/ROTATION.md`](docs/security/ROTATION.md).

La corrida de referencia está fechada el **2026-11-15/16**. Las evidencias remotas
están etiquetadas **REMOTE** y no contienen secretos ni datos personales.

## Estructura

```text
.
├── README.md                    esta guía
├── requirements.lock            versiones exactas verificadas
├── .python-version              3.12
├── .env.example                 plantilla de variables (sin secretos)
├── deploy/
│   ├── README.md                guía local y nube
│   ├── DEPLOYMENT.md            despliegue, rollback y costos
│   ├── gateway/                 FastAPI + Lambda + Dockerfile
│   ├── agents/
│   │   ├── grupo4-agente-historia/
│   │   └── grupo4-agente-geografia/
│   ├── scripts/                 preflight, smoke, deploy, empaquetado
│   └── tests/                   143 tests
├── docs/
│   ├── casos_prueba.md
│   ├── evidence/
│   └── security/ROTATION.md
└── dist/taller2-entrega.zip     entrega generada (no versionada)
```

## Entrega

El ZIP se genera sin `.env`, sin `.git`, sin `.venv`, sin cachés y sin logs:

```powershell
powershell -ExecutionPolicy Bypass -File deploy/scripts/package_delivery.ps1
```

El script imprime la cantidad de entradas y el **SHA256** del ZIP. Antes de
compartirlo, volver a correr:

```powershell
python deploy/scripts/check_no_secrets.py
```

Si la entrega se publica en GitHub, invitar al docente con permiso de **lectura**.
Si se entrega por ZIP, enviar el archivo `dist/taller2-entrega.zip` y el hash que
imprime el script.

## QA de la entrega

El ZIP se probó el **2026-11-16** en una carpeta temporal distinta, con un venv
nuevo y siguiendo esta guía:

| Comprobación | Resultado |
|---|---|
| Instalación desde `requirements.lock` + agentes editables | OK con Python 3.12.10 |
| Agentes en `2025`/`2026` y gateway en `8000` | `/ok` y `/health` 200 |
| `check_agents.py` | 401 sin token y consulta A2A `completed` en ambos |
| `smoke_local.py --chat` | `/v1/chat` 401/200 y respuesta real |
| `pytest deploy/tests -q` | **143 passed** |
| Reinicio completo de los tres procesos | Segundo smoke OK, incluida otra consulta real |
| Escaneo de secretos | OK, sin `.env`, tokens ni rutas absolutas |

La evidencia está en
[`docs/evidence/logs/qa_zip_fase5.txt`](docs/evidence/logs/qa_zip_fase5.txt).

## Créditos

Taller 2 de Producción — Grupo 4. Agentes construidos con LangChain 1.x, LangGraph,
Google Gemini y el protocolo A2A; gateway con FastAPI y AWS Lambda; canal Telegram.
