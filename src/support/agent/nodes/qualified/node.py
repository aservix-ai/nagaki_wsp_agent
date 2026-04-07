import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage
from langgraph.prebuilt import create_react_agent

from src.support.agent.state import AgentState
from src.support.agent.nodes.conversation.tools import consultar_inmuebles, listar_ubicaciones_disponibles

logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, max_tokens=300)
tools = [consultar_inmuebles, listar_ubicaciones_disponibles]
react_agent = create_react_agent(llm, tools)

QUALIFIED_SYSTEM_PROMPT = """Eres Laura, de Grupo Nagaki.
El cliente ha sido CUALIFICADO exitosamente (tiene interés real y capacidad).
Tu objetivo es derivarlo al equipo comercial de forma amable y profesional.

Instrucciones:
   - Agradécele cortésmente por su interés
   - Infórmale que será remitido a un asesor especializado
   - Asegúrale que recibirá un contacto pronto
   - Despídete de forma cálida
"""


def qualified_node(state: AgentState) -> dict:
    """
    Maneja clientes cualificados usando React Agent.
    """
    messages = state.get("messages", [])
    
    logger.info("QUALIFIED NODE - Cliente cualificado")
    
    mensajes_entrada = [SystemMessage(content=QUALIFIED_SYSTEM_PROMPT)] + messages[-5:]
    
    result = react_agent.invoke({"messages": mensajes_entrada})
    
    new_messages = result.get("messages", [])
    response_messages = [msg for msg in new_messages if msg not in mensajes_entrada]
    
    return {"messages": response_messages}


def should_continue_qualified(state: AgentState) -> str:
    """React Agent maneja herramientas internamente, siempre termina."""
    return "end"




