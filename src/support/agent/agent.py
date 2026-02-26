"""
Agente Principal Laura - Grupo Nagaki

Este módulo contiene la clase Agent que construye y gestiona el grafo
del agente de IA para Grupo Nagaki.
"""

import os
import logging
from typing import Any, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)

from src.support.agent.state import AgentState
from src.support.agent.nodes.verification.node import verification_node
from src.support.agent.routes.verification_route import verification_router
from src.support.agent.nodes.conversation.node import (
    conversation_node,
    update_points_node,
    should_continue,
    route_after_update_points,
)
from src.support.agent.nodes.conversation.tools import (
    buscar_info_viviendas,
    consultar_inmuebles,
    notificar_encargado,
    finalizar_conversacion,
)
from src.support.agent.nodes.classify_user.node import (
    classify_user_node,
    should_continue_classify,
)
from src.support.agent.nodes.qualified.node import (
    qualified_node, 
    should_continue_qualified
)


class Agent:
    """
    Construye y gestiona el grafo de flujo del agente que:
    - Verifica el estado del cliente
    - Enruta según la cualificación e interés
    - Gestiona conversaciones, clasificación y derivación a comerciales
    
    El thread_id se usa para mantener el contexto de la conversación.
    """
    
    def __init__(self, postgres_connection_string: Optional[str] = None):
        """
        Inicializa el agente con arquitectura dual (síncrono y asíncrono).
        """
        self.postgres_connection_string = (
            postgres_connection_string 
            or os.getenv("POSTGRES_CONNECTION_STRING")
        )
        
        self.checkpointer_type = os.getenv("CHECKPOINTER_TYPE", "postgres").lower()
        
        if self.checkpointer_type == "postgres":
            if not self.postgres_connection_string:
                raise ValueError(
                    "Se requiere POSTGRES_CONNECTION_STRING para inicializar el checkpointer de Postgres. "
                    "Configúralo como variable de entorno o usa CHECKPOINTER_TYPE='memory'."
                )
            
            # 1. Configuración Síncrona (Postgres)
            self._sync_checkpointer_context = PostgresSaver.from_conn_string(self.postgres_connection_string)
            sync_checkpointer = self._sync_checkpointer_context.__enter__()
            
            try:
                sync_checkpointer.setup()
                logger.info("Tablas de checkpoint (Postgres) creadas/verificadas")
            except AttributeError:
                try:
                    sync_checkpointer.setup_tables_sync()
                except AttributeError:
                    pass
        else:
            # Configuración Síncrona (Memory)
            logger.info("⚡ Usando MemorySaver (In-Memory Checkpointer) para máxima velocidad")
            self._sync_checkpointer_context = None
            sync_checkpointer = MemorySaver()

        # Compilar el grafo síncrono
        self.sync_graph = self._build_graph(checkpointer=sync_checkpointer)
        logger.info(f"Grafo síncrono compilado ({self.checkpointer_type})")
        
        # 2. Configuración Asíncrona (Placeholder - Lazy Loading)
        self._async_checkpointer_context = None
        self.async_checkpointer = None
        self.async_graph = None
        
        # 3. Compatibilidad
        self.graph = self.sync_graph
        self.checkpointer = sync_checkpointer
    
    async def _ensure_async_setup(self):
        """
        Patrón Singleton Lazy: Inicializa el grafo asíncrono solo la primera vez.
        """
        if self.async_graph is None:
            logger.info("Inicializando grafo asíncrono (primera vez)...")
            
            if self.checkpointer_type == "postgres":
                self._async_checkpointer_context = AsyncPostgresSaver.from_conn_string(self.postgres_connection_string)
                self.async_checkpointer = await self._async_checkpointer_context.__aenter__()
                try:
                    await self.async_checkpointer.setup()
                except AttributeError:
                    pass
            else:
                self.async_checkpointer = MemorySaver()
            
            self.async_graph = self._build_graph(checkpointer=self.async_checkpointer)
            logger.info("✅ Grafo asíncrono compilado exitosamente")
    
    async def cleanup(self):
        if self._async_checkpointer_context:
            try:
                await self._async_checkpointer_context.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error al cerrar conexiones asíncronas: {e}")
        
        if self._sync_checkpointer_context:
            try:
                self._sync_checkpointer_context.__exit__(None, None, None)
            except Exception as e:
                logger.error(f"Error al cerrar conexiones síncronas: {e}")
    
    def _build_graph(self, checkpointer):
        return self.make_graph(checkpointer=checkpointer)

    def make_graph(self, checkpointer=None):
        """
        Construye el grafo de flujo del agente.
        """
        workflow = StateGraph(AgentState)
        
        # Agregar nodos
        workflow.add_node("verification", verification_node)
        workflow.add_node("conversation", conversation_node)
        workflow.add_node("classify_user", classify_user_node)
        workflow.add_node("qualified", qualified_node)
        
        # Herramientas
        tools = [buscar_info_viviendas, consultar_inmuebles, notificar_encargado, finalizar_conversacion]
        workflow.add_node("tools", ToolNode(tools))
        workflow.add_node("update_points", update_points_node)
        
        # Configurar punto de entrada
        workflow.set_entry_point("verification")
        
        # Enrutamiento desde verification
        workflow.add_conditional_edges(
            "verification",
            verification_router,
            {
                "conversation": "conversation",
                "classify_user": "classify_user",
                "qualified": "qualified",
            }
        )
        
        # Flujo conversation -> tools
        workflow.add_conditional_edges(
            "conversation",
            should_continue,
            {
                "tools": "tools",
                "end": "update_points",
            }
        )
        
        # Volver de tools a conversation
        workflow.add_edge("tools", "conversation")
        
        # Evaluar después de update_points
        workflow.add_conditional_edges(
            "update_points",
            route_after_update_points,
            {
                "classify_user": "classify_user",
                "end": END,
            }
        )
        
        # Flujo classify_user
        workflow.add_conditional_edges(
            "classify_user",
            should_continue_classify,
            {
                "end": END,
                "tools": "tools",
            }
        )
        
        # Flujo qualified
        workflow.add_conditional_edges(
            "qualified",
            should_continue_qualified,
            {
                "tools": "tools",
                "end": END,
            }
        )
        
        checkpointer_to_use = checkpointer if checkpointer is not None else self.checkpointer
        return workflow.compile(checkpointer=checkpointer_to_use)
    
    def _build_initial_state(self, input_message: str, **kwargs: Any) -> AgentState:
        return {
            "messages": [HumanMessage(content=input_message)],
            "input": input_message,
            "is_customer": kwargs.get("is_customer", False),
            "points": kwargs.get("points", 0),
            "qualified": kwargs.get("qualified", False),
            "interested": kwargs.get("interested", False),
            "property_type": kwargs.get("property_type", "unknown"),
            "conversation_closed": kwargs.get("conversation_closed", False),
        }
    
    def invoke(self, input_message: str, thread_id: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        """Ejecuta el grafo de forma síncrona."""
        config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        initial_state = self._build_initial_state(input_message, **kwargs)
        
        try:
            # Obtener estado actual si existe para preservar historial
            current_state = self.sync_graph.get_state(config).values
            if current_state:
                # Actualizar solo campos nuevos o cambiados, mantener messages
                for key, value in initial_state.items():
                    if key != "messages":
                        current_state[key] = value
                
                # Añadir nuevo mensaje usuario
                current_state["messages"].append(HumanMessage(content=input_message))
                input_data = None # Ya actualizamos el estado, pasamos None
                
                # Hack: LangGraph espera input_data con las actualizaciones
                input_data = {
                    "messages": [HumanMessage(content=input_message)],
                    "input": input_message, 
                    "is_customer": kwargs.get("is_customer", False),
                    "points": kwargs.get("points", 0)
                }
            else:
                input_data = initial_state

            return self.sync_graph.invoke(input_data, config=config)
        except Exception as e:
            logger.error(f"Error invocando grafo: {e}")
            raise e

    async def ainvoke(self, input_message: str, thread_id: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        """Ejecuta el grafo de forma asíncrona."""
        await self._ensure_async_setup()
        
        config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        initial_state = self._build_initial_state(input_message, **kwargs)
        
        return await self.async_graph.ainvoke(initial_state, config=config)
