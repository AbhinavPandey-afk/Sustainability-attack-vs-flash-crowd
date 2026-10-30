"""Unit tests for experiments/match_quality.py — the matched-signature
measurement primitives (docs/research_gap_audit.md Part 7 / P0
methodology fix, Deliverable D). No live cluster required: all inputs are
synthetic raw-timeseries DataFrames with the same schema
experiments/run_experiment.py writes to data/raw/<id>/timeseries.csv.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from app.src.cost import CostModelConfig
from experiments.match_quality import (
    CalibrationCandidateParams,
    CalibrationConfig,
    CalibrationResult,
    ExperimentSignature,
    MatchTolerances,
    apply_candidate_params,
    calibrate_matched_pair,
    compare_signatures,
    compute_signature,
    next_candidate_params,
    save_calibration_report,
    save_match_report,
)


def _raw(timestamps, request_counts, replica_counts, cpu_pcts) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "request_count": request_counts,
            "replica_count": replica_counts,
            "cpu_utilization_pct": cpu_pcts,
        }
    )


# --------------------------------------------------------------------- #
# compute_signature
# --------------------------------------------------------------------- #


def test_compute_signature_matches_hand_computed_values():
    raw = _raw(
        timestamps=[0, 10, 20, 30],
        request_counts=[0, 10, 20, 30],
        replica_counts=[1, 1, 2, 2],
        cpu_pcts=[50, 50, 70, 70],
    )
    sig = compute_signature("TEST_001", raw, CostModelConfig(replica_cost_per_minute=1.0))

    assert sig.duration_seconds == pytest.approx(30.0)
    assert sig.request_count == pytest.approx(30.0)
    assert sig.request_rate == pytest.approx(1.0)
    assert sig.mean_cpu_utilization_pct == pytest.approx(60.0)
    assert sig.mean_replica_count == pytest.approx(1.5)
    assert sig.peak_replica_count == pytest.approx(2.0)
    # intervals: (1 replica, 10s) + (1 replica, 10s) + (2 replicas, 10s)
    # => replica_minutes = (10 + 10 + 20) / 60
    assert sig.replica_minutes == pytest.approx(40.0 / 60.0)
    # cpu_cost_weight defaults to 0, so cost == replica_minutes * rate
    assert sig.total_cost == pytest.approx(40.0 / 60.0)
    assert sig.cost_per_request == pytest.approx((40.0 / 60.0) / 30.0)


def test_compute_signature_handles_empty_input_without_crashing():
    sig = compute_signature("EMPTY_001", pd.DataFrame())
    assert sig.request_count == 0.0
    assert sig.total_cost == 0.0
    assert sig.request_rate == 0.0


def test_compute_signature_handles_single_row_without_crashing():
    raw = _raw(timestamps=[0], request_counts=[0], replica_counts=[1], cpu_pcts=[10])
    sig = compute_signature("ONE_ROW", raw)
    assert sig.duration_seconds == 0.0
    assert sig.total_cost == 0.0


def test_compute_signature_never_reports_negative_request_count_from_a_counter_reset():
    """request_count is a cumulative Prometheus counter — a reset
    (process restart mid-run) must not produce a fabricated negative
    request count."""
    raw = _raw(timestamps=[0, 10], request_counts=[100, 5], replica_counts=[1, 1], cpu_pcts=[10, 10])
    sig = compute_signature("RESET_CASE", raw)
    assert sig.request_count == 0.0


# --------------------------------------------------------------------- #
# compare_signatures / match_status
# --------------------------------------------------------------------- #


def _signature(**overrides) -> ExperimentSignature:
    base = dict(
        experiment_id="X",
        duration_seconds=60.0,
        request_count=100.0,
        request_rate=1.67,
        mean_cpu_utilization_pct=50.0,
        mean_replica_count=4.0,
        peak_replica_count=4.0,
        replica_minutes=4.0,
        total_cost=4.0,
        cost_per_request=0.04,
    )
    base.update(overrides)
    return ExperimentSignature(**base)


def test_compare_signatures_reports_matched_when_scaling_and_cost_are_close():
    reference = _signature(experiment_id="FC_REF", request_rate=50.0)
    candidate = _signature(
        experiment_id="EDOS_CANDIDATE",
        request_rate=8.0,  # deliberately very different — this is the point of EDoS
        mean_replica_count=4.2,
        peak_replica_count=4.0,
        total_cost=4.3,
    )
    report = compare_signatures(reference, candidate)

    assert report.match_status == "MATCHED"
    # request_rate is NOT a gating axis: EDoS is expected to differ here.
    assert abs(report.request_rate_delta_pct) > 50


def test_compare_signatures_reports_not_matched_when_scaling_diverges():
    reference = _signature(experiment_id="FC_REF", peak_replica_count=8.0, mean_replica_count=6.0, total_cost=10.0)
    candidate = _signature(experiment_id="EDOS_CANDIDATE", peak_replica_count=2.0, mean_replica_count=1.5, total_cost=1.0)
    report = compare_signatures(reference, candidate)

    assert report.match_status == "NOT_MATCHED"
    assert report.axis_matched["peak_replica_count"] is False
    assert report.axis_matched["total_cost"] is False


def test_compare_signatures_uses_absolute_tolerance_for_small_replica_counts():
    """1 vs 2 replicas is a 100% relative delta but should still count as
    matched under the default +/-1 replica absolute tolerance."""
    reference = _signature(experiment_id="FC_REF", peak_replica_count=1.0, mean_replica_count=1.0, total_cost=1.0)
    candidate = _signature(experiment_id="EDOS_CANDIDATE", peak_replica_count=2.0, mean_replica_count=1.5, total_cost=1.05)
    report = compare_signatures(reference, candidate)

    assert report.axis_matched["peak_replica_count"] is True
    assert report.axis_matched["mean_replica_count"] is True
    assert report.match_status == "MATCHED"


def test_compare_signatures_respects_custom_tolerances():
    reference = _signature(experiment_id="FC_REF", total_cost=10.0)
    candidate = _signature(experiment_id="EDOS_CANDIDATE", total_cost=10.5)  # 5% delta

    strict = compare_signatures(reference, candidate, MatchTolerances(total_cost_pct=1.0))
    loose = compare_signatures(reference, candidate, MatchTolerances(total_cost_pct=10.0))

    assert strict.axis_matched["total_cost"] is False
    assert loose.axis_matched["total_cost"] is True


def test_pct_delta_is_none_not_zero_when_reference_is_zero():
    reference = _signature(experiment_id="FC_REF", total_cost=0.0)
    candidate = _signature(experiment_id="EDOS_CANDIDATE", total_cost=5.0)
    report = compare_signatures(reference, candidate)
    assert report.total_cost_delta_pct is None
    # An undefined delta must not be silently treated as a match.
    assert report.axis_matched["total_cost"] is False


def test_match_report_to_dict_includes_primary_match_axes():
    report = compare_signatures(_signature(experiment_id="A"), _signature(experiment_id="B"))
    payload = report.to_dict()
    assert payload["primary_match_axes"] == ["peak_replica_count", "mean_replica_count", "total_cost"]
    assert payload["match_status"] in {"MATCHED", "NOT_MATCHED"}


# --------------------------------------------------------------------- #
# save_match_report
# --------------------------------------------------------------------- #


def test_save_match_report_writes_to_candidate_experiment_directory(tmp_path):
    report = compare_signatures(_signature(experiment_id="FC_REF"), _signature(experiment_id="EDOS_CANDIDATE"))
    out_path = save_match_report(report, tmp_path)

    assert out_path == tmp_path / "EDOS_CANDIDATE" / "match_report.json"
    assert out_path.exists()
    payload = json.loads(out_path.read_text())
    assert payload["reference_experiment_id"] == "FC_REF"
    assert payload["candidate_experiment_id"] == "EDOS_CANDIDATE"


# --------------------------------------------------------------------- #
# CalibrationConfig
# --------------------------------------------------------------------- #


def test_calibration_config_defaults():
    cfg = CalibrationConfig()
    assert cfg.max_iterations == 5
    assert cfg.target_axes == ("peak_replica_count", "mean_replica_count", "total_cost")


def test_calibration_config_from_dict_reads_explicit_values():
    cfg = CalibrationConfig.from_dict(
        {"max_iterations": 3, "users_step": 1, "report_complexity_step": 5, "target_axes": ["total_cost"]}
    )
    assert cfg.max_iterations == 3
    assert cfg.users_step == 1
    assert cfg.report_complexity_step == 5
    assert cfg.target_axes == ("total_cost",)


# --------------------------------------------------------------------- #
# apply_candidate_params
# --------------------------------------------------------------------- #


def test_apply_candidate_params_overrides_users_spawn_rate_and_complexity():
    scenario = {
        "scenario": {"name": "edos", "type": "edos"},
        "locust": {"users": 8, "spawn_rate": 8, "run_time_seconds": 60, "host": "http://localhost:8000"},
        "behavior": {"think_time_min": 0.05, "think_time_max": 0.2, "report_complexity": 60,
                     "weights": {"generate_report": 18, "home": 1, "search": 1, "checkout": 1}},
    }
    params = CalibrationCandidateParams(users=20, report_complexity=80)
    result = apply_candidate_params(scenario, params)

    assert result["locust"]["users"] == 20
    assert result["locust"]["spawn_rate"] == 20  # mirrors users, not a separate knob
    assert result["behavior"]["report_complexity"] == 80
    # Behavioural weights/think-time must be untouched by the search.
    assert result["behavior"]["weights"] == scenario["behavior"]["weights"]
    assert result["behavior"]["think_time_min"] == 0.05


def test_apply_candidate_params_does_not_mutate_input():
    scenario = {"locust": {"users": 8, "spawn_rate": 8}, "behavior": {"report_complexity": 60}}
    apply_candidate_params(scenario, CalibrationCandidateParams(users=99, report_complexity=99))
    assert scenario["locust"]["users"] == 8
    assert scenario["behavior"]["report_complexity"] == 60


# --------------------------------------------------------------------- #
# next_candidate_params
# --------------------------------------------------------------------- #


def test_next_candidate_params_increases_pressure_when_candidate_below_reference():
    reference = _signature(experiment_id="FC_REF", total_cost=10.0, mean_replica_count=6.0, peak_replica_count=8.0)
    candidate = _signature(experiment_id="EDOS", total_cost=2.0, mean_replica_count=1.5, peak_replica_count=2.0)
    report = compare_signatures(reference, candidate)

    current = CalibrationCandidateParams(users=8, report_complexity=60)
    nxt = next_candidate_params(current, report, CalibrationConfig(users_step=2, report_complexity_step=10))

    assert nxt.users == 10
    assert nxt.report_complexity == 70


def test_next_candidate_params_decreases_pressure_when_candidate_above_reference():
    reference = _signature(experiment_id="FC_REF", total_cost=2.0, mean_replica_count=1.5, peak_replica_count=2.0)
    candidate = _signature(experiment_id="EDOS", total_cost=10.0, mean_replica_count=6.0, peak_replica_count=8.0)
    report = compare_signatures(reference, candidate)

    current = CalibrationCandidateParams(users=20, report_complexity=80)
    nxt = next_candidate_params(current, report, CalibrationConfig(users_step=2, report_complexity_step=10))

    assert nxt.users == 18
    assert nxt.report_complexity == 70


def test_next_candidate_params_unchanged_when_already_matched():
    reference = _signature(experiment_id="FC_REF")
    candidate = _signature(experiment_id="EDOS")  # identical -> matched on every axis
    report = compare_signatures(reference, candidate)

    current = CalibrationCandidateParams(users=8, report_complexity=60)
    nxt = next_candidate_params(current, report, CalibrationConfig())
    assert nxt == current


def test_next_candidate_params_clips_to_bounds():
    reference = _signature(experiment_id="FC_REF", total_cost=1000.0, mean_replica_count=50.0, peak_replica_count=50.0)
    candidate = _signature(experiment_id="EDOS", total_cost=1.0, mean_replica_count=1.0, peak_replica_count=1.0)
    report = compare_signatures(reference, candidate)

    current = CalibrationCandidateParams(users=49, report_complexity=95)
    nxt = next_candidate_params(
        current, report, CalibrationConfig(users_step=5, report_complexity_step=10), max_users=50, max_report_complexity=100
    )
    assert nxt.users == 50  # clipped, not 54
    assert nxt.report_complexity == 100  # clipped, not 105


def test_next_candidate_params_only_considers_target_axes():
    """total_cost is unmatched but excluded from target_axes -> must not drive the step."""
    reference = _signature(experiment_id="FC_REF", total_cost=10.0, mean_replica_count=4.0, peak_replica_count=4.0)
    candidate = _signature(experiment_id="EDOS", total_cost=1.0, mean_replica_count=4.1, peak_replica_count=4.0)
    report = compare_signatures(reference, candidate)
    assert report.axis_matched["total_cost"] is False
    assert report.axis_matched["mean_replica_count"] is True

    current = CalibrationCandidateParams(users=8, report_complexity=60)
    nxt = next_candidate_params(
        current, report, CalibrationConfig(target_axes=("mean_replica_count",), users_step=2, report_complexity_step=10)
    )
    # mean_replica_count is matched and is the only target axis -> nothing to adjust
    assert nxt == current


# --------------------------------------------------------------------- #
# calibrate_matched_pair
# --------------------------------------------------------------------- #


def test_calibrate_matched_pair_stops_on_first_match():
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id=f"CAND_{params.users}", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate
    )

    assert result.final_status == "MATCHED"
    assert len(result.attempts) == 1
    assert result.attempts[0].report.match_status == "MATCHED"


def test_calibrate_matched_pair_never_fabricates_a_match():
    """A run_candidate that always returns a wildly divergent signature
    must exhaust, never report MATCHED."""
    reference = _signature(experiment_id="FC_REF", total_cost=100.0, mean_replica_count=50.0, peak_replica_count=50.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id=f"CAND_{params.users}", total_cost=1.0, mean_replica_count=1.0, peak_replica_count=1.0)

    result = calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=8, report_complexity=60),
        run_candidate,
        calibration_config=CalibrationConfig(max_iterations=3, users_step=2, report_complexity_step=10),
    )

    assert result.final_status in {"EXHAUSTED_MAX_ITERATIONS", "EXHAUSTED_NO_PROGRESS"}
    assert all(a.report.match_status == "NOT_MATCHED" for a in result.attempts)


def test_calibrate_matched_pair_exhausts_at_max_iterations_when_never_matching():
    reference = _signature(experiment_id="FC_REF", total_cost=1000.0, mean_replica_count=100.0, peak_replica_count=100.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        # Scales weakly with users so it keeps "making progress" (moving,
        # never hitting a param boundary) but never actually matches
        # within 3 iterations given the reference above.
        return _signature(
            experiment_id=f"CAND_{params.users}",
            total_cost=float(params.users),
            mean_replica_count=float(params.users) / 5,
            peak_replica_count=float(params.users) / 5,
        )

    result = calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=8, report_complexity=60),
        run_candidate,
        calibration_config=CalibrationConfig(max_iterations=3, users_step=2, report_complexity_step=10),
    )

    assert result.final_status == "EXHAUSTED_MAX_ITERATIONS"
    assert len(result.attempts) == 3


def test_calibrate_matched_pair_detects_no_progress_at_boundary():
    """Starting already at the users/report_complexity ceiling, needing
    MORE pressure, means next_candidate_params can't move -> stop after
    one attempt instead of looping."""
    reference = _signature(experiment_id="FC_REF", total_cost=1000.0, mean_replica_count=100.0, peak_replica_count=100.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND_AT_CEILING", total_cost=1.0, mean_replica_count=1.0, peak_replica_count=1.0)

    result = calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=50, report_complexity=100),  # already at default max bounds
        run_candidate,
        calibration_config=CalibrationConfig(max_iterations=5, users_step=2, report_complexity_step=10),
    )

    assert result.final_status == "EXHAUSTED_NO_PROGRESS"
    assert len(result.attempts) == 1


def test_calibrate_matched_pair_run_candidate_receives_evolving_params():
    """run_candidate must see each successive candidate's params, not the
    same initial params repeated."""
    reference = _signature(experiment_id="FC_REF", total_cost=1000.0, mean_replica_count=100.0, peak_replica_count=100.0)
    seen_users = []

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        seen_users.append(params.users)
        return _signature(experiment_id=f"CAND_{params.users}", total_cost=1.0, mean_replica_count=1.0, peak_replica_count=1.0)

    calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=8, report_complexity=60),
        run_candidate,
        calibration_config=CalibrationConfig(max_iterations=3, users_step=2, report_complexity_step=10),
    )

    assert seen_users == [8, 10, 12]


# --------------------------------------------------------------------- #
# save_calibration_report
# --------------------------------------------------------------------- #


def test_save_calibration_report_writes_attempts_and_absolute_differences(tmp_path):
    reference = _signature(experiment_id="FC_REF", total_cost=10.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=10.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60, seed=42), run_candidate,
        candidate_id_prefix="CALIB_TEST_001",
    )
    out_path = save_calibration_report(result, reference, tmp_path)

    assert out_path == tmp_path / "CALIB_TEST_001" / "calibration_report.json"
    payload = json.loads(out_path.read_text())
    assert payload["final_status"] == "MATCHED"
    assert payload["n_attempts"] == 1
    attempt = payload["attempts"][0]
    assert attempt["params"]["users"] == 8
    assert attempt["params"]["seed"] == 42
    assert attempt["absolute_differences"]["total_cost"] == pytest.approx(0.0)
    assert "tolerances" in payload
    assert "calibration_config" in payload
