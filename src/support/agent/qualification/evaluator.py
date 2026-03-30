import json
import logging
import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
load_dotenv()

from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from src.support.agent.qualification.models import QualificationResult

logger = logging.getLogger(__name__)


class EvidenceExtraction(BaseModel):
    budget_min: Optional[int] = Field(default=None)
    budget_max: Optional[int] = Field(default=None)
    preferred_zones: List[str] = Field(default_factory=list)
    desired_property_type: Optional[str] = Field(default=None)
    intent_type: Optional[str] = Field(default=None)  # investor | buyer | unknown
    selected_asset_type: Optional[str] = Field(default=None)  # cesion_remate | ocupada | libre | unknown
    needs_financing: Optional[bool] = Field(default=None)
    financing_preapproved: Optional[bool] = Field(default=None)
    has_capital_assets: Optional[bool] = Field(default=None)
    has_own_capital: Optional[bool] = Field(default=None)
    knows_asset_conditions: Optional[bool] = Field(default=None)
    asked_to_be_contacted: Optional[bool] = Field(default=None)


_VALID_DESIRED_TYPES = {
    "flat",
    "apartment",
    "house",
    "chalet",
    "bungalow",
    "duplex",
    "penthouse",
    "studio",
    "ground_floor",
    "office",
    "commercial_space",
    "garage",
    "land",
    "industrial_warehouse",
    "villa",
    "rustic_estate",
    "room",
    "building",
    "warehouse",
    "hotel",
    "storage_room",
}


def _get_evaluator_llm() -> Optional[Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        groq_key = os.getenv("GROQ_API_KEY")
        if not groq_key:
            return None
        model = os.getenv("QUAL_EVALUATOR_GROQ_MODEL", "llama-3.3-70b-versatile")
        return ChatGroq(model=model, temperature=0)
    model = os.getenv("QUAL_EVALUATOR_MODEL", "gpt-4o-mini")
    return ChatOpenAI(model=model, temperature=0)


def _map_asset_type(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"cesion_remate", "cesion de remate", "subasta", "credito"}:
        return "cesion_remate"
    if normalized in {"ocupada", "ocupado", "vivienda_ocupada"}:
        return "ocupada"
    if normalized in {"libre", "vivienda_libre", "visitable"}:
        return "inmueble_libre"
    if normalized in {"unknown", "desconocido"}:
        return "unknown"
    return None


def _safe_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None


def _normalize_zones(zones: List[str]) -> List[str]:
    out: list[str] = []
    for zone in zones or []:
        if not isinstance(zone, str):
            continue
        cleaned = " ".join(zone.split()).strip()
        if not cleaned:
            continue
        out.append(cleaned.title())
    return sorted(set(out))


def _build_extraction_prompt(
    *,
    user_text: str,
    conversation_context: str,
    current_state: Dict[str, Any],
) -> str:
    state_json = json.dumps(current_state or {}, ensure_ascii=False)
    return f"""
Eres un evaluador de leads inmobiliarios. Extrae SOLO evidencia explícita o muy inferible del contexto.

Contexto de conversación (más reciente):
{conversation_context or "(sin contexto)"}

Último turno del cliente:
{user_text}

Estado actual:
{state_json}

Reglas de extracción:
1) Para activos no visitables (cesión de remate u ocupada):
   - Si el cliente confirma que puede pagar al contado/completo sin hipoteca:
     has_capital_assets=true
   - Si dice que necesita hipoteca:
     needs_financing=true
   - Si confirma que conoce/acepta condiciones:
     knows_asset_conditions=true
2) Para vivienda libre:
   - Si confirma capital propio:
     has_own_capital=true
   - Si confirma financiación pre-aprobada/estudiada:
     financing_preapproved=true
   - Si dice que necesita financiación sin preaprobación:
     needs_financing=true
3) selected_asset_type debe ser uno de:
   cesion_remate, ocupada, libre, unknown.
   Si no se puede inferir con confianza, usa unknown.
4) intent_type:
   - investor cuando compra para invertir/rentabilizar.
   - buyer cuando compra para vivir.
   - unknown si no está claro.
5) preferred_zones: lista corta de zonas/ciudades/provincias explícitas.
6) budget_min y budget_max: enteros en euros solo si hay dato suficiente.
7) asked_to_be_contacted=true si explícitamente pide llamada/contacto/comercial.
8) desired_property_type solo con estos valores:
   flat, apartment, house, chalet, bungalow, duplex, penthouse, studio,
   ground_floor, office, commercial_space, garage, land, industrial_warehouse,
   villa, rustic_estate, room, building, warehouse, hotel, storage_room.

Devuelve únicamente JSON válido con el esquema solicitado.
"""


def _map_evidence_to_state(ev: EvidenceExtraction) -> Dict[str, Any]:
    out: Dict[str, Any] = {}

    if ev.budget_min is not None:
        out["budgetMin"] = int(ev.budget_min)
    if ev.budget_max is not None:
        out["budgetMax"] = int(ev.budget_max)

    zones = _normalize_zones(ev.preferred_zones)
    if zones:
        out["preferredZones"] = zones

    if ev.desired_property_type in _VALID_DESIRED_TYPES:
        out["desired_property_type"] = ev.desired_property_type

    intent = (ev.intent_type or "").strip().lower()
    if intent in {"investor", "buyer", "unknown"}:
        out["intent_type"] = intent
        if intent in {"investor", "buyer"}:
            out["type_of_client"] = intent

    mapped_asset = _map_asset_type(ev.selected_asset_type)
    if mapped_asset:
        out["property_type"] = mapped_asset

    needs_financing = _safe_bool(ev.needs_financing)
    if needs_financing is not None:
        out["needs_financing"] = needs_financing

    financing_preapproved = _safe_bool(ev.financing_preapproved)
    if financing_preapproved is not None:
        out["financing_preapproved"] = financing_preapproved

    has_capital_assets = _safe_bool(ev.has_capital_assets)
    if has_capital_assets is not None:
        out["has_capital_assets"] = has_capital_assets

    has_own_capital = _safe_bool(ev.has_own_capital)
    if has_own_capital is not None:
        out["has_own_capital"] = has_own_capital

    knows_conditions = _safe_bool(ev.knows_asset_conditions)
    if knows_conditions is not None:
        out["understands_asset_conditions"] = knows_conditions

    asked_contact = _safe_bool(ev.asked_to_be_contacted)
    if asked_contact is not None:
        out["asked_to_be_contacted"] = asked_contact

    return out


async def extract_evidence_from_conversation(
    *,
    user_text: str,
    current_state: Dict[str, Any],
    conversation_context: str = "",
) -> Dict[str, Any]:
    llm = _get_evaluator_llm()
    if llm is None:
        logger.warning(
            "Sin OPENAI_API_KEY ni GROQ_API_KEY: evaluador IA no disponible, se conserva estado actual"
        )
        return {}

    try:
        structured_llm = llm.with_structured_output(EvidenceExtraction)
        prompt = _build_extraction_prompt(
            user_text=user_text,
            conversation_context=conversation_context,
            current_state=current_state,
        )
        evidence = await structured_llm.ainvoke(prompt)
        extracted = _map_evidence_to_state(evidence)
        logger.debug("Evidence extracted by AI: %s", extracted)
        return extracted
    except Exception:
        logger.error("AI evaluator failed, keeping previous state", exc_info=True)
        return {}


def extract_evidence_from_text(user_input: str) -> Dict[str, Any]:
    """Compat legacy for scripts/tests. Pipeline productivo usa extract_evidence_from_conversation."""
    _ = user_input
    return {}


def merge_evidence(current_state: Dict[str, Any], extracted: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(current_state)

    for key, value in extracted.items():
        if value in (None, "", []):
            continue
        if key == "preferredZones":
            existing = merged.get("preferredZones") or []
            merged["preferredZones"] = sorted(set(existing + value))
            continue
        merged[key] = value

    has_capital_assets = bool(merged.get("has_capital_assets"))
    has_own_capital = bool(merged.get("has_own_capital"))
    merged["has_capital"] = has_capital_assets or has_own_capital

    property_type = merged.get("property_type", "unknown")
    merged["asset_is_financeable"] = property_type == "inmueble_libre"

    if bool(merged.get("financing_preapproved")):
        merged["funding_mode"] = "mortgage_preapproved"
    elif bool(merged.get("needs_financing")):
        merged["funding_mode"] = "mortgage_unstudied"
    elif bool(merged.get("has_capital")):
        merged["funding_mode"] = "cash_total"
    elif not merged.get("funding_mode"):
        merged["funding_mode"] = "unknown"

    if not merged.get("qualification_stage"):
        merged["qualification_stage"] = "new"
    if not merged.get("intent_type"):
        merged["intent_type"] = "unknown"
    if not merged.get("purchase_timeline"):
        merged["purchase_timeline"] = "unknown"

    return merged


def evaluate_qualification(state: Dict[str, Any]) -> QualificationResult:
    budget_stated = bool(state.get("budgetMin") or state.get("budgetMax"))
    is_investor = state.get("intent_type") == "investor"
    is_buyer_living = state.get("intent_type") == "buyer"
    financing_preapproved = bool(state.get("financing_preapproved"))
    needs_financing = bool(state.get("needs_financing"))
    knows_conditions = bool(state.get("understands_asset_conditions"))
    zone_stated = bool(state.get("preferredZones"))
    asked_to_be_contacted = bool(state.get("asked_to_be_contacted"))
    has_capital = bool(state.get("has_capital"))

    interested_clauses = {
        "budget_declared": budget_stated,
        "is_investor": is_investor,
        "financing_preapproved": financing_preapproved,
        "needs_financing_and_buyer": needs_financing and is_buyer_living,
        "knows_conditions_and_needs_financing": knows_conditions and needs_financing,
        "zone_and_budget": zone_stated and budget_stated,
        "asks_to_be_contacted": asked_to_be_contacted,
    }
    interested = any(interested_clauses.values())

    qualified_clauses = {
        "investor_and_has_capital": is_investor and has_capital,
        "has_capital_and_knows_conditions": has_capital and knows_conditions,
        "has_capital": has_capital,
    }
    qualified = any(qualified_clauses.values())
    if qualified:
        interested = True

    if qualified:
        stage = "qualified"
    elif interested:
        stage = "interested"
    else:
        stage = "discovery"

    missing_interested: List[str] = []
    if not interested:
        missing_interested = [k for k, v in interested_clauses.items() if not v]

    missing_qualified: List[str] = []
    if not qualified:
        missing_qualified = [k for k, v in qualified_clauses.items() if not v]

    return QualificationResult(
        interested=interested,
        qualified=qualified,
        stage=stage,
        missing_interested=missing_interested,
        missing_qualified=missing_qualified,
    )
