"""High-level helpers for the qualification sidecar.

These are the functions that the graph entrypoint and nodes should call.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from src.support.agent.qualification.store import load_snapshot


def get_default_snapshot() -> dict[str, Any]:
    """Return an explicit default snapshot for a brand-new lead.

    Using this instead of ``evaluate_qualification({})`` avoids the
    semantics mismatch where an empty state evaluates to
    ``stage="discovery"`` instead of ``"new"``.
    """
    return {
        "version": 0,
        "interested": False,
        "qualified": False,
        "qualification_stage": "new",
        "budgetMin": None,
        "budgetMax": None,
        "preferredZones": None,
        "transactionType": None,
        "type_of_client": None,
        "property_type": "unknown",
        "selected_asset_type": "unknown",
        "selected_property_reference": None,
        "selected_property_price": None,
        "desired_property_type": None,
        "purchase_timeline": "unknown",
        "intent_type": "unknown",
        "understands_asset_conditions": None,
        "funding_mode": "unknown",
        "asset_is_financeable": None,
        "asked_mortgage_for_financeable": None,
        "needs_financing": None,
        "financing_preapproved": None,
        "has_capital_assets": None,
        "has_own_capital": None,
        "has_capital": None,
        "asked_to_be_contacted": None,
        "wants_to_visit": None,
        "slot_sources": {},
        "slot_evidence": {},
        "filled_slots": [],
        "missing_slots": [],
        "channels_seen": [],
        "last_source": None,
        "last_user_text": None,
        "last_conversation_context": None,
        "qualification_reasoning": [],
        "missing_interested": [],
        "missing_qualified": [],
        "updated_at": None,
    }


async def get_qualification_context(thread_id: str) -> dict[str, Any]:
    """Load the qualification snapshot for *thread_id*, with defaults.

    Returns ``get_default_snapshot()`` when Redis is unreachable or the
    thread has never been seen before (cold start / turn 1).
    """
    snapshot = await load_snapshot(thread_id)
    if snapshot is None:
        return get_default_snapshot()
    return snapshot


async def load_qualification_snapshot(thread_id: str) -> dict[str, Any] | None:
    """Load snapshot with short timeout and fail-open behavior."""
    timeout_ms = int(os.getenv("QUAL_SNAPSHOT_TIMEOUT_MS", "250"))
    timeout_seconds = max(timeout_ms, 1) / 1000
    try:
        return await asyncio.wait_for(load_snapshot(thread_id), timeout=timeout_seconds)
    except Exception:
        return None
