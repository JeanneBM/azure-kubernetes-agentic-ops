from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from .contracts import IncidentTrigger
from .orchestrator import IncidentOrchestrator


class AlertPayload(BaseModel):
    namespace: str = Field(min_length=1)
    pod: str = Field(min_length=1)
    workload: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    correlation_id: str = Field(min_length=1)


def create_app(orchestrator: IncidentOrchestrator) -> FastAPI:
    app = FastAPI(title="AKS Agentic Ops")

    @app.post("/api/v1/incidents")
    def receive_incident(payload: AlertPayload):
        result = orchestrator.handle(IncidentTrigger(**payload.model_dump()))
        return {
            "status": result.incident.status.value,
            "deduplicated": result.deduplicated,
            "action_executed": result.action_executed,
            "correlation_id": payload.correlation_id,
        }

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    return app


def build_app() -> FastAPI:
    from .aks import AksActionExecutor, AksDiagnosticProvider
    from .foundry import FoundryDiagnosticProvider
    import os

    endpoint = os.environ["AZURE_AI_FOUNDRY_ENDPOINT"]
    deployment = os.environ["AZURE_AI_FOUNDRY_DEPLOYMENT"]
    diagnostics = FoundryDiagnosticProvider(
        AksDiagnosticProvider(), endpoint=endpoint, deployment=deployment
    )
    return create_app(IncidentOrchestrator(diagnostics, AksActionExecutor()))


app = build_app()
