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

1. Log in to Azure and select the subscription:

```powershell
az login
az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
```

2. Create an Azure AI Foundry project/model deployment and record its
   OpenAI-compatible endpoint and deployment name.
3. Create a user-assigned managed identity and grant it the Foundry project
   inference role.
4. Configure an AKS workload identity federated credential for the
   `agentic-ops` service account.
5. Build and push the image, then substitute the `${...}` values in
   [deploy/aks-agentic-ops.yaml](./deploy/aks-agentic-ops.yaml) and apply it.

Set the deployment values in PowerShell:

```powershell
$resourceGroup = "rg-agentic-ops"
$aksName = "aks-agentic-ops"
$acrName = "<YOUR_ACR_NAME>"
$env:AZURE_CLIENT_ID = "<USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID>"
$env:AZURE_AI_FOUNDRY_ENDPOINT = "https://<FOUNDRY_RESOURCE>.openai.azure.com"
$env:AZURE_AI_FOUNDRY_DEPLOYMENT = "<FOUNDRY_MODEL_DEPLOYMENT_NAME>"
$env:AGENTIC_OPS_IMAGE = "$acrName.azurecr.io/agentic-ops:0.1.0"
```

The recommended build path does not require Docker installed locally. Azure
Container Registry builds the image remotely from this repository directory:

```powershell
az acr build `
  --registry $acrName `
  --image agentic-ops:0.1.0 `
  .
```

Alternatively, if Docker is installed locally:

```powershell
az acr login --name $acrName
docker build -t $env:AGENTIC_OPS_IMAGE .
docker push $env:AGENTIC_OPS_IMAGE
```

Deploy the image to AKS:

```powershell
az aks get-credentials `
  --resource-group $resourceGroup `
  --name $aksName `
  --overwrite-existing

kubectl create namespace agentic-ops --dry-run=client -o yaml |
  kubectl apply -f -

(Get-Content .\deploy\aks-agentic-ops.yaml -Raw).
  Replace('${AZURE_CLIENT_ID}', $env:AZURE_CLIENT_ID).
  Replace('${AZURE_AI_FOUNDRY_ENDPOINT}', $env:AZURE_AI_FOUNDRY_ENDPOINT).
  Replace('${AZURE_AI_FOUNDRY_DEPLOYMENT}', $env:AZURE_AI_FOUNDRY_DEPLOYMENT).
  Replace('${AGENTIC_OPS_IMAGE}', $env:AGENTIC_OPS_IMAGE) |
  Set-Content .\deploy\aks-agentic-ops.rendered.yaml

kubectl apply -f .\deploy\aks-agentic-ops.rendered.yaml
kubectl rollout status deployment/agentic-ops -n agentic-ops
kubectl get pods -n agentic-ops
```

Verify the service health from inside the cluster:

```powershell
kubectl run agentic-ops-healthcheck `
  --rm -i --restart=Never `
  --image=curlimages/curl `
  -- curl --fail http://agentic-ops.agentic-ops.svc.cluster.local:8080/healthz
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
