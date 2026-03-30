"""Nodo de verificación basado en snapshot de calificación."""

import logging

from src.support.agent.state import AgentState

logger = logging.getLogger(__name__)


def verification_node(state: AgentState) -> AgentState:
    snapshot = state.get("qualification_snapshot") or {}
    interested = bool(snapshot.get("interested", False))
    qualified = bool(snapshot.get("qualified", False))
    stage = snapshot.get("qualification_stage", "new")

    logger.info("=" * 60)
    logger.info("VERIFICATION NODE - Snapshot de calificación")
    logger.info("=" * 60)
    logger.info("interested(snapshot): %s", interested)
    logger.info("qualified(snapshot): %s", qualified)
    logger.info("stage(snapshot): %s", stage)
    logger.info("=" * 60)

    return {
        "interested": interested,
        "qualified": qualified,
        "qualification_stage": stage,
    }

