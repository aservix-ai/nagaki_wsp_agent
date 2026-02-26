import json # Import moved to top
import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage, HumanMessage

from src.support.agent.state import AgentState, QualificationThreshold
from src.support.agent.nodes.conversation.tools import (
    buscar_info_viviendas,
    identificar_intencion,
    consultar_inmuebles,
    listar_ubicaciones_disponibles,
    obtener_hora_actual,
    realizar_calculo,
    notificar_encargado, # Herramienta de escalado
    finalizar_conversacion, # Cierre de conversaciones
)
from src.support.agent.nodes.conversation.prompt import CONVERSATION_SYSTEM_PROMPT
from src.support.agent.utils import sanitize_messages

logger = logging.getLogger(__name__)

# Inicializamos el modelo con streaming habilitado para respuestas en tiempo real
# streaming=True permite que astream_events capture tokens mientras se generan
# max_tokens=100 para respuestas breves y naturales (2-3 frases cortas, 40-60 palabras)
# temperature=0.8 para más naturalidad y variación
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.8, streaming=True, max_tokens=100)

# IMPORTANTE: NO incluir identificar_intencion aquí
# Esta herramienta la usa analyze_intent_node DIRECTAMENTE, no el LLM de conversation
tools = [buscar_info_viviendas, consultar_inmuebles, listar_ubicaciones_disponibles, obtener_hora_actual, realizar_calculo, notificar_encargado, finalizar_conversacion]
llm_with_tools = llm.bind_tools(tools)

# ... (omitted sanitize_messages comment) ...

def conversation_node(state: AgentState) -> dict:
    # Si la conversación está cerrada, no procesar más
    if state.get("conversation_closed", False):
        logger.info("🚫 Conversación cerrada - Ignorando mensaje en conversation_node")
        return {}

    messages = state.get("messages", [])
    
    # 1. Sanitizar mensajes corruptos (tool calls sin respuesta) antes de enviarlos al LLM
    messages = sanitize_messages(messages)
    
    # Lógica para saludo inicial
    system_instruction = CONVERSATION_SYSTEM_PROMPT
    if state.get("is_new_customer", False):
        system_instruction += "\n\nNOTA IMPORTANTE: Es la PRIMERA VEZ que hablas con este cliente. IMPORTANTE: Preséntate formalmente como 'Laura de Grupo Nagaki' al inicio de tu respuesta."

    # Inyección de contexto para clientes CUALIFICADOS (VIP)
    if state.get("qualified", False):
        system_instruction += "\n\n**STATUS: CLIENTE CUALIFICADO (VIP)**\nEste cliente ya ha sido validado y derivado al equipo comercial. Sigue atendiéndolo con máxima prioridad y cortesía mientras espera el contacto del especialista. Responde a todas sus dudas."

    # Lógica defensiva del System Prompt
    if not messages or not isinstance(messages[0], SystemMessage):
        mensajes_entrada = [SystemMessage(content=system_instruction)] + messages
    else:
        # Si ya existe un SystemMessage, lo actualizamos por si acaso (aunque en teoría persistence lo mantiene)
        # Para evitar mutar la lista original del estado
        mensajes_entrada = list(messages)
        mensajes_entrada[0] = SystemMessage(content=system_instruction)
    
    response = llm_with_tools.invoke(mensajes_entrada)
    
    return {"messages": [response]}


def update_points_node(state: AgentState) -> dict:
    """
    Actualiza puntos. Optimizado para manejar Parallel Tool Calls.
    Limita la suma de puntos a un máximo de 4 en el nodo de conversación.
    Marca interested=True cuando se alcancen 4 puntos.
    También calcula qualified basado en los puntos totales.
    Y DETECTA CIERRE DE CONVERSACIÓN.
    """
    messages = state.get("messages", [])
    
    puntos_sumados = 0
    conversation_closed = state.get("conversation_closed", False)
    
    # Iteramos en reverso
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            # Si llegamos a un mensaje que no es de tool, paramos...
            # PERO PRIMERO revisamos si el AIMessage anterior llamó a finalizar_conversacion
            # (LangChain graph structure: AIMessage(tool_calls) -> ToolNode -> ToolMessage)
            break
            
        # Detectar herramienta de intencion
        if msg.name == "identificar_intencion":
            try:
                content = msg.content
                if isinstance(content, str):
                    content = json.loads(content)
                puntos_sumados += content.get("puntos_sumados", 0)
            except (json.JSONDecodeError, AttributeError, TypeError):
                continue
        
        # Detectar si se llamó a finalizar_conversacion
        if msg.name == "finalizar_conversacion":
            logger.info("🛑 Detectada herramienta finalizar_conversacion: Cerrando permanentemente.")
            conversation_closed = True

    current_points = state.get("points", 0)
    
    # LÍMITE: En el nodo de conversación solo se suma hasta alcanzar 4 puntos
    new_points = min(current_points + puntos_sumados, QualificationThreshold.INTERESTED)
    
    interested = new_points >= QualificationThreshold.INTERESTED
    qualified = new_points >= QualificationThreshold.QUALIFIED
    
    updates = {}
    
    # Solo actualizamos si hubo cambios
    current_interested = state.get("interested", False)
    current_qualified = state.get("qualified", False)
    current_closed = state.get("conversation_closed", False)
    
    if puntos_sumados > 0:
        updates["points"] = new_points
    if interested != current_interested:
        updates["interested"] = interested
    if qualified != current_qualified:
        updates["qualified"] = qualified
    if conversation_closed != current_closed:
        updates["conversation_closed"] = conversation_closed
        
    return updates

def route_after_update_points(state: AgentState) -> str:
    """
    Enruta después de actualizar puntos.
    """
    # Si la conversación se cerró, terminar.
    if state.get("conversation_closed", False):
        return "end"

    interested = state.get("interested", False)
    qualified = state.get("qualified", False)
    
    if qualified:
        return "end"
    
    if interested:
        logger.info("🎯 Cliente alcanzó 4 puntos → Redirigiendo a classify_user")
        return "classify_user"
    
    return "end"


def analyze_intent_node(state: AgentState) -> dict:
    """
    Nodo que SIEMPRE analiza la intención del último mensaje del usuario.
    Se ejecuta después de conversation para asegurar que siempre se sumen puntos.
    
    IMPORTANTE: Crea un AIMessage con tool_calls seguido de un ToolMessage
    para cumplir con la estructura requerida por OpenAI API.
    """
    messages = state.get("messages", [])
    
    # Buscar el último mensaje del usuario
    user_message = None
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_message = msg.content
            break
    
    if not user_message:
        logger.warning("⚠️ No se encontró mensaje del usuario para analizar intención")
        return {}
    
    logger.info(f"🔍 Analizando intención del mensaje: {user_message[:50]}...")
    
    try:
        # Llamar directamente a la herramienta para analizar intención
        intent_result = identificar_intencion.invoke({"mensaje_usuario": user_message})
        
        # Crear un tool_call_id único
        import uuid
        tool_call_id = f"intent_analysis_{uuid.uuid4().hex[:8]}"
        
        # Crear un AIMessage con tool_calls para que OpenAI lo acepte
        # Esto simula que el LLM decidió llamar a la herramienta
        ai_message = AIMessage(
            content="",  # Sin contenido, solo tool calls
            tool_calls=[{
                "id": tool_call_id,
                "name": "identificar_intencion",
                "args": {"mensaje_usuario": user_message}
            }]
        )
        
        # Crear el ToolMessage correspondiente
        from langchain_core.messages import ToolMessage
        tool_message = ToolMessage(
            content=json.dumps(intent_result),
            name="identificar_intencion",
            tool_call_id=tool_call_id
        )
        
        logger.info(f"✅ Intención analizada: score={intent_result.get('score', 0)}, puntos={intent_result.get('puntos_sumados', 0)}")
        
        # Retornar ambos mensajes en orden: AIMessage primero, luego ToolMessage
        return {"messages": [ai_message, tool_message]}
        
    except Exception as e:
        logger.error(f"❌ Error analizando intención: {e}", exc_info=True)
        # Retornar mensaje de tool con 0 puntos en caso de error
        import uuid
        tool_call_id = f"intent_analysis_error_{uuid.uuid4().hex[:8]}"
        
        from langchain_core.messages import ToolMessage
        error_result = {
            "score": 0.0,
            "razonamiento": f"Error en análisis: {str(e)}",
            "puntos_sumados": 0
        }
        
        # Crear AIMessage con tool_calls para el error también
        ai_message = AIMessage(
            content="",
            tool_calls=[{
                "id": tool_call_id,
                "name": "identificar_intencion",
                "args": {"mensaje_usuario": user_message}
            }]
        )
        
        tool_message = ToolMessage(
            content=json.dumps(error_result),
            name="identificar_intencion",
            tool_call_id=tool_call_id
        )
        
        return {"messages": [ai_message, tool_message]}


def should_continue(state: AgentState) -> str:
    """
    Determina si el LLM necesita llamar herramientas o terminar.
    
    IMPORTANTE: El análisis de intención ahora se hace en SEGUNDO PLANO
    después de enviar la respuesta al usuario. Esto elimina el problema
    de que el JSON de herramientas se mezcle con la respuesta.
    """
    messages = state.get("messages", [])
    last_message = messages[-1]
    
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    # Terminar directamente - el análisis de intención se hace en background
    return "end"