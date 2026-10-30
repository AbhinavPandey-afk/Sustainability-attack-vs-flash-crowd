"""Matched-signature protocol — P0 methodology correction, Deliverable D
(docs/research_gap_audit.md Part 7), extended with the calibration search
loop during the final-experiment-design session
(docs/experiment_protocol.md's "MATCHED-SIGNATURE EXPERIMENT DESIGN"
section).

The project's central research condition requires constructing an EDoS
run and a flash-crowd run whose SCALING and COST signatures are
comparable despite different traffic volume/composition. Before this
module, no code measured how close two experiments actually were —
"comparable" was asserted from static scenario config, and the one time
two experiments happened to land on the same replica count
(FC_002/EDOS_002/EDOS_003), it turned out to be HPA scale-down carryover
contamination, not a genuine match (docs/research_gap_audit.md Part 3).

This module provides the pure, reusable pieces needed to MEASURE a match
rather than assert one:

  compute_signature()      raw timeseries.csv -> one experiment's
                            aggregate scaling/cost/traffic signature
  compare_signatures()     two signatures -> a MatchReport with per-axis
                            percentage deltas and a measured match_status
  save_match_report()      persists that report next to the experiment's
                            existing metadata.json

...and the calibration SEARCH LOOP that adjusts a candidate EDoS
scenario's parameters and re-measures until a match is found or the
search is exhausted:

  CalibrationCandidateParams  the only two knobs this search tunes
  apply_candidate_params()    pure function: params -> a new EDoS
                               scenario dict (no I/O)
  next_candidate_params()     pure function: last MatchReport -> next
                               params to try (no I/O, no ML)
  calibrate_matched_pair()    the iteration loop itself. Takes the actual
                               "run this candidate and measure it" step as
                               an INJECTED callable (`run_candidate`) —
                               this module never spawns traffic or talks
                               to Kubernetes/Prometheus itself. A caller
                               wires `run_candidate` to a real live-run
                               function (e.g. building on
                               experiments/run_experiment.py +
                               compute_signature()); tests wire it to a
                               fake that returns canned signatures. This
                               keeps the search logic itself fully unit
                               -testable without a live cluster, and keeps
                               this module from ever executing a live
                               calibration campaign on its own.
  save_calibration_report()   persists the full attempt history plus
                               absolute (not just percentage) per-axis
                               differences and the calibration parameters
                               used at each step.

The search is DELIBERATELY narrow in scope, per the design constraint
that only "parameters whose effect is understood and defensible" should
be tunable: it adjusts only `users` and `report_complexity` — the same
two knobs CalibrationConfig already declared step sizes for. It does not
touch think-time, spawn_rate (derived from users, matching edos.yaml's
own users==spawn_rate convention), or endpoint-weight ratios — those
would change EDoS's *behavioural* signature (the thing
docs/research_gap_audit.md Part 4/9 warns must stay a measured, not
scripted, difference) rather than only its scaling/cost pressure, and
mixing the two would confound the matched-signature condition with the
behavioural-shortcut question this project is separately trying to keep
clean.

The search is also bounded: `next_candidate_params()` never lets `users`
or `report_complexity` leave a configurable safe range, and reports
EXHAUSTED (not a fabricated match) if it cannot converge within that
range or within `CalibrationConfig.max_iterations` — matching this
project's existing "never report a false success" convention (see
ReplicaResetter.ensure_isolated for the same pattern applied to HPA
isolation).

This module intentionally never imports anything from `models/` — the
calibration search is independent of the ML classifier by construction,
operating only on ExperimentSignature's pre-declared scaling/cost/traffic
quantities, never on a trained model's predictions or SHAP output.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

from app.src.cost import CostModelConfig, ReplicaInterval, compute_cost, total_replica_minutes


@dataclass(frozen=True)
class ExperimentSignature:
    """One experiment's aggregate scaling/cost/traffic signature, computed
    from its full raw timeseries — the "how big was this run, and what
    did it cost" summary a matched pair is compared on. Units match the
    rest of the pipeline (app/src/cost.py, feature_engineering/): cost in
    cost units, rates in requests/second, replica counts as observed.
    """

    experiment_id: str
    duration_seconds: float
    request_count: float
    request_rate: float
    mean_cpu_utilization_pct: float
    mean_replica_count: float
    peak_replica_count: float
    replica_minutes: float
    total_cost: float
    cost_per_request: float


def _intervals_from_raw(raw: pd.DataFrame) -> list[ReplicaInterval]:
    """Mirrors feature_engineering/cost_features.py's
    _intervals_from_window(), applied to a full raw series instead of one
    windowed slice, so a signature's total_cost/replica_minutes stay
    computed with the exact same formula as the rest of the pipeline."""
    rows = list(raw[["timestamp", "replica_count", "cpu_utilization_pct"]].itertuples(index=False, name=None))
    intervals = []
    for (t0, replicas, cpu_pct), (t1, _r1, _c1) in zip(rows, rows[1:]):
        intervals.append(
            ReplicaInterval(
                duration_seconds=float(t1 - t0),
                replica_count=int(replicas),
                avg_cpu_utilization=float(cpu_pct) / 100.0,
            )
        )
    return intervals


def compute_signature(
    experiment_id: str, raw: pd.DataFrame, cost_config: CostModelConfig | None = None
) -> ExperimentSignature:
    """raw: the same [timestamp, request_count, replica_count,
    cpu_utilization_pct] schema experiments/run_experiment.py writes to
    data/raw/<id>/timeseries.csv (request_count is the cumulative
    counter, matching build_features.py's convention). Need not be
    sorted — this function sorts defensively.

    Returns an all-zero signature for empty/too-short input rather than
    raising — a signature is descriptive, not a hard pipeline gate, and a
    zero signature is a visible, honest "no data" rather than a crash.
    """
    cost_config = cost_config or CostModelConfig()
    if raw is None or raw.empty or len(raw) < 2:
        return ExperimentSignature(
            experiment_id=experiment_id,
            duration_seconds=0.0,
            request_count=0.0,
            request_rate=0.0,
            mean_cpu_utilization_pct=0.0,
            mean_replica_count=0.0,
            peak_replica_count=0.0,
            replica_minutes=0.0,
            total_cost=0.0,
            cost_per_request=0.0,
        )

    raw = raw.sort_values("timestamp").reset_index(drop=True)
    duration_seconds = float(raw["timestamp"].iloc[-1] - raw["timestamp"].iloc[0])
    request_count = max(float(raw["request_count"].iloc[-1] - raw["request_count"].iloc[0]), 0.0)
    request_rate = request_count / duration_seconds if duration_seconds > 0 else 0.0

    intervals = _intervals_from_raw(raw)
    total_cost = compute_cost(intervals, cost_config)
    replica_minutes = total_replica_minutes(intervals)
    cost_per_request = (total_cost / request_count) if request_count > 0 else 0.0

    return ExperimentSignature(
        experiment_id=experiment_id,
        duration_seconds=duration_seconds,
        request_count=request_count,
        request_rate=request_rate,
        mean_cpu_utilization_pct=float(raw["cpu_utilization_pct"].mean()),
        mean_replica_count=float(raw["replica_count"].mean()),
        peak_replica_count=float(raw["replica_count"].max()),
        replica_minutes=replica_minutes,
        total_cost=total_cost,
        cost_per_request=cost_per_request,
    )


@dataclass(frozen=True)
class MatchTolerances:
    """Per-axis tolerance for judging two experiments' signatures a
    genuine match, as PERCENTAGE deltas relative to the reference
    experiment's value.

    RATIONALE FOR THE 25% DEFAULT (docs/research_gap_audit.md Part 7 /
    docs/experiment_protocol.md's Matched-Signature Protocol section):
    chosen from this project's own observed same-scenario run-to-run
    variance — FC_001 vs FC_003 (both clean, uncontaminated runs of the
    IDENTICAL scenario config, differing only by Locust seed) showed
    ~5-6% deltas on request_rate/estimated_cost/mean_replica_count purely
    from run-to-run noise. Setting the match tolerance well above that
    noise floor (25%, roughly 4-5x) means a "MATCHED" verdict reflects a
    genuine, deliberately-constructed match rather than demanding
    precision the system's own repeatability doesn't support.

    replica_count_absolute_tolerance exists because percentage deltas are
    unstable at small integers (1 vs 2 replicas = 100% "delta") — an
    absolute allowance of +/-1 replica also counts as matched on the two
    replica-count axes, whichever (percentage or absolute) is more
    permissive.
    """

    request_rate_pct: float = 25.0
    cpu_pct: float = 25.0
    peak_replica_pct: float = 25.0
    mean_replica_pct: float = 25.0
    replica_minutes_pct: float = 25.0
    total_cost_pct: float = 25.0
    cost_per_request_pct: float = 25.0
    replica_count_absolute_tolerance: float = 1.0


def _pct_delta(candidate: float, reference: float) -> float | None:
    """Signed percentage delta of candidate relative to reference. None
    (undefined, not zero) when the reference value is 0 — a percentage
    against a zero baseline isn't meaningful and must never be silently
    reported as a fabricated 0% or an unbounded number."""
    if reference == 0:
        return None
    return (candidate - reference) / reference * 100.0


def _axis_matched(
    delta_pct: float | None,
    tolerance_pct: float,
    absolute_delta: float | None = None,
    absolute_tolerance: float | None = None,
) -> bool:
    if delta_pct is not None and abs(delta_pct) <= tolerance_pct:
        return True
    if absolute_delta is not None and absolute_tolerance is not None and abs(absolute_delta) <= absolute_tolerance:
        return True
    return False


# The axes that actually define this project's matched-signature research
# condition (docs/research_gap_audit.md Part 7): scaling and cost must be
# comparable. request_rate/cpu/cost_per_request are recorded for context
# and reported in every match report, but deliberately excluded from the
# match_status gate — EDoS is EXPECTED to differ on request_rate (that's
# the whole point: lower volume, comparable cost/scaling), so requiring
# it to match would contradict the research question itself.
PRIMARY_MATCH_AXES = ("peak_replica_count", "mean_replica_count", "total_cost")


@dataclass(frozen=True)
class MatchReport:
    reference_experiment_id: str
    candidate_experiment_id: str
    tolerances: MatchTolerances
    request_rate_delta_pct: float | None
    cpu_delta_pct: float | None
    peak_replica_delta_pct: float | None
    mean_replica_delta_pct: float | None
    replica_minutes_delta_pct: float | None
    total_cost_delta_pct: float | None
    cost_per_request_delta_pct: float | None
    axis_matched: dict
    match_status: str  # "MATCHED" | "NOT_MATCHED"

    def to_dict(self) -> dict:
        return {
            "reference_experiment_id": self.reference_experiment_id,
            "candidate_experiment_id": self.candidate_experiment_id,
            "tolerances": asdict(self.tolerances),
            "request_rate_delta_pct": self.request_rate_delta_pct,
            "cpu_delta_pct": self.cpu_delta_pct,
            "peak_replica_delta_pct": self.peak_replica_delta_pct,
            "mean_replica_delta_pct": self.mean_replica_delta_pct,
            "replica_minutes_delta_pct": self.replica_minutes_delta_pct,
            "total_cost_delta_pct": self.total_cost_delta_pct,
            "cost_per_request_delta_pct": self.cost_per_request_delta_pct,
            "primary_match_axes": list(PRIMARY_MATCH_AXES),
            "axis_matched": self.axis_matched,
            "match_status": self.match_status,
        }


def compare_signatures(
    reference: ExperimentSignature,
    candidate: ExperimentSignature,
    tolerances: MatchTolerances | None = None,
) -> MatchReport:
    """Measures how close `candidate` (intended to be the EDoS run) is to
    `reference` (intended to be the flash-crowd run) on every recorded
    axis, and derives match_status from the primary (scaling + cost) axes
    only — see PRIMARY_MATCH_AXES."""
    tolerances = tolerances or MatchTolerances()

    request_rate_delta = _pct_delta(candidate.request_rate, reference.request_rate)
    cpu_delta = _pct_delta(candidate.mean_cpu_utilization_pct, reference.mean_cpu_utilization_pct)
    peak_replica_delta = _pct_delta(candidate.peak_replica_count, reference.peak_replica_count)
    mean_replica_delta = _pct_delta(candidate.mean_replica_count, reference.mean_replica_count)
    replica_minutes_delta = _pct_delta(candidate.replica_minutes, reference.replica_minutes)
    total_cost_delta = _pct_delta(candidate.total_cost, reference.total_cost)
    cost_per_request_delta = _pct_delta(candidate.cost_per_request, reference.cost_per_request)

    axis_matched = {
        "request_rate": _axis_matched(request_rate_delta, tolerances.request_rate_pct),
        "cpu": _axis_matched(cpu_delta, tolerances.cpu_pct),
        "peak_replica_count": _axis_matched(
            peak_replica_delta,
            tolerances.peak_replica_pct,
            candidate.peak_replica_count - reference.peak_replica_count,
            tolerances.replica_count_absolute_tolerance,
        ),
        "mean_replica_count": _axis_matched(
            mean_replica_delta,
            tolerances.mean_replica_pct,
            candidate.mean_replica_count - reference.mean_replica_count,
            tolerances.replica_count_absolute_tolerance,
        ),
        "replica_minutes": _axis_matched(replica_minutes_delta, tolerances.replica_minutes_pct),
        "total_cost": _axis_matched(total_cost_delta, tolerances.total_cost_pct),
        "cost_per_request": _axis_matched(cost_per_request_delta, tolerances.cost_per_request_pct),
    }

    match_status = "MATCHED" if all(axis_matched[axis] for axis in PRIMARY_MATCH_AXES) else "NOT_MATCHED"

    return MatchReport(
        reference_experiment_id=reference.experiment_id,
        candidate_experiment_id=candidate.experiment_id,
        tolerances=tolerances,
        request_rate_delta_pct=request_rate_delta,
        cpu_delta_pct=cpu_delta,
        peak_replica_delta_pct=peak_replica_delta,
        mean_replica_delta_pct=mean_replica_delta,
        replica_minutes_delta_pct=replica_minutes_delta,
        total_cost_delta_pct=total_cost_delta,
        cost_per_request_delta_pct=cost_per_request_delta,
        axis_matched=axis_matched,
        match_status=match_status,
    )


def save_match_report(report: MatchReport, experiments_dir: Path) -> Path:
    """Persists alongside the candidate experiment's existing
    metadata.json: data/experiments/<candidate_id>/match_report.json —
    the same directory convention experiments/run_experiment.py already
    uses, so a match report is discoverable exactly where an engineer
    would already look for that experiment's other reproducibility
    metadata."""
    out_dir = Path(experiments_dir) / report.candidate_experiment_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "match_report.json"
    out_path.write_text(json.dumps(report.to_dict(), indent=2))
    return out_path


@dataclass(frozen=True)
class CalibrationConfig:
    """Configuration surface for the EDoS-parameter calibration search
    described in docs/experiment_protocol.md's Matched-Signature Protocol
    section, and now also the loop's actual step-size/iteration-count
    inputs (see calibrate_matched_pair() below).
    """

    max_iterations: int = 5
    users_step: int = 2
    report_complexity_step: int = 10
    target_axes: tuple = PRIMARY_MATCH_AXES

    @classmethod
    def from_dict(cls, data: dict) -> "CalibrationConfig":
        return cls(
            max_iterations=int(data.get("max_iterations", 5)),
            users_step=int(data.get("users_step", 2)),
            report_complexity_step=int(data.get("report_complexity_step", 10)),
            target_axes=tuple(data.get("target_axes", PRIMARY_MATCH_AXES)),
        )


# --------------------------------------------------------------------- #
# Calibration search loop
# --------------------------------------------------------------------- #


@dataclass(frozen=True)
class CalibrationCandidateParams:
    """The only two controllable EDoS parameters this search tunes — see
    the module docstring for why the scope is deliberately this narrow.
    `seed` is carried through (not tuned) purely so every attempt's
    provenance is recorded in the persisted calibration report; changing
    the seed is never how this search tries to close a gap."""

    users: int
    report_complexity: int
    seed: int | None = None


def apply_candidate_params(edos_scenario: dict, params: CalibrationCandidateParams) -> dict:
    """Returns a NEW scenario dict (the input is never mutated) with
    `locust.users`/`locust.spawn_rate` and `behavior.report_complexity`
    overridden to `params`. `spawn_rate` is set equal to `users`,
    mirroring traffic/scenarios/edos.yaml's own convention (users ==
    spawn_rate) rather than introducing a third tunable knob. Every other
    key (weights, think-time, search_terms, host, ...) is passed through
    unchanged, so the search never silently drifts the *behavioural*
    signature — only the scaling/cost-relevant knobs move.
    """
    scenario = copy.deepcopy(edos_scenario)
    scenario.setdefault("locust", {})["users"] = params.users
    scenario["locust"]["spawn_rate"] = params.users
    scenario.setdefault("behavior", {})["report_complexity"] = params.report_complexity
    return scenario


def _clip(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def next_candidate_params(
    current: CalibrationCandidateParams,
    report: MatchReport,
    config: CalibrationConfig,
    min_users: int = 1,
    max_users: int = 50,
    min_report_complexity: int = 1,
    max_report_complexity: int = 100,
) -> CalibrationCandidateParams:
    """Pure, deterministic step function — no ML, no randomness, no I/O.

    Looks only at `config.target_axes` (a subset of PRIMARY_MATCH_AXES)
    and picks whichever of those is currently NOT matched with the
    largest absolute percentage delta as the "driver" axis. Moves `users`
    and `report_complexity` together, by `config.users_step` /
    `config.report_complexity_step`, in the direction that reduces that
    driver axis's signed gap (candidate below reference -> increase
    pressure; candidate above reference -> decrease it).

    Both parameters are bounded to [min_users, max_users] and
    [min_report_complexity, max_report_complexity] (defaults: same rough
    ceiling as flash_crowd.yaml's user count, and the app's own complexity
    upper bound). This is a deliberate safety rail: the search must never
    silently escape the "few simulated clients, expensive workload" EDoS
    definition (CLAUDE.md section 11) into a flash-crowd-sized swarm just
    to force a numeric match. If a step would leave the range, it is
    clipped rather than skipped — calibrate_matched_pair() detects "no
    change from clipping" as exhaustion (see its docstring) rather than
    looping forever at the boundary.

    Returns `current` UNCHANGED if every axis in `config.target_axes` is
    already matched (nothing left to adjust) or if `report` has no
    delta recorded for any target axis (e.g. a reference value of 0 made
    every relevant percentage delta undefined — see `_pct_delta`).
    """
    axis_deltas = {
        "total_cost": report.total_cost_delta_pct,
        "mean_replica_count": report.mean_replica_delta_pct,
        "peak_replica_count": report.peak_replica_delta_pct,
    }
    unmatched = {
        axis: delta
        for axis, delta in axis_deltas.items()
        if axis in config.target_axes and delta is not None and not report.axis_matched.get(axis, True)
    }
    if not unmatched:
        return current

    driver_axis = max(unmatched, key=lambda axis: abs(unmatched[axis]))
    delta_pct = unmatched[driver_axis]
    # delta_pct = (candidate - reference) / reference * 100.
    # Negative => candidate is below reference => needs MORE pressure.
    direction = 1 if delta_pct < 0 else -1

    new_users = _clip(current.users + direction * config.users_step, min_users, max_users)
    new_complexity = _clip(
        current.report_complexity + direction * config.report_complexity_step,
        min_report_complexity,
        max_report_complexity,
    )
    return CalibrationCandidateParams(users=new_users, report_complexity=new_complexity, seed=current.seed)


@dataclass(frozen=True)
class CalibrationAttempt:
    """One iteration's (params, measured signature, match report) triple.
    Serialization (including absolute differences against a reference) is
    done by CalibrationResult.to_dict(), which has the reference signature
    available — a single attempt does not carry a reference of its own."""

    iteration: int
    params: CalibrationCandidateParams
    signature: ExperimentSignature
    report: MatchReport


@dataclass(frozen=True)
class FailedCalibrationAttempt:
    """One iteration's FAILURE — deliberately a structurally distinct
    shape from CalibrationAttempt, not a CalibrationAttempt with null
    fields, because a failed run never produces valid telemetry: there is
    no signature and no match report to (mis)represent as present.

    Added during the calibration-reliability-hardening session
    (2026-09-17), after the same live failure (a `ConnectionError` from a
    dead port-forward tunnel, raised by `run_candidate()` mid-campaign)
    was observed discarding every earlier successful attempt's data on
    three separate occasions — this type is what makes a failed attempt
    representable and persistable instead of only propagating as an
    uncaught exception that unwinds the whole campaign's in-memory state.
    """

    iteration: int
    params: CalibrationCandidateParams
    failure_type: str
    failure_message: str
    timestamp: str


@dataclass(frozen=True)
class CalibrationResult:
    reference_experiment_id: str
    reference_seed: int | None
    candidate_id_prefix: str
    attempts: list = field(default_factory=list)  # list[CalibrationAttempt | FailedCalibrationAttempt]
    # "MATCHED" | "EXHAUSTED_MAX_ITERATIONS" | "EXHAUSTED_NO_PROGRESS" | "CANDIDATE_FAILED" | "IN_PROGRESS"
    final_status: str = "NOT_STARTED"
    calibration_config: CalibrationConfig = field(default_factory=CalibrationConfig)
    tolerances: MatchTolerances = field(default_factory=MatchTolerances)

    def to_dict(self, reference_signature: "ExperimentSignature | None" = None) -> dict:
        """`reference_signature`, when supplied, is serialized in full as
        its own top-level `reference_signature` object — not just implied
        via percentage/absolute deltas against it. Before this fix, a
        persisted calibration_report.json had no way to recover the
        reference run's own raw quantities (request_rate, mean_cpu,
        mean/peak replicas, replica_minutes, total_cost, cost_per_request)
        without separately opening that reference experiment's own
        metadata/telemetry elsewhere — confirmed as a real gap during a
        live calibration run (2026-09-17), not a hypothetical concern.
        `final_candidate_signature` mirrors the existing
        `final_match_report` convenience field, for the same reason:
        the full candidate signature is already present per-attempt in
        `attempts[i]["signature"]`, but a top-level pointer to the LAST
        attempt's signature (paired with `final_match_report`) makes the
        final comparison auditable without hunting through the attempts
        list. Every existing field/key is unchanged; these are additions,
        not replacements.

        `attempts` may now contain a mix of `CalibrationAttempt` (real
        telemetry obtained, `status: "SUCCESS"`) and
        `FailedCalibrationAttempt` (`status: "FAILED"`, no signature/
        match_report — a failed run never has real telemetry to report).
        `final_match_report`/`final_candidate_signature` are derived from
        the LAST SUCCESSFUL attempt specifically (not simply
        `attempts[-1]`), since a trailing failed attempt has no signature
        or match report of its own to point to — if every attempt failed,
        both are None, not a crash.
        """
        last_success = next(
            (a for a in reversed(self.attempts) if isinstance(a, CalibrationAttempt)), None
        )

        def _serialize_attempt(a) -> dict:
            if isinstance(a, CalibrationAttempt):
                return {
                    "iteration": a.iteration,
                    "status": "SUCCESS",
                    "params": asdict(a.params),
                    "signature": asdict(a.signature),
                    "match_report": a.report.to_dict(),
                    "absolute_differences": (
                        _absolute_diffs(reference_signature, a.signature) if reference_signature is not None else None
                    ),
                }
            return {
                "iteration": a.iteration,
                "status": "FAILED",
                "params": asdict(a.params),
                "failure_type": a.failure_type,
                "failure_message": a.failure_message,
                "timestamp": a.timestamp,
            }

        return {
            "reference_experiment_id": self.reference_experiment_id,
            "reference_seed": self.reference_seed,
            "reference_signature": (asdict(reference_signature) if reference_signature is not None else None),
            "candidate_id_prefix": self.candidate_id_prefix,
            "final_status": self.final_status,
            "n_attempts": len(self.attempts),
            "calibration_config": asdict(self.calibration_config),
            "tolerances": asdict(self.tolerances),
            "attempts": [_serialize_attempt(a) for a in self.attempts],
            "final_match_report": last_success.report.to_dict() if last_success is not None else None,
            "final_candidate_signature": (asdict(last_success.signature) if last_success is not None else None),
        }


def _absolute_diffs(reference: "ExperimentSignature", candidate: "ExperimentSignature") -> dict:
    """Absolute (not normalized) candidate-minus-reference differences on
    every axis reported in a match — required alongside the existing
    percentage deltas so a calibration report is auditable without having
    to re-derive absolute values from percentages (which is impossible
    when the percentage is None, i.e. reference == 0)."""
    return {
        "request_rate": candidate.request_rate - reference.request_rate,
        "cpu": candidate.mean_cpu_utilization_pct - reference.mean_cpu_utilization_pct,
        "peak_replica_count": candidate.peak_replica_count - reference.peak_replica_count,
        "mean_replica_count": candidate.mean_replica_count - reference.mean_replica_count,
        "replica_minutes": candidate.replica_minutes - reference.replica_minutes,
        "total_cost": candidate.total_cost - reference.total_cost,
        "cost_per_request": candidate.cost_per_request - reference.cost_per_request,
    }


def calibrate_matched_pair(
    reference_signature: ExperimentSignature,
    initial_params: CalibrationCandidateParams,
    run_candidate: Callable[[CalibrationCandidateParams], ExperimentSignature],
    candidate_id_prefix: str = "CALIBRATION_CANDIDATE",
    tolerances: MatchTolerances | None = None,
    calibration_config: CalibrationConfig | None = None,
    reference_seed: int | None = None,
    on_attempt: Callable[["CalibrationResult"], None] | None = None,
) -> CalibrationResult:
    """The calibration search loop:

        candidate params -> run_candidate(params) -> ExperimentSignature
                          -> compare_signatures(reference, candidate)
                          -> MATCHED? stop. else: next_candidate_params()
                          -> repeat, up to calibration_config.max_iterations

    `run_candidate` is the ONLY place this function touches anything
    outside pure computation — it is supplied by the caller, never
    implemented here. A live caller wires it to something that (a) writes
    a candidate scenario YAML via apply_candidate_params(), (b) runs it
    through experiments/run_experiment.py against a real cluster, (c)
    reads back data/raw/<id>/timeseries.csv, and (d) returns
    compute_signature() of that raw data. A test wires it to a fake that
    returns canned signatures with no I/O at all — see
    tests/experiments/test_match_quality.py for both patterns. This
    function itself NEVER runs a live experiment, so calling it does not,
    by itself, execute a calibration campaign.

    `reference_seed`: the reference (flash-crowd) experiment's own
    `experiment.seed`, as recorded in ITS config/metadata — this function
    never generates or infers a seed itself, it only carries through what
    the caller already knows about the reference run's provenance (e.g.
    read from `experiments/configs/<ref_id>.yaml` or
    `data/experiments/<ref_id>/metadata.json`). Previously this was always
    hardcoded to `None` regardless of what the caller passed, silently
    discarding real provenance information from the persisted calibration
    report — fixed to actually thread the value through.

    `on_attempt`, if supplied, is called with an up-to-the-moment
    `CalibrationResult` (reflecting every attempt so far, success or
    failure) after EVERY iteration — including the terminal one — never
    only at the very end. This function still performs no I/O itself
    (the callback is the caller's own responsibility, exactly like
    `run_candidate`); a live caller wires `on_attempt` to something that
    persists the interim result (e.g. `save_calibration_report(...,
    allow_overwrite=True)`), so a later iteration's failure can never
    erase an earlier iteration's already-recorded success — see
    docs/experiment_protocol.md's calibration-reliability-hardening
    section for the incident (three separate live sessions) this fixes.

    RELIABILITY HARDENING (2026-09-17): `run_candidate(params)` is now
    wrapped in `try/except Exception`. On failure, a
    `FailedCalibrationAttempt` (iteration, params, `type(exc).__name__`,
    `str(exc)`, a UTC timestamp — NEVER a fabricated signature) is
    appended to `attempts`, `on_attempt` is notified, and this function
    RETURNS (does not raise) a `CalibrationResult` with
    `final_status="CANDIDATE_FAILED"`, preserving every prior successful
    attempt. This is a deliberate, scoped control-flow change — previously
    any exception from `run_candidate` propagated uncaught, silently
    discarding the in-memory `attempts` list built up so far. The actual
    SEARCH algorithm (`compare_signatures`, `next_candidate_params`, the
    MATCHED/EXHAUSTED_* decision logic below) is completely unchanged.
    An exception from anywhere OTHER than the `run_candidate(params)`
    call itself (e.g. a bug in `compare_signatures`, in this function's
    own bookkeeping, or in a caller's `on_attempt` callback) is
    DELIBERATELY NOT caught here and still propagates — callers should
    treat that case as a wiring/mechanism failure, distinct from a
    candidate's infrastructure failure, since it did not originate from
    executing a specific candidate.

    Stops and returns `final_status`:
      "MATCHED"                   as soon as any attempt matches
      "EXHAUSTED_NO_PROGRESS"     next_candidate_params() returned the
                                   same params as the last attempt (every
                                   target axis already matched despite an
                                   overall NOT_MATCHED status, or a
                                   boundary was hit and clipping produced
                                   no change) — continuing would loop
                                   forever on an identical candidate
      "EXHAUSTED_MAX_ITERATIONS"  ran calibration_config.max_iterations
                                   attempts without matching
      "CANDIDATE_FAILED"          run_candidate() raised — see above

    Never returns "MATCHED" without at least one attempt whose
    MatchReport.match_status is actually "MATCHED" — this function never
    fabricates a match. Never fabricates a signature for a failed
    candidate either.
    """
    tolerances = tolerances or MatchTolerances()
    calibration_config = calibration_config or CalibrationConfig()

    attempts: list = []
    params = initial_params

    def _notify(final_status: str) -> CalibrationResult:
        result = CalibrationResult(
            reference_experiment_id=reference_signature.experiment_id,
            reference_seed=reference_seed,
            candidate_id_prefix=candidate_id_prefix,
            attempts=list(attempts),
            final_status=final_status,
            calibration_config=calibration_config,
            tolerances=tolerances,
        )
        if on_attempt is not None:
            on_attempt(result)
        return result

    for i in range(1, calibration_config.max_iterations + 1):
        try:
            signature = run_candidate(params)
        except Exception as exc:  # noqa: BLE001 - deliberately broad: see docstring above
            attempts.append(
                FailedCalibrationAttempt(
                    iteration=i,
                    params=params,
                    failure_type=type(exc).__name__,
                    failure_message=str(exc),
                    timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
                )
            )
            return _notify("CANDIDATE_FAILED")

        report = compare_signatures(reference_signature, signature, tolerances)
        attempts.append(CalibrationAttempt(iteration=i, params=params, signature=signature, report=report))

        if report.match_status == "MATCHED":
            return _notify("MATCHED")

        next_params = next_candidate_params(params, report, calibration_config)
        if next_params == params:
            return _notify("EXHAUSTED_NO_PROGRESS")

        _notify("IN_PROGRESS")  # persist progress made so far; the search continues
        params = next_params

    return _notify("EXHAUSTED_MAX_ITERATIONS")


class CalibrationReportExists(FileExistsError):
    """Raised by save_calibration_report() when the target
    calibration_report.json already exists — see that function's
    docstring for why this is a hard error, not a silent overwrite."""


def _write_json_atomic(payload: dict, out_path: Path) -> Path:
    """Writes `payload` as indented JSON to `out_path` ATOMICALLY: the
    full content is written to a sibling temp file in the same directory,
    flushed and fsync'd, then moved onto `out_path` with `os.replace()` —
    which is atomic on both POSIX and Windows (unlike a plain rename,
    which Windows refuses if the destination already exists; `os.replace`
    handles that correctly on both platforms). A process interrupted
    (crash, kill, or an unrelated exception elsewhere) mid-write can only
    ever leave the TEMP file incomplete — `out_path` itself is always
    either its previous complete content or the new complete content,
    never a half-written, unparseable JSON file. The temp file lives in
    the SAME directory as `out_path` (not a generic system temp dir) so
    `os.replace()` is a same-filesystem move, which is what makes it
    atomic — a cross-filesystem "move" is actually a copy+delete and is
    not atomic. Stdlib only (`tempfile`, `os`) — no new dependency.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=out_path.parent, prefix=f".{out_path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, out_path)
    except BaseException:
        try:
            os.remove(tmp_name)
        except OSError:
            pass
        raise
    return out_path


def save_calibration_report(
    result: CalibrationResult,
    reference_signature: ExperimentSignature,
    experiments_dir: Path,
    allow_overwrite: bool = False,
) -> Path:
    """Persists the full calibration attempt history under
    data/experiments/<candidate_id_prefix>/calibration_report.json —
    alongside where save_match_report() already writes a single
    candidate's match_report.json, so both are discoverable in the same
    place. Includes every attempt's params, signature, match report
    (percentage deltas + tolerances + MATCHED/NOT_MATCHED), and absolute
    differences against the reference — everything Phase 4 of the
    final-experiment-design task requires in one machine-readable file.

    ATOMIC WRITE (2026-09-17 reliability hardening): the actual write now
    goes through `_write_json_atomic()` (temp file + `os.replace()`)
    instead of a plain `Path.write_text()` — calibration reports are
    research audit artifacts, and this function is now also called
    repeatedly DURING a live campaign (via `calibrate_matched_pair()`'s
    `on_attempt` callback, see that function's docstring) to persist
    progress after every single iteration, not only once at the end. A
    process interrupted between iterations must never be left with a
    corrupted, half-written JSON file at this path.

    COLLISION PROTECTION: `candidate_id_prefix` is caller-supplied and has
    no built-in uniqueness (e.g. the default value
    `"CALIBRATION_CANDIDATE"` is a fixed string) — a second calibration
    run using the same prefix would previously silently overwrite the
    first run's report at the identical path, destroying that run's
    audit trail with no record it ever happened. This function now
    refuses to do that: if `calibration_report.json` already exists at
    the target path, it raises `CalibrationReportExists` instead of
    overwriting, unless the caller explicitly passes `allow_overwrite=
    True`. This mirrors this project's existing convention elsewhere
    (e.g. `experiments/run_matrix.py::write_matrix_summary()` timestamps
    every matrix-run summary file specifically so one run's record can
    never overwrite a previous one). The caller is responsible for
    supplying a `candidate_id_prefix` that is unique per calibration
    attempt (e.g. including a timestamp) — this function only enforces
    that a collision, if one occurs anyway, is loud rather than silent.
    `allow_overwrite=True` is the intended mode for a live campaign's OWN
    repeated progress writes to ITS OWN path (see `on_attempt` above) —
    the collision check still applies to the very FIRST write of any
    given `candidate_id_prefix`, guarding against two DIFFERENT campaigns
    accidentally reusing the same prefix.
    """
    out_dir = Path(experiments_dir) / result.candidate_id_prefix
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "calibration_report.json"
    if out_path.exists() and not allow_overwrite:
        raise CalibrationReportExists(
            f"{out_path} already exists — refusing to silently overwrite a previous calibration "
            f"run's audit trail. Use a unique candidate_id_prefix per calibration attempt, or pass "
            f"allow_overwrite=True if overwriting this specific report is genuinely intended."
        )
    return _write_json_atomic(result.to_dict(reference_signature), out_path)
