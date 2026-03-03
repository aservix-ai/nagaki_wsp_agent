"""
Background Tasks para el Agente

Este módulo contiene funciones placeholder que se ejecutan en segundo plano.
Sistema de calificación deshabilitado temporalmente.
"""

import logging

logger = logging.getLogger(__name__)


async def update_points_background(
    user_input: str,
    thread_id: str,
    agent,
    current_points: int = 0,
    is_classify_context: bool = False,
) -> dict:
    """
    Placeholder - Sistema de calificación deshabilitado.
    """
    logger.debug(f"[Background] Sistema de calificación deshabilitado para thread: {thread_id}")
    return {
        "success": True,
        "message": "Sistema de calificación deshabilitado",
    }


async def qualify_response_background(
    tool_calls: list,
    thread_id: str,
    agent,
    current_points: int = 0,
) -> dict:
    """
    Placeholder - Sistema de calificación deshabilitado.
    """
    logger.debug(f"[Background Classify] Sistema de calificación deshabilitado para thread: {thread_id}")
    return {
        "success": True,
        "message": "Sistema de calificación deshabilitado",
    }
