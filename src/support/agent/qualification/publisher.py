"""Fire-and-forget publisher for qualification events.

The public function ``publish_qualification_event`` is synchronous and
schedules the actual Redis XADD via ``asyncio.create_task``.  It never
blocks the caller and swallows all errors so that a Redis outage cannot
affect voice latency.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from src.support.agent.qualification.store import EVENTS_STREAM, get_redis

logger = logging.getLogger(__name__)


async def _publish(
    thread_id: str,
    turn_id: int,
    user_text: str,
    source: str,
    conversation_context: str = "",
) -> None:
    try:
        r = get_redis()
        payload = {
            "thread_id": thread_id,
            "turn_id": str(turn_id),
            "user_text": user_text,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if conversation_context:
            payload["conversation_context"] = conversation_context
        await r.xadd(
            EVENTS_STREAM,
            payload,
        )
        logger.debug("Published qual event for %s turn %d", thread_id, turn_id)
    except Exception:
        logger.warning(
            "Failed to publish qual event for %s (non-fatal)", thread_id, exc_info=True,
        )


def publish_qualification_event(
    thread_id: str,
    turn_id: int,
    user_text: str,
    source: str = "voice",
    conversation_context: str = "",
) -> None:
    """Schedule event publication without blocking the caller.

    Safe to call from any async context.  If there is no running event
    loop (e.g. tests), the event is silently dropped.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(
            _publish(
                thread_id,
                turn_id,
                user_text,
                source,
                conversation_context=conversation_context,
            )
        )
    except RuntimeError:
        logger.debug("No event loop; skipping qual event for %s", thread_id)
