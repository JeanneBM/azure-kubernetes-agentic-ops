# Azure Kubernetes Agentic Ops

This repository contains the first implementation slice described in
[project-concept.md](./project-concept.md): a safety-first incident
orchestrator with source-backed facts, deduplication, rate limiting, and a
strict self-cure whitelist.

## Development

The project requires Python 3.11 or newer. Install it in editable mode and
run the tests:

```text
python -m pip install -e ".[dev]"
python -m pytest
```

The current core is deliberately infrastructure-agnostic. Kubernetes,
Prometheus/Loki, audit logging, and an event webhook can be connected through
the `DiagnosticProvider` and `ActionExecutor` protocols without weakening the
approval boundary.

## AKS and Azure AI Foundry deployment

The production adapter runs inside AKS using Workload Identity:

1. Create an Azure AI Foundry project/model deployment and record its
   OpenAI-compatible endpoint and deployment name.
2. Create a user-assigned managed identity and grant it the Foundry project
   inference role.
3. Configure an AKS workload identity federated credential for the
   `agentic-ops` service account.
4. Build and push the image, then substitute the `${...}` values in
   [deploy/aks-agentic-ops.yaml](./deploy/aks-agentic-ops.yaml) and apply it.

```text
docker build -t "$AGENTIC_OPS_IMAGE" .
docker push "$AGENTIC_OPS_IMAGE"
kubectl create namespace agentic-ops
envsubst < deploy/aks-agentic-ops.yaml | kubectl apply -f -
```

The webhook accepts `POST /api/v1/incidents` with:

```json
{
  "namespace": "payments",
  "pod": "payments-api-abc",
  "workload": "payments-api",
  "reason": "CrashLoopBackOff",
  "correlation_id": "INC-4821"
}
```

`AksDiagnosticProvider` reads pod status, events, and previous logs. The
Foundry adapter correlates only those facts and must return the validated JSON
contract. `AksActionExecutor` receives Kubernetes credentials through the pod
identity; all write operations still pass through the self-cure whitelist.

## One-command shutdown

To remove only the application from an existing AKS cluster:

```powershell
.\scripts\stop-agentic-ops.ps1 -ResourceGroup "rg-agentic-ops" -AksName "aks-agentic-ops"
```

To stop Azure billing for the environment created in this guide, delete the
entire resource group. This permanently deletes the AKS cluster, ACR, and any
other resources in that group:

```powershell
.\scripts\stop-agentic-ops.ps1 -ResourceGroup "rg-agentic-ops" -DeleteResourceGroup
```

The destructive mode asks you to type the resource group name and starts
deletion asynchronously. Use `-WhatIf` to inspect the action without changing
Azure resources.
