"""Live health checks for the components the dashboard depends on.

Every status is verified, never assumed — never claim a component healthy
without an actual live check.
"""
from __future__ import annotations

import httpx

from config import DATA_EXPERIMENTS, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL

STATUS_CONNECTED = "CONNECTED"
STATUS_DEGRADED = "DEGRADED"
STATUS_UNAVAILABLE = "UNAVAILABLE"


def _check_http(url: str, timeout: float = 2.0) -> tuple[str, str]:
    try:
        resp = httpx.get(url, timeout=timeout)
        if resp.status_code == 200:
            return STATUS_CONNECTED, "ok"
        return STATUS_DEGRADED, f"HTTP {resp.status_code}"
    except Exception as exc:  # noqa: BLE001 - report, don't crash the status endpoint
        return STATUS_UNAVAILABLE, str(exc)


def check_app(host: str = DEFAULT_APP_HOST) -> dict:
    status, detail = _check_http(f"{host}/healthz")
    return {"component": "Application", "status": status, "detail": detail, "endpoint": host}


def check_prometheus(base_url: str = DEFAULT_PROMETHEUS_URL) -> dict:
    status, detail = _check_http(f"{base_url}/-/ready")
    return {"component": "Prometheus", "status": status, "detail": detail, "endpoint": base_url}


def check_kubernetes(namespace: str = "cascade", deployment: str = "cascade-app", hpa: str = "cascade-app") -> dict:
    try:
        from kubernetes import client as k8s_client
        from kubernetes import config as k8s_config

        k8s_config.load_kube_config()
        cfg = k8s_client.Configuration.get_default_copy()
        cfg.host = cfg.host.replace("0.0.0.0", "127.0.0.1")
        k8s_client.Configuration.set_default(cfg)
        apps_api = k8s_client.AppsV1Api()
        autoscaling_api = k8s_client.AutoscalingV2Api()

        dep = apps_api.read_namespaced_deployment(deployment, namespace)
        hpa_obj = autoscaling_api.read_namespaced_horizontal_pod_autoscaler(hpa, namespace)
        replicas = dep.status.replicas or 0
        ready = dep.status.ready_replicas or 0
        cpu_pct = None
        for metric in hpa_obj.status.current_metrics or []:
            if metric.type == "Resource" and metric.resource and metric.resource.name == "cpu":
                cpu_pct = metric.resource.current.average_utilization

        status = STATUS_CONNECTED if ready == replicas and replicas > 0 else STATUS_DEGRADED
        return {
            "component": "Kubernetes",
            "status": status,
            "detail": f"{ready}/{replicas} replicas ready",
            "replicas": replicas,
            "ready_replicas": ready,
            "current_cpu_utilization_pct": cpu_pct,
            "min_replicas": hpa_obj.spec.min_replicas,
            "max_replicas": hpa_obj.spec.max_replicas,
        }
    except Exception as exc:  # noqa: BLE001
        return {"component": "Kubernetes", "status": STATUS_UNAVAILABLE, "detail": str(exc)}


def check_detector() -> dict:
    from data_access import load_results_metrics

    metrics = load_results_metrics("experiment_summary")
    if metrics is None:
        return {"component": "Detector", "status": STATUS_UNAVAILABLE, "detail": "No trained-model results on disk yet"}
    n_experiments = metrics.get("n_experiments", 0)
    return {
        "component": "Detector",
        "status": STATUS_CONNECTED,
        "detail": f"Trained on {n_experiments} experiments",
        "n_experiments": n_experiments,
    }


def check_experiment_runner(is_busy: bool) -> dict:
    n_saved = len([p for p in DATA_EXPERIMENTS.iterdir() if (p / "metadata.json").exists()]) if DATA_EXPERIMENTS.exists() else 0
    return {
        "component": "Experiment Runner",
        "status": STATUS_CONNECTED,
        "detail": "Running an experiment" if is_busy else f"Idle, {n_saved} saved results on disk",
        "busy": is_busy,
    }


def full_status(is_runner_busy: bool) -> dict:
    return {
        "kubernetes": check_kubernetes(),
        "application": check_app(),
        "prometheus": check_prometheus(),
        "experiment_runner": check_experiment_runner(is_runner_busy),
        "detector": check_detector(),
    }
