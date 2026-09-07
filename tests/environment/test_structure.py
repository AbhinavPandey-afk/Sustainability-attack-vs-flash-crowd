"""Static/unit tests for the Phase 1 repository scaffold.

These tests do NOT require Docker, k3d, kubectl, or a running cluster.
They only check that the expected files exist and that the Kubernetes
manifests are syntactically valid YAML with the expected shape.

Live-cluster behaviour is covered separately in test_live_cluster.py,
which is marked with pytest.mark.live and excluded by default.
"""
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

REQUIRED_ROOT_FILES = [
    "CLAUDE.md",
    "README.md",
    ".gitignore",
    ".env.example",
]

REQUIRED_BASH_SCRIPTS = [
    "scripts/setup-cluster.sh",
    "scripts/delete-cluster.sh",
    "scripts/cluster-status.sh",
    "scripts/smoke-test.sh",
]

REQUIRED_PS_SCRIPTS = [
    "scripts/setup-cluster.ps1",
    "scripts/delete-cluster.ps1",
    "scripts/cluster-status.ps1",
    "scripts/smoke-test.ps1",
]

REQUIRED_MANIFESTS = [
    "kubernetes/smoke-test/namespace.yaml",
    "kubernetes/smoke-test/deployment.yaml",
    "kubernetes/smoke-test/service.yaml",
]

REQUIRED_DOCS = [
    "docs/environment.md",
]


@pytest.mark.parametrize("relative_path", REQUIRED_ROOT_FILES)
def test_root_file_exists(relative_path):
    assert (REPO_ROOT / relative_path).is_file(), f"Missing required file: {relative_path}"


@pytest.mark.parametrize("relative_path", REQUIRED_BASH_SCRIPTS)
def test_bash_script_exists(relative_path):
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"Missing required script: {relative_path}"
    content = path.read_text(encoding="utf-8")
    assert content.startswith("#!/usr/bin/env bash"), f"{relative_path} must have a bash shebang"
    assert "set -euo pipefail" in content, f"{relative_path} should use defensive bash settings"


@pytest.mark.parametrize("relative_path", REQUIRED_PS_SCRIPTS)
def test_powershell_script_exists(relative_path):
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"Missing required script: {relative_path}"
    content = path.read_text(encoding="utf-8")
    assert "$ErrorActionPreference" in content, f"{relative_path} should set $ErrorActionPreference"


@pytest.mark.parametrize("relative_path", REQUIRED_MANIFESTS)
def test_manifest_is_valid_yaml(relative_path):
    path = REPO_ROOT / relative_path
    assert path.is_file(), f"Missing required manifest: {relative_path}"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(doc, dict)
    assert "apiVersion" in doc
    assert "kind" in doc
    assert doc.get("metadata", {}).get("name")


def test_smoke_test_namespace_is_dedicated():
    path = REPO_ROOT / "kubernetes/smoke-test/namespace.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["kind"] == "Namespace"
    assert doc["metadata"]["name"] == "cascade-test"


def test_smoke_test_deployment_targets_dedicated_namespace():
    path = REPO_ROOT / "kubernetes/smoke-test/deployment.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["kind"] == "Deployment"
    assert doc["metadata"]["namespace"] == "cascade-test"
    assert doc["spec"]["replicas"] <= 2, "Smoke-test deployment should stay small"
    containers = doc["spec"]["template"]["spec"]["containers"]
    assert len(containers) == 1
    assert "image" in containers[0]


def test_smoke_test_service_is_not_publicly_exposed():
    path = REPO_ROOT / "kubernetes/smoke-test/service.yaml"
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert doc["kind"] == "Service"
    assert doc["metadata"]["namespace"] == "cascade-test"
    service_type = doc["spec"].get("type", "ClusterIP")
    assert service_type == "ClusterIP", "Smoke-test service must not use NodePort/LoadBalancer by default"


@pytest.mark.parametrize("relative_path", REQUIRED_DOCS)
def test_docs_exist(relative_path):
    assert (REPO_ROOT / relative_path).is_file(), f"Missing required doc: {relative_path}"


def test_environment_doc_does_not_claim_future_phase_functionality():
    path = REPO_ROOT / "docs/environment.md"
    content = path.read_text(encoding="utf-8").lower()
    forbidden_claims = [
        "prometheus monitors the application",
        "hpa is scaling the application",
        "lightgbm is trained",
    ]
    for claim in forbidden_claims:
        assert claim not in content, f"docs/environment.md should not claim: {claim}"


def test_readme_has_phase1_status_section():
    path = REPO_ROOT / "README.md"
    content = path.read_text(encoding="utf-8")
    assert re.search(r"phase\s*1", content, re.IGNORECASE), "README must document Phase 1 status"


def test_gitignore_excludes_local_artifacts():
    path = REPO_ROOT / ".gitignore"
    content = path.read_text(encoding="utf-8")
    for pattern in [".env", "__pycache__", ".venv"]:
        assert pattern in content


def test_env_example_defines_cluster_name():
    path = REPO_ROOT / ".env.example"
    content = path.read_text(encoding="utf-8")
    assert "CASCADE_CLUSTER_NAME" in content
