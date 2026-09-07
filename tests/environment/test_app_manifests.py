"""Static/unit tests for the Phase 3 Kubernetes manifests (app + HPA +
Prometheus). No cluster required — pure YAML/structure checks.
"""
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

MANIFESTS = [
    "kubernetes/namespace.yaml",
    "kubernetes/app-deployment.yaml",
    "kubernetes/app-service.yaml",
    "kubernetes/hpa.yaml",
    "kubernetes/prometheus/rbac.yaml",
    "kubernetes/prometheus/config.yaml",
    "kubernetes/prometheus/deployment.yaml",
    "kubernetes/prometheus/service.yaml",
]


def _load_all(relative_path):
    text = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
    return [doc for doc in yaml.safe_load_all(text) if doc]


@pytest.mark.parametrize("relative_path", MANIFESTS)
def test_manifest_is_valid_yaml(relative_path):
    docs = _load_all(relative_path)
    assert docs, f"{relative_path} produced no YAML documents"
    for doc in docs:
        assert "apiVersion" in doc
        assert "kind" in doc
        assert doc.get("metadata", {}).get("name")


def test_namespace_is_cascade():
    doc = _load_all("kubernetes/namespace.yaml")[0]
    assert doc["kind"] == "Namespace"
    assert doc["metadata"]["name"] == "cascade"


def test_app_deployment_targets_cascade_namespace_and_has_cpu_request():
    doc = _load_all("kubernetes/app-deployment.yaml")[0]
    assert doc["kind"] == "Deployment"
    assert doc["metadata"]["namespace"] == "cascade"
    container = doc["spec"]["template"]["spec"]["containers"][0]
    # HPA cannot compute CPU utilization without a request.
    assert "cpu" in container["resources"]["requests"]
    assert container["imagePullPolicy"] == "IfNotPresent"


def test_app_deployment_pod_template_has_prometheus_scrape_annotations():
    doc = _load_all("kubernetes/app-deployment.yaml")[0]
    annotations = doc["spec"]["template"]["metadata"]["annotations"]
    assert annotations["prometheus.io/scrape"] == "true"
    assert annotations["prometheus.io/port"] == "8000"


def test_app_service_is_cluster_ip_only():
    doc = _load_all("kubernetes/app-service.yaml")[0]
    assert doc["kind"] == "Service"
    assert doc["metadata"]["namespace"] == "cascade"
    assert doc["spec"].get("type", "ClusterIP") == "ClusterIP"


def test_hpa_targets_cascade_app_deployment():
    doc = _load_all("kubernetes/hpa.yaml")[0]
    assert doc["kind"] == "HorizontalPodAutoscaler"
    assert doc["spec"]["scaleTargetRef"]["name"] == "cascade-app"
    assert doc["spec"]["minReplicas"] >= 1
    assert doc["spec"]["maxReplicas"] > doc["spec"]["minReplicas"]


def test_prometheus_rbac_is_namespace_scoped_not_cluster_wide():
    docs = _load_all("kubernetes/prometheus/rbac.yaml")
    kinds = {doc["kind"] for doc in docs}
    assert "Role" in kinds
    assert "ClusterRole" not in kinds
    for doc in docs:
        if doc["kind"] in ("Role", "RoleBinding", "ServiceAccount"):
            assert doc["metadata"]["namespace"] == "cascade"


def test_prometheus_config_scrape_job_targets_cascade_namespace():
    doc = _load_all("kubernetes/prometheus/config.yaml")[0]
    assert doc["kind"] == "ConfigMap"
    prometheus_yml = yaml.safe_load(doc["data"]["prometheus.yml"])
    job = prometheus_yml["scrape_configs"][0]
    sd_config = job["kubernetes_sd_configs"][0]
    assert sd_config["namespaces"]["names"] == ["cascade"]


def test_prometheus_service_is_cluster_ip_only():
    doc = _load_all("kubernetes/prometheus/service.yaml")[0]
    assert doc["spec"].get("type", "ClusterIP") == "ClusterIP"


def test_deploy_scripts_exist_and_have_defensive_settings():
    sh = REPO_ROOT / "scripts/deploy-app.sh"
    ps1 = REPO_ROOT / "scripts/deploy-app.ps1"
    assert sh.is_file()
    assert ps1.is_file()
    assert "set -euo pipefail" in sh.read_text(encoding="utf-8")
    assert "$ErrorActionPreference" in ps1.read_text(encoding="utf-8")
