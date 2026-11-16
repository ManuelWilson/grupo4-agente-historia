# Casos de prueba — Taller 2

Corrida del **2026-11-15/16** (los `ts` de los logs están en UTC: 2026-11-16 por la
noche local; las capturas de API y log 08/09 son del 2026-11-16). Entorno local:
`langgraph dev` en `127.0.0.1:2025` (historia) y `:2026` (geografía), gateway en
`127.0.0.1:8000` y bot de prueba `@grupo4_taller2_prueba_bot` por *long polling*.

Reglas de lectura:

- **`chat_id_hash`** es un SHA-256 truncado a 12 caracteres con una sal. Sin
  `LOG_HASH_SALT` fija, la sal es aleatoria por proceso, así que el mismo chat puede
  mostrar hashes distintos tras un reinicio. No es reversible.
- Los logs **no** guardan el texto del mensaje, el `chat_id` en claro ni tokens.
  Los archivos `api_*.json` son capturas de respuesta (incluyen la pregunta y el
  texto devuelto a propósito), no logs.
- `request_id` une el cuerpo de `/v1/chat` o la línea del bot con las líneas JSON
  del gateway. `a2a_task_id` es el `task_id` que devuelve el agente A2A.

## Tabla de casos

| # | Entorno | Fecha | Solicitud | Esperado | Obtenido | Observaciones | Archivo |
|---:|---|---|---|---|---|---|---|
| 1 | LOCAL | 2026-11-15 | `¿Cuáles fueron las causas de la Revolución Francesa?` | Ruta `historia`; respuesta con causas y 1789 | `route=historia`, agente `historia`, **5154** caracteres en **2** mensajes, `request_id=190e49f74165`, `a2a_task_id=d1257012…:01a1e207…` | Captura 01; `reason=palabras clave: revolucion francesa` | `capturas/01_telegram_historia.png`, `logs/telegram_bot.jsonl`, `logs/api_historia.json` |
| 2 | LOCAL | 2026-11-15 | `¿Cómo se formó la cordillera de los Andes?` | Ruta `geografia`; respuesta geográfica | `route=geografia`, agente `geografia`, **2912** caracteres en **1** mensaje, `request_id=81df9f4e14e8`, `a2a_task_id=cc5e29ba…:01a1e20a…` | Captura 02; placa de Nazca y Sudamericana | `capturas/02_telegram_geografia.png`, `logs/telegram_bot.jsonl`, `logs/api_geografia.json` |
| 3 | LOCAL | 2026-11-15 | `¿Cómo influyó el clima del Nilo en el Egipto antiguo?` | Ruta `mixta`; ambos agentes en paralelo, respuestas etiquetadas | `route=mixta`, `agents=historia,geografia`, **9730** caracteres en **3** mensajes, **dos** `a2a_task_id` (`d1257012…` y `cc5e29ba…`), `request_id=5921b2caac8e` | Captura 03 muestra el bloque `Historia:`; la captura **03b** muestra el bloque `Geografía:` completo; los dos `task_id` están en `api_mixta.json` | `capturas/03_telegram_mixta.png`, `capturas/03b_telegram_mixta_geografia.png`, `logs/telegram_bot.jsonl`, `logs/api_mixta.json` |
| 4 | LOCAL | 2026-11-15 | `Háblame de la independencia` | Pedir región/período/nivel; no inventar | Pregunta **“¿A qué proceso de independencia te referís?”** y luego **región/país** y **nivel educativo**; 1262 caracteres, `route=historia` | Captura 04; no entrega un relato único sin contexto | `capturas/04_telegram_datos_faltantes.png`, `logs/telegram_bot.jsonl` |
| 5 | LOCAL | 2026-11-15 | `Resuelve esta integral: x^2 dx` | Derivar o rechazar claramente | `route=generica`, 154 caracteres: “Este chat es para consultas de historia y geografía…” | Sin llamada a agentes (`agents` vacío) | `logs/api_fuera_de_alcance.json` |
| 6 | LOCAL | 2026-11-15 | Foto sin texto | Mensaje claro con ejemplos; no llamar al agente | `route=entrada_invalida`, `status=error`, `error_code=tipo_no_soportado`, 268 caracteres, **0** agentes, `request_id=4ea42d7d531d` | Captura 05; `latency_ms=0` | `capturas/05_telegram_entrada_invalida.png`, `logs/telegram_bot.jsonl` |
| 7 | LOCAL | 2026-11-15 | Mensaje vacío / 2700 caracteres por API | `422` en los dos casos | `422` y `422` | Límite `MAX_INPUT_CHARS=2000` | `logs/api_entradas_invalidas.txt` |
| 8 | LOCAL | 2026-11-16 | `POST /v1/chat` sin y con token | `401` / `200` | `401` sin `Authorization` (`request_id=e25515eea0b3`); `200` con Bearer, `route=geografia` (`request_id=95f6818dac2e`) | Captura 08; `X-Request-ID` presente en ambas respuestas | `capturas/08_api_local_401_200.png`, `logs/api_local.txt`, `logs/smoke_local.txt` |
| 9 | LOCAL | 2026-11-15 | `hola` desde el chat autorizado | Responde sin llamar a agentes | `route=generica`, 154 caracteres, `status=ok`, `request_id=c02c95fe758f`, `chat_id_hash=d8f73e05fcb6` | Captura 06; allowlist con 1 chat | `capturas/06_telegram_acceso_permitido.png`, `logs/telegram_bot.jsonl` |
| 10 | LOCAL | 2026-11-15 | `hola` desde un chat **no** autorizado | “No estoy autorizado…”; 0 llamadas al agente | `route=acceso`, `status=error`, `error_code=no_autorizado`, 100 caracteres, **0** agentes, `latency_ms=0`, `request_id=58a61f62fb84`, `chat_id_hash=b4958e39ffc0` | Captura 07 **completa**: el mensaje “No estoy autorizado…” está visible, el hash `b4958e39ffc0` identifica el chat sin exponer el id | `capturas/07_telegram_acceso_rechazado.png`, `logs/telegram_bot.jsonl` |
| 11 | LOCAL | 2026-11-16 | Consulta de geografía por API | Log con solicitud → agente → tarea A2A | `request_id=95f6818dac2e`; `route=geografia`; `agents=geografia`; `a2a_task_id=1b82ef73…:01a1e489…`; `latency_ms=5531`; el `task_id` coincide con el del cuerpo | Captura 09; una línea JSON por evento | `capturas/09_log_a2a_task_id.png`, `logs/gateway_local.jsonl`, `logs/api_local.txt` |
| 12 | LOCAL | 2026-11-15 | Respuestas de 5154 y 9730 caracteres | Partir sin perder texto | 2 y 3 mensajes respectivamente; los `chars` del log coinciden con el total | Chunking por párrafos, tope 4000 | `logs/telegram_bot.jsonl` |
| 13 | LOCAL | 2026-11-15 | Agente caído / respuesta parcial | `502` si falla el único agente; `200` parcial si falla uno de la mixta | Cubierto por tests: `test_fallo_del_agente_es_502`, `test_mixta_con_un_fallo_lo_dice_y_no_inventa`, `test_mixta_con_ambos_fallos_es_error` | Sin captura en esta corrida | `logs/pytest.txt` |
| 14 | LOCAL | 2026-11-15 | Contexto y `/reset` | El seguimiento hereda el tema; `/reset` lo borra | Cubierto por tests: `test_seguimiento_hereda_el_agente_del_contexto`, `test_reset_rota_el_contexto_y_olvida_la_ruta` | Verificado en Telegram en la Fase 2 | `logs/pytest.txt` |
| 15 | REMOTE | 2026-11-16 | Agent Cards de Heroku | Card pública con URL pública y auth declarada | Ambas `200`; `url=https://…herokuapp.com/a2a/<uuid>`, `security=[{"bearer":[]}]` y `securitySchemes=bearer` | Captura 10; `remote_cards.json` | `capturas/10_remoto_a2a_401_200.png`, `logs/remote_cards.json`, `logs/remote_a2a_auth.txt` |
| 16 | REMOTE | 2026-11-16 | `POST /a2a/<uuid>` sin y con token | `401` sin token; `200` con tarea `completed` | Historia: `401` + `WWW-Authenticate: Bearer`; con Bearer `200`, `state=completed`, 207 chars, `task_id=40a4c89b…:01a1e49f…`. Geografía: `200`, 213 chars, `task_id=a73ba7dd…` | Captura 10; sin error JSON-RPC; `check_agents.py` repite 401/200 | `capturas/10_remoto_a2a_401_200.png`, `logs/remote_a2a_auth.txt`, `logs/check_agents_remoto.txt` |
| 17 | REMOTE | 2026-11-16 | Lambda `gateway-telegram` | Imagen nueva, timeout 120, token A2A y allowlist | `ImageUri=…gateway-lambda:fase4-20261116`, timeout **120 s**, `A2A_SHARED_TOKEN` seteado, `A2A_TIMEOUT_SECONDS=45`, allowlist 1 chat, `TELEGRAM_ALLOW_ALL=false` | Verificado por API; sin secretos en la evidencia | `logs/remote_lambda.json`, `deploy/DEPLOYMENT.md` |
| 18 | REMOTE | 2026-11-16 | Consulta real desde Telegram Web | El bot productivo responde por el webhook | `route=historia`, `status=ok`, `a2a_task_id=c0e8f2b3…:01a1e4c0…`, **407** caracteres, `mensajes=1`, `latency_ms=2420`, `update_id=837466093` | Captura 11 recortada (sin contactos ni datos de la cuenta); chat `@history_teacher_taller_bot` | `capturas/11_remoto_telegram.png`, `logs/remote_telegram_real.txt` |
| 19 | LOCAL (ZIP) | 2026-11-16 | Descomprimir el ZIP en una carpeta temporal, crear venv e instalar según el README | Arranque repetido, consulta real y 143 tests | Venv nuevo con Python 3.12.10; `check_agents` 401/200; `smoke_local --chat` 200; **143 passed**; se detuvo y reinició todo y el segundo smoke dio OK | Sin `.env` dentro del ZIP; el `.env` de QA se creó aparte; sin secretos en la evidencia | `logs/qa_zip_fase5.txt` |

## Cómo reconstruir un caso

Ejemplo con el caso 1:

1. La captura `01_telegram_historia.png` muestra la pregunta y la respuesta.
2. En `telegram_bot.jsonl`, la línea `consulta` con `request_id=190e49f74165` dice
   `route=historia`, `agents=historia`, `a2a_task_id=d1257012…`, `chars=5154`,
   `latency_ms=7250` y `update_id=276417187`.
3. La línea `telegram_enviado` del mismo `request_id` confirma 2 mensajes enviados.
4. `api_historia.json` repite el mismo camino por HTTP y trae el `task_id` completo.

## Límites conocidos de esta corrida

- La conversación real del **bot remoto** se validó con un update firmado contra la
  Function URL (ver caso 18). No se automatiza el envío desde una cuenta de Telegram:
  el chat debe haber iniciado el bot; si no, la API devuelve `chat not found`.
- El acceso rechazado se probó cambiando la allowlist a un chat inexistente y
  reiniciando el bot de prueba; el chat real quedó fuera y no se llamó a ningún agente.
- Los `a2a_task_id` completos están en los JSON; en la tabla se abrevian para lectura.
- El `GET /health` de `health_local.json` se capturó con la allowlist real
  (`telegram_allow_all=false`, 1 chat). Las pruebas de `POST /v1/chat` corrieron con
  `TELEGRAM_ALLOW_ALL=true` porque el endpoint no recibe `chat_id` y, con la allowlist
  cerrada, responde 502 (`no_autorizado`).
- Los agentes remotos exigen `A2A_SHARED_TOKEN`; la Lambda lo envía. Una llamada
  directa a `/a2a/*` sin token responde 401 y no ejecuta el agente.
