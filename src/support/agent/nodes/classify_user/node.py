"""
Nodo de Clasificación de Usuario - Grupo Nagaki

Este nodo clasifica usuarios interesados para determinar su nivel de cualificación.
Hace 3 preguntas de cualificación y suma puntos por respuestas positivas.
"""

import json
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from src.support.agent.utils import sanitize_messages

from src.support.agent.state import AgentState, QualificationThreshold
from src.support.agent.nodes.classify_user.tools import calificar_respuesta_usuario
from src.support.agent.nodes.conversation.tools import consultar_inmuebles  # Importar herramienta de búsqueda
from src.support.agent.nodes.classify_user.prompt import (
    CLASSIFY_USER_SYSTEM_PROMPT,
    get_property_question
)

logger = logging.getLogger(__name__)

# Inicializar LLM con streaming habilitado para respuestas en tiempo real
# max_tokens=120 para respuestas breves y naturales (2-3 frases cortas)
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, streaming=True, max_tokens=120)
# Agregamos consultar_inmuebles para que pueda responder dudas sobre pisos durante la cualificación
tools = [calificar_respuesta_usuario, consultar_inmuebles] 
llm_with_tools = llm.bind_tools(tools)


def classify_user_node(state: AgentState) -> dict:
    """
    Nodo principal de clasificación de usuario.
    
    Extrae el property_type del estado y genera un prompt dinámico
    con la pregunta específica según el tipo de inmueble.
    
    Args:
        state: Estado actual del agente
        
    Returns:
        dict: Estado actualizado con el mensaje del agente
    """
    messages = state.get("messages", [])
    # 1. Sanitizar mensajes corruptos (tool calls sin respuesta)
    messages = sanitize_messages(messages)
    
    property_type = state.get("property_type", "unknown")
    
    # Generar la pregunta dinámica según el tipo de inmueble
    property_question = get_property_question(property_type)
    
    # Crear el system prompt completo con la pregunta dinámica
    full_system_prompt = f"""{CLASSIFY_USER_SYSTEM_PROMPT}

**PREGUNTA ESPECÍFICA SOBRE EL TIPO DE INMUEBLE:**
{property_question}

Usa esta pregunta en el momento apropiado de la conversación."""
    
    # Lógica defensiva del System Prompt
    if not messages or not isinstance(messages[0], SystemMessage):
        mensajes_entrada = [SystemMessage(content=full_system_prompt)] + messages
    else:
        # Si ya hay un SystemMessage, lo reemplazamos con el nuestro
        mensajes_entrada = [SystemMessage(content=full_system_prompt)] + messages[1:]
    
    # Logging para debugging
    logger.info("=" * 60)
    logger.info("CLASSIFY USER NODE - Clasificando Usuario")
    logger.info("=" * 60)
    logger.info(f"property_type: {property_type}")
    logger.info(f"Puntos actuales: {state.get('points', 0)}")
    logger.info("=" * 60)
    
    # Invocar el LLM con herramientas
    response = llm_with_tools.invoke(mensajes_entrada)
    
    return {"messages": [response]}


def update_points_classify_node(state: AgentState) -> dict:
    """
    Actualiza puntos después de las calificaciones.
    Similar al update_points_node pero para el nodo classify_user.
    """
    messages = state.get("messages", [])
    
    puntos_sumados = 0
    
    # Iteramos en reverso para encontrar los ToolMessages más recientes
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            break
            
        if msg.name == "calificar_respuesta_usuario":
            try:
                # Manejo robusto de contenido
                content = msg.content
                if isinstance(content, str):
                    content = json.loads(content)
                
                # Sumamos los puntos
                puntos_sumados += content.get("puntos_sumados", 0)
                
            except (json.JSONDecodeError, AttributeError, TypeError):
                logger.error(f"Error parseando output de tool: {msg.content}")
                continue

    current_points = state.get("points", 0)
    new_points = current_points + puntos_sumados
    
    # Calcular qualified basado en los puntos totales
    qualified = new_points >= QualificationThreshold.QUALIFIED
    
    # Logging para debugging
    if puntos_sumados > 0:
        logger.info("=" * 60)
        logger.info("UPDATE POINTS CLASSIFY NODE - Actualización de Puntos")
        logger.info("=" * 60)
        logger.info(f"Puntos anteriores: {current_points}")
        logger.info(f"Puntos sumados en este turno: {puntos_sumados}")
        logger.info(f"Puntos totales (nuevos): {new_points}")
        logger.info(f"qualified: {state.get('qualified', False)} → {qualified} (points >= {QualificationThreshold.QUALIFIED})")
        if qualified:
            logger.info("🎉 Cliente CUALIFICADO - Derivar a comercial")
        logger.info("=" * 60)
    
    # Solo actualizamos si hubo cambios
    current_qualified = state.get("qualified", False)
    
    if puntos_sumados > 0 or qualified != current_qualified:
        return {
            "points": new_points,
            "qualified": qualified,
        }
    
    return {}


def should_continue_classify(state: AgentState) -> str:
    """
    Determina si el agente necesita llamar herramientas o terminar.
    
    IMPORTANTE: La calificación de respuestas ahora se hace en SEGUNDO PLANO
    pero si hay consultas reales (inmuebles), las ejecutamos en el grafo.
    """
    messages = state.get("messages", [])
    if not messages:
        return "end"
        
    last_message = messages[-1]
    
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return "end"
        
    # Verificar qué herramientas se llamaron
    tool_names = [tc["name"] for tc in last_message.tool_calls]
    
    # Si hay herramientas de consulta "reales", ejecutarlas en el grafo
    # Esto desviará temporalmente a 'tools' -> 'conversation'
    if "consultar_inmuebles" in tool_names or "listar_ubicaciones_disponibles" in tool_names:
        logger.info(f"🛠️ [Classify] Desviando a herramientas reales: {tool_names}")
        return "tools"
        
    # Si solo es calificación, terminar (se procesa en background)
    return "end"


def route_after_classify_update_points(state: AgentState) -> str:
    """
    Enruta después de actualizar puntos en classify_user.
    Si el cliente alcanzó >= 7 puntos (qualified=True), va a qualified.
    Si no, vuelve a classify_user para continuar la conversación.
    """
    qualified = state.get("qualified", False)
    
    if qualified:
        logger.info("🎯 Cliente alcanzó >= 7 puntos → Redirigiendo a qualified")
        return "qualified"
    
    return "classify_user"
