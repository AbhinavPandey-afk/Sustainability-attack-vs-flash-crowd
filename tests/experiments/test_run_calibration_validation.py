"""Integration smoke test for experiments/run_calibration_validation.py's
own persistence wiring (`make_on_attempt`) — the calibration-reliability
-hardening session's Phase 8 smoke validation.

Deliberately NOT a live-cluster test: `make_run_candidate`/`run_reference`
(the functions that actually call experiments.run_experiment.run_experiment
against a real k3d cluster) are not exercised here at all. This test
imports the REAL `make_on_attempt` factory from the real script and wires
it to `experiments.match_quality.calibrate_matched_pair()` with a fake
`run_candidate` — verifying the actual production integration code (not
a reimplementation of it in test_match_quality.py) persists progress
correctly, per this task's explicit preference for an isolated test over
spending live cluster time when persistence behavior itself is what's
under test.
"""
from __future__ import annotations

import json

import pytest

from experiments.match_quality import (
    CalibrationCandidateParams,
    CalibrationConfig,
    ExperimentSignature,
    calibrate_matched_pair,
)
from experiments.run_calibration_validation import make_on_attempt


def _reference() -> ExperimentSignature:
    return ExperimentSignature(
        experiment_id="FC_HARDNEG_REF",
        duration_seconds=75.0,
        request_count=3569.0,
        request_rate=47.59,
        mean_cpu_utilization_pct=81.87,
        mean_replica_count=1.968,
        peak_replica_count=3.0,
        replica_minutes=2.495,
        total_cost=2.495,
        cost_per_request=0.000699,
    )


def _candidate_signature(experiment_id: str) -> ExperimentSignature:
    return ExperimentSignature(
        experiment_id=experiment_id,
        duration_seconds=75.0,
        request_count=1360.0,
        request_rate=18.13,
        mean_cpu_utilization_pct=237.94,
        mean_replica_count=3.839,
        peak_replica_count=8.0,
        replica_minutes=4.885,
        total_cost=4.885,
        cost_per_request=0.003592,
    )


def test_real_on_attempt_persists_a_successful_iteration_immediately(tmp_path):
    """successful candidate iteration -> verify the campaign report
    survives on disk after just that one iteration, using the ACTUAL
    make_on_attempt() from run_calibration_validation.py."""
    reference = _reference()
    on_attempt = make_on_attempt(reference, tmp_path)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _candidate_signature("CALIBRATION_CANDIDATE_SMOKETEST_A1")

    result = calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=8, report_complexity=60, seed=48),
        run_candidate,
        candidate_id_prefix="SMOKE_TEST_CAMPAIGN",
        calibration_config=CalibrationConfig(max_iterations=1),
        reference_seed=42,
        on_attempt=on_attempt,
    )

    assert result.final_status in {"EXHAUSTED_MAX_ITERATIONS", "MATCHED"}
    out_path = tmp_path / "SMOKE_TEST_CAMPAIGN" / "calibration_report.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["n_attempts"] == 1
    assert payload["attempts"][0]["status"] == "SUCCESS"
    assert payload["attempts"][0]["signature"]["experiment_id"] == "CALIBRATION_CANDIDATE_SMOKETEST_A1"
    assert payload["reference_signature"]["peak_replica_count"] == pytest.approx(3.0)


def test_real_on_attempt_survives_a_controlled_later_failure(tmp_path):
    """successful candidate iteration -> controlled failure of a LATER
    iteration -> verify the campaign report survives with iteration 1
    intact, using the real make_on_attempt() wiring end to end."""
    reference = _reference()
    on_attempt = make_on_attempt(reference, tmp_path)
    call_count = {"n": 0}

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _candidate_signature("CALIBRATION_CANDIDATE_SMOKETEST_A1")
        # Controlled, injected failure — mirrors the real live failure
        # mode (a dead port-forward tunnel) without touching any cluster.
        raise ConnectionError(
            "http://localhost:8000 is not reachable right before traffic generation was about to "
            "start (a kubectl port-forward tunnel may have died during the isolation wait). "
            "Experiment aborted before traffic generation."
        )

    result = calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=8, report_complexity=60, seed=48),
        run_candidate,
        candidate_id_prefix="SMOKE_TEST_CAMPAIGN_WITH_FAILURE",
        calibration_config=CalibrationConfig(max_iterations=5, users_step=2, report_complexity_step=10),
        reference_seed=42,
        on_attempt=on_attempt,
    )

    assert result.final_status == "CANDIDATE_FAILED"

    out_path = tmp_path / "SMOKE_TEST_CAMPAIGN_WITH_FAILURE" / "calibration_report.json"
    assert out_path.exists(), "campaign report must survive on disk despite the later failure"
    payload = json.loads(out_path.read_text())

    assert payload["final_status"] == "CANDIDATE_FAILED"
    assert payload["n_attempts"] == 2
    # Iteration 1's real, successful telemetry must still be there.
    assert payload["attempts"][0]["status"] == "SUCCESS"
    assert payload["attempts"][0]["signature"]["experiment_id"] == "CALIBRATION_CANDIDATE_SMOKETEST_A1"
    assert payload["attempts"][0]["signature"]["peak_replica_count"] == pytest.approx(8.0)
    # Iteration 2's failure is honestly recorded — no fabricated signature.
    assert payload["attempts"][1]["status"] == "FAILED"
    assert payload["attempts"][1]["failure_type"] == "ConnectionError"
    assert "port-forward" in payload["attempts"][1]["failure_message"]
    assert "signature" not in payload["attempts"][1]
    # The reference signature — the other schema-completeness fix from
    # the prior session — is also still fully present.
    assert payload["reference_signature"]["experiment_id"] == "FC_HARDNEG_REF"
    assert payload["reference_seed"] == 42
