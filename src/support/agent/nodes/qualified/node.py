import logging
import os
import asyncio
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, SystemMessage

from src.support.agent.state import AgentState

logger = logging.getLogger(__name__)

# LLM para el nodo qualified
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7)

QUALIFIED_SYSTEM_PROMPT = """Eres Laura, de Grupo Nagaki.
El cliente ha sido CUALIFICADO exitosamente (tiene interés real y capacidad).
Tu objetivo es derivarlo al equipo comercial de forma amable y profesional.

Instrucciones:
1. SI EL CLIENTE PIDE INFORMACIÓN ESPECÍFICA (pisos, fotos, precios):
   - PRIMERO usa las herramientas (`consultar_inmuebles`) para darle la información.
   - LUEGO, añade el mensaje de derivación.
   
2. Si no pide info o ya se la diste:
   - Agradécele cortésmente por su interés y el tiempo dedicado.
   - Infórmale que será remitido a un asesor profesional especializado.
   - Asegúrale que recibirá un contacto pronto.
   - Despídete de forma cálida y profesional.

Ejemplo con info:
"Aquí tienes las fotos del piso en Málaga... [INFO].
Como veo que tienes un perfil excelente, voy a derivar tu contacto a un especialista para que te asesore personalmente en la compra. ¡Hablamos pronto!"
"""

async def notify_manager(client_phone: str, state: AgentState) -> None:
    """
    Notifica al encargado sobre un cliente cualificado.
    
    Args:
        client_phone: Número de teléfono del cliente
        state: Estado actual del agente con información del cliente
    """
    try:
        # Importar aquí para evitar dependencias circulares
        from src.support.api.evolution_webhook import send_whatsapp_message
        
        # Obtener número del encargado desde variables de entorno
        manager_phone = os.getenv("QUALIFIED_MANAGER_PHONE", "").strip()
        
        if not manager_phone:
            logger.warning("⚠️ QUALIFIED_MANAGER_PHONE no está configurado en .env")
            return
        
        # Extraer información relevante del estado
        points = state.get("points", 0)
        property_type = state.get("property_type", "No especificado")
        interested = state.get("interested", False)
        
        # Obtener últimos mensajes para contexto
        messages = state.get("messages", [])
        last_messages = []
        for msg in messages[-5:]:
            if hasattr(msg, 'content') and msg.content:
                role = "Cliente" if hasattr(msg, 'type') and msg.type == "human" else "Laura"
                last_messages.append(f"{role}: {msg.content[:100]}...")
        
        conversation_context = "\n".join(last_messages) if last_messages else "No disponible"
        
        # Crear mensaje de notificación
        notification_message = f"""🌟 *NUEVO CLIENTE CUALIFICADO* 🌟

📱 *Cliente:* {client_phone}
⭐ *Puntos:* {points}
🏢 *Tipo de propiedad:* {property_type}
💼 *Interesado:* {"Sí" if interested else "No"}

📝 *Últimos mensajes:*
{conversation_context}

---
Este cliente ha sido cualificado exitosamente y está listo para atención personalizada."""

        # Enviar notificación al encargado
        logger.info(f"📲 Notificando al encargado ({manager_phone[:4]}***) sobre cliente cualificado: {client_phone[:6]}***")
        success = await send_whatsapp_message(manager_phone, notification_message)
        
        if success:
            logger.info(f"✅ Encargado notificado exitosamente sobre cliente {client_phone[:6]}***")
        else:
            logger.error(f"❌ No se pudo notificar al encargado sobre cliente {client_phone[:6]}***")
            
    except Exception as e:
        logger.error(f"❌ Error al notificar al encargado: {e}", exc_info=True)


from src.support.agent.nodes.conversation.tools import consultar_inmuebles, listar_ubicaciones_disponibles

# Bindeamos herramientas al LLM para permitir consultas de último momento
tools = [consultar_inmuebles, listar_ubicaciones_disponibles]
llm_with_tools = llm.bind_tools(tools)

def qualified_node(state: AgentState) -> dict:
    """
    Maneja clientes cualificados y los deriva al comercial.
    Genera un mensaje final de despedida/derivación y notifica al encargado.
    Permite responder dudas de inmuebles antes de derivar.
    """
    messages = state.get("messages", [])
    
    logger.info("🌟 QUALIFIED NODE - Cliente cualificado, generando mensaje de derivación")
    
    # Generar respuesta (puede incluir tool calls)
    response = llm_with_tools.invoke([
        SystemMessage(content=QUALIFIED_SYSTEM_PROMPT)
    ] + messages[-5:]) # Usar últimos mensajes para contexto
    
    # Obtener el thread_id (número de teléfono del cliente) del estado
    client_phone = state.get("thread_id", "desconocido")
    
    # Programar notificación al encargado de forma asíncrona
    if client_phone and client_phone != "desconocido":
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(notify_manager(client_phone, state))
        except Exception as e:
            logger.warning(f"⚠️ No se pudo programar notificación al encargado: {e}")
            # Intentar ejecutar de forma síncrona como fallback
            try:
                asyncio.run(notify_manager(client_phone, state))
            except Exception as e2:
                logger.error(f"❌ Error ejecutando notificación al encargado: {e2}")
    else:
        logger.warning("⚠️ No se pudo obtener el número de teléfono del cliente para notificar al encargado")
    
    return {"messages": [response]}


def should_continue_qualified(state: AgentState) -> str:
    """
    Determina si el agente necesita llamar herramientas en el nodo qualified.
    """
    messages = state.get("messages", [])
    if not messages:
        return "end"
        
    last_message = messages[-1]
    
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return "end"
    
    return "tools"





