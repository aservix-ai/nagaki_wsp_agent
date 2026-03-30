"""Qualification sidecar worker.

Consumes events from the ``qual:events`` Redis stream via a consumer
group, extracts evidence, evaluates qualification, and writes snapshots
to ``qual:state:{thread_id}``.

Run standalone::

    python -m src.support.agent.qualification.worker
"""

from __future__ import annotations


import asyncio
import logging
import platform
from datetime import datetime, timezone
from typing import Any

from src.support.agent.lead_sync import trigger_lead_sync
from src.support.agent.qualification.evaluator import (
    evaluate_qualification,
    extract_evidence_from_conversation,
    merge_evidence,
)
from src.support.agent.qualification.service import get_default_snapshot
from src.support.agent.qualification.store import (
    CONSUMER_GROUP,
    EVENTS_STREAM,
    ensure_consumer_group,
    get_redis,
    load_snapshot,
    save_snapshot,
)

logger = logging.getLogger(__name__)

WORKER_NAME = f"worker-{platform.node()}"

# All fields persisted in the snapshot
_SNAPSHOT_FIELDS = (
    "interested",
    "qualified",
    "qualification_stage",
    "budgetMin",
    "budgetMax",
    "preferredZones",
    "transactionType",
    "type_of_client",
    "property_type",
    "desired_property_type",
    "purchase_timeline",
    "intent_type",
    "understands_asset_conditions",
    "funding_mode",
    "asset_is_financeable",
    "asked_mortgage_for_financeable",
    "needs_financing",
    "financing_preapproved",
    "has_capital_assets",
    "has_own_capital",
    "has_capital",
    "asked_to_be_contacted",
)


def _build_snapshot(
    merged: dict[str, Any],
    result: Any,
    turn_id: int,
) -> dict[str, Any]:
    """Build a snapshot dict from merged state + evaluation result."""
    snap: dict[str, Any] = {"version": turn_id}
    for field in _SNAPSHOT_FIELDS:
        snap[field] = merged.get(field)
    snap["interested"] = result.interested
    snap["qualified"] = result.qualified
    snap["qualification_stage"] = result.stage
    snap["missing_interested"] = result.missing_interested
    snap["missing_qualified"] = result.missing_qualified
    snap["updated_at"] = datetime.now(timezone.utc).isoformat()
    return snap


async def _process_event(
    thread_id: str,
    turn_id: int,
    user_text: str,
    conversation_context: str = "",
) -> None:
    """Process a single qualification event."""
    current = await load_snapshot(thread_id)
    if current is None:
        current = get_default_snapshot()

    if turn_id <= current.get("version", 0):
        logger.debug(
            "Skipping stale event for %s: turn %d <= version %d",
            thread_id, turn_id, current["version"],
        )
        return

    extracted = await extract_evidence_from_conversation(
        user_text=user_text,
        current_state=current,
        conversation_context=conversation_context,
    )
    merged = merge_evidence(current, extracted)
    result = evaluate_qualification(merged)
    new_snapshot = _build_snapshot(merged, result, turn_id)

    await save_snapshot(thread_id, new_snapshot)
    logger.info(
        "Snapshot updated %s turn=%d stage=%s interested=%s qualified=%s",
        thread_id, turn_id, result.stage, result.interested, result.qualified,
    )

    previous_stage = current.get("qualification_stage", "new")
    if result.stage != previous_stage and result.stage in ("interested", "qualified"):
        idempotency_key = f"{thread_id}:{result.stage}:v{turn_id}"
        trigger_lead_sync(
            state=new_snapshot,
            thread_id=thread_id,
            stage=result.stage,
            idempotency_key=idempotency_key,
        )
        logger.info("Lead sync triggered for %s -> %s", thread_id, result.stage)


async def run_qualification_worker() -> None:
    """Main worker loop.  Blocks indefinitely consuming from the stream."""
    r = get_redis()
    consumer_group_ready = False
    logger.info("Qualification worker starting (%s)", WORKER_NAME)

    while True:
        try:
            if not consumer_group_ready:
                await ensure_consumer_group()
                await r.ping()
                consumer_group_ready = True
                logger.info("Qualification worker connected to Redis and ready")

            # First, claim any pending (unACKed) events from a previous crash
            pending = await r.xreadgroup(
                CONSUMER_GROUP, WORKER_NAME,
                {EVENTS_STREAM: "0"},
                count=10,
            )
            entries = _extract_entries(pending)

            if not entries:
                # No pending entries; block for new ones
                result = await r.xreadgroup(
                    CONSUMER_GROUP, WORKER_NAME,
                    {EVENTS_STREAM: ">"},
                    count=10,
                    block=5000,
                )
                entries = _extract_entries(result)

            for entry_id, data in entries:
                thread_id = data.get("thread_id", "")
                try:
                    turn_id = int(data.get("turn_id", "0"))
                except (ValueError, TypeError):
                    turn_id = 0
                user_text = data.get("user_text", "")
                conversation_context = data.get("conversation_context", "")

                if not thread_id or not user_text:
                    logger.warning("Malformed event %s, ACKing and skipping", entry_id)
                    await r.xack(EVENTS_STREAM, CONSUMER_GROUP, entry_id)
                    continue

                try:
                    await _process_event(
                        thread_id=thread_id,
                        turn_id=turn_id,
                        user_text=user_text,
                        conversation_context=conversation_context,
                    )
                except Exception:
                    logger.error(
                        "Error processing event %s for %s",
                        entry_id, thread_id, exc_info=True,
                    )

                await r.xack(EVENTS_STREAM, CONSUMER_GROUP, entry_id)

        except asyncio.CancelledError:
            logger.info("Worker shutting down")
            break
        except Exception:
            consumer_group_ready = False
            logger.error("Worker loop error, retrying in 2s", exc_info=True)
            await asyncio.sleep(2)


def _extract_entries(
    raw: list | None,
) -> list[tuple[str, dict[str, str]]]:
    """Flatten XREADGROUP response into a list of (entry_id, data) tuples."""
    if not raw:
        return []
    entries: list[tuple[str, dict[str, str]]] = []
    for _stream_name, stream_entries in raw:
        for entry_id, data in stream_entries:
            entries.append((entry_id, data))
    return entries


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    asyncio.run(run_qualification_worker())
