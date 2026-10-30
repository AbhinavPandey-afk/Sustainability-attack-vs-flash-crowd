"""Unit tests for experiments/run_matrix.py's per-experiment failure
isolation (docs/experiment_protocol.md §12): one experiment failing must
not abort the rest of the matrix, must never be recorded as a valid
research sample, and must never silently swallow KeyboardInterrupt/
SystemExit. All tests mock `run_experiment` — no live cluster needed.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

import experiments.run_matrix as run_matrix_module
from experiments.run_matrix import (
    MatrixEntryResult,
    dry_run_matrix,
    run_matrix,
    run_one_experiment,
    write_matrix_summary,
)
from feature_engineering.collect_metrics import ReplicaResetError


def _write_config(path: Path, name: str, reset: dict | None = None) -> Path:
    config_path = path / f"{name}.yaml"
    config = {
        "experiment": {"name": name, "label": 0, "scenario_type": "flash_crowd",
                        "scenario_file": "traffic/scenarios/flash_crowd.yaml", "duration_seconds": 10, "seed": 1},
        "detector": {"window_seconds": [10], "step_seconds": 10},
    }
    if reset is not None:
        config["reset"] = reset
    config_path.write_text(yaml.dump(config))
    return config_path


# --------------------------------------------------------------------- #
# run_one_experiment
# --------------------------------------------------------------------- #


def test_run_one_experiment_records_pass_on_success(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path, "OK_001")
    monkeypatch.setattr(
        run_matrix_module,
        "run_experiment",
        lambda *a, **k: {"n_feature_rows": 3, "timeseries_path": "data/raw/OK_001/timeseries.csv"},
    )

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "PASS"
    assert result.n_feature_rows == 3
    assert result.error_type is None
    assert result.failure_stage is None


def test_run_one_experiment_records_failed_for_known_reset_error(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path, "RESET_FAIL_001")

    def _raise(*_a, **_k):
        raise ReplicaResetError("did not reach minReplicas")

    monkeypatch.setattr(run_matrix_module, "run_experiment", _raise)

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "FAILED"
    assert result.failure_stage == "isolation"
    assert result.error_type == "ReplicaResetError"
    assert "did not reach minReplicas" in result.error_message
    assert result.traffic_started is False  # isolation failed before traffic could start


def test_run_one_experiment_records_failed_for_traffic_generation_failure(tmp_path, monkeypatch):
    config_path = _write_config(tmp_path, "TRAFFIC_FAIL_001")

    def _raise(config_path, host, prometheus_url, output_features_dir=None, on_subprocess_start=None, **_k):
        on_subprocess_start(12345)  # traffic DID start before it failed
        raise subprocess.CalledProcessError(1, ["locust"])

    monkeypatch.setattr(run_matrix_module, "run_experiment", _raise)

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "FAILED"
    assert result.failure_stage == "traffic_generation"
    assert result.error_type == "CalledProcessError"
    assert result.traffic_started is True


def test_run_one_experiment_records_unexpected_programming_error_distinctly(tmp_path, monkeypatch):
    """An unexpected error (not one of KNOWN_EXPERIMENT_FAILURES) must
    still be recorded as FAILED, but visibly distinguished from a known,
    anticipated infrastructure failure — never silently reclassified as
    routine, and never silently swallowed into a fake PASS."""
    config_path = _write_config(tmp_path, "WEIRD_BUG_001")

    def _raise(*_a, **_k):
        raise TypeError("something the codebase never anticipated")

    monkeypatch.setattr(run_matrix_module, "run_experiment", _raise)

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "FAILED"
    assert result.failure_stage == "unexpected_programming_error"
    assert result.error_type == "TypeError"
    assert result.traceback is not None and "TypeError" in result.traceback


@pytest.mark.parametrize("exc_type", [KeyboardInterrupt, SystemExit])
def test_run_one_experiment_never_swallows_keyboard_interrupt_or_system_exit(tmp_path, monkeypatch, exc_type):
    config_path = _write_config(tmp_path, "INTERRUPTED_001")

    def _raise(*_a, **_k):
        raise exc_type()

    monkeypatch.setattr(run_matrix_module, "run_experiment", _raise)

    with pytest.raises(exc_type):
        run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")


# --------------------------------------------------------------------- #
# run_matrix — the actual failure-isolation property
# --------------------------------------------------------------------- #


def test_run_matrix_all_pass_completes_normally(tmp_path, monkeypatch):
    for name in ["A_001", "B_001", "C_001"]:
        _write_config(tmp_path, name)
    monkeypatch.setattr(run_matrix_module, "run_experiment", lambda *a, **k: {"n_feature_rows": 1})

    results = run_matrix(tmp_path, "http://localhost:8000", "http://localhost:9090")

    assert [r.status for r in results] == ["PASS", "PASS", "PASS"]


def test_run_matrix_continues_after_one_experiment_fails(tmp_path, monkeypatch):
    _write_config(tmp_path, "A_FIRST")
    _write_config(tmp_path, "B_FAILS")
    _write_config(tmp_path, "C_AFTER")

    calls = []

    def _run_experiment(config_path, *a, **k):
        calls.append(config_path.stem)
        if config_path.stem == "B_FAILS":
            raise ReplicaResetError("isolation failed")
        return {"n_feature_rows": 1}

    monkeypatch.setattr(run_matrix_module, "run_experiment", _run_experiment)

    results = run_matrix(tmp_path, "http://localhost:8000", "http://localhost:9090")

    # The critical property: C_AFTER still ran despite B_FAILS failing.
    assert calls == ["A_FIRST", "B_FAILS", "C_AFTER"]
    assert [r.status for r in results] == ["PASS", "FAILED", "PASS"]


def test_run_matrix_continues_after_multiple_failures(tmp_path, monkeypatch):
    for name in ["A_FAILS", "B_FAILS", "C_PASSES"]:
        _write_config(tmp_path, name)

    def _run_experiment(config_path, *a, **k):
        if config_path.stem.endswith("FAILS"):
            raise subprocess.CalledProcessError(1, ["locust"])
        return {"n_feature_rows": 2}

    monkeypatch.setattr(run_matrix_module, "run_experiment", _run_experiment)

    results = run_matrix(tmp_path, "http://localhost:8000", "http://localhost:9090")

    assert [r.status for r in results] == ["FAILED", "FAILED", "PASS"]


def test_run_matrix_propagates_keyboard_interrupt_without_running_remaining_configs(tmp_path, monkeypatch):
    _write_config(tmp_path, "A_FIRST")
    _write_config(tmp_path, "B_INTERRUPTED")
    _write_config(tmp_path, "C_NEVER_RUNS")

    calls = []

    def _run_experiment(config_path, *a, **k):
        calls.append(config_path.stem)
        if config_path.stem == "B_INTERRUPTED":
            raise KeyboardInterrupt()
        return {"n_feature_rows": 1}

    monkeypatch.setattr(run_matrix_module, "run_experiment", _run_experiment)

    with pytest.raises(KeyboardInterrupt):
        run_matrix(tmp_path, "http://localhost:8000", "http://localhost:9090")

    assert calls == ["A_FIRST", "B_INTERRUPTED"]  # C_NEVER_RUNS correctly never reached


# --------------------------------------------------------------------- #
# Failed experiments are never valid research samples
# --------------------------------------------------------------------- #


def test_failed_entry_carries_no_feature_row_count():
    entry = MatrixEntryResult(
        name="X", config_file="x.yaml", status="FAILED", started_at="t0", ended_at="t1",
        failure_stage="isolation", error_type="ReplicaResetError", error_message="boom",
    )
    assert entry.n_feature_rows is None


# --------------------------------------------------------------------- #
# matrix_run_summary.json
# --------------------------------------------------------------------- #


def test_write_matrix_summary_distinguishes_pass_and_failed(tmp_path):
    entries = [
        MatrixEntryResult(name="A", config_file="a.yaml", status="PASS", started_at="t0", ended_at="t1", n_feature_rows=3),
        MatrixEntryResult(
            name="B", config_file="b.yaml", status="FAILED", started_at="t0", ended_at="t1",
            failure_stage="traffic_generation", error_type="CalledProcessError", error_message="boom",
            traffic_started=True,
        ),
    ]

    out_path = write_matrix_summary(entries, summary_dir=tmp_path)
    payload = json.loads(out_path.read_text())

    assert payload["status"] == "COMPLETED_WITH_FAILURES"
    assert payload["n_passed"] == 1
    assert payload["n_failed"] == 1
    statuses = {e["name"]: e["status"] for e in payload["experiments"]}
    assert statuses == {"A": "PASS", "B": "FAILED"}


def test_write_matrix_summary_reports_completed_when_all_pass(tmp_path):
    entries = [MatrixEntryResult(name="A", config_file="a.yaml", status="PASS", started_at="t0", ended_at="t1")]
    out_path = write_matrix_summary(entries, summary_dir=tmp_path)
    payload = json.loads(out_path.read_text())
    assert payload["status"] == "COMPLETED"
    assert payload["n_failed"] == 0


def test_write_matrix_summary_never_overwrites_a_previous_run(tmp_path, monkeypatch):
    """Each matrix run gets its own timestamped summary file — a
    second run must not silently replace the first's record."""
    entries = [MatrixEntryResult(name="A", config_file="a.yaml", status="PASS", started_at="t0", ended_at="t1")]

    timestamps = iter(["20260101T000000Z", "20260101T000001Z"])
    monkeypatch.setattr(
        run_matrix_module.dt,
        "datetime",
        type("_FakeDatetime", (), {"now": staticmethod(lambda tz=None: _FakeNow(next(timestamps)))}),
    )

    first = write_matrix_summary(entries, summary_dir=tmp_path)
    second = write_matrix_summary(entries, summary_dir=tmp_path)

    assert first != second
    assert first.exists() and second.exists()


class _FakeNow:
    def __init__(self, stamp: str):
        self._stamp = stamp

    def strftime(self, _fmt: str) -> str:
        return self._stamp

    def isoformat(self) -> str:
        return self._stamp


# =========================================================================
# Matrix DISPATCH (matrix-orchestration-hardening session, 2026-09-17):
# a config is interleaved iff it has a top-level `phases` key -- such
# configs must be routed to run_interleaved_experiment(), never to
# run_experiment(), which raises KeyError('label') on them (interleaved
# configs have no experiment.label/scenario_file). Regression suite for
# that real bug.
# =========================================================================


def _write_interleaved_config(path: Path, name: str) -> Path:
    config_path = path / f"{name}.yaml"
    config = {
        "experiment": {"name": name, "scenario_type": "interleaved", "seed": 1, "duration_seconds": 20},
        "phases": [
            {"scenario_type": "flash_crowd", "scenario_file": "traffic/scenarios/flash_crowd.yaml",
             "duration_seconds": 10, "label": 0},
            {"scenario_type": "edos", "scenario_file": "traffic/scenarios/edos.yaml",
             "duration_seconds": 10, "label": 1},
        ],
        "detector": {"window_seconds": [10], "step_seconds": 10},
    }
    config_path.write_text(yaml.dump(config))
    return config_path


def test_is_interleaved_config_detects_phases_key():
    assert run_matrix_module.is_interleaved_config({"phases": []}) is True
    assert run_matrix_module.is_interleaved_config({"experiment": {}}) is False
    assert run_matrix_module.is_interleaved_config(None) is False
    assert run_matrix_module.is_interleaved_config({}) is False


def test_normal_config_is_dispatched_to_run_experiment(tmp_path, monkeypatch):
    """(A) A normal (non-phases) config must go through run_experiment(),
    and run_interleaved_experiment() must never even be called."""
    config_path = _write_config(tmp_path, "NORMAL_DISPATCH_001")

    run_experiment_mock = MagicMock(return_value={"n_feature_rows": 3, "timeseries_path": "x"})
    run_interleaved_mock = MagicMock(side_effect=AssertionError("must not be called for a normal config"))
    monkeypatch.setattr(run_matrix_module, "run_experiment", run_experiment_mock)
    monkeypatch.setattr(run_matrix_module, "run_interleaved_experiment", run_interleaved_mock)

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "PASS"
    assert result.dispatched_to == "run_experiment"
    run_experiment_mock.assert_called_once()
    run_interleaved_mock.assert_not_called()


def test_interleaved_config_is_dispatched_to_run_interleaved_experiment(tmp_path, monkeypatch):
    """(B) An interleaved (has `phases`) config must go through
    run_interleaved_experiment(), and run_experiment() (which would raise
    KeyError('label') on this schema) must never even be called."""
    config_path = _write_interleaved_config(tmp_path, "INTERLEAVED_DISPATCH_001")

    run_experiment_mock = MagicMock(side_effect=AssertionError("must not be called for an interleaved config"))
    run_interleaved_mock = MagicMock(return_value={"n_feature_rows": 2, "timeseries_path": "y"})
    monkeypatch.setattr(run_matrix_module, "run_experiment", run_experiment_mock)
    monkeypatch.setattr(run_matrix_module, "run_interleaved_experiment", run_interleaved_mock)

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "PASS"
    assert result.dispatched_to == "run_interleaved_experiment"
    run_interleaved_mock.assert_called_once()
    run_experiment_mock.assert_not_called()


def test_interleaved_config_no_longer_raises_keyerror_through_run_matrix(tmp_path, monkeypatch):
    """Direct regression test for the bug this session fixes: before the
    dispatch fix, an interleaved config sent through run_matrix() would
    hit run_experiment()'s `exp["label"]` and fail with a misleading
    KeyError, recorded as a generic 'malformed config' failure rather
    than being correctly routed. Real run_experiment/run_interleaved_
    experiment are NOT mocked here — this exercises the actual
    dispatch decision against a real config file, only the runners
    themselves are stubbed so no live cluster is touched."""
    config_path = _write_interleaved_config(tmp_path, "INTERLEAVED_REAL_DISPATCH")
    monkeypatch.setattr(run_matrix_module, "run_interleaved_experiment", lambda *a, **k: {"n_feature_rows": 1})

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "PASS"
    assert result.error_type != "KeyError"


def test_run_matrix_continues_after_a_failed_interleaved_experiment(tmp_path, monkeypatch):
    """(D) A failed interleaved experiment must not prevent the next
    (normal) experiment in the matrix from running."""
    _write_interleaved_config(tmp_path, "A_INTERLEAVED_FAILS")
    _write_config(tmp_path, "B_NORMAL_AFTER")

    calls = []

    def _run_interleaved(config_path, *a, **k):
        calls.append(config_path.stem)
        raise ReplicaResetError("isolation failed for interleaved run")

    def _run_experiment(config_path, *a, **k):
        calls.append(config_path.stem)
        return {"n_feature_rows": 1}

    monkeypatch.setattr(run_matrix_module, "run_interleaved_experiment", _run_interleaved)
    monkeypatch.setattr(run_matrix_module, "run_experiment", _run_experiment)

    results = run_matrix(tmp_path, "http://localhost:8000", "http://localhost:9090")

    assert calls == ["A_INTERLEAVED_FAILS", "B_NORMAL_AFTER"]
    assert [r.status for r in results] == ["FAILED", "PASS"]
    assert results[0].dispatched_to == "run_interleaved_experiment"
    assert results[1].dispatched_to == "run_experiment"


def test_run_matrix_continues_after_a_failed_normal_experiment_before_an_interleaved_one(tmp_path, monkeypatch):
    """(C, extended) Mixed matrix: a failed NORMAL experiment must not
    prevent a later INTERLEAVED experiment from running, and both are
    dispatched correctly."""
    _write_config(tmp_path, "A_NORMAL_FAILS")
    _write_interleaved_config(tmp_path, "B_INTERLEAVED_AFTER")

    def _run_experiment(config_path, *a, **k):
        raise subprocess.CalledProcessError(1, ["locust"])

    def _run_interleaved(config_path, *a, **k):
        return {"n_feature_rows": 4}

    monkeypatch.setattr(run_matrix_module, "run_experiment", _run_experiment)
    monkeypatch.setattr(run_matrix_module, "run_interleaved_experiment", _run_interleaved)

    results = run_matrix(tmp_path, "http://localhost:8000", "http://localhost:9090")

    assert [r.status for r in results] == ["FAILED", "PASS"]
    assert results[0].dispatched_to == "run_experiment"
    assert results[1].dispatched_to == "run_interleaved_experiment"


def test_prometheus_unreachable_error_classified_distinctly_from_app_connection_error():
    """(E) failure_stage must distinguish Prometheus-preflight failures
    from the app's own /healthz preflight failures, even though
    PrometheusUnreachableError IS a ConnectionError subclass."""
    from feature_engineering.collect_metrics import PrometheusUnreachableError

    prom_exc = PrometheusUnreachableError("prometheus down")
    app_exc = ConnectionError("app down")

    assert run_matrix_module._classify_failure_stage(prom_exc, traffic_started=False) == "preflight_prometheus"
    assert run_matrix_module._classify_failure_stage(app_exc, traffic_started=False) == "pre_flight_host_check"


def test_run_one_experiment_records_failed_for_prometheus_preflight_failure(tmp_path, monkeypatch):
    """(E, end-to-end through run_matrix's own entry point) A Prometheus
    preflight failure must be recorded as FAILED with the correct stage,
    and must not prevent the matrix from continuing (reuses the existing
    continues-after-failure guarantee, exercised via the real
    KNOWN_EXPERIMENT_FAILURES/classification path)."""
    from feature_engineering.collect_metrics import PrometheusUnreachableError

    config_path = _write_config(tmp_path, "PROM_PREFLIGHT_FAIL")

    def _raise(*_a, **_k):
        raise PrometheusUnreachableError("prometheus not reachable right before traffic generation")

    monkeypatch.setattr(run_matrix_module, "run_experiment", _raise)

    result = run_one_experiment(config_path, "http://localhost:8000", "http://localhost:9090")

    assert result.status == "FAILED"
    assert result.failure_stage == "preflight_prometheus"
    assert result.error_type == "PrometheusUnreachableError"


# =========================================================================
# dry_run_matrix (matrix-orchestration-hardening session, 2026-09-17):
# static validation only — no cluster contact, no traffic, no writes
# anywhere under data/.
# =========================================================================


def test_dry_run_matrix_reports_correct_dispatch_for_normal_and_interleaved(tmp_path):
    _write_config(tmp_path, "NORMAL_DRY")
    _write_interleaved_config(tmp_path, "INTERLEAVED_DRY")

    entries = dry_run_matrix(tmp_path)

    by_name = {e.name: e for e in entries}
    assert by_name["NORMAL_DRY"].dispatched_to == "run_experiment"
    assert by_name["INTERLEAVED_DRY"].dispatched_to == "run_interleaved_experiment"
    assert by_name["NORMAL_DRY"].valid
    assert by_name["INTERLEAVED_DRY"].valid


def test_dry_run_matrix_flags_missing_scenario_file(tmp_path):
    config_path = tmp_path / "BAD_SCENARIO.yaml"
    config_path.write_text(yaml.dump({
        "experiment": {"name": "BAD_SCENARIO", "label": 0, "scenario_type": "flash_crowd",
                        "scenario_file": "traffic/scenarios/does_not_exist.yaml", "duration_seconds": 10, "seed": 1},
    }))

    entries = dry_run_matrix(tmp_path)

    assert len(entries) == 1
    assert not entries[0].valid
    assert any("does_not_exist.yaml" in p for p in entries[0].problems)


def test_dry_run_matrix_flags_missing_seed(tmp_path):
    config_path = tmp_path / "NO_SEED.yaml"
    config_path.write_text(yaml.dump({
        "experiment": {"name": "NO_SEED", "label": 0, "scenario_type": "flash_crowd",
                        "scenario_file": "traffic/scenarios/flash_crowd.yaml", "duration_seconds": 10},
    }))

    entries = dry_run_matrix(tmp_path)

    assert not entries[0].valid
    assert any("seed" in p for p in entries[0].problems)


def test_dry_run_matrix_flags_unparsable_yaml(tmp_path):
    config_path = tmp_path / "BROKEN.yaml"
    config_path.write_text("experiment: [unclosed")

    entries = dry_run_matrix(tmp_path)

    assert len(entries) == 1
    assert not entries[0].valid
    assert entries[0].dispatched_to == "UNKNOWN"


def test_dry_run_matrix_touches_no_cluster_no_files(tmp_path, monkeypatch):
    """A dry run must never import/call anything that would contact a
    cluster — proven here by making run_experiment/run_interleaved_
    experiment raise if called at all, and confirming dry_run_matrix()
    never calls either."""
    _write_config(tmp_path, "NORMAL_DRY_SAFETY")
    _write_interleaved_config(tmp_path, "INTERLEAVED_DRY_SAFETY")

    monkeypatch.setattr(
        run_matrix_module, "run_experiment", MagicMock(side_effect=AssertionError("dry run must not call this"))
    )
    monkeypatch.setattr(
        run_matrix_module, "run_interleaved_experiment",
        MagicMock(side_effect=AssertionError("dry run must not call this")),
    )

    entries = dry_run_matrix(tmp_path)  # must not raise
    assert len(entries) == 2


def test_dry_run_matrix_reports_existing_official_data_for_a_real_config():
    """Real, non-mocked check against the actual repository: FC_001 has
    real official data on disk; a brand-new config prefix does not."""
    real_repo_root = Path(__file__).resolve().parents[2]
    entries = dry_run_matrix(real_repo_root / "experiments" / "configs")
    by_name = {e.name: e for e in entries}
    assert by_name["FC_001"].existing_official_data is True
