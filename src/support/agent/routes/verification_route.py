"""
Enrutador del Nodo de Verificación - Grupo Nagaki

Este módulo contiene la función de enrutamiento que decide el siguiente nodo
basándose en el estado del cliente.

Lógica de enrutamiento basada en combinaciones de is_customer, interested y qualified:
- is_customer=True, interested=True, qualified=False → classify_user
- is_customer=True, interested=False, qualified=True → qualified
- is_customer=True, interested=False, qualified=False → conversation
- is_customer=False, interested=False, qualified=False → conversation
- is_customer=False, interested=True, qualified=False → classify_user
- is_customer=False, interested=False, qualified=True → qualified
"""

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
    # Extraer valores del estado
    is_customer = state.get("is_customer", False)
    interested = state.get("interested", False)
    qualified = state.get("qualified", False)
    
    # Logging del routing decision
    logger.info("ROUTING DECISION:")
    logger.info(f"  is_customer={is_customer}, interested={interested}, qualified={qualified}")
    
    # Prioridad: Si está qualified, significa que YA fue cualificado en el pasado.
    # No lo enviamos de nuevo al nodo 'qualified' (que es solo para el handover inicial).
    # Lo enviamos a 'conversation' para que Laura siga atendiéndolo con herramientas.
    if qualified:
        logger.info("  → Routing a: conversation (Usuario ya cualificado - VIP)")
        return "conversation"
    
    # Si no está qualified, evaluar según los casos restantes
    
    # Caso 1: is_customer=True, interested=True, qualified=False → classify_user
    if is_customer and interested:
        logger.info("  → Routing a: classify_user")
        return "classify_user"
    
    # Caso 3: is_customer=True, interested=False, qualified=False → conversation
    if is_customer and not interested:
        logger.info("  → Routing a: conversation")
        return "conversation"
    
    # Caso 5: is_customer=False, interested=True, qualified=False → classify_user
    if not is_customer and interested:
        logger.info("  → Routing a: classify_user")
        return "classify_user"
    
    # Caso 4: is_customer=False, interested=False, qualified=False → conversation
    if not is_customer and not interested:
        logger.info("  → Routing a: conversation")
        return "conversation"
    
    # Caso por defecto (no debería llegar aquí, pero por seguridad)
    logger.warning(f"  → Caso no contemplado, routing por defecto a: conversation")
    return "conversation"

