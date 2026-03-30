"""Enrutador de verificación basado en snapshot de calificación."""

import logging
from src.support.agent.state import AgentState

logger = logging.getLogger(__name__)


def verification_router(state: AgentState) -> str:
    """
    Enruta al siguiente nodo basándose en el estado del cliente.
    
    Extrae is_customer, interested y qualified del estado y aplica la lógica
    de enrutamiento según las combinaciones especificadas.
    
    Args:
        state: Estado actual del agente
        
    Returns:
        str: Nombre del siguiente nodo al que enrutar
    """
    snapshot = state.get("qualification_snapshot") or {}
    interested = bool(snapshot.get("interested", state.get("interested", False)))
    qualified = bool(snapshot.get("qualified", state.get("qualified", False)))
    stage = snapshot.get("qualification_stage", state.get("qualification_stage", "new"))
    
    # Logging del routing decision
    logger.info("ROUTING DECISION:")
    logger.info(f"  interested={interested}, qualified={qualified}, stage={stage}")
    
    # Prioridad: si está qualified, ir a nodo qualified
    if qualified:
        logger.info("  → Routing a: qualified")
        return "qualified"

    # Resto del flujo sigue en conversación
    logger.info("  → Routing a: conversation")
    return "conversation"
