"""Phase 4 static tests: scenario YAML shape and locustfile.py generator
dispatch. No live server or cluster required — no HTTP requests are made,
only Locust User classes are constructed and inspected.
"""
import importlib.util
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCUSTFILE = REPO_ROOT / "traffic" / "locustfile.py"

SCENARIOS = [
    "traffic/scenarios/normal.yaml",
    "traffic/scenarios/flash_crowd.yaml",
    "traffic/scenarios/edos.yaml",
    "traffic/scenarios/flash_crowd_viral.yaml",
]


def _load_locustfile(relative_path: str, monkeypatch):
    monkeypatch.setenv("CASCADE_SCENARIO", relative_path)
    module_name = "_cascade_locustfile_" + relative_path.replace("/", "_").replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("relative_path", SCENARIOS)
def test_scenario_yaml_has_required_fields(relative_path):
    config = yaml.safe_load((REPO_ROOT / relative_path).read_text())
    assert config["scenario"]["name"]
    assert config["scenario"]["type"] in {"normal", "flash_crowd", "edos", "mixed"}
    assert config["locust"]["users"] > 0
    assert config["locust"]["spawn_rate"] > 0
    assert config["locust"]["run_time_seconds"] > 0
    assert "weights" in config["behavior"]


@pytest.mark.parametrize("relative_path", SCENARIOS)
def test_locustfile_builds_nonempty_task_set_for_each_scenario(relative_path, monkeypatch):
    module = _load_locustfile(relative_path, monkeypatch)
    assert module.CascadeUser.tasks
    assert all(weight > 0 for weight in module.CascadeUser.tasks.values())


def test_edos_scenario_concentrates_on_expensive_endpoint():
    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/edos.yaml").read_text())
    weights = config["behavior"]["weights"]
    assert weights.get("generate_report", 0) > 0
    assert weights.get("home", 0) == 0
    assert weights.get("search", 0) == 0


def test_flash_crowd_scenario_uses_diverse_endpoints():
    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd.yaml").read_text())
    weights = config["behavior"]["weights"]
    nonzero = [k for k, v in weights.items() if v > 0]
    assert len(nonzero) >= 2, "flash_crowd should hit more than one endpoint class"


def test_edos_uses_fewer_users_than_flash_crowd():
    """CLAUDE.md section 11: EDoS 'can use fewer simulated clients'."""
    edos = yaml.safe_load((REPO_ROOT / "traffic/scenarios/edos.yaml").read_text())
    flash = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd.yaml").read_text())
    assert edos["locust"]["users"] < flash["locust"]["users"]


def test_edos_and_flash_crowd_scenario_generators_tag_requests_with_scenario_name(monkeypatch):
    """The X-Scenario header set in on_start must match the scenario's own
    name, so app_conversion_total / http_requests_total etc. can later be
    sliced per scenario (CLAUDE.md section 7)."""
    for relative_path, expected_name in [
        ("traffic/scenarios/flash_crowd.yaml", "flash_crowd"),
        ("traffic/scenarios/edos.yaml", "edos"),
    ]:
        module = _load_locustfile(relative_path, monkeypatch)
        assert module._scenario["name"] == expected_name


def test_unknown_scenario_type_raises(tmp_path, monkeypatch):
    bad_scenario = tmp_path / "bad.yaml"
    bad_scenario.write_text(
        "scenario:\n  name: bad\n  type: not_a_real_type\nlocust:\n  users: 1\nbehavior:\n  weights: {}\n"
    )
    monkeypatch.setenv("CASCADE_SCENARIO", str(bad_scenario))
    spec = importlib.util.spec_from_file_location("_cascade_locustfile_bad", LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(ValueError, match="Unknown scenario type"):
        spec.loader.exec_module(module)


def test_run_scenario_script_exists_and_is_executable_python():
    script = REPO_ROOT / "traffic" / "run_scenario.py"
    assert script.is_file()
    content = script.read_text(encoding="utf-8")
    assert "argparse" in content
    assert "data" in content and "raw" in content  # writes telemetry under data/raw/
