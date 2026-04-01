import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain.agents import create_agent

from src.support.agent.state import AgentState
from src.support.agent.nodes.conversation.tools import (
    buscar_info_viviendas,
    consultar_inmuebles,
    listar_ubicaciones_disponibles,
    buscar_inmueble_por_referencia,
    obtener_hora_actual,
    realizar_calculo,
    registrar_interes_cliente,
    finalizar_conversacion,
)
from src.support.agent.nodes.conversation.prompt import CONVERSATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, max_tokens=500)

tools = [
    buscar_info_viviendas,
    consultar_inmuebles,
    listar_ubicaciones_disponibles,
    buscar_inmueble_por_referencia,
    obtener_hora_actual,
    realizar_calculo,
    registrar_interes_cliente,
    finalizar_conversacion,
]

react_agent = create_agent(llm, tools=tools)


def _sanitize_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Filtra mensajes técnicos/corruptos antes de reenviarlos al modelo.

    El checkpointer persiste mensajes de herramientas, pero OpenAI rechaza
    historiales con ``tool`` huérfanos si ya no vienen precedidos por el
    ``assistant`` que originó los ``tool_calls``. Para nuevos turnos solo
    reenviamos memoria conversacional útil.
    """
    out: list[BaseMessage] = []
    for msg in messages:
        if msg is None:
            continue
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            # El tool call ya fue resuelto en un turno anterior; conservarlo en
            # checkpoint no implica reenviarlo al modelo en el siguiente turno.
            continue
        content = getattr(msg, "content", None)
        if content is None:
            continue
        if isinstance(content, str) and not content.strip():
            continue
        out.append(msg)
    return out


def conversation_node(state: AgentState) -> dict:
    messages = _sanitize_messages(state.get("messages", []))

    snapshot = state.get("qualification_snapshot") or {}
    qualified = bool(snapshot.get("qualified", state.get("qualified", False)))

    system_instruction = CONVERSATION_SYSTEM_PROMPT
    if qualified:
        system_instruction += (
            "\n\nSTATUS: CLIENTE CUALIFICADO (VIP). "
            "Este cliente ya fue validado. Atiéndelo con prioridad."
        )

    if not messages or not isinstance(messages[0], SystemMessage):
        mensajes_entrada = [SystemMessage(content=system_instruction)] + messages
    else:
        mensajes_entrada = list(messages)
        mensajes_entrada[0] = SystemMessage(content=system_instruction)

    result = react_agent.invoke({"messages": mensajes_entrada})
    new_messages = result.get("messages", [])

    response_messages = [msg for msg in new_messages if msg not in mensajes_entrada]
    return {"messages": response_messages}


def route_after_conversation(state: AgentState) -> str:
    """El turno termina tras conversation y vuelve a verification en el siguiente input."""
    _ = state
    return "end"
