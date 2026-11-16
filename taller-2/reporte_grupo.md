# Reporte para el grupo — Taller 2 listo para entrega

**Base:** `verificacion-plan.md` (matriz inicial: 6 críticas, 5 ⚠️, solo 2 ✅). 
**Hoy:** todas las fases 0–5 cerradas con evidencia.

## Antes → después

| Requisito | Antes | Ahora |
|---|---|---|
| Recorrido local reproducible | ❌ solo Lambda | ✅ README + `requirements.lock` + Python 3.12; 3 terminales y corre |
| Control de acceso | ❌ bot público | ✅ allowlist por chat/usuario + `LOCAL_API_TOKEN` + Bearer A2A |
| Errores y límites | ❌ errores crudos, silencios | ✅ 502 claro, 422, dry-run, rate limit, tope de entrada/salida |
| Varios agentes y fidelidad | ⚠️ un solo agente | ✅ ruta mixta en paralelo, texto exacto etiquetado |
| Evidencia y trazabilidad | ❌ no había | ✅ 18 casos, 11 capturas, logs JSON con `request_id`→`a2a_task_id` |
| Secretos y portabilidad | ❌ `.env` dentro | ✅ `.env` fuera, `.env.example`, escáner, ZIP limpio (135 entradas) |
| Despliegue | ⚠️ card interna, sin auth, 30 s | ✅ card pública, 401 sin token, timeout 120 s, Basic |
| README / pruebas | ❌ | ✅ README raíz + 143 tests |

## Por fase (lo hecho)

- **F0 Seguridad:** `.env` fuera del repo, `.env.example`, `.gitignore`, `check_no_secrets.py`.
- **F1 Local:** gateway FastAPI (`/health`, `/v1/chat`, webhook), `local_bot.py` con polling y bot de prueba propio, `smoke_local.py`.
- **F2 Robustez:** allowlist (falla cerrado), 401/403, errores A2A tipados, chunking >4000 chars, Markdown→HTML, reintentos 429, `/start /help /reset`.
- **F3 Evidencia:** logs JSON sanitizados (`chat_id_hash`, sin texto ni ids), tabla de 18 casos, capturas 01–11.
- **F4 +1 nube:** Heroku con card pública y `securitySchemes: bearer`; Lambda imagen `fase4-20261116`, timeout **120 s**, `A2A_TIMEOUT_SECONDS=45`; bot respondió consulta real desde Telegram Web (407 chars, 2,4 s).
- **F5 Empaquetado:** `package_delivery.ps1`, ZIP probado en venv nuevo (143 tests OK, arranque repetido OK).

## Números de cierre

- **143 tests OK** · **18 casos** (11 LOCAL, 4 REMOTE, 3 de ZIP/QA) · **12 capturas**
- ZIP: `dist/taller2-entrega.zip` — 135 entradas, SHA256 `8FCBFB0C…` (ver `dist/taller2-entrega.sha256.txt`)
- GitHub: PR [#1](https://github.com/ManuelWilson/grupo4-agente-historia/pull/1) (rama `taller-2`, todo en `taller-2/`, `main` intacto)

## Lo que queda

- Sin idempotencia por `update_id` (riesgo de respuesta duplicada si Telegram reintenta).
- Contexto en memoria (se pierde al reiniciar); rate limit por instancia, no global.
- Token viejo de `@history_teacher_001_bot` y Google API key anterior: hay que revocarlos desde BotFather/AI Studio (no se puede desde acá).

## Verificar en 3 comandos

```powershell
python -m pip install -r requirements.lock
python -m pytest deploy/tests -q        # 143 passed
python deploy/scripts/smoke_local.py --chat
```

Punto de partida: `README.md` raíz. Detalle: `deploy/DEPLOYMENT.md`. Evidencia: `docs/evidence/README.md`.