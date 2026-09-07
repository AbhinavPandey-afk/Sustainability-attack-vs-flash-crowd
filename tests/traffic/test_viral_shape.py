"""Pure unit tests for the viral-event arrival-curve shape (no Locust
runtime / live infra needed) — traffic/generators/viral_shape.py.
"""
from pathlib import Path

import yaml

from traffic.generators.viral_shape import phase_boundaries, total_duration, users_at

REPO_ROOT = Path(__file__).resolve().parents[2]

SHAPE_CFG = {
    "trickle_users": 5,
    "trickle_seconds": 10,
    "ramp_seconds": 25,
    "peak_users": 50,
    "peak_seconds": 30,
    "decay_seconds": 25,
    "decay_floor_users": 10,
    "ramp_steepness": 10.0,
}


def test_phase_boundaries_are_cumulative():
    t1, t2, t3, t4 = phase_boundaries(SHAPE_CFG)
    assert t1 == 10
    assert t2 == 35
    assert t3 == 65
    assert t4 == 90
    assert total_duration(SHAPE_CFG) == 90


def test_trickle_phase_is_flat_and_low():
    for elapsed in (0, 5, 9.9):
        assert users_at(elapsed, SHAPE_CFG) == SHAPE_CFG["trickle_users"]


def test_ramp_phase_is_monotonically_increasing_and_bounded():
    samples = [users_at(t, SHAPE_CFG) for t in range(10, 36, 2)]
    assert all(a <= b + 1e-9 for a, b in zip(samples, samples[1:])), "ramp must not decrease"
    assert samples[0] >= SHAPE_CFG["trickle_users"] - 1e-6
    assert samples[-1] <= SHAPE_CFG["peak_users"] + 1e-6


def test_ramp_starts_near_trickle_and_ends_near_peak():
    just_after_ramp_start = users_at(10.5, SHAPE_CFG)
    just_before_ramp_end = users_at(34.5, SHAPE_CFG)
    assert just_after_ramp_start < SHAPE_CFG["peak_users"] / 2
    assert just_before_ramp_end > SHAPE_CFG["peak_users"] / 2


def test_peak_phase_holds_at_peak_users():
    for elapsed in (35, 50, 64.9):
        assert users_at(elapsed, SHAPE_CFG) == SHAPE_CFG["peak_users"]


def test_decay_phase_decreases_toward_floor():
    samples = [users_at(t, SHAPE_CFG) for t in range(65, 90, 3)]
    assert all(a >= b - 1e-9 for a, b in zip(samples, samples[1:])), "decay must not increase"
    assert samples[0] <= SHAPE_CFG["peak_users"] + 1e-6
    assert samples[-1] >= SHAPE_CFG["decay_floor_users"] - 1e-6


def test_returns_none_past_total_duration():
    assert users_at(90, SHAPE_CFG) is None
    assert users_at(150, SHAPE_CFG) is None


def test_flash_crowd_viral_scenario_yaml_defines_a_consistent_shape():
    config = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd_viral.yaml").read_text())
    assert config["scenario"]["type"] == "flash_crowd"
    shape_cfg = config["locust"]["arrival_shape"]
    assert total_duration(shape_cfg) == config["locust"]["run_time_seconds"]


def test_flash_crowd_viral_shares_behaviour_with_flash_crowd():
    viral = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd_viral.yaml").read_text())
    plain = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd.yaml").read_text())
    assert viral["behavior"]["weights"] == plain["behavior"]["weights"]
