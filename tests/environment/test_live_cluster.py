"""Live-cluster tests for Phase 1.

These tests require Docker, k3d, kubectl, AND a running "cascade" cluster
(created via scripts/setup-cluster.sh or scripts/setup-cluster.ps1).

They are marked `live` and are EXCLUDED from the default `pytest` run
(see pytest.ini: `addopts = -m "not live"`).

Run them explicitly with:

    pytest -m live tests/environment/test_live_cluster.py
"""
import json
import os
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.live

CLUSTER_NAME = os.environ.get("CASCADE_CLUSTER_NAME", "cascade")
NAMESPACE = os.environ.get("CASCADE_TEST_NAMESPACE", "cascade-test")


def _kubectl_available():
    return shutil.which("kubectl") is not None


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


@pytest.mark.skipif(not _kubectl_available(), reason="kubectl not installed")
def test_nodes_are_ready():
    result = _run(["kubectl", "get", "nodes", "-o", "json"])
    assert result.returncode == 0, result.stderr
    nodes = json.loads(result.stdout)["items"]
    assert len(nodes) >= 1, "Expected at least one node"
    for node in nodes:
        conditions = {c["type"]: c["status"] for c in node["status"]["conditions"]}
        assert conditions.get("Ready") == "True", f"Node {node['metadata']['name']} is not Ready"


@pytest.mark.skipif(not _kubectl_available(), reason="kubectl not installed")
def test_smoke_test_namespace_exists():
    result = _run(["kubectl", "get", "namespace", NAMESPACE])
    assert result.returncode == 0, (
        f"Namespace '{NAMESPACE}' not found. Run scripts/smoke-test.sh first."
    )


@pytest.mark.skipif(not _kubectl_available(), reason="kubectl not installed")
def test_smoke_test_deployment_is_available():
    result = _run([
        "kubectl", "-n", NAMESPACE, "get", "deployment", "smoke-test", "-o", "json"
    ])
    assert result.returncode == 0, (
        "smoke-test deployment not found. Run scripts/smoke-test.sh first."
    )
    deployment = json.loads(result.stdout)
    status = deployment.get("status", {})
    assert status.get("readyReplicas", 0) >= 1


@pytest.mark.skipif(not _kubectl_available(), reason="kubectl not installed")
def test_smoke_test_service_exists():
    result = _run(["kubectl", "-n", NAMESPACE, "get", "svc", "smoke-test"])
    assert result.returncode == 0, "smoke-test service not found."
