"""Sincronización idempotente de leads por API o Supabase."""

import asyncio
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

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


def _normalize_phone(thread_id: str) -> str:
    phone = thread_id.strip()
    for prefix in ("sip-", "lead:"):
        if phone.startswith(prefix):
            phone = phone[len(prefix):]
    return phone


def _get_admin_phone() -> str:
    return (
        os.getenv("QUALIFIED_ADMIN_PHONE")
        or os.getenv("QUALIFIED_MANAGER_PHONE")
        or os.getenv("ADMIN_PHONE")
        or ""
    ).strip()


def _get_supabase_project_url() -> str:
    return (
        os.getenv("SUPABASE_PROJECT_URL")
        or os.getenv("SUPABASE_URL")
        or ""
    ).rstrip("/")


def _get_supabase_api_key() -> str:
    return (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_API_KEY", "")
    ).strip()


def _infer_source(thread_id: str) -> str:
    if thread_id.startswith("sip-"):
        return "voice"
    if thread_id.startswith("lead:"):
        return "whatsapp"
    return "unknown"


def _build_admin_notification_message(state: Dict[str, Any], thread_id: str, stage: str) -> str:
    phone = _normalize_phone(thread_id) or thread_id
    preferred_zones = state.get("preferredZones") or []
    zones_text = ", ".join(preferred_zones) if preferred_zones else "No especificadas"
    budget_min = state.get("budgetMin")
    budget_max = state.get("budgetMax")
    if budget_min and budget_max:
        budget_text = f"{budget_min} - {budget_max}"
    elif budget_max:
        budget_text = str(budget_max)
    elif budget_min:
        budget_text = str(budget_min)
    else:
        budget_text = "No especificado"

    return "\n".join(
        [
            "Nuevo lead calificado",
            f"Canal: {_infer_source(thread_id)}",
            f"Thread ID: {thread_id}",
            f"Telefono: {phone}",
            f"Stage: {stage}",
            f"Tipo inmueble: {state.get('property_type') or 'No especificado'}",
            f"Zonas: {zones_text}",
            f"Presupuesto: {budget_text}",
            f"Financiacion: {state.get('funding_mode') or 'No especificado'}",
            f"Intencion: {state.get('intent_type') or 'No especificada'}",
            f"Tiene capital: {state.get('has_capital')}",
            f"Quiere contacto: {state.get('asked_to_be_contacted')}",
        ]
    )


def _build_supabase_row(state: Dict[str, Any], thread_id: str, stage: str) -> Dict[str, Any]:
    interested = stage in {"interested", "qualified"}
    qualified = stage == "qualified"
    return {
        "phone": _normalize_phone(thread_id),
        "thread_id": thread_id,
        "stage": stage,
        "interested": interested,
        "qualified": qualified,
        "property_type": state.get("property_type"),
        "funding_mode": state.get("funding_mode"),
        "intent_type": state.get("intent_type"),
        "understands_asset_conditions": state.get("understands_asset_conditions"),
        "budget_min": state.get("budgetMin"),
        "budget_max": state.get("budgetMax"),
        "preferred_zones": state.get("preferredZones") or [],
        "last_contact": _now_iso(),
        "metadata": {
            "qualification_stage": stage,
            "asked_to_be_contacted": state.get("asked_to_be_contacted"),
            "transaction_type": state.get("transactionType"),
            "purchase_timeline": state.get("purchase_timeline"),
            "has_capital": state.get("has_capital"),
            "has_own_capital": state.get("has_own_capital"),
            "has_capital_assets": state.get("has_capital_assets"),
        },
    }


def _sync_lead_to_supabase(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> bool:
    project_url = _get_supabase_project_url()
    api_key = _get_supabase_api_key()
    table = os.getenv("SUPABASE_LEADS_TABLE", "leads").strip() or "leads"
    conflict_column = os.getenv("SUPABASE_LEADS_UPSERT_ON", "phone").strip() or "phone"

    if not project_url or not api_key:
        logger.warning(
            "Supabase no configurado: falta SUPABASE_PROJECT_URL/SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY/SUPABASE_SERVICE_KEY/SUPABASE_API_KEY"
        )
        return False

    query = urlencode({"on_conflict": conflict_column})
    url = f"{project_url}/rest/v1/{table}?{query}"
    row = _build_supabase_row(state=state, thread_id=thread_id, stage=stage)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Idempotency-Key": idempotency_key,
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    max_retries = int(os.getenv("LEAD_SYNC_MAX_RETRIES", "3"))
    timeout_seconds = int(os.getenv("LEAD_SYNC_TIMEOUT_SECONDS", "15"))
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=row, headers=headers, timeout=timeout_seconds)
            response.raise_for_status()
            return True
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "Supabase lead sync failed %s/%s for %s: %s",
                attempt + 1,
                max_retries,
                thread_id,
                exc,
            )
            time.sleep(2**attempt)

    _mark_event_status(idempotency_key, "failed", last_error)
    return False


def _notify_qualified_admin(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> bool:
    admin_phone = _get_admin_phone()
    if not admin_phone:
        logger.warning("QUALIFIED_ADMIN_PHONE/QUALIFIED_MANAGER_PHONE no configurado; no se notifica admin")
        return False

    api_url = (os.getenv("EVOLUTION_API_URL") or "").rstrip("/")
    api_key = os.getenv("EVOLUTION_API_KEY", "")
    instance = os.getenv("EVOLUTION_INSTANCE", "")
    if not api_url or not api_key or not instance:
        logger.warning("Evolution API no configurada completamente; no se notifica admin")
        return False

    number_to_send = admin_phone
    if not admin_phone.endswith("@s.whatsapp.net"):
        number_to_send = f"{admin_phone}@s.whatsapp.net"

    payload = {
        "number": number_to_send,
        "text": _build_admin_notification_message(state=state, thread_id=thread_id, stage=stage),
    }
    headers = {
        "apikey": api_key,
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
    }
    url = f"{api_url}/message/sendText/{instance}"
    logger.info("Sending qualified admin notification via Evolution API to %s", number_to_send)

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
                "Qualified admin notification failed %s/%s for %s: %s",
                attempt + 1,
                max_retries,
                thread_id,
                exc,
            )
            time.sleep(2**attempt)

    _mark_event_status(idempotency_key, "failed", last_error)
    return False


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


def _is_supabase_configured() -> bool:
    project_url = _get_supabase_project_url().strip()
    api_key = _get_supabase_api_key()
    return bool(project_url and api_key)


def _is_leads_api_configured() -> bool:
    return bool((os.getenv("LEADS_API_BASE_URL") or "").strip())


def _resolve_lead_sync_backend() -> str:
    requested = (os.getenv("LEAD_SYNC_BACKEND", "api") or "api").strip().lower()

    if requested == "supabase":
        return "supabase"

    if requested == "api":
        if _is_leads_api_configured():
            return "api"
        if _is_supabase_configured():
            logger.info(
                "LEADS_API_BASE_URL no configurado; usando backend Supabase porque hay credenciales disponibles"
            )
            return "supabase"
        return "api"

    if requested:
        logger.warning(
            "LEAD_SYNC_BACKEND desconocido: %s. Se intentará autodetección.",
            requested,
        )

    if _is_supabase_configured():
        return "supabase"
    return "api"


def _sync_lead(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> bool:
    backend = _resolve_lead_sync_backend()
    if backend == "supabase":
        return _sync_lead_to_supabase(
            state=state,
            thread_id=thread_id,
            stage=stage,
            idempotency_key=idempotency_key,
        )
    return _sync_interested_lead_to_api(
        state=state,
        thread_id=thread_id,
        stage=stage,
        idempotency_key=idempotency_key,
    )


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
        _sync_lead,
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


async def notify_qualified_admin(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> bool:
    event_type = "qualified_admin_notification"
    if not _try_claim_event(idempotency_key=idempotency_key, thread_id=thread_id, event_type=event_type):
        logger.info("⏭️ Notificacion admin ignorada por idempotencia: %s", idempotency_key)
        return True

    ok = await asyncio.to_thread(
        _notify_qualified_admin,
        state,
        thread_id,
        stage,
        idempotency_key,
    )
    if ok:
        _mark_event_status(idempotency_key, "sent")
        logger.info("✅ Admin notificado sobre lead qualified: %s", thread_id)
    return ok


def trigger_qualified_admin_notification(
    state: Dict[str, Any],
    thread_id: str,
    stage: str,
    idempotency_key: str,
) -> None:
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(notify_qualified_admin(state, thread_id, stage, idempotency_key))
    except RuntimeError:
        def _runner() -> None:
            asyncio.run(notify_qualified_admin(state, thread_id, stage, idempotency_key))

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
