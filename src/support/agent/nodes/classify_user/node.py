"""
Nodo de Clasificación de Usuario - Grupo Nagaki

Este nodo maneja conversaciones con usuarios interesados.
Usa React Agent para manejar herramientas internamente.
"""

import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AIMessage
from langgraph.prebuilt import create_react_agent
from src.support.agent.utils import sanitize_messages

from src.support.agent.state import AgentState
from src.support.agent.nodes.conversation.tools import consultar_inmuebles, listar_ubicaciones_disponibles
from src.support.agent.nodes.classify_user.prompt import (
    CLASSIFY_USER_SYSTEM_PROMPT,
    get_property_question
)

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, max_tokens=300)
tools = [consultar_inmuebles, listar_ubicaciones_disponibles]
react_agent = create_react_agent(llm, tools)


def classify_user_node(state: AgentState) -> dict:
    """
    Nodo de conversación para usuarios interesados.
    Usa React Agent para manejar herramientas.
    """
    messages = state.get("messages", [])
    messages = sanitize_messages(messages)
    
    property_type = state.get("property_type", "unknown")
    property_question = get_property_question(property_type)
    
    full_system_prompt = f"""{CLASSIFY_USER_SYSTEM_PROMPT}

**PREGUNTA ESPECÍFICA SOBRE EL TIPO DE INMUEBLE:**
{property_question}

Usa esta pregunta en el momento apropiado de la conversación."""
    
    if not messages or not isinstance(messages[0], SystemMessage):
        mensajes_entrada = [SystemMessage(content=full_system_prompt)] + messages
    else:
        mensajes_entrada = [SystemMessage(content=full_system_prompt)] + messages[1:]
    
    logger.info("CLASSIFY USER NODE - property_type: %s", property_type)
    
    result = react_agent.invoke({"messages": mensajes_entrada})
    
    new_messages = result.get("messages", [])
    response_messages = [msg for msg in new_messages if msg not in mensajes_entrada]
    
    return {"messages": response_messages}


def should_continue_classify(state: AgentState) -> str:
    """React Agent maneja herramientas internamente, siempre termina."""
    return "end"
