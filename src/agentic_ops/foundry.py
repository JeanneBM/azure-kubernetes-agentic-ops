from __future__ import annotations

import json
from typing import Any

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

from .contracts import ActionRequest, Evidence, Facts, IncidentTrigger


class FoundryDiagnosticProvider:
    """Uses an Azure AI Foundry model to correlate AKS evidence.

    The model receives only evidence returned by the read-only AKS provider.
    Its response is constrained to a small JSON contract and is validated
    before it can influence self-cure.
    """

    def __init__(
        self,
        evidence_provider,
        *,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-10-21",
        http_client: httpx.Client | None = None,
    ) -> None:
        self._evidence_provider = evidence_provider
        self._endpoint = endpoint.rstrip("/")
        self._deployment = deployment
        self._api_version = api_version
        self._client = http_client or httpx.Client(timeout=30)
        credential = DefaultAzureCredential()
        self._token = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )

    def collect(self, trigger: IncidentTrigger) -> Facts:
        raw = self._evidence_provider.collect(trigger)
        response = self._client.post(
            f"{self._endpoint}/openai/deployments/{self._deployment}/chat/completions",
            params={"api-version": self._api_version},
            headers={"Authorization": f"Bearer {self._token()}"},
            json={
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": json.dumps({
                        "trigger": trigger.__dict__,
                        "evidence": [item.__dict__ for item in raw.items],
                    })},
                ],
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return self._parse_facts(content, raw)

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are the AKS diagnostic agent. Use only supplied evidence. "
            "Return JSON with groundedness (0..1), summary, and safe_action "
            "(null or {name,parameters}). safe_action may only be rollout_restart, "
            "scale, or evict_pod, and only for a clearly transient issue. "
            "Never invent facts, identifiers, or parameters."
        )

    @staticmethod
    def _parse_facts(content: str, raw: Facts) -> Facts:
        try:
            data: dict[str, Any] = json.loads(content)
            groundedness = float(data["groundedness"])
            action_data = data.get("safe_action")
            action = (
                ActionRequest(action_data["name"], action_data.get("parameters", {}))
                if action_data is not None
                else None
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ValueError("Foundry response did not match the facts contract") from error
        if action is not None and action.name not in {"rollout_restart", "scale", "evict_pod"}:
            raise ValueError("Foundry returned an action outside the self-cure contract")
        return Facts(raw.items, groundedness, action)
