from typing import Annotated, List, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # Historial de conversación
    messages: Annotated[list[BaseMessage], add_messages]
    input: str

    # Estado base del lead
    is_customer: bool
    interested: bool
    qualified: bool
    qualification_stage: str  # new | discovery | interested | qualified | disqualified

    # Datos comerciales
    budgetMin: Optional[int]
    budgetMax: Optional[int]
    preferredZones: Optional[List[str]]
    transactionType: Optional[str]
    type_of_client: Optional[str]
    property_type: str  # cesion_remate | npl | reo_sin_posesion | inmueble_libre | inmueble_ocupado | unknown

    # Evidencia de cualificación
    intent_type: str  # investor | buyer | unknown
    understands_asset_conditions: Optional[bool]
    funding_mode: str  # cash_total | mortgage_preapproved | mortgage_unstudied | unknown
    asset_is_financeable: Optional[bool]
    asked_mortgage_for_financeable: Optional[bool]
