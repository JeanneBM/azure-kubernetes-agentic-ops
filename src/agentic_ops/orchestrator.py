from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol

from .contracts import (
    ActionRequest,
    Facts,
    Incident,
    IncidentStatus,
    IncidentTrigger,
    Recommendation,
)
from .safety import ActionExecutor, authorize_self_cure


class DiagnosticProvider(Protocol):
    def collect(self, trigger: IncidentTrigger) -> Facts:
        """Collect read-only, source-backed facts."""


@dataclass(frozen=True)
class IncidentResult:
    incident: Incident
    deduplicated: bool = False
    action_executed: bool = False


class IncidentOrchestrator:
    """Coordinates incident handling without executing unapproved changes."""

    def __init__(
        self,
        diagnostics: DiagnosticProvider,
        executor: ActionExecutor,
        *,
        groundedness_threshold: float = 0.85,
        cooldown: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 0 <= groundedness_threshold <= 1:
            raise ValueError("groundedness_threshold must be between 0 and 1")
        if cooldown < timedelta(0):
            raise ValueError("cooldown cannot be negative")
        self._diagnostics = diagnostics
        self._executor = executor
        self._groundedness_threshold = groundedness_threshold
        self._cooldown = cooldown
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._incidents: dict[str, tuple[Incident, datetime]] = {}

    def handle(self, trigger: IncidentTrigger) -> IncidentResult:
        now = self._clock()
        existing = self._incidents.get(trigger.deduplication_key)
        if existing and (
            existing[0].status in {IncidentStatus.OPEN, IncidentStatus.ESCALATED}
            or now - existing[1] < self._cooldown
        ):
            return IncidentResult(existing[0], deduplicated=True)

        facts = self._diagnostics.collect(trigger)
        action_executed = False
        recommendation: Recommendation | None = None

        if facts.groundedness < self._groundedness_threshold:
            status = IncidentStatus.ESCALATED
        elif facts.safe_action is not None:
            authorize_self_cure(facts.safe_action)
            self._executor.execute(self._bind_action_context(facts.safe_action, trigger, now))
            action_executed = True
            status = IncidentStatus.RESOLVED
        else:
            recommendation = Recommendation(
                summary=f"Investigate {trigger.reason} for {trigger.deduplication_key}",
                action=self._required_approval_action(trigger),
                evidence_sources=tuple(item.source for item in facts.items),
            )
            status = IncidentStatus.ESCALATED

        incident = Incident(trigger, status, facts, recommendation)
        self._incidents[trigger.deduplication_key] = (incident, now)
        return IncidentResult(incident, action_executed=action_executed)

    @staticmethod
    def _required_approval_action(trigger: IncidentTrigger) -> ActionRequest:
        return ActionRequest(
            "human_review",
            {"namespace": trigger.namespace, "workload": trigger.workload},
        )

    @staticmethod
    def _bind_action_context(
        action: ActionRequest, trigger: IncidentTrigger, now: datetime
    ) -> ActionRequest:
        parameters = dict(action.parameters)
        parameters.setdefault("namespace", trigger.namespace)
        parameters.setdefault("pod", trigger.pod)
        parameters.setdefault("deployment", trigger.workload)
        parameters.setdefault("timestamp", now.isoformat())
        return ActionRequest(action.name, parameters)
