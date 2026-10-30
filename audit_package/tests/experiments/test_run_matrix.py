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
