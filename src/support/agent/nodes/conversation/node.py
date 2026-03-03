import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, ToolMessage
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
from src.support.agent.utils import sanitize_messages

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


def conversation_node(state: AgentState) -> dict:
    if state.get("conversation_closed", False):
        logger.info("Conversación cerrada - Ignorando mensaje")
        return {}

    messages = state.get("messages", [])
    messages = sanitize_messages(messages)
    
    system_instruction = CONVERSATION_SYSTEM_PROMPT
    if state.get("is_new_customer", False):
        system_instruction += "\n\nNOTA: Es la PRIMERA VEZ que hablas con este cliente. Preséntate como 'Laura de Grupo Nagaki'."

    if state.get("qualified", False):
        system_instruction += "\n\nSTATUS: CLIENTE CUALIFICADO (VIP). Este cliente ya fue validado. Atiéndelo con prioridad."

    if not messages or not isinstance(messages[0], SystemMessage):
        mensajes_entrada = [SystemMessage(content=system_instruction)] + messages
    else:
        mensajes_entrada = list(messages)
        mensajes_entrada[0] = SystemMessage(content=system_instruction)
    
    result = react_agent.invoke({"messages": mensajes_entrada})
    
    new_messages = result.get("messages", [])
    
    response_messages = []
    for msg in new_messages:
        if msg not in mensajes_entrada:
            response_messages.append(msg)
    
    return {"messages": response_messages}


def update_points_node(state: AgentState) -> dict:
    """
    Detecta cierre de conversación.
    Sistema de puntos deshabilitado temporalmente.
    """
    messages = state.get("messages", [])
    conversation_closed = state.get("conversation_closed", False)
    
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            break
        
        if msg.name == "finalizar_conversacion":
            logger.info("🛑 Detectada herramienta finalizar_conversacion: Cerrando permanentemente.")
            conversation_closed = True
            break

    updates = {}
    current_closed = state.get("conversation_closed", False)
    
    if conversation_closed != current_closed:
        updates["conversation_closed"] = conversation_closed
        
    return updates

def route_after_update_points(state: AgentState) -> str:
    """Enruta después de update_points. Siempre termina."""
    return "end"