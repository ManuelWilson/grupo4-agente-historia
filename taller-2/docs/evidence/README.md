# Evidencias — Taller 2

Fecha de la corrida: **2026-11-15/16**. Entorno local: Windows, Python 3.12, los dos
agentes con `langgraph dev` (`127.0.0.1:2025` y `:2026`), gateway FastAPI
(`127.0.0.1:8000`) y el bot de prueba `@grupo4_taller2_prueba_bot` por *long polling*.
La verificación remota del 2026-11-16 usa Lambda + Heroku y está etiquetada
**REMOTE** en los archivos.

Cada caso de `docs/casos_prueba.md` apunta al archivo de esta carpeta que lo respalda.
La regla es simple: **si no hay captura o log, el caso no está probado**.

## Privacidad

- Los logs no guardan el texto de las consultas, el `chat_id` ni tokens: solo un
  `chat_id_hash` de 12 caracteres derivado con `LOG_HASH_SALT`. Si la sal no está
  fijada, es aleatoria por proceso: el mismo chat cambia de hash tras un reinicio.
- Verificación de esta corrida sobre `logs/*.jsonl` y `logs/*.txt`: el `chat_id`
  real no aparece, el token local tampoco y ninguna de las cinco consultas de
  Telegram aparece como texto. Los `logs/api_*.json` son capturas de respuesta
  (incluyen pregunta y respuesta a propósito), no logs.
- Las capturas de Telegram muestran la conversación, nunca el token del bot ni
  datos de la cuenta. El bot y el chat se identifican por su nombre público.

## Estructura

```text
docs/evidence/
├── README.md                  este archivo
├── capturas/                  Telegram (01-07), API/log local (08-09) y remoto (10-11)
└── logs/
    ├── smoke_local.txt        /ok + cards + /health + API 401/200
    ├── api_local.txt          401 sin token y 200 con token, con X-Request-ID
    ├── api_<caso>.json        respuesta completa de /v1/chat por caso
    ├── api_casos.txt          resumen: ruta, agentes, task_ids, longitud
    ├── api_entradas_invalidas.txt   vacío y >2000 caracteres → 422
    ├── gateway_local.jsonl    líneas JSON reales del gateway (API)
    ├── telegram_bot.jsonl     líneas JSON reales del bot por long polling
    ├── health_local.json      GET /health
    ├── check_agents_local.txt preflight local: /ok + card + consulta A2A
    ├── check_agents_remoto.txt  preflight remoto: /ok + card + 401 + consulta A2A
    ├── remote_cards.json      cards de Heroku: URL pública + security bearer
    ├── remote_a2a_auth.txt    401 sin token / 200 con token en Heroku
    ├── remote_lambda.json     imagen, timeout 120 y env de la Lambda (sin valores)
    ├── remote_telegram_invoke.txt  update firmado + logs de CloudWatch
    ├── remote_telegram_real.txt    consulta real desde Telegram Web + logs
    ├── webhook_info.txt       getWebhookInfo del bot de producción
    ├── pytest.txt             tests del gateway
    ├── qa_zip_fase5.txt       QA del ZIP: venv nuevo, instalación, 143 tests y reinicio
    └── sanitizacion.txt       notebooks y .run.log sin rutas absolutas
```

## Cómo se generó

```powershell
# Agentes y gateway (terminales separadas)
langgraph dev --port 2025 --no-browser
langgraph dev --port 2026 --no-browser
uvicorn gateway.app:app --host 127.0.0.1 --port 8000   # desde deploy/gateway

# Preflight y smoke
python deploy/scripts/check_agents.py --historia http://127.0.0.1:2025 --geografia http://127.0.0.1:2026
python deploy/scripts/smoke_local.py --chat

# Tests
python -m pytest deploy/tests -q
```

`gateway_local.jsonl` se extrajo del log del gateway filtrando por el `request_id`
que devuelve `POST /v1/chat` (header `X-Request-ID` y campo `request_id` del cuerpo).
Así se une, en una sola línea, la solicitud con la ruta, los agentes y el
`a2a_task_id` de la tarea A2A.

`telegram_bot.jsonl` sale del `stdout` del bot local con `LOG_FORMAT=json`. Cada
update de Telegram trae `update_id` y `chat_id_hash`; si el proceso se reinicia sin
`LOG_HASH_SALT`, el hash cambia, pero la secuencia de eventos se mantiene.

## Capturas

| Archivo | Qué muestra |
|---|---|
| `capturas/01_telegram_historia.png` | Consulta de historia respondida por el agente de historia |
| `capturas/02_telegram_geografia.png` | Consulta de geografía respondida por el agente de geografía |
| `capturas/03_telegram_mixta.png` | Consulta mixta: bloque `Historia:` de la respuesta |
| `capturas/03b_telegram_mixta_geografia.png` | Consulta mixta: bloque `Geografía:` completo |
| `capturas/04_telegram_datos_faltantes.png` | El agente pide región/período antes de responder |
| `capturas/05_telegram_entrada_invalida.png` | Foto rechazada con ejemplos de uso |
| `capturas/06_telegram_acceso_permitido.png` | Chat en la allowlist: responde |
| `capturas/07_telegram_acceso_rechazado.png` | Chat fuera de la allowlist: “No estoy autorizado…” (mensaje completo visible, capturado a las 00:09 UTC) |
| `capturas/08_api_local_401_200.png` | `POST /v1/chat` sin token → 401 y con Bearer → 200, con `X-Request-ID` |
| `capturas/09_log_a2a_task_id.png` | Línea JSON del gateway que une `request_id` con `a2a_task_id` |
| `capturas/10_remoto_a2a_401_200.png` | **REMOTE**: Agent Cards de Heroku, A2A sin token → 401 y con Bearer → 200 |
| `capturas/11_remoto_telegram.png` | **REMOTE**: pregunta enviada desde Telegram Web y respuesta del bot productivo (recortada para excluir contactos) |

Las capturas 08, 09, 10 y 11 son imágenes de la **salida real** guardada en
`logs/api_local.txt`, `logs/gateway_local.jsonl`, `logs/remote_a2a_auth.txt` y de
la conversación real de Telegram Web: no son mockups. La captura 11 se recortó
para excluir el sidebar con contactos y datos de la cuenta. El `/health` se
capturó con `TELEGRAM_ALLOW_ALL=false` y la allowlist real; la prueba de API local
corrió con `TELEGRAM_ALLOW_ALL=true` porque `/v1/chat` no recibe `chat_id` y, con
allowlist cerrada, responde 502.

## Alcance remoto (+1)

`remote_cards.json`, `remote_a2a_auth.txt` y `remote_lambda.json` prueban el
despliegue del 2026-11-16:

- Las Agent Cards de Heroku publican `https://<app>.herokuapp.com/a2a/<uuid>` y
  declaran `securitySchemes: bearer`.
- `POST /a2a/<uuid>` sin `Authorization` responde **401** con
  `WWW-Authenticate: Bearer`; con `Authorization: Bearer <A2A_SHARED_TOKEN>`
  responde **200** y una tarea `completed` con texto real.
- La Lambda corre la imagen `gateway-lambda:fase4-20261116` con timeout **120 s**,
  `A2A_SHARED_TOKEN`, `A2A_TIMEOUT_SECONDS=45` y allowlist real.

`remote_telegram_invoke.txt` documenta la invocación del webhook con un update
firmado y los logs de CloudWatch. `remote_telegram_real.txt` y la captura 11
muestran el ida y vuelta real desde Telegram Web: pregunta de historia, respuesta
del agente y `telegram_enviado` con `mensajes=1`. El bot solo puede responder a un
chat que haya iniciado el bot: si el `chat_id` de la allowlist no existe para ese
bot, Telegram devuelve `chat not found` (se documenta como límite, no como éxito).

## QA de la entrega

`qa_zip_fase5.txt` registra la prueba final del **ZIP** en una carpeta temporal
distinta, con un venv nuevo y siguiendo el `README.md` de la raíz:

- instalación desde `requirements.lock` y los dos agentes en modo editable;
- agentes en `2025`/`2026` y gateway en `8000`;
- `check_agents.py` con 401 sin token y consulta A2A `completed`;
- `smoke_local.py --chat` con `/v1/chat` 401/200 y respuesta real;
- **143 tests OK**;
- reinicio completo de los tres procesos y segundo smoke OK.

El ZIP de esa corrida tenía **134 entradas** y SHA256
`CC49E2B7D4178772526C9ACF37D3905A5E8704108FBAE831943707924F002C84`.
Al agregar esta evidencia y volver a empaquetar, el ZIP final conserva el mismo
contenido funcional y gana una entrada; su hash cambia porque el contenido cambia.
Un ZIP no puede contener su propio hash, así que el hash final **no se fija dentro
del paquete**: lo imprime `package_delivery.ps1` y queda en
`dist/taller2-entrega.sha256.txt` (el mismo archivo que acompaña al ZIP en la
entrega). Sobre el ZIP final reempaquetado se repitieron `pytest` (143 OK) y el
preflight de agentes, además del escaneo de secretos.
