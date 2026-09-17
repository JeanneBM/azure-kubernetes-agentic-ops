from __future__ import annotations

from kubernetes import client, config

from .contracts import ActionRequest, Evidence, Facts, IncidentTrigger
from .safety import ActionExecutor


class AksDiagnosticProvider:
    """Read-only AKS diagnostics using the in-cluster Kubernetes identity."""

    def __init__(self) -> None:
        config.load_incluster_config()
        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()

    def collect(self, trigger: IncidentTrigger) -> Facts:
        pod = self._core.read_namespaced_pod(trigger.pod, trigger.namespace)
        events = self._core.list_namespaced_event(
            trigger.namespace, field_selector=f"involvedObject.name={trigger.pod}"
        )
        evidence = [
            Evidence("pod-phase", pod.status.phase or "unknown", f"k8s://pod/{trigger.namespace}/{trigger.pod}"),
            Evidence(
                "pod-containers",
                self._container_states(pod),
                f"k8s://pod/{trigger.namespace}/{trigger.pod}/status",
            ),
            Evidence(
                "pod-events",
                self._events_text(events.items),
                f"k8s://events/{trigger.namespace}/{trigger.pod}",
            ),
        ]
        for container in pod.spec.containers:
            try:
                logs = self._core.read_namespaced_pod_log(
                    trigger.pod,
                    trigger.namespace,
                    container=container.name,
                    previous=True,
                    tail_lines=100,
                )
            except client.exceptions.ApiException as error:
                if error.status == 400:
                    logs = "No previous container logs available"
                else:
                    raise
            evidence.append(
                Evidence(
                    f"previous-logs/{container.name}",
                    logs or "No previous container logs available",
                    f"k8s://logs/{trigger.namespace}/{trigger.pod}/{container.name}/previous",
                )
            )
        return Facts(tuple(evidence), groundedness=1.0)

    @staticmethod
    def _container_states(pod: client.V1Pod) -> str:
        statuses = pod.status.container_statuses or []
        return "; ".join(
            f"{item.name}:ready={item.ready},restarts={item.restart_count},"
            f"state={item.state.to_dict() if item.state else 'unknown'}"
            for item in statuses
        )

    @staticmethod
    def _events_text(events: list[client.V1Event]) -> str:
        return "; ".join(
            f"{event.reason or 'unknown'}: {event.message or ''}" for event in events
        ) or "No matching events"


class AksActionExecutor(ActionExecutor):
    """Executes only actions already authorized by the orchestrator."""

    def __init__(self) -> None:
        config.load_incluster_config()
        self._core = client.CoreV1Api()
        self._apps = client.AppsV1Api()

    def execute(self, action: ActionRequest) -> None:
        namespace = action.parameters["namespace"]
        if action.name == "evict_pod":
            self._core.delete_namespaced_pod(action.parameters["pod"], namespace)
        elif action.name == "rollout_restart":
            deployment = action.parameters["deployment"]
            patch = {"spec": {"template": {"metadata": {"annotations": {
                "agentic-ops/restarted-at": action.parameters["timestamp"],
            }}}}}
            self._apps.patch_namespaced_deployment(deployment, namespace, patch)
        elif action.name == "scale":
            deployment = action.parameters["deployment"]
            replicas = int(action.parameters["replicas"])
            self._apps.patch_namespaced_deployment(
                deployment, namespace, {"spec": {"replicas": replicas}}
            )
        else:
            raise PermissionError(f"Unsupported AKS action: {action.name}")
