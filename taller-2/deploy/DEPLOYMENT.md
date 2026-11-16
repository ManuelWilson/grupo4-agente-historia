# Guía de despliegue y redespliegue

Arquitectura:

```
Telegram → AWS Lambda (gateway) → A2A (HTTPS + Bearer) → Heroku (agentes LangGraph)
```

Estado verificado el **2026-11-16**:

| Servicio | Estado | URL / identificador | Notas |
|---|---|---|---|
| `grupo4-agente-historia` | ✅ | `https://grupo4-agente-historia-d810bfcccd22.herokuapp.com` | Dyno **Basic**, `PUBLIC_BASE_URL` y `A2A_SHARED_TOKEN` seteados |
| `grupo4-agente-geografia` | ✅ | `https://grupo4-agente-geografia-df1b26d2ed18.herokuapp.com` | Dyno **Basic**, `PUBLIC_BASE_URL` y `A2A_SHARED_TOKEN` seteados |
| `gateway-telegram` (Lambda) | ✅ | `https://4fnvq6jlgay2it2asa2w5pj2ji0xxxob.lambda-url.us-east-1.on.aws` | Imagen `gateway-lambda:fase4-20261116`, timeout **120 s**, 512 MB |
| Webhook de Telegram | ✅ | `…lambda-url.us-east-1.on.aws/telegram` | `pending_update_count=0` |
| Auth A2A | ✅ | `/a2a/<uuid>` | Sin `Authorization` → **401**; con Bearer → **200** |
| Agent Card | ✅ | `/.well-known/agent-card.json?assistant_id=<uuid>` | `url` pública de Heroku + `securitySchemes: bearer` |

Assistant IDs vigentes:

- Historia: `7f6f2b12-8dc5-5ce2-a178-2db47369944a`
- Geografía: `bed88ad6-7b48-5518-a206-cb2d85c69cda`

> Los `assistant_id` pueden cambiar si la app se recrea. El gateway los descubre
> solo con `POST /assistants/search`; fijarlos en la Lambda es una optimización.

---

## 0. Prerrequisitos

- **AWS:** cuenta `421572135000`, región `us-east-1`, permisos de Lambda, ECR e IAM.
- **Heroku:** dos apps con dyno **Basic** (siempre activas) o Eco (se duermen).
- **Docker Desktop** corriendo (la imagen se construye para `linux/amd64`).
- **Python 3.12** con `boto3` (los scripts no necesitan AWS CLI).
- **Telegram:** bot creado en @BotFather y un chat que haya iniciado el bot.

### Secretos

No van en el repositorio. Archivo único fuera del proyecto:

```
%USERPROFILE%\.config\taller2\.env
```

Variables necesarias:

```
GOOGLE_API_KEY=...
TELEGRAM_TOKEN=...
TELEGRAM_SECRET=...
MODELO=gemini-3.5-flash-lite

A2A_HISTORIA_URL=https://grupo4-agente-historia-d810bfcccd22.herokuapp.com
A2A_GEOGRAFIA_URL=https://grupo4-agente-geografia-df1b26d2ed18.herokuapp.com
A2A_HISTORIA_ASSISTANT_ID=...
A2A_GEOGRAFIA_ASSISTANT_ID=...
A2A_SHARED_TOKEN=...          # el mismo en Lambda y en las dos apps de Heroku
A2A_TIMEOUT_SECONDS=45

TELEGRAM_ALLOWED_CHAT_IDS=... # chat que puede usar el bot
PUBLIC_URL=https://4fnvq6jlgay2it2asa2w5pj2ji0xxxob.lambda-url.us-east-1.on.aws

HEROKU_API_KEY=...
HEROKU_APP_HISTORIA=grupo4-agente-historia
HEROKU_APP_GEOGRAFIA=grupo4-agente-geografia

AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=421572135000
```

El archivo debe tener ACL solo para el usuario. Los scripts de este repo nunca
imprimen los valores.

---

## 1. Reproducción local

La guía paso a paso está en [`README.md`](README.md). Resumen:

```powershell
# Agentes (dos terminales), con el mismo A2A_SHARED_TOKEN si se prueba auth
langgraph dev --port 2025 --no-browser
langgraph dev --port 2026 --no-browser

# Gateway
uvicorn gateway.app:app --host 127.0.0.1 --port 8000
```

Sin `A2A_SHARED_TOKEN`, los agentes no exigen auth (modo local). Con token,
`/a2a/*` devuelve 401 sin `Authorization: Bearer`; la Agent Card y
`/assistants/search` siguen públicos.

---

## 2. Agentes en Heroku

### 2.1 Config Vars

| Variable | Valor |
|---|---|
| `GOOGLE_API_KEY` | clave de AI Studio |
| `MODELO` | `gemini-3.5-flash-lite` |
| `PUBLIC_BASE_URL` | `https://<app>.herokuapp.com` |
| `A2A_SHARED_TOKEN` | el mismo token que la Lambda |

No hace falta `PORT`: Heroku lo inyecta y el `Procfile` lo usa.

Para setear o rotar el token en las dos apps:

```powershell
python deploy/scripts/update_cloud_secrets.py --a2a-token
```

> **Orden importante:** primero se despliega el código del gateway y de los
> agentes que entiende el token, después se activa. Si se activa en los agentes
> antes de actualizar la Lambda, el bot productivo deja de responder (401).

### 2.2 Desplegar código

No hay Heroku CLI ni remoto de git: se usa la API de builds.

```powershell
python deploy/scripts/deploy_heroku_build.py --dry-run   # ver archivos y hash
python deploy/scripts/deploy_heroku_build.py             # subir y esperar el build
```

El script arma un tarball determinístico (sin `.git`, `.env`, cachés ni logs),
lo sube a la URL prefirmada y espera a que el build termine. Imprime el sha256
del tarball para trazabilidad.

### 2.3 Configurar y verificar las Agent Cards

```powershell
python deploy/scripts/configure_agent_cards.py
```

Lee la `web_url` real de cada app, setea `PUBLIC_BASE_URL`, elimina
`LANGGRAPH_API_URL` y espera a que la card publique
`https://<app>.herokuapp.com/a2a/<uuid>`.

Verificación manual:

```powershell
# 1) La card es pública y la URL no es 0.0.0.0
curl "https://<app>.herokuapp.com/.well-known/agent-card.json?assistant_id=<uuid>"

# 2) A2A sin token -> 401
curl -i -X POST "https://<app>.herokuapp.com/a2a/<uuid>" `
  -H "Content-Type: application/json" `
  -d '{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"message/send\",\"params\":{\"message\":{\"role\":\"user\",\"messageId\":\"<uuid>\",\"contextId\":\"<uuid>\",\"parts\":[{\"kind\":\"text\",\"text\":\"hola\"}]}}}'

# 3) A2A con token -> 200 y result.status.state=completed
curl -i -X POST "https://<app>.herokuapp.com/a2a/<uuid>" `
  -H "Authorization: Bearer <A2A_SHARED_TOKEN>" `
  -H "Content-Type: application/json" `
  -d '...'
```

`messageId` y `contextId` deben ser **UUID válidos** (con guiones). Un
`contextId` arbitrario devuelve HTTP 200 con un error JSON-RPC
`Failed to create run: Invalid thread ID`; el cliente del gateway lo trata como
fallo y nunca lo presenta como respuesta.

### 2.4 Rollback de un agente

Heroku guarda releases y builds. Por API:

```powershell
# Ver releases (la más reciente primero)
# GET /apps/<app>/releases
# Volver a una release anterior
# POST /apps/<app>/releases/<version>/rollback
```

También se puede redesplegar el tarball anterior: el script imprime el sha256 y
el build queda en **Activity**. En el panel: *Activity → build anterior →
Rollback*. Los dynos Basic no se duermen, así que un rollback no cambia el costo.

---

## 3. Gateway en AWS Lambda

### 3.1 Construir y subir la imagen

```powershell
cd deploy/gateway
docker build --no-cache --provenance=false --platform linux/amd64 `
  -t gateway-lambda:fase4-20261116 -t gateway-lambda:latest .
```

El login de ECR se hace con un token de boto3 (no hace falta AWS CLI):

```python
import base64, subprocess
import boto3

ecr = boto3.client("ecr", region_name="us-east-1")
registro = "421572135000.dkr.ecr.us-east-1.amazonaws.com"
token = ecr.get_authorization_token()["authorizationData"][0]["authorizationToken"]
password = base64.b64decode(token).decode().split(":", 1)[1]
subprocess.run(
    ["docker", "login", "--username", "AWS", "--password-stdin", registro],
    input=password.encode(),
    check=True,
)
subprocess.run(["docker", "tag", "gateway-lambda:fase4-20261116", f"{registro}/gateway-lambda:fase4-20261116"], check=True)
subprocess.run(["docker", "push", f"{registro}/gateway-lambda:fase4-20261116"], check=True)
```

La etiqueta `fase4-20261116` es inmutable y permite rollback; `latest` queda como
alias de conveniencia. Digest de esta corrida:
`sha256:6ec07e2990eed10c5899db29ff7f94ebb938e35573bbe50f019fe3ea4ae9872a`.

### 3.2 Actualizar código y configuración

```python
import boto3

lam = boto3.client("lambda", region_name="us-east-1")
lam.update_function_code(
    FunctionName="gateway-telegram",
    ImageUri="421572135000.dkr.ecr.us-east-1.amazonaws.com/gateway-lambda:fase4-20261116",
    Publish=True,
)
# Esperar State=Active y LastUpdateStatus=Successful antes de seguir.
```

Variables de entorno (preservar las existentes y agregar/actualizar):

| Variable | Valor |
|---|---|
| `GOOGLE_API_KEY`, `TELEGRAM_TOKEN`, `TELEGRAM_SECRET`, `MODELO` | secretos |
| `A2A_HISTORIA_URL`, `A2A_GEOGRAFIA_URL` | URLs de Heroku |
| `A2A_HISTORIA_ASSISTANT_ID`, `A2A_GEOGRAFIA_ASSISTANT_ID` | UUIDs vigentes |
| `A2A_SHARED_TOKEN` | mismo token que los agentes |
| `A2A_TIMEOUT_SECONDS` | `45` |
| `TELEGRAM_ALLOWED_CHAT_IDS` | chat(s) autorizados, separados por coma |
| `TELEGRAM_ALLOW_ALL` | `false` |
| `TELEGRAM_SEND_ENABLED` | `true` |
| `LOG_FORMAT` | `json` |
| `LOG_LEVEL` | `INFO` |

El timeout de la función es **120 s**. Justificación: el gateway espera hasta 45 s
por agente y una consulta mixta llama a los dos en paralelo; 120 s cubre el cold
start de Heroku y la latencia de Gemini sin acercarse al máximo de la Function URL.

```python
lam.update_function_configuration(
    FunctionName="gateway-telegram",
    Environment={"Variables": variables},
    Timeout=120,
)
```

Para rotar solo el token en Lambda y Heroku:

```powershell
python deploy/scripts/update_cloud_secrets.py --a2a-token
```

### 3.3 Function URL y webhook

La Function URL ya existe con `AuthType=NONE`. El webhook se configura con:

```powershell
python deploy/scripts/set_webhook.py
python deploy/scripts/webhook_info.py
```

Debe apuntar a `https://<function-url>/telegram`, con el mismo `TELEGRAM_SECRET`
que valida la Lambda.

### 3.4 Verificación end-to-end

Opción A (Telegram real): escribir al bot desde el chat autorizado.

Opción B (update firmado, sin esperar a una persona):

```python
import json, time, httpx

update = {
    "update_id": int(time.time() * 1000) % 2_000_000_000,
    "message": {
        "message_id": 1,
        "date": int(time.time()),
        "chat": {"id": CHAT_ID, "type": "private", "first_name": "Prueba"},
        "from": {"id": CHAT_ID, "is_bot": False, "first_name": "Prueba"},
        "text": "¿Cuál fue la causa principal de la Revolución Francesa?",
    },
}
r = httpx.post(
    FUNCTION_URL + "/telegram",
    json=update,
    headers={"X-Telegram-Bot-Api-Secret-Token": TELEGRAM_SECRET},
    timeout=180,
)
assert r.status_code == 200 and r.text == "OK"
```

En CloudWatch deben aparecer `clasificacion`, `consulta` con `status=ok` y
`a2a_task_id`, y `telegram_enviado` con `mensajes>=1`. Si aparece
`telegram_error: chat not found`, el `chat_id` de la allowlist nunca inició el
bot: no es un fallo del despliegue.

---

## 4. Rollback completo

### Lambda (imagen anterior)

```python
lam.update_function_code(
    FunctionName="gateway-telegram",
    ImageUri="421572135000.dkr.ecr.us-east-1.amazonaws.com/gateway-lambda@sha256:<digest-anterior>",
)
```

Listar digests:

```python
ecr.describe_images(repositoryName="gateway-lambda")["imageDetails"]
```

### Heroku (código anterior)

Panel: *Activity → release/build anterior → Rollback*. Por API:
`POST /apps/<app>/releases/<version>/rollback`.

### Orden seguro al revertir auth

1. Quitar `A2A_SHARED_TOKEN` de los agentes (o desplegar código anterior).
2. Revertir la Lambda a la imagen anterior.
3. Revertir los agentes.

Nunca dejar la Lambda nueva (que envía Bearer) contra agentes viejos que no lo
esperan, ni agentes nuevos (que lo exigen) contra una Lambda vieja que no lo envía.

---

## 5. Troubleshooting

| Síntoma | Causa probable | Solución |
|---|---|---|
| `401` en `/a2a/*` | Falta el Bearer o el token no coincide | Verificar `A2A_SHARED_TOKEN` en Lambda y en la app; rotar con `--a2a-token` |
| `502` en `/v1/chat` | Agente caído, timeout o auth rechazada | Revisar `/ok`, logs del gateway (`error_code`) y el token |
| `200` con error JSON-RPC `Invalid thread ID` | `contextId`/`messageId` no son UUID | Usar `uuid.uuid4()`; el gateway ya lo hace |
| `telegram_error: chat not found` | El chat de la allowlist nunca inició el bot | Enviar `/start` al bot o corregir el id |
| Lambda timeout | Agente lento o cold start | Timeout ya en 120 s; revisar latencia de Gemini/Heroku |
| `402 RESOURCE_EXHAUSTED` | Cuota de Gemini agotada | Recargar AI Studio o cambiar clave |
| Webhook sin respuesta | Secret o URL incorrectos | `webhook_info.py`; reconfigurar con `set_webhook.py` |
| Imagen no soportada | Manifest multi-arch | Rebuild con `--platform linux/amd64 --provenance=false` |
| Dyno dormido | Se cambió a Eco | Volver a Basic o usar un ping externo |

---

## 6. Costos

| Servicio | Costo/mes |
|---|---|
| AWS Lambda (gateway) | $0 (free tier; 512 MB, < 1 s de cómputo por consulta) |
| Heroku **Basic** × 2 (agentes) | **$14** |
| Google Gemini API (~100 mensajes) | ~$0.01 |
| Telegram Bot API | $0 |
| **Total** | **~$14.01** |

Si se baja a **Eco** ($5/app, $10 total), Heroku duerme los dynos tras 30 min de
inactividad: el primer mensaje paga cold start y puede acercarse al timeout. Para
producción con tráfico real, Basic es la opción documentada.

---

## 7. Riesgos y límites conocidos

- **Dynos:** Basic no duerme; Eco sí. El estado actual usa Basic.
- **Idempotencia:** no hay deduplicación persistente por `update_id`
  (DynamoDB/SQS). Si Telegram reintenta un update, el bot puede responder dos
  veces y consumir cuota. El límite por chat reduce el impacto, no lo elimina.
- **Límites en memoria:** `RATE_LIMIT_PER_MINUTE`/`DAY` viven en cada contenedor
  de Lambda; con varias instancias el límite efectivo se multiplica.
- **Contexto:** el gateway guarda el hilo por chat en memoria; en Lambda se pierde
  al reciclar el contenedor. No es una conversación persistente.
- **Credenciales viejas:** el token de `@history_teacher_001_bot` y la
  `GOOGLE_API_KEY` anterior siguen válidos hasta revocarlos en BotFather / AI
  Studio. No se pueden revocar desde este repositorio.
- **Sin AWS CLI:** los procedimientos usan boto3/Docker; si se instala AWS CLI,
  los mismos pasos aplican con `aws lambda`/`aws ecr`.

---

## 8. Checklist de replicabilidad

- [ ] Crear las dos apps de Heroku y elegir dyno (Basic para 24/7).
- [ ] Cargar Config Vars: `GOOGLE_API_KEY`, `MODELO`, `PUBLIC_BASE_URL`,
      `A2A_SHARED_TOKEN`.
- [ ] Desplegar agentes con `deploy_heroku_build.py`.
- [ ] Verificar `/ok` y `configure_agent_cards.py`.
- [ ] Construir y subir la imagen Lambda a ECR.
- [ ] Actualizar código, variables y timeout 120 s en Lambda.
- [ ] Configurar la Function URL y el webhook.
- [ ] Probar card pública, A2A 401/200 y una consulta end-to-end.
- [ ] Guardar evidencia remota en `docs/evidence/`.
- [ ] Rotar/revocar credenciales viejas fuera del repositorio.

---

*Evidencia de la corrida: `docs/evidence/logs/remote_a2a_auth.txt`,
`remote_cards.json`, `remote_lambda.json`, `remote_telegram_invoke.txt`,
`remote_telegram_real.txt` y capturas
`docs/evidence/capturas/10_remoto_a2a_401_200.png` y
`11_remoto_telegram.png`.*
