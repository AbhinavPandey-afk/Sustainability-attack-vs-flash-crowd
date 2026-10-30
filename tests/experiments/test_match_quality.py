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
    CalibrationAttempt,
    CalibrationCandidateParams,
    CalibrationConfig,
    CalibrationReportExists,
    CalibrationResult,
    ExperimentSignature,
    FailedCalibrationAttempt,
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


# --------------------------------------------------------------------- #
# reference_seed provenance (live-calibration-validation session fix)
# --------------------------------------------------------------------- #


def test_calibrate_matched_pair_threads_reference_seed_through_to_result():
    """Regression test for a real bug found before any live run: every
    return path in calibrate_matched_pair() previously hardcoded
    reference_seed=None regardless of what the caller passed, silently
    discarding real provenance information the caller already knew (the
    reference experiment's actual config seed)."""
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        reference_seed=42,
    )
    assert result.reference_seed == 42


def test_calibrate_matched_pair_reference_seed_defaults_to_none_when_not_supplied():
    """The fix must not fabricate a seed value that wasn't actually
    supplied — None is the honest default when the caller doesn't know
    the reference's seed, distinct from a real seed of 0."""
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
    )
    assert result.reference_seed is None


def test_calibrate_matched_pair_threads_reference_seed_on_exhausted_paths_too():
    """The bug existed on all three CalibrationResult return paths
    (MATCHED, EXHAUSTED_NO_PROGRESS, EXHAUSTED_MAX_ITERATIONS) — this
    checks the exhaustion path specifically, not just the matched one."""
    reference = _signature(experiment_id="FC_REF", total_cost=1000.0, mean_replica_count=100.0, peak_replica_count=100.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=1.0, mean_replica_count=1.0, peak_replica_count=1.0)

    result = calibrate_matched_pair(
        reference,
        CalibrationCandidateParams(users=50, report_complexity=100),  # already at boundary -> EXHAUSTED_NO_PROGRESS
        run_candidate,
        reference_seed=99,
    )
    assert result.final_status == "EXHAUSTED_NO_PROGRESS"
    assert result.reference_seed == 99


def test_saved_calibration_report_includes_reference_seed(tmp_path):
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="SEED_PROVENANCE_TEST", reference_seed=42,
    )
    out_path = save_calibration_report(result, reference, tmp_path)
    payload = json.loads(out_path.read_text())
    assert payload["reference_seed"] == 42


# --------------------------------------------------------------------- #
# reference_signature / final_candidate_signature completeness
# (real gap found and fixed during a live calibration run, 2026-09-17:
# the persisted report had no way to recover the reference's own raw
# signature values without separately opening that experiment's own
# metadata/telemetry elsewhere)
# --------------------------------------------------------------------- #


def test_saved_calibration_report_includes_the_complete_reference_signature(tmp_path):
    reference = _signature(
        experiment_id="FC_HARDNEG_REF",
        request_rate=41.68,
        mean_cpu_utilization_pct=84.52,
        mean_replica_count=2.419,
        peak_replica_count=4.0,
        replica_minutes=3.075,
        total_cost=3.075,
        cost_per_request=0.000984,
    )

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=10.0, mean_replica_count=10.0, peak_replica_count=10.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="REF_SIGNATURE_COMPLETENESS_TEST", reference_seed=42,
        calibration_config=CalibrationConfig(max_iterations=1),
    )
    out_path = save_calibration_report(result, reference, tmp_path)
    payload = json.loads(out_path.read_text())

    assert "reference_signature" in payload
    ref_sig = payload["reference_signature"]
    # Every field of ExperimentSignature must round-trip, not just a subset.
    assert ref_sig["experiment_id"] == "FC_HARDNEG_REF"
    assert ref_sig["request_rate"] == pytest.approx(41.68)
    assert ref_sig["mean_cpu_utilization_pct"] == pytest.approx(84.52)
    assert ref_sig["mean_replica_count"] == pytest.approx(2.419)
    assert ref_sig["peak_replica_count"] == pytest.approx(4.0)
    assert ref_sig["replica_minutes"] == pytest.approx(3.075)
    assert ref_sig["total_cost"] == pytest.approx(3.075)
    assert ref_sig["cost_per_request"] == pytest.approx(0.000984)


def test_saved_calibration_report_includes_the_complete_final_candidate_signature(tmp_path):
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(
            experiment_id="EDOS_CANDIDATE_A1",
            request_rate=21.213,
            mean_cpu_utilization_pct=232.90,
            mean_replica_count=4.548,
            peak_replica_count=8.0,
            replica_minutes=5.783,
            total_cost=5.783,
            cost_per_request=0.003635,
        )

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="CANDIDATE_SIGNATURE_COMPLETENESS_TEST",
        calibration_config=CalibrationConfig(max_iterations=1),
    )
    out_path = save_calibration_report(result, reference, tmp_path)
    payload = json.loads(out_path.read_text())

    assert "final_candidate_signature" in payload
    cand_sig = payload["final_candidate_signature"]
    assert cand_sig["experiment_id"] == "EDOS_CANDIDATE_A1"
    assert cand_sig["request_rate"] == pytest.approx(21.213)
    assert cand_sig["mean_cpu_utilization_pct"] == pytest.approx(232.90)
    assert cand_sig["peak_replica_count"] == pytest.approx(8.0)
    assert cand_sig["total_cost"] == pytest.approx(5.783)
    # Must be identical to the last attempt's own embedded signature —
    # a convenience pointer, not a second, potentially-divergent copy.
    assert cand_sig == payload["attempts"][-1]["signature"]


def test_saved_calibration_report_preserves_every_previously_existing_field(tmp_path):
    """Regression guard: the schema-completeness fix must be additive
    only — every field the report already had before this fix must still
    be present with the same meaning."""
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60, seed=48), run_candidate,
        candidate_id_prefix="BACKWARD_COMPAT_TEST", reference_seed=42,
    )
    out_path = save_calibration_report(result, reference, tmp_path)
    payload = json.loads(out_path.read_text())

    for key in (
        "reference_experiment_id", "reference_seed", "candidate_id_prefix", "final_status",
        "n_attempts", "calibration_config", "tolerances", "attempts", "final_match_report",
    ):
        assert key in payload, f"pre-existing field {key!r} missing after the schema-completeness fix"
    assert payload["attempts"][0]["params"]["seed"] == 48
    assert payload["attempts"][0]["absolute_differences"]["total_cost"] == pytest.approx(0.0)


# --------------------------------------------------------------------- #
# save_calibration_report collision protection (live-calibration
# -validation session fix)
# --------------------------------------------------------------------- #


def test_save_calibration_report_refuses_to_silently_overwrite_an_existing_report(tmp_path):
    """Regression test for a real collision risk: candidate_id_prefix has
    no built-in uniqueness (default is a fixed string), so a second
    calibration run reusing the same prefix would previously silently
    destroy the first run's audit trail."""
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    first = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="COLLISION_TEST",
    )
    save_calibration_report(first, reference, tmp_path)

    second = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=10, report_complexity=70), run_candidate,
        candidate_id_prefix="COLLISION_TEST",  # same prefix — deliberate collision
    )
    with pytest.raises(CalibrationReportExists):
        save_calibration_report(second, reference, tmp_path)

    # The FIRST report must survive untouched — not partially overwritten.
    payload = json.loads((tmp_path / "COLLISION_TEST" / "calibration_report.json").read_text())
    assert payload["attempts"][0]["params"]["users"] == 8


def test_save_calibration_report_allows_explicit_overwrite(tmp_path):
    reference = _signature(experiment_id="FC_REF", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    first = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="OVERWRITE_TEST",
    )
    save_calibration_report(first, reference, tmp_path)

    second = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=10, report_complexity=70), run_candidate,
        candidate_id_prefix="OVERWRITE_TEST",
    )
    out_path = save_calibration_report(second, reference, tmp_path, allow_overwrite=True)
    payload = json.loads(out_path.read_text())
    assert payload["attempts"][0]["params"]["users"] == 10


# =========================================================================
# Calibration campaign RELIABILITY HARDENING (2026-09-17)
#
# Regression suite for the real failure observed live across THREE
# separate sessions: a mid-campaign infrastructure exception from
# run_candidate() propagated uncaught out of calibrate_matched_pair(),
# discarding every earlier successful attempt's real telemetry with
# nothing ever persisted to disk.
# =========================================================================


def _reference() -> ExperimentSignature:
    return _signature(
        experiment_id="FC_HARDNEG_REF", request_rate=47.59, mean_cpu_utilization_pct=81.87,
        mean_replica_count=1.968, peak_replica_count=3.0, replica_minutes=2.495,
        total_cost=2.495, cost_per_request=0.000699,
    )


# --------------------------------------------------------------------- #
# 1. Successful iteration is persisted immediately (on_attempt fires
#    per-iteration, not only at the end)
# --------------------------------------------------------------------- #


def test_on_attempt_is_called_after_every_successful_iteration_not_only_at_the_end():
    reference = _signature(experiment_id="FC_REF", total_cost=1000.0, mean_replica_count=100.0, peak_replica_count=100.0)
    calls = []

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id=f"CAND_{params.users}", total_cost=1.0, mean_replica_count=1.0, peak_replica_count=1.0)

    calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        calibration_config=CalibrationConfig(max_iterations=3, users_step=2, report_complexity_step=10),
        on_attempt=lambda r: calls.append((r.final_status, len(r.attempts))),
    )

    # 3 iterations run (never matching, never hitting a boundary) -> one
    # "IN_PROGRESS" notification after each of the 3 iterations (the loop
    # notifies progress before checking whether max_iterations was just
    # reached), plus one final terminal EXHAUSTED_MAX_ITERATIONS
    # notification once the loop exits — 4 calls total. The key property
    # under test is that on_attempt fires repeatedly DURING the campaign,
    # not only once at the very end.
    assert len(calls) == 4
    assert calls[0] == ("IN_PROGRESS", 1)
    assert calls[1] == ("IN_PROGRESS", 2)
    assert calls[2] == ("IN_PROGRESS", 3)
    assert calls[3] == ("EXHAUSTED_MAX_ITERATIONS", 3)


def test_on_attempt_receives_the_real_signature_immediately_after_first_success():
    reference = _reference()
    seen_signatures = []

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(
            experiment_id="CAND_A1", total_cost=4.885, mean_replica_count=3.839, peak_replica_count=8.0,
        )

    calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        calibration_config=CalibrationConfig(max_iterations=1),
        on_attempt=lambda r: seen_signatures.append(r.attempts[-1].signature.experiment_id if r.attempts else None),
    )
    # max_iterations=1: notified once as "IN_PROGRESS" right after the
    # single attempt succeeds, then once more as the terminal
    # EXHAUSTED_MAX_ITERATIONS status — both carrying the same real
    # candidate signature, since no second attempt ever ran.
    assert seen_signatures == ["CAND_A1", "CAND_A1"]


# --------------------------------------------------------------------- #
# 2. Later candidate failure preserves earlier successful iteration
# --------------------------------------------------------------------- #


def test_calibrate_matched_pair_preserves_earlier_success_when_a_later_candidate_fails():
    """The exact regression: iteration 1 succeeds (real signature, real
    NOT_MATCHED comparison), iteration 2 raises (simulating the live
    ConnectionError from a dead port-forward). The function must RETURN
    (not raise) with iteration 1's data intact."""
    reference = _reference()

    call_count = {"n": 0}

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _signature(experiment_id="CAND_A1", total_cost=4.885, mean_replica_count=3.839, peak_replica_count=8.0)
        raise ConnectionError("http://localhost:8000 is not reachable right before traffic generation was about to start")

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60, seed=48), run_candidate,
        calibration_config=CalibrationConfig(max_iterations=5, users_step=2, report_complexity_step=10),
    )

    assert result.final_status == "CANDIDATE_FAILED"
    assert len(result.attempts) == 2
    # Iteration 1's success must survive, byte for byte.
    assert isinstance(result.attempts[0], CalibrationAttempt)
    assert result.attempts[0].iteration == 1
    assert result.attempts[0].signature.experiment_id == "CAND_A1"
    assert result.attempts[0].report.match_status == "NOT_MATCHED"
    # Iteration 2's failure is recorded, not silently dropped.
    assert isinstance(result.attempts[1], FailedCalibrationAttempt)
    assert result.attempts[1].iteration == 2
    assert result.attempts[1].failure_type == "ConnectionError"
    assert "not reachable" in result.attempts[1].failure_message


def test_calibrate_matched_pair_never_raises_on_a_candidate_failure_anymore():
    """Pre-hardening behavior: this would raise ConnectionError
    uncaught. Post-hardening: it must return normally."""
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        raise ConnectionError("tunnel died")

    result = calibrate_matched_pair(  # must not raise
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
    )
    assert result.final_status == "CANDIDATE_FAILED"


def test_calibration_report_survives_on_disk_after_a_later_iteration_fails(tmp_path):
    """End-to-end: the on_attempt callback persists progress via
    save_calibration_report(); after a later failure, the file on disk
    must still contain the earlier success — the literal scenario from
    the task's own example schema."""
    reference = _reference()
    call_count = {"n": 0}

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _signature(experiment_id="CAND_A1", total_cost=4.885, mean_replica_count=3.839, peak_replica_count=8.0)
        raise ConnectionError("tunnel died mid-campaign")

    written = {"flag": False}

    def on_attempt(interim_result):
        save_calibration_report(interim_result, reference, tmp_path, allow_overwrite=written["flag"])
        written["flag"] = True

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="SURVIVAL_TEST",
        calibration_config=CalibrationConfig(max_iterations=5, users_step=2, report_complexity_step=10),
        on_attempt=on_attempt,
    )
    assert result.final_status == "CANDIDATE_FAILED"

    out_path = tmp_path / "SURVIVAL_TEST" / "calibration_report.json"
    payload = json.loads(out_path.read_text())
    assert payload["final_status"] == "CANDIDATE_FAILED"
    assert payload["n_attempts"] == 2
    assert payload["attempts"][0]["status"] == "SUCCESS"
    assert payload["attempts"][0]["signature"]["experiment_id"] == "CAND_A1"
    assert payload["attempts"][1]["status"] == "FAILED"
    assert payload["attempts"][1]["failure_type"] == "ConnectionError"


# --------------------------------------------------------------------- #
# 3. Failed iteration contains failure information but no fabricated
#    signature
# --------------------------------------------------------------------- #


def test_failed_attempt_has_no_signature_field_at_all():
    """A FailedCalibrationAttempt must not have a `signature` attribute
    to accidentally fabricate — it structurally cannot represent one."""
    failed = FailedCalibrationAttempt(
        iteration=1, params=CalibrationCandidateParams(users=8, report_complexity=60),
        failure_type="ConnectionError", failure_message="tunnel died",
        timestamp="2026-09-17T00:00:00+00:00",
    )
    assert not hasattr(failed, "signature")
    assert not hasattr(failed, "report")


def test_serialized_failed_attempt_never_contains_a_signature_key():
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        raise OSError("scenario file missing")

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
    )
    payload = result.to_dict(reference)
    failed_entry = payload["attempts"][0]
    assert failed_entry["status"] == "FAILED"
    assert "signature" not in failed_entry
    assert "match_report" not in failed_entry
    assert failed_entry["failure_type"] == "OSError"


def test_final_candidate_signature_and_match_report_are_none_when_every_attempt_fails():
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        raise ConnectionError("never reachable")

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
    )
    payload = result.to_dict(reference)
    assert payload["final_candidate_signature"] is None
    assert payload["final_match_report"] is None


def test_final_candidate_signature_falls_back_to_last_success_when_trailing_attempt_failed():
    """If iteration 1 succeeds and iteration 2 fails, the convenience
    top-level pointers must point at iteration 1's real data, not crash
    or silently return None despite real data being available."""
    reference = _reference()
    call_count = {"n": 0}

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return _signature(experiment_id="CAND_A1", total_cost=4.885, mean_replica_count=3.839, peak_replica_count=8.0)
        raise ConnectionError("tunnel died")

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        calibration_config=CalibrationConfig(max_iterations=5, users_step=2, report_complexity_step=10),
    )
    payload = result.to_dict(reference)
    assert payload["final_candidate_signature"]["experiment_id"] == "CAND_A1"
    assert payload["final_match_report"]["candidate_experiment_id"] == "CAND_A1"


# --------------------------------------------------------------------- #
# 4. Atomic write behavior
# --------------------------------------------------------------------- #


def test_save_calibration_report_leaves_no_temp_file_behind_on_success(tmp_path):
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="ATOMIC_TEST", calibration_config=CalibrationConfig(max_iterations=1),
    )
    out_path = save_calibration_report(result, reference, tmp_path)

    all_files = list((tmp_path / "ATOMIC_TEST").iterdir())
    assert all_files == [out_path]  # no leftover .tmp file


def test_save_calibration_report_never_leaves_a_half_written_file_on_a_simulated_crash(tmp_path, monkeypatch):
    """Simulates a crash DURING the write (os.replace never happens) and
    confirms the destination file is left in whatever state it was in
    before this call — either absent (first write) or the PREVIOUS
    complete content (a repeat write) — never a truncated/partial file."""
    import experiments.match_quality as mq

    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="CRASH_TEST", calibration_config=CalibrationConfig(max_iterations=1),
    )

    original_replace = mq.os.replace

    def _boom(*args, **kwargs):
        raise OSError("simulated crash before the atomic rename completes")

    monkeypatch.setattr(mq.os, "replace", _boom)
    with pytest.raises(OSError, match="simulated crash"):
        save_calibration_report(result, reference, tmp_path)
    monkeypatch.setattr(mq.os, "replace", original_replace)

    out_path = tmp_path / "CRASH_TEST" / "calibration_report.json"
    assert not out_path.exists()  # never partially created
    # No leftover temp file either — the except path cleans it up.
    leftover = list((tmp_path / "CRASH_TEST").glob("*.tmp"))
    assert leftover == []


def test_atomic_write_a_second_time_does_not_corrupt_an_existing_complete_report(tmp_path):
    reference = _reference()
    call_count = {"n": 0}

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        call_count["n"] += 1
        return _signature(experiment_id=f"CAND_{call_count['n']}", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    r1 = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="REWRITE_TEST", calibration_config=CalibrationConfig(max_iterations=1),
    )
    save_calibration_report(r1, reference, tmp_path)

    r2 = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=6, report_complexity=50), run_candidate,
        candidate_id_prefix="REWRITE_TEST", calibration_config=CalibrationConfig(max_iterations=1),
    )
    out_path = save_calibration_report(r2, reference, tmp_path, allow_overwrite=True)
    payload = json.loads(out_path.read_text())  # must parse cleanly, not be corrupted
    assert payload["attempts"][0]["signature"]["experiment_id"] == "CAND_2"


# --------------------------------------------------------------------- #
# 5. Existing complete reference signature remains in the report
# --------------------------------------------------------------------- #


def test_reference_signature_still_fully_present_after_reliability_hardening(tmp_path):
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="REF_SIG_STILL_PRESENT", calibration_config=CalibrationConfig(max_iterations=1),
        reference_seed=42,
    )
    out_path = save_calibration_report(result, reference, tmp_path)
    payload = json.loads(out_path.read_text())

    assert payload["reference_signature"]["request_rate"] == pytest.approx(47.59)
    assert payload["reference_signature"]["peak_replica_count"] == pytest.approx(3.0)
    assert payload["reference_seed"] == 42


# --------------------------------------------------------------------- #
# 6. Existing collision protection remains functional
# --------------------------------------------------------------------- #


def test_collision_protection_still_refuses_a_genuinely_different_campaigns_overwrite(tmp_path):
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    first = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
        candidate_id_prefix="COLLISION_STILL_WORKS", calibration_config=CalibrationConfig(max_iterations=1),
    )
    save_calibration_report(first, reference, tmp_path)

    second = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=99, report_complexity=99), run_candidate,
        candidate_id_prefix="COLLISION_STILL_WORKS", calibration_config=CalibrationConfig(max_iterations=1),
    )
    with pytest.raises(CalibrationReportExists):
        save_calibration_report(second, reference, tmp_path)  # default allow_overwrite=False


# --------------------------------------------------------------------- #
# 7. A genuine NOT_MATCHED result remains distinct from candidate
#    failure
# --------------------------------------------------------------------- #


def test_not_matched_and_candidate_failed_are_never_conflated():
    reference = _reference()

    def run_candidate_not_matched(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="OVERSHOOT", total_cost=4.885, mean_replica_count=3.839, peak_replica_count=8.0)

    def run_candidate_fails(params: CalibrationCandidateParams) -> ExperimentSignature:
        raise ConnectionError("tunnel died")

    not_matched_result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate_not_matched,
        calibration_config=CalibrationConfig(max_iterations=1),
    )
    failed_result = calibrate_matched_pair(
        reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate_fails,
        calibration_config=CalibrationConfig(max_iterations=1),
    )

    assert not_matched_result.final_status in {"EXHAUSTED_MAX_ITERATIONS", "EXHAUSTED_NO_PROGRESS"}
    assert not_matched_result.attempts[-1].report.match_status == "NOT_MATCHED"
    assert isinstance(not_matched_result.attempts[-1], CalibrationAttempt)

    assert failed_result.final_status == "CANDIDATE_FAILED"
    assert isinstance(failed_result.attempts[-1], FailedCalibrationAttempt)

    # The two must never be reported under the same status string.
    assert not_matched_result.final_status != failed_result.final_status


def test_wiring_failure_still_propagates_uncaught_unlike_a_candidate_failure():
    """An exception from OUTSIDE run_candidate() (simulated here as a bug
    in an on_attempt callback) must NOT be swallowed or reclassified as
    CANDIDATE_FAILED — it is a mechanism-level (wiring) problem and must
    still surface as a real exception to the caller."""
    reference = _reference()

    def run_candidate(params: CalibrationCandidateParams) -> ExperimentSignature:
        return _signature(experiment_id="CAND", total_cost=4.0, mean_replica_count=4.0, peak_replica_count=4.0)

    def broken_on_attempt(interim_result):
        raise RuntimeError("bug in the caller's own persistence callback")

    with pytest.raises(RuntimeError, match="bug in the caller"):
        calibrate_matched_pair(
            reference, CalibrationCandidateParams(users=8, report_complexity=60), run_candidate,
            calibration_config=CalibrationConfig(max_iterations=1),
            on_attempt=broken_on_attempt,
        )
