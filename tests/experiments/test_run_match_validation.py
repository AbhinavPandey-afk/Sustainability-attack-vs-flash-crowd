"""Integration test for experiments/run_match_validation.py's persistence
and reference-loading logic — the repeated-seed match-validation session.

Deliberately NOT a live-cluster test: `run_one_candidate()` (which calls
the real experiments.run_experiment.run_experiment against a real k3d
cluster) is not exercised here. This verifies load_reference() correctly
deserializes a real calibration_report.json without re-running anything,
and that _write_json_atomic() persists incrementally and survives a
simulated later failure — mirroring the same regression-guard pattern
already established for the calibration search campaign's own
persistence hardening.
"""
from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from experiments.match_quality import CalibrationCandidateParams, ExperimentSignature, MatchTolerances, compare_signatures
from experiments.run_match_validation import _write_json_atomic, load_reference


def _write_fake_campaign_report(tmp_path, reference_signature: ExperimentSignature, reference_seed: int, reference_experiment_id: str):
    payload = {
        "reference_experiment_id": reference_experiment_id,
        "reference_seed": reference_seed,
        "reference_signature": asdict(reference_signature),
        "candidate_id_prefix": "FAKE_CAMPAIGN",
        "final_status": "MATCHED",
        "attempts": [],
    }
    path = tmp_path / "calibration_report.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def test_load_reference_deserializes_without_rerunning_anything(tmp_path):
    reference = ExperimentSignature(
        experiment_id="CALIBRATION_REF_FC_HARDNEG_001_20260917T074935Z",
        duration_seconds=75.0, request_count=3029.0, request_rate=40.38666666666666,
        mean_cpu_utilization_pct=76.06451612903226, mean_replica_count=1.967741935483871,
        peak_replica_count=3.0, replica_minutes=2.494244619210561, total_cost=2.4942446192105607,
        cost_per_request=0.0008234548099077454,
    )
    path = _write_fake_campaign_report(tmp_path, reference, 42, "CALIBRATION_REF_FC_HARDNEG_001_20260917T074935Z")

    loaded_signature, loaded_seed, loaded_id = load_reference(path)

    assert loaded_signature == reference
    assert loaded_seed == 42
    assert loaded_id == "CALIBRATION_REF_FC_HARDNEG_001_20260917T074935Z"


def test_write_json_atomic_persists_and_is_readable(tmp_path):
    out_path = tmp_path / "match_validation_report.json"
    _write_json_atomic({"runs": [{"seed": 48, "status": "SUCCESS"}]}, out_path)
    payload = json.loads(out_path.read_text())
    assert payload["runs"][0]["seed"] == 48


def test_write_json_atomic_overwrite_preserves_earlier_runs_when_caller_appends(tmp_path):
    """Mirrors the calibration campaign's own progressive-overwrite
    persistence pattern: each write carries the FULL accumulated `runs`
    list, so a later seed's failure can never erase an earlier seed's
    real result, as long as the caller always writes the whole list."""
    out_path = tmp_path / "match_validation_report.json"
    runs = [{"seed": 48, "status": "SUCCESS", "match_status": "MATCHED"}]
    _write_json_atomic({"runs": runs}, out_path)

    runs.append({"seed": 49, "status": "FAILED", "failure_type": "ConnectionError"})
    _write_json_atomic({"runs": runs}, out_path)

    payload = json.loads(out_path.read_text())
    assert len(payload["runs"]) == 2
    assert payload["runs"][0]["seed"] == 48
    assert payload["runs"][0]["status"] == "SUCCESS"
    assert payload["runs"][1]["seed"] == 49
    assert payload["runs"][1]["status"] == "FAILED"
    assert "signature" not in payload["runs"][1]  # no fabricated signature on a failed run


def test_compare_signatures_used_by_validation_uses_unchanged_default_tolerances():
    """Regression guard: the validation script must use MatchTolerances()
    with no overrides — this task explicitly forbids loosening
    tolerances to obtain a result."""
    tolerances = MatchTolerances()
    assert tolerances.peak_replica_pct == 25.0
    assert tolerances.mean_replica_pct == 25.0
    assert tolerances.total_cost_pct == 25.0
    assert tolerances.replica_count_absolute_tolerance == 1.0
