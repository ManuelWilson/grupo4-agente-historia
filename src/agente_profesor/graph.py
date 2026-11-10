"""Agente profesor de historia · se expone por A2A de forma NATIVA con el servidor de LangGraph.

No hay código de servidor aquí. `langgraph dev` lee `langgraph.json`, levanta este grafo y publica:
  · la Agent Card  →  GET  /.well-known/agent-card.json?assistant_id=<uuid>
  · el endpoint    →  POST /a2a/<assistant_id>  (message/send, message/stream, tasks/get, tasks/cancel)

Requisito único: el estado del grafo debe tener la clave `messages` (create_agent la trae).
El `contextId` de A2A se convierte en `thread_id`: la memoria por conversación viene gratis.
"""
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import create_agent

from agente_profesor.herramientas import HERRAMIENTAS
from agente_profesor.prompts import SYSTEM_PROMPT

load_dotenv()

modelo = ChatGoogleGenerativeAI(model=os.environ.get("MODELO", "gemini-3.5-flash-lite"))

# Agente ReAct (LangChain 1.x): el modelo decide qué herramienta llamar, la llama, lee el resultado y responde.
graph = create_agent(
    model=modelo,
    tools=HERRAMIENTAS,
    system_prompt=SYSTEM_PROMPT,
    name="agente_profesor_historia",
)
