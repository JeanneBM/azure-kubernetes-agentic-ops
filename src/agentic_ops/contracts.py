from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping


class IncidentStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


@dataclass(frozen=True)
class IncidentTrigger:
    namespace: str
    pod: str
    workload: str
    reason: str
    correlation_id: str

    @property
    def deduplication_key(self) -> str:
        return f"{self.namespace}/{self.pod}/{self.workload}"


@dataclass(frozen=True)
class Evidence:
    name: str
    value: str
    source: str

    def __post_init__(self) -> None:
        if not self.name or not self.value or not self.source:
            raise ValueError("Evidence name, value, and source are required")


@dataclass(frozen=True)
class ActionRequest:
    name: str
    parameters: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Facts:
    items: tuple[Evidence, ...]
    groundedness: float
    safe_action: ActionRequest | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.groundedness <= 1:
            raise ValueError("groundedness must be between 0 and 1")


@dataclass(frozen=True)
class Recommendation:
    summary: str
    action: ActionRequest
    evidence_sources: tuple[str, ...]
    requires_human_approval: bool = True


@dataclass
class Incident:
    trigger: IncidentTrigger
    status: IncidentStatus
    facts: Facts
    recommendation: Recommendation | None = None
