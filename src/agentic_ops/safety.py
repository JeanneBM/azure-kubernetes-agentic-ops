from __future__ import annotations

from typing import Protocol

from .contracts import ActionRequest


SAFE_ACTIONS = frozenset({"rollout_restart", "scale", "evict_pod"})


class ActionExecutor(Protocol):
    def execute(self, action: ActionRequest) -> None:
        """Execute an already-authorized action."""


def is_safe_action(action: ActionRequest) -> bool:
    return action.name in SAFE_ACTIONS


def authorize_self_cure(action: ActionRequest) -> None:
    if not is_safe_action(action):
        raise PermissionError(
            f"Action {action.name!r} is outside the self-cure whitelist"
        )
