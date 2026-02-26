"""
Background Tasks para el Agente

Este módulo contiene funciones que se ejecutan en segundo plano,
separadas del flujo principal de respuesta al usuario.

La función principal es `update_points_background` que:
- Analiza la intención del usuario con `identificar_intencion`
- Actualiza los puntos en el estado del agente
- Todo esto SIN afectar el streaming de respuestas
"""

import json
import logging
import asyncio
from typing import Optional
from langchain_core.messages import AIMessage, ToolMessage

from src.support.agent.nodes.conversation.tools import identificar_intencion
from src.support.agent.nodes.classify_user.tools import calificar_respuesta_usuario
from src.support.agent.state import QualificationThreshold

logger = logging.getLogger(__name__)


async def update_points_background(
    user_input: str,
    thread_id: str,
    agent,
    current_points: int = 0,
    is_classify_context: bool = False,
) -> dict:
    """
    Actualiza los puntos del usuario en segundo plano.
    
    Esta función se ejecuta DESPUÉS de enviar la respuesta al usuario,
    de forma asíncrona y sin bloquear el stream.
    
    Args:
        user_input: El mensaje del usuario a analizar
        thread_id: ID del thread para actualizar el estado
        agent: Instancia del agente con acceso al checkpointer
        current_points: Puntos actuales del usuario
        is_classify_context: Si True, no aplica el límite de 4 puntos
        
    Returns:
        dict con los resultados de la actualización
    """
    try:
        logger.info(f"🔄 [Background] Iniciando análisis de intención para thread: {thread_id}")
        logger.info(f"🔄 [Background] Input: {user_input[:50]}...")
        
        # 1. Llamar a identificar_intencion directamente (es una herramienta síncrona)
        # La ejecutamos en un thread pool para no bloquear el event loop
        loop = asyncio.get_event_loop()
        intent_result = await loop.run_in_executor(
            None,
            lambda: identificar_intencion.invoke({"mensaje_usuario": user_input})
        )
        
        score = intent_result.get("score", 0)
        puntos_sumados = intent_result.get("puntos_sumados", 0)
        razonamiento = intent_result.get("razonamiento", "")
        
        logger.info(f"✅ [Background] Intención analizada: score={score}, puntos={puntos_sumados}")
        logger.debug(f"   Razonamiento: {razonamiento[:100]}...")
        
        # 2. Calcular nuevos puntos
        if is_classify_context:
            # En contexto de classify, no hay límite de 4
            new_points = current_points + puntos_sumados
        else:
            # En contexto de conversation, límite de 4 puntos
            new_points = min(current_points + puntos_sumados, QualificationThreshold.INTERESTED)
        
        # 3. Calcular interested y qualified
        interested = new_points >= QualificationThreshold.INTERESTED
        qualified = new_points >= QualificationThreshold.QUALIFIED
        
        # 4. Actualizar el estado en el checkpointer
        await _update_state_in_checkpointer(
            agent=agent,
            thread_id=thread_id,
            new_points=new_points,
            interested=interested,
            qualified=qualified,
            intent_result=intent_result,
        )
        
        logger.info(f"📊 [Background] Puntos actualizados: {current_points} → {new_points}")
        if interested and not qualified:
            logger.info(f"🎯 [Background] Usuario alcanzó {QualificationThreshold.INTERESTED} puntos - Interesado!")
        if qualified:
            logger.info(f"🏆 [Background] Usuario alcanzó {QualificationThreshold.QUALIFIED} puntos - Cualificado!")
        
        return {
            "success": True,
            "previous_points": current_points,
            "new_points": new_points,
            "points_added": puntos_sumados,
            "score": score,
            "interested": interested,
            "qualified": qualified,
        }
        
    except Exception as e:
        logger.error(f"❌ [Background] Error actualizando puntos: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "previous_points": current_points,
            "new_points": current_points,
        }


async def _update_state_in_checkpointer(
    agent,
    thread_id: str,
    new_points: int,
    interested: bool,
    qualified: bool,
    intent_result: dict,
) -> None:
    """
    Actualiza el estado en el checkpointer de LangGraph.
    
    Esto permite que las siguientes llamadas del mismo thread
    vean los puntos actualizados.
    """
    try:
        await agent._ensure_async_setup()
        
        config = {"configurable": {"thread_id": thread_id}}
        
        # Obtener el estado actual
        current_state = await agent.async_graph.aget_state(config)
        
        if current_state and current_state.values:
            # Preparar los mensajes de tool call para el historial
            # Esto mantiene consistencia con el formato esperado
            import uuid
            tool_call_id = f"bg_intent_{uuid.uuid4().hex[:8]}"
            
            ai_message = AIMessage(
                content="",
                tool_calls=[{
                    "id": tool_call_id,
                    "name": "identificar_intencion",
                    "args": {"mensaje_usuario": "[analizado en background]"}
                }]
            )
            
            tool_message = ToolMessage(
                content=json.dumps(intent_result),
                name="identificar_intencion",
                tool_call_id=tool_call_id,
            )
            
            # Actualizar el estado con los nuevos valores
            update = {
                "points": new_points,
                "interested": interested,
                "qualified": qualified,
                "messages": [ai_message, tool_message],
            }
            
            await agent.async_graph.aupdate_state(config, update)
            logger.debug(f"✅ [Background] Estado actualizado en checkpointer")
        else:
            logger.warning(f"⚠️ [Background] No se encontró estado previo para thread: {thread_id}")
            
    except Exception as e:
        logger.error(f"❌ [Background] Error actualizando checkpointer: {e}", exc_info=True)
        # No re-raise - es una operación en background, no debe afectar al usuario


async def qualify_response_background(
    tool_calls: list,
    thread_id: str,
    agent,
    current_points: int = 0,
) -> dict:
    """
    Ejecuta la calificación de respuestas del usuario en segundo plano.
    
    Esta función se ejecuta cuando el LLM de classify_user decide
    llamar a calificar_respuesta_usuario. Se ejecuta DESPUÉS de enviar
    la respuesta al usuario.
    
    Args:
        tool_calls: Lista de tool_calls del AIMessage (contienen los argumentos)
        thread_id: ID del thread para actualizar el estado
        agent: Instancia del agente con acceso al checkpointer
        current_points: Puntos actuales del usuario
        
    Returns:
        dict con los resultados de la calificación
    """
    try:
        logger.info(f"🔄 [Background Classify] Iniciando calificación para thread: {thread_id}")
        logger.info(f"🔄 [Background Classify] Tool calls a procesar: {len(tool_calls)}")
        
        puntos_sumados = 0
        resultados = []
        
        # Ejecutar cada tool call
        for tc in tool_calls:
            tool_name = tc.get("name", "")
            if tool_name != "calificar_respuesta_usuario":
                continue
                
            args = tc.get("args", {})
            pregunta = args.get("pregunta", "")
            respuesta_usuario = args.get("respuesta_usuario", "")
            contexto = args.get("contexto", "")
            
            # ------------------------------------------------------------------
            # CORRECCIÓN DE AUTOCALIFICACIÓN:
            # El LLM a veces alucina y pone su propia respuesta en 'respuesta_usuario'.
            # Para evitarlo, recuperamos el ÚLTIMO MENSAJE REAL DEL USUARIO del historial.
            # ------------------------------------------------------------------
            
            real_user_response = respuesta_usuario # Fallback
            
            try:
                # Recuperar estado fresco
                # Esto es seguro porque estamos en background
                config = {"configurable": {"thread_id": thread_id}}
                state_snapshot = await agent.async_graph.aget_state(config)
                
                if state_snapshot and state_snapshot.values and state_snapshot.values.get("messages"):
                    messages = state_snapshot.values.get("messages")
                    from langchain_core.messages import HumanMessage
                    
                    # Buscar último mensaje humano
                    for m in reversed(messages):
                        if isinstance(m, HumanMessage):
                             real_user_response = m.content
                             logger.info(f"✅ [Background Classify] Corregido 'respuesta_usuario' con historial: '{real_user_response[:50]}...'")
                             break
            except Exception as e:
                logger.warning(f"⚠️ [Background Classify] No se pudo recuperar historial para corregir input: {e}")

            logger.info(f"🔍 [Background Classify] Calificando respuesta REAL: {real_user_response[:50]}...")
            
            # Ejecutar la herramienta en un thread pool
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: calificar_respuesta_usuario.invoke({
                    "pregunta": pregunta,
                    "respuesta_usuario": real_user_response, # USAMOS EL CORREGIDO
                    "contexto": contexto,
                })
            )
            
            puntos = result.get("puntos_sumados", 0)
            puntos_sumados += puntos
            resultados.append(result)
            
            es_positiva = result.get("es_positiva", False)
            logger.info(f"✅ [Background Classify] Respuesta {'positiva' if es_positiva else 'negativa'}: +{puntos} puntos")
        
        # Calcular nuevos puntos (sin límite en classify)
        new_points = current_points + puntos_sumados
        
        # Calcular qualified
        qualified = new_points >= QualificationThreshold.QUALIFIED
        interested = new_points >= QualificationThreshold.INTERESTED
        
        # Actualizar el estado en el checkpointer
        await _update_classify_state_in_checkpointer(
            agent=agent,
            thread_id=thread_id,
            new_points=new_points,
            qualified=qualified,
            tool_calls=tool_calls,
            results=resultados,
        )
        
        logger.info(f"📊 [Background Classify] Puntos actualizados: {current_points} → {new_points}")
        if qualified:
            logger.info(f"🏆 [Background Classify] Usuario CUALIFICADO! ({new_points} >= {QualificationThreshold.QUALIFIED})")
        
        return {
            "success": True,
            "previous_points": current_points,
            "new_points": new_points,
            "points_added": puntos_sumados,
            "qualified": qualified,
            "results": resultados,
        }
        
    except Exception as e:
        logger.error(f"❌ [Background Classify] Error calificando respuesta: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "previous_points": current_points,
            "new_points": current_points,
        }


async def _update_classify_state_in_checkpointer(
    agent,
    thread_id: str,
    new_points: int,
    qualified: bool,
    tool_calls: list,
    results: list,
) -> None:
    """
    Actualiza el estado en el checkpointer después de la calificación.
    """
    try:
        await agent._ensure_async_setup()
        
        config = {"configurable": {"thread_id": thread_id}}
        
        # Obtener el estado actual
        current_state = await agent.async_graph.aget_state(config)
        
        if current_state and current_state.values:
            import uuid
            
            messages_to_add = []
            
            # Crear ToolMessages para cada resultado
            for i, (tc, result) in enumerate(zip(tool_calls, results)):
                tool_call_id = tc.get("id", f"bg_classify_{uuid.uuid4().hex[:8]}")
                
                tool_message = ToolMessage(
                    content=json.dumps(result),
                    name="calificar_respuesta_usuario",
                    tool_call_id=tool_call_id,
                )
                messages_to_add.append(tool_message)
            
            # Calcular interested basado en puntos
            interested = new_points >= QualificationThreshold.INTERESTED
            
            # Actualizar el estado
            update = {
                "points": new_points,
                "interested": interested,
                "qualified": qualified,
                "messages": messages_to_add,
            }
            
            await agent.async_graph.aupdate_state(config, update)
            logger.debug(f"✅ [Background Classify] Estado actualizado en checkpointer")
        else:
            logger.warning(f"⚠️ [Background Classify] No se encontró estado previo para thread: {thread_id}")
            
    except Exception as e:
        logger.error(f"❌ [Background Classify] Error actualizando checkpointer: {e}", exc_info=True)

