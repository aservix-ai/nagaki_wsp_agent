"""
Nodo de Verificación - Grupo Nagaki

Este nodo verifica el estado del cliente y enruta al siguiente nodo apropiado.
Punto de entrada del grafo que determina el routing inicial.
"""

import logging
from src.support.agent.state import AgentState

logger = logging.getLogger(__name__)


def verification_node(state: AgentState) -> AgentState:
    """
    Verifica el estado del cliente para determinar el routing.
    
    Args:
        state: Estado actual del agente
        
    Returns:
        Estado (sin cambios por ahora - solo logging)
    """
    is_customer = state.get("is_customer", False)
    qualified = state.get("qualified", False)
    
    logger.info("=" * 60)
    logger.info("VERIFICATION NODE - Estado del Cliente")
    logger.info("=" * 60)
    logger.info(f"is_customer: {is_customer}")
    logger.info(f"qualified: {qualified}")
    logger.info("=" * 60)
    
    return {}


