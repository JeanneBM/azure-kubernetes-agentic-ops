from datetime import datetime, timedelta, timezone

import pytest

from agentic_ops import (
    ActionRequest,
    Evidence,
    Facts,
    IncidentOrchestrator,
    IncidentStatus,
    IncidentTrigger,
)


class Diagnostics:
    def __init__(self, facts):
        self.facts = facts
        self.calls = 0

    def collect(self, trigger):
        self.calls += 1
        return self.facts


class Executor:
    def __init__(self):
        self.actions = []

    def execute(self, action):
        self.actions.append(action)


def trigger():
    return IncidentTrigger("payments", "api-1", "api", "CrashLoopBackOff", "corr-1")


def facts(action=None, groundedness=0.95):
    return Facts((Evidence("pod-state", "waiting", "k8s://pod/api-1"),), groundedness, action)


def test_safe_action_is_executed_and_incident_resolved():
    diagnostics = Diagnostics(facts(ActionRequest("rollout_restart")))
    executor = Executor()

    result = IncidentOrchestrator(diagnostics, executor).handle(trigger())

    assert result.incident.status is IncidentStatus.RESOLVED
    assert result.action_executed
    assert executor.actions[0].name == "rollout_restart"
    assert executor.actions[0].parameters["namespace"] == "payments"


def test_non_whitelisted_action_is_rejected():
    diagnostics = Diagnostics(facts(ActionRequest("patch_deployment")))

    with pytest.raises(PermissionError):
        IncidentOrchestrator(diagnostics, Executor()).handle(trigger())


def test_unknown_cause_is_escalated_without_recommendation():
    result = IncidentOrchestrator(Diagnostics(facts(groundedness=0.84)), Executor()).handle(
        trigger()
    )

    assert result.incident.status is IncidentStatus.ESCALATED
    assert result.incident.recommendation is None


def test_non_safe_case_creates_human_approval_recommendation():
    result = IncidentOrchestrator(Diagnostics(facts()), Executor()).handle(trigger())

    assert result.incident.status is IncidentStatus.ESCALATED
    assert result.incident.recommendation.requires_human_approval
    assert result.incident.recommendation.evidence_sources == ("k8s://pod/api-1",)


def test_open_incident_is_deduplicated():
    diagnostics = Diagnostics(facts(ActionRequest("evict_pod")))
    orchestrator = IncidentOrchestrator(diagnostics, Executor())

    first = orchestrator.handle(trigger())
    second = orchestrator.handle(trigger())

    assert not first.deduplicated
    assert second.deduplicated
    assert diagnostics.calls == 1


def test_closed_incident_is_rate_limited_during_cooldown():
    now = [datetime(2026, 1, 1, tzinfo=timezone.utc)]
    diagnostics = Diagnostics(facts(ActionRequest("rollout_restart")))
    orchestrator = IncidentOrchestrator(
        diagnostics, Executor(), cooldown=timedelta(minutes=10), clock=lambda: now[0]
    )
    orchestrator.handle(trigger())
    now[0] += timedelta(minutes=5)

    result = orchestrator.handle(trigger())

    assert result.deduplicated
    assert diagnostics.calls == 1
