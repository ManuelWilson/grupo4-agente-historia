"""Orquestación de la consulta: router + agentes A2A + acceso + límites + logs.

El servicio no sabe de Telegram ni de HTTP: recibe texto y devuelve un `Reply`.
Así el mismo código atiende `POST /v1/chat` y el webhook de Telegram.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from gateway.a2a_client import (
    A2AClient,
    A2AError,
    AgentReply,
    AgentTarget,
)
from gateway.config import Settings
from gateway.router import Route, build_llm_router, classify

logger = logging.getLogger(__name__)

ETIQUETAS = {"historia": "Historia", "geografia": "Geografía"}

COMANDOS = ("/start", "/help", "/reset")

# Nombres legibles para lo que Telegram puede mandar y este bot no procesa.
TIPOS_NO_TEXTO = {
    "photo": "una foto",
    "voice": "una nota de voz",
    "audio": "un audio",
    "video": "un video",
    "video_note": "un video corto",
    "document": "un documento",
    "sticker": "un sticker",
    "location": "una ubicación",
    "contact": "un contacto",
    "poll": "una encuesta",
    "animation": "un GIF",
}

EJEMPLOS = (
    "Ejemplos de consultas:\n"
    "· ¿Cuáles fueron las causas de la Revolución Francesa?\n"
    "· ¿Cómo se forma un delta fluvial?\n"
    "· ¿Cómo influyó el relieve de los Andes en la economía colonial?"
)

TEXTO_AYUDA = f"Puedo responder consultas de historia y de geografía.\n{EJEMPLOS}"

TEXTO_START = (
    "¡Hola! Soy el asistente del Taller 2: respondo consultas de historia y geografía.\n\n"
    f"{EJEMPLOS}\n\n"
    "Comandos: /help para ver esto, /reset para empezar una conversación nueva."
)

TEXTO_RESET = (
    "Listo: empezamos una conversación nueva. "
    "Lo que hablamos antes ya no lo tengo en cuenta."
)

TEXTO_GENERICA = (
    "Este chat es para consultas de historia y geografía, y esa no parece ser de "
    "ninguno de los dos temas. ¿Querés preguntarme algo de historia o de geografía?"
)
TEXTO_SIN_CLASIFICAR = (
    "No pude clasificar la consulta. Probá reformularla mencionando el tema "
    "(por ejemplo, historia o geografía)."
)


def _sin_autorizacion() -> str:
    return (
        "No estoy autorizado a responder en este chat. "
        "Pedí que agreguen tu chat a TELEGRAM_ALLOWED_CHAT_IDS."
    )


def _comando_de(texto: str) -> str:
    """`/start@mi_bot` cuenta como `/start`: en grupos Telegram agrega el sufijo."""
    if not texto.startswith("/"):
        return ""
    return texto.split()[0].split("@", 1)[0].lower()


def _demasiado_larga(caracteres: int, maximo: int) -> str:
    return (
        f"La consulta es demasiado larga ({caracteres} caracteres; máximo {maximo}). "
        "Resumila y volvé a intentar."
    )


@dataclass(frozen=True)
class Reply:
    text: str
    route: str
    agents: tuple[str, ...] = field(default_factory=tuple)
    ok: bool = True
    error: str = ""
    task_ids: tuple[str, ...] = field(default_factory=tuple)


class RateLimiter:
    """Límite deslizante por clave (chat o usuario), en memoria del proceso.

    Es una protección de costo, no una cuota contable: en Lambda cada contenedor
    arranca con su propio contador. Sirve para que un bucle accidental no queme
    la cuota de Gemini; para límites exactos hace falta un almacén compartido.
    """

    def __init__(self, per_minute: int, per_day: int):
        self.per_minute = per_minute
        self.per_day = per_day
        self._eventos: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, now: float | None = None) -> tuple[bool, str]:
        """Devuelve `(permitido, motivo)`; si no se permite, no consume cupo."""
        if self.per_minute <= 0 and self.per_day <= 0:
            return True, ""
        now = time.monotonic() if now is None else now
        eventos = self._eventos[key]
        while eventos and now - eventos[0] > 86400:
            eventos.popleft()

        if self.per_day > 0:
            en_el_dia = len(eventos)
            if en_el_dia >= self.per_day:
                return False, f"límite diario de {self.per_day} consultas"
        if self.per_minute > 0:
            en_el_minuto = sum(1 for instante in eventos if now - instante <= 60)
            if en_el_minuto >= self.per_minute:
                return False, f"límite de {self.per_minute} consultas por minuto"

        eventos.append(now)
        return True, ""

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._eventos.clear()
        else:
            self._eventos.pop(key, None)


class GatewayService:
    def __init__(
        self,
        settings: Settings,
        client: A2AClient | None = None,
        llm_router=None,
    ):
        self.settings = settings
        self.client = client or A2AClient(
            timeout=settings.a2a_timeout,
            shared_token=settings.a2a_shared_token,
        )
        self.llm_router = llm_router if llm_router is not None else build_llm_router(settings)
        self.targets = {
            "historia": AgentTarget(
                "Historia",
                settings.historia_url,
                settings.historia_graph,
                settings.historia_assistant_id,
            ),
            "geografia": AgentTarget(
                "Geografía",
                settings.geografia_url,
                settings.geografia_graph,
                settings.geografia_assistant_id,
            ),
        }
        self.limiter = RateLimiter(
            settings.rate_limit_per_minute, settings.rate_limit_per_day
        )
        # Ruta por conversación: un seguimiento ("¿de qué te pregunté antes?") no
        # tiene palabras clave y el LLM lo vería como genérico. Se conserva el
        # agente del turno anterior. Best-effort: en Lambda cada contenedor tiene
        # su propia memoria.
        self._ruta_por_contexto: dict[str, str] = {}
        # Contexto vigente por chat: `/reset` lo rota y el agente arranca de cero.
        self._contexto_por_chat: dict[str, str] = {}

    # ---------- acceso ----------

    def is_allowed(self, chat_id: int | str | None, user_id: int | str | None) -> tuple[bool, str]:
        """Falla cerrado: sin allowlist configurada y sin `TELEGRAM_ALLOW_ALL`, rechaza."""
        if self.settings.telegram_allow_all:
            return True, "TELEGRAM_ALLOW_ALL=true"
        chat = str(chat_id) if chat_id is not None else ""
        user = str(user_id) if user_id is not None else ""
        if chat and chat in self.settings.telegram_allowed_chat_ids:
            return True, "chat autorizado"
        if user and user in self.settings.telegram_allowed_user_ids:
            return True, "usuario autorizado"
        return False, "chat/usuario fuera de la allowlist"

    # ---------- contexto por chat ----------

    def context_for_chat(self, chat_id: int | str) -> str:
        """Contexto estable por chat: la conversación sigue entre mensajes."""
        clave = f"tg:{chat_id}"
        contexto = self._contexto_por_chat.get(clave)
        if not contexto:
            contexto = f"tg:{chat_id}:{uuid.uuid4().hex}"
            if len(self._contexto_por_chat) >= 1000:
                self._contexto_por_chat.pop(next(iter(self._contexto_por_chat)))
            self._contexto_por_chat[clave] = contexto
        return contexto

    def reset_context(self, chat_id: int | str) -> None:
        """`/reset`: nuevo contexto y se olvida la ruta pegajosa anterior."""
        clave = f"tg:{chat_id}"
        anterior = self._contexto_por_chat.pop(clave, None)
        if anterior:
            self._ruta_por_contexto.pop(anterior, None)

    # ---------- canal Telegram ----------

    def handle_chat(
        self,
        chat_id: int | str | None,
        user_id: int | str | None = None,
        text: str = "",
        *,
        media_type: str | None = None,
    ) -> Reply:
        """Punto de entrada del canal Telegram: acceso, comandos, medios y límites."""
        started = time.monotonic()
        texto = (text or "").strip()

        allowed, motivo = self.is_allowed(chat_id, user_id)
        if not allowed:
            # El hash del chat ya viaja en el contexto de logs: nunca el id en claro.
            logger.info("acceso_rechazado", extra={"motivo": motivo})
            return self._finish(
                Reply(_sin_autorizacion(), "acceso", ok=False, error="no_autorizado"),
                started,
                motivo,
            )

        comando = _comando_de(texto)
        if comando in COMANDOS:
            return self._comando(comando, chat_id, started)

        if media_type:
            que = TIPOS_NO_TEXTO.get(media_type, "un archivo")
            return self._finish(
                Reply(
                    f"Por ahora solo puedo leer texto y me llegó {que}. "
                    "Escribime la consulta y la respondo.\n\n"
                    f"{EJEMPLOS}",
                    "entrada_invalida",
                    ok=False,
                    error="tipo_no_soportado",
                ),
                started,
                f"media:{media_type}",
            )

        if texto.startswith("/"):
            return self._finish(
                Reply(
                    f"No conozco el comando {texto.split()[0]}. "
                    "Los disponibles son /help y /reset.\n\n"
                    f"{EJEMPLOS}",
                    "comando_desconocido",
                    ok=False,
                    error="comando_desconocido",
                ),
                started,
                "comando desconocido",
            )

        if not texto:
            return self._finish(
                Reply(TEXTO_AYUDA, "entrada_invalida", ok=False, error="texto_vacio"),
                started,
                "texto vacío",
            )
        if len(texto) > self.settings.max_input_chars:
            return self._finish(
                Reply(
                    _demasiado_larga(len(texto), self.settings.max_input_chars),
                    "entrada_invalida",
                    ok=False,
                    error="texto_largo",
                ),
                started,
                "texto demasiado largo",
            )

        clave = f"user:{user_id}" if user_id is not None else f"chat:{chat_id}"
        permitido, motivo_limite = self.limiter.check(clave)
        if not permitido:
            # `clave` contiene el id: solo se registra el motivo y el sujeto.
            logger.info(
                "limite_alcanzado",
                extra={"motivo": motivo_limite, "sujeto": "user" if user_id is not None else "chat"},
            )
            return self._finish(
                Reply(
                    f"Llegaste al {motivo_limite}. "
                    "Esperá un poco y volvé a intentar; así cuidamos la cuota del modelo.",
                    "limite",
                    ok=False,
                    error="limite_de_uso",
                ),
                started,
                motivo_limite,
            )

        return self.handle(
            texto,
            self.context_for_chat(chat_id) if chat_id is not None else None,
            chat_id=chat_id,
            user_id=user_id,
        )

    def _comando(self, comando: str, chat_id: int | str | None, started: float) -> Reply:
        if comando == "/reset":
            if chat_id is not None:
                self.reset_context(chat_id)
            return self._finish(Reply(TEXTO_RESET, "comando"), started, "/reset")
        texto = TEXTO_START if comando == "/start" else TEXTO_AYUDA
        return self._finish(Reply(texto, "comando"), started, comando)

    # ---------- consulta ----------

    def handle(
        self,
        text: str,
        context_id: str | None = None,
        *,
        chat_id: int | str | None = None,
        user_id: int | str | None = None,
    ) -> Reply:
        started = time.monotonic()
        texto = (text or "").strip()

        if not texto:
            return self._finish(
                Reply(TEXTO_AYUDA, "sin_clasificar", ok=False, error="texto_vacio"),
                started,
                "texto vacío",
            )
        if len(texto) > self.settings.max_input_chars:
            return self._finish(
                Reply(
                    _demasiado_larga(len(texto), self.settings.max_input_chars),
                    "sin_clasificar",
                    ok=False,
                    error="texto_largo",
                ),
                started,
                "texto demasiado largo",
            )

        allowed, motivo = self.is_allowed(chat_id, user_id)
        if not allowed:
            # El hash del chat ya viaja en el contexto de logs: nunca el id en claro.
            logger.info("acceso_rechazado", extra={"motivo": motivo})
            return self._finish(
                Reply(_sin_autorizacion(), "sin_clasificar", ok=False, error="no_autorizado"),
                started,
                motivo,
            )

        route = classify(texto, self.llm_router)
        route = self._continuidad(route, context_id)

        logger.info(
            "clasificacion",
            extra={"route": route.name, "method": route.method, "reason": route.reason},
        )

        if route.name in ("historia", "geografia") and context_id:
            self._recordar(context_id, route.name)

        if route.name == "generica":
            return self._finish(Reply(TEXTO_GENERICA, route.name), started, route.reason)
        if route.name == "sin_clasificar":
            return self._finish(Reply(TEXTO_SIN_CLASIFICAR, route.name, ok=False), started, route.reason)

        base_context = context_id or str(uuid.uuid4())

        if route.name == "mixta":
            return self._handle_mixed(texto, base_context, route, started)

        reply = self._ask(route.name, texto, base_context)
        return self._finish(reply, started, route.reason)

    def _ask(self, ruta: str, texto: str, context_id: str) -> Reply:
        target = self.targets[ruta]
        etiqueta = ETIQUETAS[ruta]
        try:
            agent_reply: AgentReply = self.client.send_text(
                target,
                texto,
                self._context_for(context_id, ruta),
            )
        except A2AError as exc:
            logger.warning(
                "agente_error",
                extra={"agent": ruta, "error": type(exc).__name__, "detail": exc.detail},
            )
            return Reply(
                f"No pude consultar al agente de {etiqueta}. "
                "Puede ser un problema momentáneo del servicio; probá de nuevo en un momento.",
                ruta,
                (ruta,),
                ok=False,
                error=type(exc).__name__,
            )
        return Reply(
            agent_reply.text,
            ruta,
            (ruta,),
            error="",
            task_ids=(agent_reply.task_id,) if agent_reply.task_id else (),
        )

    def _handle_mixed(self, texto: str, context_id: str, route: Route, started: float) -> Reply:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futuros = {
                ruta: pool.submit(self._ask, ruta, texto, context_id)
                for ruta in ("historia", "geografia")
            }
            respuestas = {ruta: futuro.result() for ruta, futuro in futuros.items()}

        bloques: list[str] = []
        fallos: list[str] = []
        task_ids: list[str] = []
        for ruta in ("historia", "geografia"):
            respuesta = respuestas[ruta]
            if respuesta.ok:
                bloques.append(f"{ETIQUETAS[ruta]}:\n{respuesta.text}")
                task_ids.extend(respuesta.task_ids)
            else:
                fallos.append(ETIQUETAS[ruta])

        if fallos:
            bloques.append(
                "No pude consultar al agente de "
                + " ni al de ".join(fallos)
                + ". Probá de nuevo en un momento."
            )

        ok = len(fallos) < 2
        return self._finish(
            Reply(
                "\n\n".join(bloques),
                route.name,
                ("historia", "geografia"),
                ok=ok,
                task_ids=tuple(task_ids),
            ),
            started,
            route.reason,
        )

    @staticmethod
    def _context_for(context_id: str, ruta: str) -> str:
        """Un `contextId` por agente: la memoria de cada uno queda separada."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{context_id}:{ruta}"))

    def _continuidad(self, route: Route, context_id: str | None) -> Route:
        """Un seguimiento sin tema propio hereda el agente del turno anterior."""
        if not context_id or route.name not in ("generica", "sin_clasificar"):
            return route
        previa = self._ruta_por_contexto.get(context_id)
        if not previa:
            return route
        return Route(
            previa,
            f"seguimiento de la conversación ({route.name} sin tema propio)",
            "seguimiento",
        )

    def _recordar(self, context_id: str, ruta: str) -> None:
        if len(self._ruta_por_contexto) >= 1000:
            self._ruta_por_contexto.pop(next(iter(self._ruta_por_contexto)))
        self._ruta_por_contexto[context_id] = ruta

    def _finish(self, reply: Reply, started: float, reason: str) -> Reply:
        logger.info(
            "consulta",
            extra={
                "route": reply.route,
                "agents": ",".join(reply.agents),
                "a2a_task_id": ",".join(reply.task_ids),
                "status": "ok" if reply.ok else "error",
                "error_code": reply.error,
                "chars": len(reply.text),
                "latency_ms": round((time.monotonic() - started) * 1000),
                "reason": reason,
            },
        )
        return reply

    # ---------- salud ----------

    def health(self) -> dict:
        return {"ok": True, "service": "gateway", **self.settings.summary()}
