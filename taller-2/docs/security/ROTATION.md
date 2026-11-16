# Rotación de secretos — Fase 0

Fecha de trabajo: **2026-11-15**.

Los secretos reales **no viven en este repositorio**. La copia de trabajo está en:

```text
%USERPROFILE%\.config\taller2\.env
```

Esa carpeta está fuera de la entrega y tiene permisos restringidos al usuario actual. Los backups de rotación también quedan ahí; no se incluyen en el ZIP.

## Estado

| Credencial | Estado | Verificación |
|---|---|---|
| AWS access key | ✅ Rotada | La key vieja quedó `Inactive` y STS la rechaza con `InvalidClientTokenId`; la nueva funciona. |
| Heroku API key | ✅ Rotada | Se creó una autorización nueva, se eliminó la vieja y la vieja responde HTTP 401. |
| Telegram webhook secret | ✅ Rotado | El secreto viejo recibe HTTP 403; el nuevo recibe HTTP 200 en la Function URL. |
| Telegram bot token | ⚠️ Migrado a bot propio | Se creó `@history_teacher_taller_bot` y Lambda/webhook ya usan su token. El token del bot viejo (`@history_teacher_001_bot`) sigue válido: solo lo puede revocar el compañero dueño de ese bot. |
| Google AI Studio key | ⚠️ Nueva key sincronizada | Lambda y los dos agentes de Heroku ya usan la key nueva y `/ok` responde 200. La vieja sigue siendo válida hasta revocarla en AI Studio. |

## Qué se hizo

1. Se sacó `.env` de la carpeta del proyecto.
2. Se creó `.env.example` en la raíz y se actualizaron los ejemplos de cada agente con valores ficticios.
3. Se agregó `.gitignore` raíz para `.env*`, `.venv`, cachés, logs, `.git` anidados, `.vscode` y artefactos de empaquetado.
4. Se agregó `deploy/scripts/check_no_secrets.py` y se ejecutó sobre todo el proyecto.
5. Se agregó `deploy/scripts/package_delivery.ps1`; el ZIP de prueba se generó sin `.env`, `.git`, `.venv`, cachés ni logs.
6. Se sanitizaron rutas absolutas de usuario en notebooks y logs de evidencias.
7. Se rotaron AWS, Heroku y el secreto del webhook de Telegram.
8. Se migró el gateway a un bot propio (`@history_teacher_taller_bot`); el token viejo del bot del compañero sigue válido hasta que él lo revoque.

## Excepción aceptada (2026-11-15)

No fue posible contactar al compañero dueño del bot viejo ni, por ahora, revocar la key vieja de Google. Se decide proseguir con el plan de mejora dejando el riesgo documentado:

- El token viejo del bot (`@history_teacher_001_bot`) y la Google API key vieja siguen siendo válidas, pero ya no se usan en Lambda, Heroku ni en la entrega.
- El riesgo se limita a quien posea esas credenciales: puede controlar el bot viejo o consumir cuota de la key vieja.
- La Fase 0 no se cierra como completa hasta que ambas revocaciones se verifiquen con `verify_phase0.py` (debe devolver `0`).
- Cuando haya contacto, se revocan, se reejecuta el verificador y, si ya no hacen falta, se eliminan los backups `.env.before-*` de la carpeta segura.

## Pendiente 1 — Token del bot viejo (dueño: compañero)

Se migró el proyecto a un bot propio (`@history_teacher_taller_bot`) y ya está sincronizado con Lambda. Pero el token viejo del bot del compañero todavía funciona, y eso no cumple el criterio de aceptación.

1. El compañero dueño de `@history_teacher_001_bot` abre Telegram con **@BotFather**.
2. `/mybots` → selecciona `@history_teacher_001_bot` → **API Token** → **Revoke current token**.
3. Confirma conmigo que lo revocó; vuelvo a ejecutar:

   ```powershell
   python deploy/scripts/verify_phase0.py
   ```

   La línea del token viejo debe pasar de `FALLO` a `OK`.

Si el compañero no puede revocarlo, la alternativa es aceptar ese riesgo por escrito antes de entregar; no se puede cerrar la Fase 0 como completa mientras el token viejo responda.

## Pendiente 2 — Google AI Studio key

La clave de Gemini permite consumir cuota y está en Lambda y en las dos apps de Heroku. Hay que reemplazarla y revocar la vieja.

1. Entrar a <https://aistudio.google.com/app/apikey> con la cuenta del proyecto.
2. Crear una key nueva, idealmente restringida a **Generative Language API**.
3. Guardarla **solo** en `%USERPROFILE%\.config\taller2\.env`:

   ```dotenv
   GOOGLE_API_KEY=<key-nueva>
   ```

4. Sincronizar Lambda y Heroku:

   ```powershell
   python deploy/scripts/update_cloud_secrets.py --google
   ```

   El script valida la key nueva antes de tocar la nube, actualiza `GOOGLE_API_KEY` en Lambda y en `HEROKU_APP_HISTORIA` y `HEROKU_APP_GEOGRAFIA`, y verifica `/ok` en ambos agentes. Si la key es inválida, aborta sin cambios.

5. Probar una consulta A2A real a cada agente (ver `deploy/scripts/check_agents.py` cuando esté disponible en la Fase 3).
6. Recién después de verificar, **revocar/eliminar la key vieja** en AI Studio. Si la key vieja pertenece al proyecto de tu compañero, él tiene que eliminarla; la creación de una key nueva propia no la invalida.

## Verificación de aceptación de la Fase 0

El criterio se comprueba con un solo comando, sin exponer secretos:

```powershell
python deploy/scripts/verify_phase0.py
```

El script revisa la carpeta del proyecto, el ZIP de entrega y, con los valores
viejos que quedaron en los backups fuera del repositorio, prueba que cada
credencial anterior ya fue rechazada. Devuelve:

- `0`: cumple todo.
- `1`: hay un fallo (por ejemplo, una credencial vieja todavía funciona).
- `2`: quedan pendientes.

Salida actual (2026-11-15):

```text
[OK   ] No hay archivos .env dentro del proyecto.
[OK   ] El escaneo de secretos no encontro hallazgos.
[OK   ] El ZIP de entrega esta limpio (52 entradas).
[OK   ] La access key vieja de AWS (DCOC) esta rechazada (InvalidClientTokenId).
[OK   ] El token viejo de Heroku esta rechazado (HTTP 401).
[FALLO] El token viejo del bot todavia funciona: revocarlo en BotFather.
[OK   ] El gateway rechaza un secreto invalido (403) y acepta el actual (200).
[FALLO] La Google API key vieja todavia es valida: revocarla en AI Studio.
[OK   ] Historia: /ok devolvio HTTP 200.
[OK   ] Geografia: /ok devolvio HTTP 200.
```

- [x] `.env` no existe dentro de la carpeta del proyecto.
- [x] `.env.example` existe con valores ficticios.
- [x] `python deploy/scripts/check_no_secrets.py` devuelve `OK`.
- [x] El ZIP de prueba no contiene `.env`, `.git`, `.venv`, cachés ni logs.
- [x] AWS access key vieja desactivada y rechazada.
- [x] Heroku API key vieja eliminada y rechazada.
- [x] Telegram webhook secret viejo rechazado (403) y nuevo aceptado (200).
- [x] Telegram migrado a bot propio (`@history_teacher_taller_bot`); Lambda y webhook actualizados.
- [ ] Telegram bot token viejo revocado en BotFather (requiere el compañero dueño del bot).
- [ ] Google API key vieja revocada en AI Studio.

**No cerrar la Fase 0 como completa hasta que los dos pendientes estén marcados y
`verify_phase0.py` devuelva `0`.**

## Notas de seguridad

- Los backups `.env.before-rotation-*` contienen credenciales viejas. Mantenerlos en la carpeta restringida y eliminarlos cuando ya no se necesiten para rollback.
- No enviar capturas del `.env`, de la consola con tokens ni de la configuración de Lambda/Heroku con valores.
- Si una credencial se compartió fuera de este equipo, asumir que está comprometida aunque se revoque: revisar logs de uso y rotar de nuevo si hay actividad extraña.
- Para el +1, el evaluador debe recibir acceso autorizado por un canal privado, no el token ni la API key.
