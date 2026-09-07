"""Unit tests for the E3 (simultaneous mixed) traffic generator —
traffic/generators/mixed.py — and its scenario YAML. No live server or
cluster required.
"""
import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCUSTFILE = REPO_ROOT / "traffic" / "locustfile.py"


def _load_locustfile(monkeypatch):
    monkeypatch.setenv("CASCADE_SCENARIO", "traffic/scenarios/mixed.yaml")
    spec = importlib.util.spec_from_file_location("_cascade_locustfile_mixed", LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mixed_scenario_yaml_has_both_sub_scenarios():
    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/mixed.yaml").read_text())
    assert config["scenario"]["type"] == "mixed"
    assert config["flash_crowd"]["users"] > 0
    assert config["edos"]["users"] > 0
    assert config["locust"]["users"] == config["flash_crowd"]["users"] + config["edos"]["users"]


def test_build_user_classes_returns_two_distinct_classes():
    from traffic.generators.mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/mixed.yaml").read_text())
    fc_cls, edos_cls = build_user_classes(config["scenario"], config)
    assert fc_cls is not edos_cls
    assert fc_cls.tasks
    assert edos_cls.tasks


def test_build_user_classes_sets_weight_from_configured_user_counts():
    from traffic.generators.mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/mixed.yaml").read_text())
    fc_cls, edos_cls = build_user_classes(config["scenario"], config)
    assert fc_cls.weight == config["flash_crowd"]["users"]
    assert edos_cls.weight == config["edos"]["users"]


def test_locustfile_exposes_both_user_classes_for_mixed_scenario(monkeypatch):
    module = _load_locustfile(monkeypatch)
    assert hasattr(module, "FlashCrowdUser")
    assert hasattr(module, "EdosUser")
    assert not hasattr(module, "CascadeUser")
    assert module.FlashCrowdUser.tasks
    assert module.EdosUser.tasks


class _FakeClient:
    def __init__(self):
        self.headers: dict = {}


def test_mixed_generator_tags_requests_with_own_scenario_names():
    from traffic.generators.mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/mixed.yaml").read_text())
    fc_cls, edos_cls = build_user_classes(config["scenario"], config)

    fc_instance = fc_cls.__new__(fc_cls)
    fc_instance.client = _FakeClient()
    fc_cls.on_start(fc_instance)
    assert fc_instance.client.headers.get("X-Scenario") == "flash_crowd"

    edos_instance = edos_cls.__new__(edos_cls)
    edos_instance.client = _FakeClient()
    edos_cls.on_start(edos_instance)
    assert edos_instance.client.headers.get("X-Scenario") == "edos"
