"""Redis store for qualification snapshots and event streams.

Keys:
    qual:state:{thread_id}  - JSON snapshot of qualification state
    qual:turn:{thread_id}   - Monotonic turn counter per thread
    qual:events             - Redis Stream of qualification events
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

SNAPSHOT_PREFIX = "qual:state:"
EVENTS_STREAM = "qual:events"
TURN_PREFIX = "qual:turn:"
CONSUMER_GROUP = "qual-workers"

_redis_client: Optional[aioredis.Redis] = None


def get_redis() -> aioredis.Redis:
    """Return a singleton async Redis client."""
    global _redis_client
    if _redis_client is None:
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2.0,
            # Worker uses XREADGROUP with BLOCK > 2s; keep a larger read timeout.
            socket_timeout=10.0,
        )
    return _redis_client


async def save_snapshot(thread_id: str, snapshot: dict[str, Any]) -> None:
    """Persist a qualification snapshot as JSON."""
    snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
    try:
        r = get_redis()
        await r.set(f"{SNAPSHOT_PREFIX}{thread_id}", json.dumps(snapshot))
    except Exception:
        logger.warning("Redis write failed for %s", thread_id, exc_info=True)


async def load_snapshot(thread_id: str) -> Optional[dict[str, Any]]:
    """Load a qualification snapshot. Returns None on any failure (fail-open)."""
    try:
        r = get_redis()
        raw = await r.get(f"{SNAPSHOT_PREFIX}{thread_id}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.warning("Redis read failed for %s", thread_id, exc_info=True)
        return None


async def next_turn_id(thread_id: str) -> int:
    """Return a monotonically increasing turn counter for the thread.

    Falls back to 0 if Redis is unreachable so the caller can still proceed.
    """
    try:
        r = get_redis()
        return await r.incr(f"{TURN_PREFIX}{thread_id}")
    except Exception:
        logger.warning("Redis INCR failed for %s, returning 0", thread_id, exc_info=True)
        return 0


async def ensure_consumer_group() -> None:
    """Create the consumer group idempotently (safe to call on every startup)."""
    try:
        r = get_redis()
        await r.xgroup_create(
            EVENTS_STREAM, CONSUMER_GROUP, id="0", mkstream=True,
        )
        logger.info("Consumer group '%s' created on '%s'", CONSUMER_GROUP, EVENTS_STREAM)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            logger.debug("Consumer group '%s' already exists", CONSUMER_GROUP)
        else:
            raise


async def health_check() -> bool:
    """Return True if Redis responds to PING."""
    try:
        r = get_redis()
        return await r.ping()
    except Exception:
        return False
