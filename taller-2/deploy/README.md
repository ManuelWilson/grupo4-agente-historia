# Guía del Taller 2 — Agentes A2A y gateway

Dos modos de ejecución, con el mismo código:

```
Local:  /v1/chat  ─┐
       Telegram   ─┴→ gateway (FastAPI) → A2A → agentes (langgraph dev, 2025/2026)

Nube:   Telegram → AWS Lambda (gateway) → A2A → agentes en Heroku
```

## Ejecución local (sin AWS ni Heroku)

Requisitos: **Python 3.12**, una `GOOGLE_API_KEY` propia y los dos agentes en este repo.
La guía de entrega, con la instalación reproducible desde `requirements.lock`, está
en el [`README.md`](../README.md) de la raíz. Este documento profundiza el modo local
y el despliegue.

### 1. Preparar el entorno

```powershell
# Windows
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r deploy/agents/grupo4-agente-historia/requirements.txt
pip install -r deploy/agents/grupo4-agente-geografia/requirements.txt
pip install -r deploy/gateway/requirements.txt
pip install -e deploy/agents/grupo4-agente-historia -e deploy/agents/grupo4-agente-geografia
```

```bash
# Linux / macOS
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r deploy/agents/grupo4-agente-historia/requirements.txt \
            -r deploy/agents/grupo4-agente-geografia/requirements.txt \
            -r deploy/gateway/requirements.txt
pip install -e deploy/agents/grupo4-agente-historia -e deploy/agents/grupo4-agente-geografia
```

Copiar `.env.example` a `.env` en la raíz y completar:

- `GOOGLE_API_KEY` (AI Studio)
- `LOCAL_API_TOKEN` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`)
- `TELEGRAM_ALLOW_ALL=true` para la prueba local, o tus IDs en `TELEGRAM_ALLOWED_CHAT_IDS`
- `A2A_SHARED_TOKEN` (opcional en local; si lo definís, debe ser el mismo en el gateway y en cada agente)

El `.env` nunca se sube: el escaneo de la entrega lo detecta.

### 2. Levantar los agentes (terminales 1 y 2)

```powershell
cd deploy/agents/grupo4-agente-historia
langgraph dev --port 2025 --no-browser
```

```powershell
cd deploy/agents/grupo4-agente-geografia
langgraph dev --port 2026 --no-browser
```

Cada uno publica `http://127.0.0.1:<puerto>/ok`, la Agent Card en
`/.well-known/agent-card.json?assistant_id=<uuid>` y el endpoint A2A en `/a2a/<uuid>`.

Si definiste `A2A_SHARED_TOKEN` en el `.env` del gateway, exportá el mismo valor antes
de levantar cada agente. Con token configurado, `/a2a/*` responde **401** sin
`Authorization: Bearer <token>`; la Agent Card y `/assistants/search` siguen públicas
para poder descubrir el agente. Sin token, el modo local no exige auth.

### 3. Levantar el gateway (terminal 3)

```powershell
cd deploy/gateway
uvicorn gateway.app:app --host 127.0.0.1 --port 8000
```

Endpoints:

| Método | Ruta | Protección |
|---|---|---|
| `GET` | `/health` | ninguna |
| `POST` | `/v1/chat` | `Authorization: Bearer <LOCAL_API_TOKEN>` |
| `POST` | `/telegram/webhook` | `X-Telegram-Bot-Api-Secret-Token` |

```powershell
$token = (Get-Content .env | Where-Object { $_ -match '^LOCAL_API_TOKEN=' }) -replace '^LOCAL_API_TOKEN=', ''
Invoke-RestMethod -Method Post http://127.0.0.1:8000/v1/chat `
  -Headers @{ Authorization = "Bearer $token" } `
  -ContentType 'application/json' `
  -Body '{"message":"¿Cuáles fueron las causas de la Revolución Francesa?"}'
```

Sin token, `/v1/chat` responde **401**. Si el agente falla, responde **502** con un mensaje
claro: un fallo nunca se devuelve como respuesta exitosa.

Comportamiento de `/v1/chat`:

- `route` puede ser `historia`, `geografia`, `mixta`, `generica` o `sin_clasificar`.
- Si la consulta toca los dos temas, se llama a **ambos agentes en paralelo** y la respuesta
  trae los dos textos etiquetados. Si uno falla, responde 200 con el texto del que sí
  funcionó y una línea que dice cuál falló.
- Reenviar el mismo `context_id` mantiene la conversación: cada agente tiene su propio
  `contextId` derivado, y un seguimiento sin palabras clave ("¿de qué te pregunté antes?")
  hereda el agente del turno anterior.
- Entrada vacía o mayor a `MAX_INPUT_CHARS` → **422**.

### 4. Verificar todo

```powershell
python deploy/scripts/check_agents.py --historia http://127.0.0.1:2025 --geografia http://127.0.0.1:2026
python deploy/scripts/smoke_local.py          # /ok, Agent Cards y /health
python deploy/scripts/smoke_local.py --chat   # agrega una consulta real por /v1/chat
```

`check_agents.py` valida `/ok`, la Agent Card pública y una consulta A2A real por
agente; si `A2A_SHARED_TOKEN` está definido, además comprueba que `/a2a/*` responda
**401** sin token. Sale con código 1 si algo falla. Sin `--historia/--geografia` usa
las URLs del entorno, así que también sirve como preflight de Heroku.

Los logs salen en JSON por defecto (`LOG_FORMAT=text` para el formato legible) con
`request_id`, `update_id`, `chat_id_hash`, `route`, `agents`, `a2a_task_id`,
`status`, `latency_ms` y `error_code`. Nunca incluyen el texto del mensaje ni el
`chat_id` en claro.

Si un `assistant_id` cambió al reiniciar los agentes:

```powershell
python deploy/scripts/discover_assistants.py
```

El gateway lo descubre solo; el script sirve para verlo o fijarlo en el `.env`.

## Uso por Telegram

### Comandos

| Comando | Qué hace |
|---|---|
| `/start` | Presentación y ejemplos de consulta |
| `/help` | Ejemplos de uso (lo mismo que `/start`, sin la presentación) |
| `/reset` | Empieza una conversación nueva: el agente olvida el hilo anterior |

Cualquier otro `/comando` recibe un aviso con los comandos disponibles, sin llamar
al agente. Un mensaje que no sea texto (foto, nota de voz, documento, sticker) recibe
un aviso con ejemplos: el bot solo lee texto.

### Límites y costos

| Variable | Default | Para qué |
|---|---|---|
| `MAX_INPUT_CHARS` | `2000` | Corta consultas gigantes antes de gastar una llamada al modelo |
| `RATE_LIMIT_PER_MINUTE` | `6` | Evita bucles accidentales; `0` lo desactiva |
| `RATE_LIMIT_PER_DAY` | `100` | Tope diario por chat/usuario; `0` lo desactiva |
| `MAX_OUTPUT_TOKENS` | `1024` | Tope de salida del modelo; lo leen los agentes |
| `TELEGRAM_SEND_ENABLED` | `true` | `false` = dry-run: procesa y loguea, pero no envía |

Los límites de uso viven en la memoria del proceso: en Lambda cada contenedor
arranca su propio contador. Alcanzan para proteger la cuota de Gemini de un bucle,
no para una cuota exacta entre instancias.

`MAX_OUTPUT_TOKENS` se lee al arrancar los agentes: si se cambia, hay que reiniciar
`langgraph dev` (o el dyno de Heroku).

### Cómo detener todo

1. `Ctrl+C` en la terminal del gateway y en la de cada agente.
2. Bot de prueba (long polling): `Ctrl+C`; opcionalmente
   `curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook?drop_pending_updates=true"`.
3. Nube: `heroku ps:scale web=0 --app <app>` en cada app, o poner la concurrencia
   reservada de la Lambda en **0** (deja de aceptar invocaciones sin borrar nada).
4. Para cortar el gasto de modelos: revocar la `GOOGLE_API_KEY` en AI Studio.
5. Presupuesto: en Google Cloud, un presupuesto con alerta al 50 % y 100 % no frena
   el gasto por sí solo; para frenarlo de verdad, revocar la clave o poner la
   concurrencia de Lambda en 0.

### Probar el canal Telegram en local (long polling)

```powershell
python deploy/scripts/local_bot.py
```

Usa `TELEGRAM_TOKEN_LOCAL`, un bot de **prueba** creado en @BotFather. El script:

- se niega a arrancar si ese token es igual a `TELEGRAM_TOKEN` (el de producción),
  porque `getUpdates` borra el webhook y el bot de la nube dejaría de responder;
- ejecuta `deleteWebhook` solo sobre el bot de prueba;
- procesa los mensajes con el mismo `GatewayService` que el webhook y `/v1/chat`
  (comandos, allowlist, límites, Markdown y troceado incluidos).

## Estructura

```
deploy/
├── gateway/
│   ├── gateway/
│   │   ├── config.py           # variables validadas al arrancar
│   │   ├── a2a_client.py       # JSON-RPC + descubrimiento + errores tipados
│   │   ├── router.py           # palabras clave + fallback LLM
│   │   ├── telegram_client.py  # Markdown→HTML, chunking, 429, ok:false
│   │   ├── telegram_update.py  # texto vs foto/voz/documento
│   │   ├── service.py          # orquestación, comandos, allowlist, límites, logs
│   │   ├── app.py              # FastAPI local
│   │   └── lambda_handler.py   # adaptador AWS
│   ├── lambda_handler.py       # entrypoint que usa Lambda
│   ├── Dockerfile
│   └── requirements.txt
├── agents/
│   ├── grupo4-agente-historia/   # agente A2A (puerto 2025)
│   └── grupo4-agente-geografia/  # agente A2A (puerto 2026)
├── scripts/
│   ├── smoke_local.py            # verificación local completa
│   ├── local_bot.py              # bot de prueba por long polling
│   ├── discover_assistants.py    # assistant_id de cada agente
│   ├── check_no_secrets.py       # escaneo antes de empaquetar
│   ├── package_delivery.ps1      # ZIP limpio
│   ├── deploy_heroku_build.py    # deploy por API de builds
│   ├── configure_agent_cards.py  # PUBLIC_BASE_URL + verificación de cards
│   ├── set_webhook.py
│   └── webhook_info.py
└── README.md
```

## Despliegue en la nube (opcional, +1)

### 1. Desplegar los agentes en Heroku

1. Crear las apps `grupo4-agente-historia` y `grupo4-agente-geografia`.
2. Config Vars: `GOOGLE_API_KEY`, `MODELO`, `PUBLIC_BASE_URL=https://<app>.herokuapp.com`
   y `A2A_SHARED_TOKEN` (el mismo valor que en la Lambda).
3. Desplegar: `python deploy/scripts/deploy_heroku_build.py` (o el deploy de GitHub).
4. Verificar: `https://<app>.herokuapp.com/ok` y
   `python deploy/scripts/configure_agent_cards.py`.

La Agent Card debe publicar `https://<app>.herokuapp.com/a2a/<uuid>`. Si aparece
`http://0.0.0.0:<puerto>`, falta `PUBLIC_BASE_URL` o no se desplegó el middleware
`src/.../http_app.py`.

Obtener el `assistant_id`:

```bash
curl -X POST https://<app>.herokuapp.com/assistants/search \
  -H "Content-Type: application/json" \
  -d '{"graph_id": "agente_profesor_historia"}'
```

### 2. Desplegar el gateway en AWS Lambda

1. Crear imagen Docker:
   ```bash
   cd deploy/gateway
   docker build -t gateway-lambda .
   ```
2. Subir a ECR:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com
   docker tag gateway-lambda:latest <account>.dkr.ecr.us-east-1.amazonaws.com/gateway-lambda:latest
   docker push <account>.dkr.ecr.us-east-1.amazonaws.com/gateway-lambda:latest
   ```
3. Crear la función Lambda desde la imagen (handler `lambda_handler.lambda_handler`).
4. Crear Function URL (Auth: NONE, o con IAM si preferís).
5. Configurar variables: `GOOGLE_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_SECRET`, `MODELO`,
   `A2A_HISTORIA_URL`, `A2A_GEOGRAFIA_URL`, `A2A_*_ASSISTANT_ID`, `A2A_SHARED_TOKEN`,
   `A2A_TIMEOUT_SECONDS=45`, `TELEGRAM_ALLOWED_CHAT_IDS` (o `TELEGRAM_ALLOW_ALL=true`),
   `LOG_FORMAT=json`.
6. Timeout: **120 segundos** (el gateway espera hasta 45 s por agente; una consulta
   mixta los llama en paralelo).

### 3. Configurar el webhook de Telegram

```bash
export TELEGRAM_TOKEN="tu_token"
export TELEGRAM_SECRET="tu_secreto"
export PUBLIC_URL="https://<function-url>.lambda-url.us-east-1.on.aws"

python deploy/scripts/set_webhook.py
python deploy/scripts/webhook_info.py
```

El detalle paso a paso del despliegue original está en `DEPLOYMENT.md`.

## Notas de seguridad

- El token de Telegram viaja en la URL de la Bot API. Por eso `gateway/logging_setup.py`
  deja los loggers `httpx`/`httpcore` en WARNING: sin eso, cada `sendMessage` quedaba
  registrado con el token completo.
- Los logs del gateway no guardan el texto de las consultas ni tokens; solo ruta,
  agentes, longitud, estado y duración.
- La allowlist y el `LOCAL_API_TOKEN` viven en variables de entorno, nunca en el código.
- El tráfico gateway → agentes se autentica con `A2A_SHARED_TOKEN` (Bearer). El token
  debe ser idéntico en la Lambda y en las dos apps de Heroku; si falta o no coincide,
  el agente responde **401** y el gateway devuelve un error claro, nunca una respuesta
  vacía como si fuera éxito.

## Costos (prueba mínima, ≤ 100 iteraciones)

| Servicio | Costo/mes |
|---|---|
| AWS Lambda (gateway) | $0 (free tier) |
| Heroku Basic dyno × 2 (agentes) | $14 |
| Google Gemini API (100 msg) | ~$0.01 |
| Telegram Bot API | $0 |
| **Total** | **~$14.01** |

## Riesgos operativos conocidos

- **Dynos:** hoy las dos apps usan dynos **Basic** (siempre activos, ~$14/mes). Si se
  bajan a **Eco** ($5/app), Heroku los duerme tras 30 min de inactividad: el primer
  mensaje paga el arranque en frío y puede superar el timeout del gateway.
- **Idempotencia:** el webhook de Telegram puede reintentar un `update_id` si la
  invocación tarda o falla. Hoy no hay deduplicación persistente (DynamoDB/SQS): un
  reintento puede generar una segunda respuesta y consumir cuota. El límite por chat
  acota el daño, no lo elimina.
- **Límites en memoria:** `RATE_LIMIT_*` vive en cada contenedor de Lambda; con varias
  instancias el límite efectivo se multiplica.
- **Credenciales:** el token viejo de `@history_teacher_001_bot` y la `GOOGLE_API_KEY`
  anterior siguen válidos hasta que se revoquen en BotFather / AI Studio.

## Notas

- Los dynos **Basic** de Heroku no se duermen; los **Eco** sí, tras 30 min de
  inactividad. El costo de la tabla asume Basic en las dos apps.
- Lambda Function URL tiene timeout máximo de 15 min (suficiente para Gemini).
- Para producción real, considerar Heroku Basic ($7/dyno) o AWS Fargate.
- `local_bot.py` (long polling) usa `TELEGRAM_TOKEN_LOCAL` y nunca el token de producción:
  `getUpdates` borra el webhook y el bot de la nube dejaría de responder.
