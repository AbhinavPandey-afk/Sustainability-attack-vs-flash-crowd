from pathlib import Path

import yaml

from experiments.run_interleaved_experiment import label_for_timestamp

REPO_ROOT = Path(__file__).resolve().parents[2]

PHASE_SCHEDULE = [
    {"index": 0, "scenario_type": "flash_crowd", "label": 0, "start": 100.0, "end": 120.0},
    {"index": 1, "scenario_type": "edos", "label": 1, "start": 120.0, "end": 140.0},
    {"index": 2, "scenario_type": "flash_crowd", "label": 0, "start": 140.0, "end": 160.0},
    {"index": 3, "scenario_type": "edos", "label": 1, "start": 160.0, "end": 180.0},
]


def test_timestamp_inside_a_phase_gets_that_phase_label():
    assert label_for_timestamp(110.0, PHASE_SCHEDULE) == 0
    assert label_for_timestamp(130.0, PHASE_SCHEDULE) == 1
    assert label_for_timestamp(150.0, PHASE_SCHEDULE) == 0
    assert label_for_timestamp(170.0, PHASE_SCHEDULE) == 1


def test_timestamp_before_first_phase_falls_back_to_first_phase():
    assert label_for_timestamp(50.0, PHASE_SCHEDULE) == 0


def test_timestamp_after_last_phase_falls_back_to_last_phase():
    assert label_for_timestamp(250.0, PHASE_SCHEDULE) == 1


def test_timestamp_exactly_on_a_boundary_resolves_unambiguously():
    # 120.0 is the end of phase 0 AND the start of phase 1 — the first
    # matching phase in schedule order wins (phase 0).
    assert label_for_timestamp(120.0, PHASE_SCHEDULE) == 0


def test_all_windows_of_a_realistic_20s_schedule_map_correctly():
    """Mirrors INTERLEAVED_001.yaml: four 20s phases, one 20s feature
    window per phase — every window_end should land inside exactly the
    phase it was generated during."""
    schedule = [
        {"index": i, "scenario_type": "x", "label": i % 2 != 0 and 1 or 0, "start": 1000.0 + i * 20, "end": 1000.0 + (i + 1) * 20}
        for i in range(4)
    ]
    window_ends = [1000.0 + (i + 1) * 20 - 0.5 for i in range(4)]  # just inside each phase
    labels = [label_for_timestamp(t, schedule) for t in window_ends]
    assert labels == [0, 1, 0, 1]


def test_interleaved_001_config_duration_matches_sum_of_phases():
    config = yaml.safe_load((REPO_ROOT / "experiments/configs/INTERLEAVED_001.yaml").read_text())
    phases = config["phases"]
    assert config["experiment"]["duration_seconds"] == sum(p["duration_seconds"] for p in phases)
    assert [p["label"] for p in phases] == [0, 1, 0, 1]
    for phase in phases:
        assert phase["duration_seconds"] == config["detector"]["window_seconds"][0]
