"""Estado compartido del agente."""

from typing import Annotated, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    # Historial de conversación
    messages: Annotated[list[BaseMessage], add_messages]
    input: str

    # Estado base del lead
    is_customer: bool
    qualification_snapshot: Optional[dict[str, Any]]

    # Mirrors transicionales (derivados del snapshot)
    interested: Optional[bool]
    qualified: Optional[bool]
    qualification_stage: Optional[str]






