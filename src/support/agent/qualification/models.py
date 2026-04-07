from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class QualificationResult:
    interested: bool
    qualified: bool
    stage: str
    missing_interested: List[str] = field(default_factory=list)
    missing_qualified: List[str] = field(default_factory=list)
