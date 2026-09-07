"""Builds ad-hoc scenario + experiment config YAML pairs from user-supplied
Attack Simulator / Flash Crowd Simulator parameters.

A generated pair is written in exactly the same shape as a hand-authored
preset (experiments/configs/EDOS_001.yaml + traffic/scenarios/edos.yaml) —
so the rest of the pipeline (experiments/run_experiment.py,
traffic/run_scenario.py, traffic/locustfile.py) runs completely unchanged. A
generated config is indistinguishable on disk from a preset one.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

import yaml

from config import DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, REPO_ROOT

GENERATED_SCENARIOS_DIR = REPO_ROOT / "traffic" / "scenarios" / "generated"
GENERATED_CONFIGS_DIR = REPO_ROOT / "experiments" / "configs" / "generated"

USERS_RANGE = (1, 200)
DURATION_RANGE = (10, 300)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _window_seconds(duration_seconds: int) -> int:
    return int(max(10, min(20, duration_seconds // 2)))


def _timestamp_id(prefix: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return f"{prefix}_{now.strftime('%Y%m%dT%H%M%S')}{now.microsecond // 1000:03d}Z"


def _write_experiment_config(experiment_id: str, label: int, scenario_type: str, scenario_path: Path, duration_seconds: int) -> Path:
    window = _window_seconds(duration_seconds)
    config: dict[str, Any] = {
        "experiment": {
            "name": experiment_id,
            "label": label,
            "scenario_type": scenario_type,
            "scenario_file": str(scenario_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "duration_seconds": duration_seconds,
            "seed": 42,
        },
        "detector": {"window_seconds": [window], "step_seconds": window},
        "cost_model": {"replica_cost_per_minute": 1.0, "cpu_cost_weight": 0.0, "memory_cost_weight": 0.0},
        "replica_sampler": {
            "interval_seconds": 5,
            "namespace": "cascade",
            "deployment": "cascade-app",
            "hpa": "cascade-app",
        },
        "prometheus": {"base_url": DEFAULT_PROMETHEUS_URL},
    }
    GENERATED_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    config_path = GENERATED_CONFIGS_DIR / f"{experiment_id}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    return config_path


def build_flash_crowd_config(params: dict[str, Any]) -> tuple[str, Path]:
    users = int(_clamp(float(params.get("users") or 50), *USERS_RANGE))
    spawn_rate = float(_clamp(float(params.get("spawn_rate") or max(1, users // 5)), 1, users))
    duration_seconds = int(_clamp(float(params.get("duration_seconds") or 60), *DURATION_RANGE))
    think_time_min = float(_clamp(float(params.get("think_time_min") or 0.3), 0.01, 10))
    think_time_max = float(_clamp(float(params.get("think_time_max") or 1.5), think_time_min, 15))
    weight_home = int(_clamp(float(params.get("weight_home") if params.get("weight_home") is not None else 3), 0, 100))
    weight_search = int(_clamp(float(params.get("weight_search") if params.get("weight_search") is not None else 5), 0, 100))
    weight_checkout = int(_clamp(float(params.get("weight_checkout") if params.get("weight_checkout") is not None else 1), 0, 100))

    experiment_id = _timestamp_id("ADHOC_FC")
    scenario: dict[str, Any] = {
        "scenario": {
            "name": experiment_id,
            "type": "flash_crowd",
            "description": "Ad-hoc Flash Crowd Simulator run (webapp)",
        },
        "locust": {
            "users": users,
            "spawn_rate": spawn_rate,
            "run_time_seconds": duration_seconds,
            "host": DEFAULT_APP_HOST,
        },
        "behavior": {
            "think_time_min": think_time_min,
            "think_time_max": think_time_max,
            "search_terms": ["laptop", "phone", "shoes", "book", "camera", "headphones", "monitor"],
            "weights": {"home": weight_home, "search": weight_search, "checkout": weight_checkout},
        },
    }
    GENERATED_SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenario_path = GENERATED_SCENARIOS_DIR / f"{experiment_id}.yaml"
    scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False))

    config_path = _write_experiment_config(
        experiment_id, label=0, scenario_type="flash_crowd", scenario_path=scenario_path, duration_seconds=duration_seconds
    )
    return experiment_id, config_path


def build_attack_config(params: dict[str, Any]) -> tuple[str, Path]:
    users = int(_clamp(float(params.get("users") or 8), *USERS_RANGE))
    spawn_rate = float(_clamp(float(params.get("spawn_rate") or users), 1, users))
    duration_seconds = int(_clamp(float(params.get("duration_seconds") or 60), *DURATION_RANGE))
    think_time_min = float(_clamp(float(params.get("think_time_min") or 0.05), 0.01, 10))
    think_time_max = float(_clamp(float(params.get("think_time_max") or 0.2), think_time_min, 15))
    report_complexity = int(_clamp(float(params.get("report_complexity") or 60), 1, 100))

    experiment_id = _timestamp_id("ADHOC_ATTACK")
    scenario: dict[str, Any] = {
        "scenario": {
            "name": experiment_id,
            "type": "edos",
            "description": "Ad-hoc Attack Simulator run (webapp)",
        },
        "locust": {
            "users": users,
            "spawn_rate": spawn_rate,
            "run_time_seconds": duration_seconds,
            "host": DEFAULT_APP_HOST,
        },
        "behavior": {
            "think_time_min": think_time_min,
            "think_time_max": think_time_max,
            "report_complexity": report_complexity,
            "weights": {"generate_report": 10, "checkout": 0},
        },
    }
    GENERATED_SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenario_path = GENERATED_SCENARIOS_DIR / f"{experiment_id}.yaml"
    scenario_path.write_text(yaml.safe_dump(scenario, sort_keys=False))

    config_path = _write_experiment_config(
        experiment_id, label=1, scenario_type="edos", scenario_path=scenario_path, duration_seconds=duration_seconds
    )
    return experiment_id, config_path
