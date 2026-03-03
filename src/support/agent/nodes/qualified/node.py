import logging
import os
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage
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
1. Si el cliente pide información específica (pisos, fotos, precios), usa las herramientas para darle la información.
2. Si no pide info o ya se la diste:
   - Agradécele cortésmente por su interés
   - Infórmale que será remitido a un asesor especializado
   - Asegúrale que recibirá un contacto pronto
   - Despídete de forma cálida
"""


async def notify_manager(client_phone: str, state: AgentState) -> None:
    """Notifica al encargado sobre un cliente cualificado."""
    try:
        from src.support.api.evolution_webhook import send_whatsapp_message
        
        manager_phone = os.getenv("QUALIFIED_MANAGER_PHONE", "").strip()
        if not manager_phone:
            logger.warning("QUALIFIED_MANAGER_PHONE no está configurado")
            return
        
        property_type = state.get("property_type", "No especificado")
        
        messages = state.get("messages", [])
        last_messages = []
        for msg in messages[-5:]:
            if hasattr(msg, 'content') and msg.content:
                role = "Cliente" if hasattr(msg, 'type') and msg.type == "human" else "Laura"
                last_messages.append(f"{role}: {msg.content[:100]}...")
        
        conversation_context = "\n".join(last_messages) if last_messages else "No disponible"
        
        notification_message = f"""NUEVO CLIENTE CUALIFICADO

Cliente: {client_phone}
Tipo de propiedad: {property_type}

Últimos mensajes:
{conversation_context}
"""
        
        logger.info(f"Notificando al encargado sobre cliente cualificado")
        await send_whatsapp_message(manager_phone, notification_message)
            
    except Exception as e:
        logger.error(f"Error al notificar al encargado: {e}")


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
    
    client_phone = state.get("thread_id", "desconocido")
    if client_phone and client_phone != "desconocido":
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(notify_manager(client_phone, state))
        except Exception as e:
            logger.warning(f"No se pudo programar notificación: {e}")
    
    return {"messages": response_messages}


def should_continue_qualified(state: AgentState) -> str:
    """React Agent maneja herramientas internamente, siempre termina."""
    return "end"





