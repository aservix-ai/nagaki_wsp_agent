from src.support.agent.qualification.evaluator import (
    evaluate_qualification,
    extract_evidence_from_conversation,
    extract_evidence_from_text,
    merge_evidence,
)
from src.support.agent.qualification.models import QualificationResult
from src.support.agent.qualification.publisher import publish_qualification_event
from src.support.agent.qualification.service import (
    get_default_snapshot,
    get_qualification_context,
    load_qualification_snapshot,
)

__all__ = [
    "evaluate_qualification",
    "extract_evidence_from_conversation",
    "extract_evidence_from_text",
    "merge_evidence",
    "QualificationResult",
    "publish_qualification_event",
    "get_default_snapshot",
    "get_qualification_context",
    "load_qualification_snapshot",
    "run_qualification_worker",
]


def __getattr__(name: str):
    if name == "run_qualification_worker":
        from src.support.agent.qualification.worker import run_qualification_worker

        return run_qualification_worker
    raise AttributeError(name)
