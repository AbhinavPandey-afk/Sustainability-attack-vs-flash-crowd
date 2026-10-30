#!/usr/bin/env python
"""Repeated-seed MATCH VALIDATION for an already-calibrated operating
point — NOT a calibration search, NOT final research data collection.

Given a fixed (users, report_complexity) pair that already produced a
MATCHED result once (via experiments/match_quality.py::calibrate_matched_pair()),
this script re-runs that SAME candidate under several seeds against the
SAME, already-persisted reference signature (loaded, never re-run), to
test whether the match reproduces or was a single noisy observation.

Deliberately reuses existing, unmodified primitives only:
  apply_candidate_params()   same pure function, same edos.yaml source,
                              same untouched behavioural weights
  run_experiment()           same real experiment pipeline, no bypass
  compute_signature()        same real signature computation
  compare_signatures()       same real comparison, SAME MatchTolerances
                              defaults (25% / +/-1 replica) — never
                              loosened, never tuned toward a result

This is intentionally NOT built on calibrate_matched_pair()'s search
loop: there is no "next candidate" being searched for here — every run
uses the IDENTICAL (users, report_complexity), varying only the seed.
That is a repeated-measurement / stability question, not a search
question, so it gets its own minimal, honestly-scoped persistence
schema instead of overloading the search campaign's MATCHED/EXHAUSTED_*
vocabulary (which describes when a SEARCH stops, not whether a fixed
point reproduces).

Every run's outcome (success or infrastructure failure) is persisted
IMMEDIATELY and atomically, exactly like the reliability-hardened
calibration campaign — a later seed's failure can never erase an
earlier seed's real result.

All telemetry is kept out of the official research dataset, under a
dedicated data/experiments/calibration_validation/ / data/features/
calibration_validation/ location, distinct from both the official
dataset and the calibration SEARCH artifacts under
data/experiments/calibration/.

Usage:
    python experiments/run_match_validation.py \
        --host http://localhost:8000 \
        --campaign-report data/experiments/calibration/CALIBRATION_RUN_20260917T074935Z/calibration_report.json \
        --users 2 --report-complexity 30 \
        --seeds 48,48,49,50,51,52
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.match_quality import (  # noqa: E402
    CalibrationCandidateParams,
    ExperimentSignature,
    MatchTolerances,
    apply_candidate_params,
    compare_signatures,
    compute_signature,
)
from experiments.run_experiment import run_experiment  # noqa: E402

VALIDATION_FEATURES_DIR = REPO_ROOT / "data" / "features" / "calibration_validation"
VALIDATION_CONFIGS_DIR = REPO_ROOT / "experiments" / "configs" / "calibration_validation"
VALIDATION_SCENARIOS_DIR = REPO_ROOT / "traffic" / "scenarios" / "calibration_validation"
VALIDATION_REPORT_DIR = REPO_ROOT / "data" / "experiments" / "calibration_validation"

EDOS_SCENARIO_SOURCE = REPO_ROOT / "traffic" / "scenarios" / "edos.yaml"


def _write_json_atomic(payload: dict, out_path: Path) -> Path:
    """Same atomic-write discipline as match_quality.py::_write_json_atomic
    (temp file in the same directory + os.replace()) — duplicated here
    rather than imported, since that helper is a private (leading-
    underscore) implementation detail of match_quality.py, not part of
    its public API."""
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


def load_reference(campaign_report_path: Path) -> tuple[ExperimentSignature, int | None, str]:
    """Loads the REAL, already-collected reference signature from an
    existing calibration campaign's report — never re-runs it, per this
    task's explicit instruction not to regenerate or modify the
    reference."""
    d = json.loads(campaign_report_path.read_text())
    signature = ExperimentSignature(**d["reference_signature"])
    return signature, d["reference_seed"], d["reference_experiment_id"]


def run_one_candidate(host: str, prometheus_url: str, users: int, report_complexity: int, seed: int, candidate_id: str) -> ExperimentSignature:
    """One real validation run: apply_candidate_params() (unmodified
    weights) -> real run_experiment() -> real compute_signature().
    Raises on any failure — no synthetic fallback, no fabricated
    signature."""
    edos_scenario = yaml.safe_load(EDOS_SCENARIO_SOURCE.read_text())
    candidate_scenario = apply_candidate_params(
        edos_scenario, CalibrationCandidateParams(users=users, report_complexity=report_complexity, seed=seed)
    )
    VALIDATION_SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenario_path = VALIDATION_SCENARIOS_DIR / f"{candidate_id}.yaml"
    scenario_path.write_text(yaml.safe_dump(candidate_scenario, sort_keys=False))

    reference_config = yaml.safe_load((REPO_ROOT / "experiments" / "configs" / "EDOS_001.yaml").read_text())
    candidate_config = {
        "experiment": {
            "name": candidate_id,
            "label": 1,
            "scenario_type": "edos",
            "scenario_file": str(scenario_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "duration_seconds": 75,  # identical to the reference run's duration — unchanged
            "seed": seed,
        },
        "detector": reference_config["detector"],
        "cost_model": reference_config["cost_model"],
        "replica_sampler": reference_config["replica_sampler"],
        "prometheus": {"base_url": prometheus_url},
    }
    VALIDATION_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    config_path = VALIDATION_CONFIGS_DIR / f"{candidate_id}.yaml"
    config_path.write_text(yaml.safe_dump(candidate_config, sort_keys=False))

    print(f"=== VALIDATION RUN: {candidate_id} (users={users}, report_complexity={report_complexity}, seed={seed}) ===")
    metadata = run_experiment(config_path, host, prometheus_url, output_features_dir=VALIDATION_FEATURES_DIR)

    raw = pd.read_csv(Path(metadata["timeseries_path"]))
    signature = compute_signature(candidate_id, raw)
    print(f"    -> signature: {signature}")
    return signature


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--campaign-report", required=True, help="Path to the existing calibration_report.json whose reference_signature to reuse")
    parser.add_argument("--users", type=int, required=True)
    parser.add_argument("--report-complexity", type=int, required=True)
    parser.add_argument("--seeds", required=True, help="Comma-separated list of seeds, e.g. 48,48,49,50,51,52 (repeats allowed and expected)")
    args = parser.parse_args()

    seeds = [int(s.strip()) for s in args.seeds.split(",")]

    reference_signature, reference_seed, reference_experiment_id = load_reference(Path(args.campaign_report))
    print(f"=== REUSED REFERENCE (not re-run): {reference_experiment_id} (seed={reference_seed}) ===")
    print(f"{reference_signature}\n")

    tolerances = MatchTolerances()  # unchanged defaults — never loosened
    session_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = VALIDATION_REPORT_DIR / session_ts / "match_validation_report.json"

    runs: list[dict] = []
    seed_occurrence: dict[int, int] = {}

    def persist() -> None:
        payload = {
            "purpose": "repeated-seed match validation of an already-calibrated operating point — NOT a search, NOT final research data",
            "reference_experiment_id": reference_experiment_id,
            "reference_seed": reference_seed,
            "reference_signature": asdict(reference_signature),
            "candidate_users": args.users,
            "candidate_report_complexity": args.report_complexity,
            "tolerances": asdict(tolerances),
            "seeds_planned": seeds,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "runs": runs,
        }
        _write_json_atomic(payload, report_path)
        print(f"    [progress persisted: {len(runs)} run(s) recorded -> {report_path}]")

    for seed in seeds:
        seed_occurrence[seed] = seed_occurrence.get(seed, 0) + 1
        run_index = seed_occurrence[seed]
        candidate_id = f"CALIBRATION_VALIDATION_{session_ts}_SEED{seed}_R{run_index}"

        try:
            signature = run_one_candidate(args.host, args.prometheus_url, args.users, args.report_complexity, seed, candidate_id)
        except Exception as exc:
            runs.append(
                {
                    "seed": seed,
                    "run_index": run_index,
                    "candidate_experiment_id": candidate_id,
                    "status": "FAILED",
                    "failure_type": type(exc).__name__,
                    "failure_message": str(exc),
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            )
            persist()
            print(f"    !! seed {seed} run {run_index} FAILED ({type(exc).__name__}) — continuing to next seed (each seed is an independent replicate, not a search step)")
            continue

        report = compare_signatures(reference_signature, signature, tolerances)
        runs.append(
            {
                "seed": seed,
                "run_index": run_index,
                "candidate_experiment_id": candidate_id,
                "status": "SUCCESS",
                "signature": asdict(signature),
                "match_report": report.to_dict(),
                "match_status": report.match_status,
            }
        )
        persist()

    n_success = sum(1 for r in runs if r["status"] == "SUCCESS")
    n_failed = sum(1 for r in runs if r["status"] == "FAILED")
    n_matched = sum(1 for r in runs if r["status"] == "SUCCESS" and r["match_status"] == "MATCHED")
    print(f"\n=== VALIDATION CAMPAIGN COMPLETE: {n_success} scientifically evaluated "
          f"({n_matched} MATCHED, {n_success - n_matched} NOT_MATCHED), {n_failed} infrastructure failures ===")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
