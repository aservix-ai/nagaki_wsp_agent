import logging
from langchain_core.messages import AIMessage, ToolMessage, HumanMessage

logger = logging.getLogger(__name__)

def sanitize_messages(messages: list) -> list:
    """
    Sanitiza el historial de mensajes para cumplir con las reglas estrictas de OpenAI API.
    
    Reglas:
    1. AIMessage con tool_calls debe ir seguido de TODAS sus respuestas ToolMessage.
    2. No puede haber ToolMessages huérfanos.
    """
    if not messages:
        return []

    sanitized = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            # 1. Identificar qué tool_calls hay
            tool_call_ids = {tc.get("id") for tc in msg.tool_calls}
            found_tools = []
            
            # 2. Buscar las respuestas inmediatamente después
            j = i + 1
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                if messages[j].tool_call_id in tool_call_ids:
                    found_tools.append(messages[j])
                    tool_call_ids.remove(messages[j].tool_call_id)
                j += 1
            
            # 3. Si están todas las respuestas, conservamos el bloque
            if not tool_call_ids:
                sanitized.append(msg)
                sanitized.extend(found_tools)
                i = j  # Saltar los mensajes ya procesados
            else:
                # Si faltan respuestas, OpenAI lanzará error 400. 
                # Convertimos el AI message a texto plano si tiene contenido, o lo omitimos.
                if msg.content and msg.content.strip() and msg.content != "...":
                    clean_ai = AIMessage(content=msg.content, id=getattr(msg, "id", None))
                    sanitized.append(clean_ai)
                    logger.debug(f"🧹 AIMessage sanitizado (tool_calls eliminados por incompletos)")
                else:
                    logger.debug(f"🧹 AIMessage eliminado (sin contenido y tool_calls incompletos)")
                i = j # Saltamos los ToolMessages huérfanos que pudieran haber
        elif isinstance(msg, ToolMessage):
            # ToolMessage suelto sin su AIMessage previo (huérfano)
            logger.debug(f"🧹 Eliminando ToolMessage huérfano: {getattr(msg, 'tool_call_id', 'unknown')}")
            i += 1
        else:
            # Mensajes normales (Human, System, AI sin tools)
            sanitized.append(msg)
            i += 1
            
    return sanitized
