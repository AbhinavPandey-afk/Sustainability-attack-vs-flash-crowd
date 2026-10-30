import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import experiments.run_interleaved_experiment as run_interleaved_module
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


def test_interleaved_edos_first_001_config_is_the_opposite_phase_order():
    """Final-matrix-design session, Phase 6: the EDoS-first direction
    (audit's own "E7") was previously missing only as a CONFIG, not as a
    code capability — run_interleaved_experiment.py's phase loop is
    already generic over phase order. This config supplies that missing
    ordering without any change to the runner itself."""
    config = yaml.safe_load((REPO_ROOT / "experiments/configs/INTERLEAVED_EDOS_FIRST_001.yaml").read_text())
    phases = config["phases"]
    assert config["experiment"]["duration_seconds"] == sum(p["duration_seconds"] for p in phases)
    assert [p["label"] for p in phases] == [1, 0, 1, 0]
    assert [p["scenario_type"] for p in phases] == ["edos", "flash_crowd", "edos", "flash_crowd"]
    for phase in phases:
        assert phase["duration_seconds"] == config["detector"]["window_seconds"][0]
    # Distinct seed from INTERLEAVED_001, so the two can never collide if
    # ever run back-to-back or referenced together in the same matrix run.
    fc_first = yaml.safe_load((REPO_ROOT / "experiments/configs/INTERLEAVED_001.yaml").read_text())
    assert config["experiment"]["seed"] != fc_first["experiment"]["seed"]


# --------------------------------------------------------------------- #
# Sampler-thread cleanup on a mid-run phase failure
# (docs/experiment_protocol.md §12.2/§13) — this runner's traffic
# generation loop had NO exception handling at all before this fix, a
# real gap distinct from (and more severe than) run_experiment.py's
# original one, confirmed by direct inspection, not assumed.
# --------------------------------------------------------------------- #


class _OkResetter:
    def __init__(self, **_kwargs):
        pass

    def ensure_isolated(self, *_args, **_kwargs):
        return 1


class _OkPrometheusClient:
    """Always-reachable fake — see the identical class/rationale in
    tests/experiments/test_run_experiment.py: without this, a test
    reaching past check_host_reachable would silently depend on a real,
    live Prometheus being reachable in whatever environment the suite
    runs in, rather than being properly isolated."""

    def __init__(self, **_kwargs):
        pass

    def check_reachable(self, timeout_seconds=None):
        pass


class _RealisticStoppableSampler:
    """Mimics ReplicaSampler.sample_for's real loop-and-sleep shape so a
    test can prove the stop_event is actually honored promptly."""

    def __init__(self, **_kwargs):
        self.samples = []

    def sample_for(self, duration_seconds, interval_seconds, stop_event=None):
        end = time.time() + duration_seconds
        while time.time() < end:
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(0.01)
        return self.samples


class _RealisticSamplerThatCollectsSamples(_RealisticStoppableSampler):
    """Same stoppable shape, but actually records ReplicaSample-like
    points — needed for the happy-path test, where align_raw_dataframe/
    build_features must receive real, non-empty data to avoid crashing
    on an unrelated (pre-existing) empty-input edge case."""

    def sample_for(self, duration_seconds, interval_seconds, stop_event=None):
        from feature_engineering.collect_metrics import ReplicaSample

        end = time.time() + duration_seconds
        t = time.time()
        while time.time() < end:
            if stop_event is not None and stop_event.is_set():
                break
            self.samples.append(ReplicaSample(timestamp=time.time(), replica_count=1, cpu_utilization_pct=10.0))
            time.sleep(0.01)
        if not self.samples:
            self.samples.append(ReplicaSample(timestamp=t, replica_count=1, cpu_utilization_pct=10.0))
        return self.samples


def test_run_interleaved_experiment_stops_sampler_thread_promptly_when_a_phase_fails(tmp_path, monkeypatch):
    """A phase failing partway through must not leave the background
    replica sampler polling for the rest of total_duration.
    total_duration is deliberately large (50s across two 25s phases) —
    if the stop_event fix regressed, this test would take ~50s instead
    of returning almost immediately.
    """
    config = {
        "experiment": {"name": "INTERLEAVED_CLEANUP_TEST", "seed": 1, "duration_seconds": 50},
        "phases": [
            {"scenario_type": "flash_crowd", "scenario_file": "traffic/scenarios/flash_crowd.yaml",
             "duration_seconds": 25, "label": 0},
            {"scenario_type": "edos", "scenario_file": "traffic/scenarios/edos.yaml",
             "duration_seconds": 25, "label": 1},
        ],
        "detector": {"window_seconds": [20], "step_seconds": 20},
    }
    config_path = tmp_path / "interleaved_cleanup.yaml"
    config_path.write_text(yaml.dump(config))

    monkeypatch.setattr(run_interleaved_module, "ReplicaResetter", _OkResetter)
    monkeypatch.setattr(run_interleaved_module, "check_host_reachable", lambda host: None)
    monkeypatch.setattr(run_interleaved_module, "PrometheusClient", _OkPrometheusClient)
    monkeypatch.setattr(run_interleaved_module, "ReplicaSampler", _RealisticStoppableSampler)

    # Phase 0 "succeeds" (returncode 0), phase 1 fails.
    call_count = {"n": 0}

    def _run(cmd, cwd=None, check=False):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise subprocess.CalledProcessError(1, cmd)
        return MagicMock(returncode=0)

    monkeypatch.setattr(run_interleaved_module.subprocess, "run", _run)

    started = time.time()
    with pytest.raises(subprocess.CalledProcessError):
        run_interleaved_module.run_interleaved_experiment(config_path, host="http://localhost:8000")
    elapsed = time.time() - started

    assert call_count["n"] == 2  # phase 1 never ran after phase (index) 1 failed... i.e. only 2 phases attempted
    assert elapsed < 5.0, f"sampler thread was not stopped promptly (took {elapsed:.1f}s of a 50s total_duration)"


def test_run_interleaved_experiment_completes_normally_when_all_phases_succeed(tmp_path, monkeypatch):
    """Happy-path regression: the stop_event fix must not cut the
    sampler off early, or otherwise change behaviour, on success."""
    import pandas as pd

    config = {
        "experiment": {"name": "INTERLEAVED_HAPPY_TEST", "seed": 1, "duration_seconds": 0.06},
        "phases": [
            {"scenario_type": "flash_crowd", "scenario_file": "traffic/scenarios/flash_crowd.yaml",
             "duration_seconds": 0.03, "label": 0},
            {"scenario_type": "edos", "scenario_file": "traffic/scenarios/edos.yaml",
             "duration_seconds": 0.03, "label": 1},
        ],
        "detector": {"window_seconds": [20], "step_seconds": 20},
    }
    config_path = tmp_path / "interleaved_happy.yaml"
    config_path.write_text(yaml.dump(config))

    monkeypatch.setattr(run_interleaved_module, "ReplicaResetter", _OkResetter)
    monkeypatch.setattr(run_interleaved_module, "check_host_reachable", lambda host: None)
    monkeypatch.setattr(run_interleaved_module, "ReplicaSampler", _RealisticSamplerThatCollectsSamples)
    # Also used internally by git_commit()'s own subprocess.run call —
    # give it a real string stdout so json.dumps(metadata) doesn't choke
    # on a MagicMock.
    monkeypatch.setattr(
        run_interleaved_module.subprocess, "run", lambda *a, **k: MagicMock(returncode=0, stdout="fakecommit\n")
    )

    counter_columns = [
        "request_count", "error_count", "cheap_count", "medium_count", "expensive_count",
        "cache_hits", "cache_misses", "conversions", "active_sessions",
        "session_duration_sum", "session_duration_count",
    ]

    class _FakePrometheusClient:
        def __init__(self, **_kwargs):
            pass

        def check_reachable(self, timeout_seconds=None):
            pass  # fake Prometheus is always reachable in this happy-path test

        def collect_app_metrics(self, start, end, step_seconds):
            return {
                name: pd.DataFrame({"timestamp": [start, end], "value": [0.0, 1.0]}) for name in counter_columns
            }

    monkeypatch.setattr(run_interleaved_module, "PrometheusClient", _FakePrometheusClient)

    metadata = run_interleaved_module.run_interleaved_experiment(
        config_path, host="http://localhost:8000", output_features_dir=tmp_path / "features"
    )

    assert metadata["experiment_id"] == "INTERLEAVED_HAPPY_TEST"
    assert len(metadata["phases"]) == 2


def test_run_interleaved_experiment_aborts_before_any_phase_when_prometheus_unreachable(tmp_path, monkeypatch):
    """(E, interleaved path) Prometheus preflight must abort BEFORE any
    phase's traffic starts — isolation and /healthz both succeed
    (mocked), Prometheus is down, and NO subprocess.run call for any
    phase must ever happen."""
    from feature_engineering.collect_metrics import PrometheusUnreachableError

    config = {
        "experiment": {"name": "INTERLEAVED_PROM_FAIL", "seed": 1, "duration_seconds": 20},
        "phases": [
            {"scenario_type": "flash_crowd", "scenario_file": "traffic/scenarios/flash_crowd.yaml",
             "duration_seconds": 10, "label": 0},
            {"scenario_type": "edos", "scenario_file": "traffic/scenarios/edos.yaml",
             "duration_seconds": 10, "label": 1},
        ],
        "detector": {"window_seconds": [10], "step_seconds": 10},
    }
    config_path = tmp_path / "interleaved_prom_fail.yaml"
    config_path.write_text(yaml.dump(config))

    monkeypatch.setattr(run_interleaved_module, "ReplicaResetter", _OkResetter)
    monkeypatch.setattr(run_interleaved_module, "check_host_reachable", lambda host: None)

    class _FailingPrometheusClient:
        def __init__(self, **_kwargs):
            pass

        def check_reachable(self, timeout_seconds=None):
            raise PrometheusUnreachableError("simulated: prometheus down before any interleaved phase")

    monkeypatch.setattr(run_interleaved_module, "PrometheusClient", _FailingPrometheusClient)
    run_mock = MagicMock()
    monkeypatch.setattr(run_interleaved_module.subprocess, "run", run_mock)

    with pytest.raises(PrometheusUnreachableError, match="prometheus down"):
        run_interleaved_module.run_interleaved_experiment(config_path, host="http://localhost:8000")

    run_mock.assert_not_called()
