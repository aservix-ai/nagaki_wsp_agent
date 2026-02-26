"""
Nodo de Verificación - Grupo Nagaki

Este nodo verifica el estado del cliente y enruta al siguiente nodo apropiado.
Extrae y calcula points, interested y qualified, y determina el routing correcto.
"""

import logging
from src.support.agent.state import AgentState, QualificationThreshold

# Configurar logger
logger = logging.getLogger(__name__)


def verification_node(state: AgentState) -> AgentState:
    """
    Verifica el estado del cliente, extrae puntos y calcula interested/qualified.
    
    Este nodo:
    1. Extrae los puntos del estado
    2. Calcula si está interesado (points >= 4)
    3. Calcula si está cualificado (points >= 7)
    4. Loggea la información para debugging
    
    Args:
        state: Estado actual del agente
        
    Returns:
        Estado actualizado con interested y qualified calculados
    """
    # Extraer valores del estado
    is_customer = state.get("is_customer", False)
    points = state.get("points", 0)
    current_interested = state.get("interested", False)
    current_qualified = state.get("qualified", False)
    
    # Calcular interested y qualified basado en puntos
    interested = points >= QualificationThreshold.INTERESTED  # >= 4 puntos
    qualified = points >= QualificationThreshold.QUALIFIED    # >= 7 puntos
    
    # Logging detallado para debugging
    logger.info("=" * 60)
    logger.info("VERIFICATION NODE - Estado del Cliente")
    logger.info("=" * 60)
    logger.info(f"is_customer: {is_customer}")
    logger.info(f"points: {points} (suma total)")
    logger.info(f"interested: {current_interested} → {interested} (calculado: points >= {QualificationThreshold.INTERESTED})")
    logger.info(f"qualified: {current_qualified} → {qualified} (calculado: points >= {QualificationThreshold.QUALIFIED})")
    logger.info("=" * 60)
    
    # Preparar actualización del estado
    state_update = {}
    
    # Solo actualizar si hay cambios para evitar logs innecesarios
    if interested != current_interested:
        state_update["interested"] = interested
        logger.info(f"✓ Actualizado interested: {current_interested} → {interested}")
    
    if qualified != current_qualified:
        state_update["qualified"] = qualified
        logger.info(f"✓ Actualizado qualified: {current_qualified} → {qualified}")
    
    # Si no hay cambios, loggear igual para debugging
    if not state_update:
        logger.info("✓ No hay cambios en interested/qualified")
    
    return state_update


