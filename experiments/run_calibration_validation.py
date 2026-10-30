#!/usr/bin/env python
"""Live matched-signature calibration MECHANISM VALIDATION — NOT a
research data collection run.

Wires experiments/run_experiment.py into
experiments/match_quality.py::calibrate_matched_pair() end-to-end against
a real k3d cluster, to verify:

  1. a live reference signature can be generated from FC_HARDNEG_001's
     scenario (flash_crowd_hard_negative.yaml), under a distinct
     CALIBRATION_REF_ experiment_id so the official FC_HARDNEG_001 data
     point is never created/overwritten by this validation;
  2. a calibration candidate can actually be generated from
     apply_candidate_params() (edos.yaml + only users/report_complexity
     overridden — endpoint weights untouched);
  3. the candidate runs through the REAL experiment pipeline
     (experiments/run_experiment.py — no bypass, no fake signature);
  4. the resulting raw telemetry converts into a real ExperimentSignature;
  5. compare_signatures() / calibrate_matched_pair() / save_calibration_report()
     all operate on real, not synthetic, data.

`--max-iterations` defaults to 1 (a single-candidate wiring check); pass
a higher value (e.g. 5) to run an actual multi-iteration calibration
campaign. Either way this script never tunes toward a desired result —
`next_candidate_params()` alone decides the search direction — and never
silently retries a failed candidate.

RELIABILITY (2026-09-17): every iteration's outcome (success OR
infrastructure failure) is persisted to calibration_report.json
IMMEDIATELY, via calibrate_matched_pair()'s `on_attempt` callback — not
only once at the very end. A later iteration's failure can no longer
discard an earlier iteration's already-successful, already-real
telemetry from the record; see make_on_attempt()'s docstring.

All telemetry from this script is kept out of the official research
dataset:
  - experiment configs: experiments/configs/calibration/
  - candidate scenario YAML: traffic/scenarios/calibration/
  - features CSVs: data/features/calibration/ (NOT under data/features/
    root, so experiments/summarize_results.py::load_dataset()'s
    data/features/*.csv glob never sees them — same exclusion pattern
    already used by held_out/, baseline/, validation_live_gate/,
    smoke_test_matrix/)
  - calibration_report.json: data/experiments/calibration/
  - raw telemetry / per-run metadata: written by run_experiment.py to its
    normal data/raw/<id>/ and data/experiments/<id>/ locations, but under
    distinctly CALIBRATION_-prefixed experiment IDs that can never
    collide with or overwrite EDOS_001/002/003, FC_001/002/003,
    FC_HARDNEG_001, MIX_001, INTERLEAVED_001, or any other official
    experiment_id.

Usage:
    python experiments/run_calibration_validation.py --host http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.match_quality import (  # noqa: E402
    CalibrationCandidateParams,
    CalibrationConfig,
    CalibrationResult,
    apply_candidate_params,
    calibrate_matched_pair,
    compute_signature,
    save_calibration_report,
)
from experiments.run_experiment import run_experiment  # noqa: E402

CALIBRATION_FEATURES_DIR = REPO_ROOT / "data" / "features" / "calibration"
CALIBRATION_CONFIGS_DIR = REPO_ROOT / "experiments" / "configs" / "calibration"
CALIBRATION_SCENARIOS_DIR = REPO_ROOT / "traffic" / "scenarios" / "calibration"
CALIBRATION_REPORT_DIR = REPO_ROOT / "data" / "experiments" / "calibration"

REFERENCE_CONFIG_SOURCE = REPO_ROOT / "experiments" / "configs" / "FC_HARDNEG_001.yaml"
EDOS_SCENARIO_SOURCE = REPO_ROOT / "traffic" / "scenarios" / "edos.yaml"


def _write_config(base_config: dict, experiment_id: str) -> Path:
    """Writes a config dict to experiments/configs/calibration/<id>.yaml.
    Never touches the official experiments/configs/ directory itself —
    run_matrix.py's own config_dir.glob("*.yaml") is non-recursive, so
    this subdirectory is already excluded from any matrix run the same
    way experiments/configs/generated/ already is."""
    CALIBRATION_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CALIBRATION_CONFIGS_DIR / f"{experiment_id}.yaml"
    out_path.write_text(yaml.safe_dump(base_config, sort_keys=False))
    return out_path


def run_reference(host: str, prometheus_url: str, reference_id: str) -> dict:
    """ONE clean reference run using FC_HARDNEG_001's real scenario
    (flash_crowd_hard_negative.yaml), under a distinct experiment_id.
    Does NOT touch data/experiments/FC_HARDNEG_001 or
    data/raw/FC_HARDNEG_001 — confirmed by construction: `reference_id`
    is never "FC_HARDNEG_001" (checked below)."""
    if reference_id == "FC_HARDNEG_001":
        raise ValueError("refusing to run under the official FC_HARDNEG_001 experiment_id")

    config = yaml.safe_load(REFERENCE_CONFIG_SOURCE.read_text())
    original_seed = config["experiment"]["seed"]
    config["experiment"]["name"] = reference_id
    # scenario_file/duration/seed/cost_model/replica_sampler/prometheus/
    # detector are all left EXACTLY as FC_HARDNEG_001.yaml declares them —
    # this run uses the real flash_crowd_hard_negative.yaml scenario,
    # unmodified.
    config_path = _write_config(config, reference_id)

    print(f"=== REFERENCE RUN: {reference_id} (real seed={original_seed}, scenario={config['experiment']['scenario_file']}) ===")
    metadata = run_experiment(
        config_path, host, prometheus_url, output_features_dir=CALIBRATION_FEATURES_DIR
    )
    metadata["_source_seed"] = original_seed
    return metadata


def make_run_candidate(host: str, prometheus_url: str, session_ts: str):
    """Builds the run_candidate callable calibrate_matched_pair() will
    call. Each call: (1) receives CalibrationCandidateParams, (2) applies
    them to a FRESH copy of edos.yaml via apply_candidate_params() (never
    mutating the real scenario file), (3) assigns a unique candidate
    experiment ID (session-timestamp + attempt counter, so repeated runs
    of this script — or multiple attempts within one run — can never
    collide), (4) runs it through the REAL experiment pipeline
    (experiments.run_experiment.run_experiment — not bypassed, not
    mocked), (5) reads back the real raw timeseries.csv, (6) computes and
    returns a real ExperimentSignature. Raises (does not swallow) on any
    failure — calibrate_matched_pair() has no failure-handling of its
    own, and neither does this callable; a failed candidate run must
    propagate, not silently become an all-zero signature."""
    edos_scenario = yaml.safe_load(EDOS_SCENARIO_SOURCE.read_text())
    attempt_counter = {"n": 0}

    def run_candidate(params: CalibrationCandidateParams):
        attempt_counter["n"] += 1
        candidate_id = f"CALIBRATION_CANDIDATE_{session_ts}_A{attempt_counter['n']}"

        candidate_scenario = apply_candidate_params(edos_scenario, params)
        CALIBRATION_SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
        scenario_path = CALIBRATION_SCENARIOS_DIR / f"{candidate_id}.yaml"
        scenario_path.write_text(yaml.safe_dump(candidate_scenario, sort_keys=False))

        # Mirror EDOS_001.yaml's non-behavioural config structure exactly;
        # only experiment.name/scenario_file/seed/duration differ.
        reference_config = yaml.safe_load((REPO_ROOT / "experiments" / "configs" / "EDOS_001.yaml").read_text())
        candidate_config = {
            "experiment": {
                "name": candidate_id,
                "label": 1,
                "scenario_type": "edos",
                "scenario_file": str(scenario_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "duration_seconds": 75,  # matches the reference run's duration, per final_matrix.yaml's design note
                "seed": params.seed,
            },
            "detector": reference_config["detector"],
            "cost_model": reference_config["cost_model"],
            "replica_sampler": reference_config["replica_sampler"],
            "prometheus": {"base_url": prometheus_url},
        }
        config_path = _write_config(candidate_config, candidate_id)

        print(f"=== CANDIDATE RUN {attempt_counter['n']}: {candidate_id} (users={params.users}, report_complexity={params.report_complexity}, seed={params.seed}) ===")
        metadata = run_experiment(
            config_path, host, prometheus_url, output_features_dir=CALIBRATION_FEATURES_DIR
        )

        raw_path = Path(metadata["timeseries_path"])
        raw = pd.read_csv(raw_path)
        signature = compute_signature(candidate_id, raw)
        print(f"    -> candidate signature: {signature}")
        return signature

    return run_candidate


def make_on_attempt(reference_signature, report_dir: Path):
    """Builds the `on_attempt` callback passed to calibrate_matched_pair()
    (reliability hardening, 2026-09-17). Persists the CURRENT interim
    CalibrationResult after every single iteration — success or failure —
    so a later iteration's failure can never erase an earlier iteration's
    already-recorded success (the exact failure mode observed live across
    three prior sessions: a mid-campaign ConnectionError propagated
    uncaught, discarding every previously-successful attempt's data with
    nothing ever written to disk).

    The first call uses save_calibration_report()'s default collision
    protection (allow_overwrite=False) — refusing to clobber a
    DIFFERENT, pre-existing campaign that happens to reuse the same
    candidate_id_prefix. Every SUBSEQUENT call in the same campaign uses
    allow_overwrite=True, since by then we already know this exact path
    is this campaign's own, and it is being progressively updated by
    design, not collided with.
    """
    written_once = {"flag": False}

    def on_attempt(interim_result: CalibrationResult) -> None:
        save_calibration_report(
            interim_result, reference_signature, report_dir, allow_overwrite=written_once["flag"]
        )
        written_once["flag"] = True
        print(f"    [progress persisted: {interim_result.final_status}, {len(interim_result.attempts)} attempt(s) recorded]")

    return on_attempt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--max-iterations", type=int, default=1, help="Wiring test default: exactly one real candidate run.")
    args = parser.parse_args()

    session_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    reference_id = f"CALIBRATION_REF_FC_HARDNEG_001_{session_ts}"

    # Deliberately OUTSIDE the try/except below: a reference-run failure
    # is its own distinct category (REFERENCE_FAILED) and must propagate
    # exactly as before — it is not a calibration-campaign concern at all.
    reference_metadata = run_reference(args.host, args.prometheus_url, reference_id)
    reference_raw = pd.read_csv(Path(reference_metadata["timeseries_path"]))
    reference_signature = compute_signature(reference_id, reference_raw)
    print(f"\n=== REFERENCE SIGNATURE ===\n{reference_signature}\n")

    run_candidate = make_run_candidate(args.host, args.prometheus_url, session_ts)
    on_attempt = make_on_attempt(reference_signature, CALIBRATION_REPORT_DIR)

    initial_params = CalibrationCandidateParams(users=8, report_complexity=60, seed=48)
    calibration_config = CalibrationConfig(max_iterations=args.max_iterations)

    # calibrate_matched_pair() itself now catches a candidate's own
    # infrastructure failures internally and returns a CalibrationResult
    # with final_status="CANDIDATE_FAILED" rather than raising (see its
    # docstring) — so anything that STILL escapes this call is, by
    # construction, NOT a candidate-execution failure: it is a bug in the
    # calibration mechanism itself (compare_signatures, next_candidate_
    # params, this script's own on_attempt callback, etc.) — classified
    # here as CALIBRATION_WIRING_FAILED, a third, distinct category from
    # both CANDIDATE_FAILED and a scientific NOT_MATCHED/MATCHED outcome.
    try:
        result = calibrate_matched_pair(
            reference_signature,
            initial_params,
            run_candidate,
            candidate_id_prefix=f"CALIBRATION_RUN_{session_ts}",
            calibration_config=calibration_config,
            reference_seed=reference_metadata["_source_seed"],
            on_attempt=on_attempt,
        )
    except Exception:
        print("\n=== CALIBRATION_WIRING_FAILED ===")
        print("An exception escaped calibrate_matched_pair() itself (not a candidate's own "
              "run_candidate() call, which is caught internally) — this indicates a bug in the "
              "calibration mechanism, not an infrastructure failure of one candidate.")
        raise

    print(f"\n=== CALIBRATION RESULT: {result.final_status} ===")
    print(f"Calibration report: {CALIBRATION_REPORT_DIR / result.candidate_id_prefix / 'calibration_report.json'}")
    print(json.dumps(result.to_dict(reference_signature), indent=2, default=str))
    return 0 if result.final_status in {"MATCHED", "EXHAUSTED_NO_PROGRESS", "EXHAUSTED_MAX_ITERATIONS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
