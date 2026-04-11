"""
Nodo de cliente cualificado para WhatsApp.

Genera una respuesta corta y natural basada en el historial y en el snapshot
de calificación, sin volver a abrir un flujo de herramientas.
"""

import logging

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableConfig

from src.support.agent.state import AgentState

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, max_tokens=220)

QUALIFIED_SYSTEM_PROMPT = """Eres Laura, asesora inmobiliaria de Grupo Nagaki, hablando por WhatsApp.

El cliente YA quedó cualificado. No vuelvas a hacer preguntas de calificación.

Tu objetivo en esta fase es:
1. Responder de forma breve y natural.
2. Confirmar el siguiente paso comercial cuando corresponda.
3. Si el cliente acepta seguir, decirle que un asesor lo contactará lo antes posible.

Reglas:
- Responde en tono humano y cercano.
- Sin emojis, sin markdown, sin listas.
- No repitas información técnica innecesaria.
- No abras búsquedas nuevas salvo que el cliente lo pida claramente.
- No inventes datos.
"""


def qualified_node(state: AgentState, config: RunnableConfig | None = None) -> dict:
    messages = state.get("messages", [])
    snapshot = state.get("qualification_snapshot") or {}

    context_parts = []
    preferred_zones = snapshot.get("preferredZones") or []
    if preferred_zones:
        context_parts.append(f"Zonas de interés: {', '.join(preferred_zones)}")
    if snapshot.get("budgetMax"):
        context_parts.append(f"Presupuesto máximo: {snapshot.get('budgetMax')} euros")
    if snapshot.get("property_type"):
        context_parts.append(f"Tipo de inmueble: {snapshot.get('property_type')}")
    if snapshot.get("funding_mode"):
        context_parts.append(f"Financiación: {snapshot.get('funding_mode')}")
    if snapshot.get("intent_type"):
        context_parts.append(f"Intención: {snapshot.get('intent_type')}")

    context_info = "\n".join(context_parts) if context_parts else "Sin datos adicionales"
    system_prompt = f"{QUALIFIED_SYSTEM_PROMPT}\n\nContexto útil del cliente:\n{context_info}"

    logger.info("=" * 60)
    logger.info("🏆 QUALIFIED NODE - Cliente Cualificado")
    logger.info("=" * 60)
    logger.info("Qualification stage: %s", snapshot.get("qualification_stage", "qualified"))
    logger.info("Tipo de propiedad: %s", snapshot.get("property_type", "unknown"))
    logger.info("Mensajes en historial: %s", len(messages))
    logger.info("=" * 60)

    input_messages = [SystemMessage(content=system_prompt), *messages]
    response = llm.invoke(input_messages)

    logger.info("💬 Qualified response: %s...", str(response.content)[:80])
    return {"messages": [response]}
