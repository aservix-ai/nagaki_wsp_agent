"""
Agente Principal Laura - Grupo Nagaki

Este módulo contiene la clase Agent que construye y gestiona el grafo
del agente de IA para Grupo Nagaki.

Arquitectura simplificada:
- verification: Nodo inicial que verifica el estado del cliente
- conversation: Agente ReAct para conversación (maneja tools automáticamente)
- qualified: Nodo final para clientes cualificados
"""

import os
import logging
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage

from src.support.agent.state import AgentState
from src.support.agent.nodes.verification.node import verification_node
from src.support.agent.routes.verification_route import verification_router
from src.support.agent.nodes.conversation.node import (
    conversation_node,
    route_after_conversation,
)
from src.support.agent.nodes.qualified.node import qualified_node

logger = logging.getLogger(__name__)


class Agent:
    """
    Construye y gestiona el grafo de flujo del agente.
    
    Flujo simplificado:
    1. verification → Verifica estado del cliente con evidencia
    2. conversation → Agente ReAct que maneja búsquedas automáticamente
    3. qualified → Mensaje de cierre y derivación a comercial
    
    El thread_id se usa para mantener el contexto de la conversación.
    """
    
    def __init__(self, postgres_connection_string: Optional[str] = None):
        """
        Inicializa el agente con arquitectura dual (síncrono y asíncrono).
        
        Args:
            postgres_connection_string: String de conexión a PostgreSQL.
                Si no se proporciona, se usa la variable de entorno.
        """
        self.postgres_connection_string = (
            postgres_connection_string 
            or os.getenv("POSTGRES_CONNECTION_STRING")
        )
        
        self.checkpointer_type = os.getenv("CHECKPOINTER_TYPE", "postgres").lower()
        
        if self.checkpointer_type == "postgres":
            if not self.postgres_connection_string:
                raise ValueError(
                    "Se requiere POSTGRES_CONNECTION_STRING para el checkpointer de Postgres. "
                    "Configúralo como variable de entorno o usa CHECKPOINTER_TYPE='memory'."
                )
            
            # Configuración Síncrona (Postgres)
            self._sync_checkpointer_context = PostgresSaver.from_conn_string(
                self.postgres_connection_string
            )
            sync_checkpointer = self._sync_checkpointer_context.__enter__()
            
            # Crear las tablas necesarias
            try:
                sync_checkpointer.setup()
                logger.info("✅ Tablas de checkpoint (Postgres) creadas/verificadas")
            except AttributeError:
                pass
        else:
            # Configuración Síncrona (Memory)
            logger.info("⚡ Usando MemorySaver (In-Memory Checkpointer)")
            self._sync_checkpointer_context = None
            sync_checkpointer = MemorySaver()

        # Compilar el grafo síncrono
        self.sync_graph = self._build_graph(checkpointer=sync_checkpointer)
        logger.info(f"✅ Grafo síncrono compilado ({self.checkpointer_type})")
        
        # Configuración Asíncrona (Lazy Loading)
        self._async_checkpointer_context = None
        self.async_checkpointer = None
        self.async_graph = None
        
        # Compatibilidad
        self.graph = self.sync_graph
        self.checkpointer = sync_checkpointer
    
    async def _ensure_async_setup(self):
        """
        Inicializa el grafo asíncrono solo la primera vez (lazy loading).
        """
        if self.async_graph is None:
            logger.info("🔄 Inicializando grafo asíncrono (primera vez)...")
            
            if self.checkpointer_type == "postgres":
                self._async_checkpointer_context = AsyncPostgresSaver.from_conn_string(
                    self.postgres_connection_string
                )
                self.async_checkpointer = await self._async_checkpointer_context.__aenter__()
                
                try:
                    await self.async_checkpointer.setup()
                    logger.info("✅ Tablas de checkpoint verificadas (async)")
                except AttributeError:
                    pass
            else:
                self.async_checkpointer = MemorySaver()
                logger.info("⚡ Grafo asíncrono usando MemorySaver")
            
            self.async_graph = self._build_graph(checkpointer=self.async_checkpointer)
            logger.info("✅ Grafo asíncrono compilado")
    
    async def cleanup(self):
        """Cierra conexiones al apagar la app."""
        if self._async_checkpointer_context:
            try:
                await self._async_checkpointer_context.__aexit__(None, None, None)
                logger.info("✅ Conexiones asíncronas cerradas")
            except Exception as e:
                logger.error(f"❌ Error cerrando conexiones async: {e}")
        
        if self._sync_checkpointer_context:
            try:
                self._sync_checkpointer_context.__exit__(None, None, None)
                logger.info("✅ Conexiones síncronas cerradas")
            except Exception as e:
                logger.error(f"❌ Error cerrando conexiones sync: {e}")
    
    def _build_graph(self, checkpointer):
        """Construye y compila el grafo."""
        return make_graph(checkpointer=checkpointer)
    
    def _build_initial_state(self, input_message: str, **kwargs: Any) -> AgentState:
        """Construye el estado inicial del agente."""
        qualification_snapshot = kwargs.get("qualification_snapshot")
        return {
            "messages": [HumanMessage(content=input_message)],
            "input": input_message,
            "is_customer": kwargs.get("is_customer", False),
            "qualification_snapshot": qualification_snapshot,
            # Mirrors transicionales para compatibilidad con logs/rutas existentes
            "interested": kwargs.get(
                "interested",
                qualification_snapshot.get("interested", False) if isinstance(qualification_snapshot, dict) else False,
            ),
            "qualified": kwargs.get(
                "qualified",
                qualification_snapshot.get("qualified", False) if isinstance(qualification_snapshot, dict) else False,
            ),
            "qualification_stage": kwargs.get(
                "qualification_stage",
                qualification_snapshot.get("qualification_stage", "new")
                if isinstance(qualification_snapshot, dict)
                else "new",
            ),
        }
    
    def invoke(
        self, 
        input_message: str, 
        thread_id: Optional[str] = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Ejecuta el agente con un mensaje de entrada (síncrono)."""
        initial_state = self._build_initial_state(input_message, **kwargs)
        config = {"configurable": {"thread_id": thread_id or "test-thread"}}
        return self.sync_graph.invoke(initial_state, config=config)
    
    async def ainvoke(
        self, 
        input_message: str, 
        thread_id: Optional[str] = None,
        **kwargs: Any
    ) -> dict[str, Any]:
        """Ejecuta el agente de forma asíncrona."""
        await self._ensure_async_setup()
        initial_state = self._build_initial_state(input_message, **kwargs)
        config = {"configurable": {"thread_id": thread_id or "test-thread"}}
        return await self.async_graph.ainvoke(initial_state, config=config)

    async def astream(
        self,
        input_message: str,
        thread_id: Optional[str] = None,
        **kwargs: Any
    ):
        """Stream de respuestas del agente."""
        await self._ensure_async_setup()
        initial_state = self._build_initial_state(input_message, **kwargs)
        config = {"configurable": {"thread_id": thread_id or "test-thread"}}
        
        async for chunk in self.async_graph.astream(initial_state, config=config):
            yield chunk


def make_graph(checkpointer=None):
    """
    Función factory para crear el grafo del agente.
    
    Flujo simplificado:
    
    ```
    [START] → verification → {routing}
                             ├── conversation → {routing} → END o qualified
                             └── qualified → END
    ```
    
    El nodo conversation usa un agente ReAct internamente.
    
    Args:
        checkpointer: Checkpointer opcional (PostgresSaver o MemorySaver)
    
    Returns:
        CompiledGraph: Grafo compilado del agente
    """
    
    # Si no se proporciona checkpointer, crear uno
    if checkpointer is None:
        postgres_conn = os.getenv("POSTGRES_CONNECTION_STRING")
        if postgres_conn:
            checkpointer = PostgresSaver.from_conn_string(postgres_conn)
            try:
                checkpointer.setup()
            except AttributeError:
                pass
        else:
            checkpointer = MemorySaver()
    
    # Crear el grafo con el estado
    workflow = StateGraph(AgentState)
    
    # =========================================================================
    # AGREGAR NODOS
    # =========================================================================
    
    # Nodo de verificación (entrada)
    workflow.add_node("verification", verification_node)
    
    # Nodo de conversación (usa ReAct agent internamente)
    workflow.add_node("conversation", conversation_node)
    
    # Nodo de cliente cualificado (salida)
    workflow.add_node("qualified", qualified_node)
    
    # =========================================================================
    # CONFIGURAR FLUJO
    # =========================================================================
    
    # Punto de entrada
    workflow.set_entry_point("verification")
    
    # Desde verification: enrutar según estado del cliente
    workflow.add_conditional_edges(
        "verification",
        verification_router,
        {
            "conversation": "conversation",
            "qualified": "qualified",
        }
    )
    
    # Desde conversation: enrutar según interés/cualificación
    workflow.add_conditional_edges(
        "conversation",
        route_after_conversation,
        {
            "end": END,
        }
    )
    
    # qualified siempre termina
    workflow.add_edge("qualified", END)
    
    # Compilar y retornar
    return workflow.compile(checkpointer=checkpointer)
