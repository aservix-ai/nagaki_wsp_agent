"""Sincronización idempotente de leads por API."""

import asyncio
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

_DB_PATH = os.getenv("LEAD_SYNC_DB_PATH", "/tmp/nagaki_lead_sync.db")
_DB_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH, timeout=30, check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_sync_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            idempotency_key TEXT NOT NULL UNIQUE,
            thread_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def _try_claim_event(idempotency_key: str, thread_id: str, event_type: str) -> bool:
    with _DB_LOCK:
        conn = _get_db_connection()
        try:
            now = _now_iso()
            conn.execute(
                """
                INSERT INTO lead_sync_events (
                    idempotency_key, thread_id, event_type, status, attempt_count, created_at, updated_at
                ) VALUES (?, ?, ?, 'pending', 0, ?, ?)
                """,
                (idempotency_key, thread_id, event_type, now, now),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()


def _mark_event_status(idempotency_key: str, status: str, error: Optional[str] = None) -> None:
    with _DB_LOCK:
        conn = _get_db_connection()
        try:
            conn.execute(
                """
                UPDATE lead_sync_events
                SET status = ?, attempt_count = attempt_count + 1, last_error = ?, updated_at = ?
                WHERE idempotency_key = ?
                """,
                (status, error, _now_iso(), idempotency_key),
            )
            conn.commit()
        finally:
            conn.close()


def _build_payload(state: Dict[str, Any], thread_id: str, stage: str) -> Dict[str, Any]:
    interest = {
        "budgetMin": state.get("budgetMin"),
        "budgetMax": state.get("budgetMax"),
        "preferredZones": state.get("preferredZones") or [],
        "propertyType": state.get("property_type", "unknown"),
        "fundingMode": state.get("funding_mode", "unknown"),
    }
    interest = {k: v for k, v in interest.items() if v not in (None, "", [])}

    return {
        "lead": {
            "phone": thread_id,
            "stage": stage,
            "qualified": stage == "qualified",
            "interest": interest,
            "metadata": {
                "intentType": state.get("intent_type", "unknown"),
                "understandsAssetConditions": state.get("understands_asset_conditions"),
                "qualificationStage": stage,
            },
            "updatedAt": _now_iso(),
        }
    }


def _sync_interested_lead_to_api(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> bool:
    base_url = (os.getenv("LEADS_API_BASE_URL") or "").rstrip("/")
    if not base_url:
        logger.warning("LEADS_API_BASE_URL no configurado, no se sincroniza lead")
        return False

    endpoint = os.getenv("LEADS_API_UPSERT_ENDPOINT", "/api/v1/leads")
    url = f"{base_url}{endpoint}"
    payload = _build_payload(state=state, thread_id=thread_id, stage=stage)

    api_key = os.getenv("LEADS_API_KEY", "")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Idempotency-Key": idempotency_key,
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    max_retries = int(os.getenv("LEAD_SYNC_MAX_RETRIES", "3"))
    timeout_seconds = int(os.getenv("LEAD_SYNC_TIMEOUT_SECONDS", "15"))
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout_seconds)
            response.raise_for_status()
            return True
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Sync lead failed %s/%s for %s: %s",
                attempt + 1,
                max_retries,
                thread_id,
                exc,
            )
            time.sleep(2**attempt)

    _mark_event_status(idempotency_key, "failed", last_error)
    return False


async def sync_lead(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> bool:
    event_type = f"{stage}_reached"
    if not _try_claim_event(idempotency_key=idempotency_key, thread_id=thread_id, event_type=event_type):
        logger.info("⏭️ Sync ignorado por idempotencia: %s", idempotency_key)
        return True

    ok = await asyncio.to_thread(
        _sync_interested_lead_to_api,
        state,
        thread_id,
        stage,
        idempotency_key,
    )
    if ok:
        _mark_event_status(idempotency_key, "sent")
        logger.info("✅ Lead sincronizado: %s (%s)", thread_id, stage)
    return ok


def trigger_lead_sync(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(sync_lead(state, thread_id, stage, idempotency_key))
    except RuntimeError:
        def _runner() -> None:
            asyncio.run(sync_lead(state, thread_id, stage, idempotency_key))

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()

