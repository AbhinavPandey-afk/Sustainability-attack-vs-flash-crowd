#!/usr/bin/env python
"""Official matched-signature (E6) experiment — anchored to the ACTUAL
FC_HARDNEG_001 experiment_id, not a calibration-session stand-in.

Background: the live calibration/validation campaigns (see
experiments/match_quality.py, experiments/run_match_validation.py) found
and repeatedly (6/6) confirmed a MATCHED operating point (EDoS
users=2, report_complexity=30) against a REFERENCE that was a separate
live re-run of FC_HARDNEG_001's own scenario/config
(flash_crowd_hard_negative.yaml, seed 42) under a
CALIBRATION_REF_FC_HARDNEG_001_* experiment_id — never against the
official FC_HARDNEG_001 experiment_id itself, which by then already had
its own real, clean, persisted data (data/experiments/FC_HARDNEG_001/).

This script closes that specific gap, and ONLY that gap:
  1. Loads FC_HARDNEG_001's ALREADY-COLLECTED raw timeseries/features —
     does NOT re-run it (it is already clean; re-running it would be
     pointless duplication of existing evidence, not new evidence).
  2. Runs ONE fresh EDoS candidate at the ALREADY-CALIBRATED operating
     point (users=2, report_complexity=30) — the exact same values found
     by the search, never re-derived or adjusted here — through the
     normal, unmodified experiments/run_experiment.py pipeline, so the
     candidate gets full behavioural/cost/scaling features, not just an
     ExperimentSignature.
  3. Computes compare_signatures() between the two using the UNCHANGED
     MatchTolerances() defaults (25% / +/-1 replica) — never loosened.
  4. Persists a match_report.json under
     data/experiments/<candidate_id>/, via the existing
     save_match_report() primitive.

Deliberately reuses match_quality.py's existing primitives
(apply_candidate_params, compute_signature, compare_signatures,
save_match_report) and run_experiment.py's existing pipeline unmodified —
no new matching methodology, no new tolerance, no new operating point.

The candidate's features are written to an isolated pending-review
location (data/features/matched_e6_pending_review/), mirroring this
project's existing gen2_pending_review/ and e5_pending_review/
convention — NOT the main training glob, NOT promoted.

Usage:
    python experiments/run_official_matched_e6.py \
        --host http://localhost:8000 --prometheus-url http://localhost:9090 \
        --candidate-id EDOS_MATCHED_E6_001 --seed 48
"""
from __future__ import annotations

import argparse
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
    MatchTolerances,
    apply_candidate_params,
    compare_signatures,
    compute_signature,
    save_match_report,
)
from experiments.run_experiment import run_experiment  # noqa: E402

CANDIDATE_FEATURES_DIR = REPO_ROOT / "data" / "features" / "matched_e6_pending_review"
CANDIDATE_SCENARIOS_DIR = REPO_ROOT / "traffic" / "scenarios" / "matched_e6_pending_review"
CANDIDATE_CONFIGS_DIR = REPO_ROOT / "experiments" / "configs" / "matched_e6_pending_review"
EDOS_SCENARIO_SOURCE = REPO_ROOT / "traffic" / "scenarios" / "edos.yaml"

REFERENCE_EXPERIMENT_ID = "FC_HARDNEG_001"
REFERENCE_METADATA_PATH = REPO_ROOT / "data" / "experiments" / REFERENCE_EXPERIMENT_ID / "metadata.json"

# The already-calibrated operating point (experiments/match_quality.py's
# live search result, docs/experiment_protocol.md's Gen2/E6 sections) —
# NOT re-derived here, per the explicit "do not invent a new operating
# point" instruction.
CALIBRATED_USERS = 2
CALIBRATED_REPORT_COMPLEXITY = 30


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", required=True)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--candidate-id", default="EDOS_MATCHED_E6_001")
    parser.add_argument("--seed", type=int, default=48, help="Seed for this candidate run (the calibration search's own converged seed)")
    args = parser.parse_args()

    # --- Reference: load the OFFICIAL FC_HARDNEG_001's already-collected
    # data, never re-run it. ---
    ref_metadata = json.loads(REFERENCE_METADATA_PATH.read_text())
    ref_raw = pd.read_csv(ref_metadata["timeseries_path"])
    reference_signature = compute_signature(REFERENCE_EXPERIMENT_ID, ref_raw)
    reference_seed = ref_metadata["seed"]
    print(f"=== OFFICIAL REFERENCE (not re-run): {REFERENCE_EXPERIMENT_ID} (seed={reference_seed}) ===")
    print(f"{reference_signature}\n")

    # --- Candidate: one fresh live EDoS run at the already-calibrated
    # operating point. ---
    edos_scenario = yaml.safe_load(EDOS_SCENARIO_SOURCE.read_text())
    candidate_scenario = apply_candidate_params(
        edos_scenario,
        CalibrationCandidateParams(users=CALIBRATED_USERS, report_complexity=CALIBRATED_REPORT_COMPLEXITY, seed=args.seed),
    )
    CANDIDATE_SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)
    scenario_path = CANDIDATE_SCENARIOS_DIR / f"{args.candidate_id}.yaml"
    scenario_path.write_text(yaml.safe_dump(candidate_scenario, sort_keys=False))

    reference_config = yaml.safe_load((REPO_ROOT / "experiments" / "configs" / "FC_HARDNEG_001.yaml").read_text())
    candidate_config = {
        "experiment": {
            "name": args.candidate_id,
            "label": 1,
            "scenario_type": "edos",
            "scenario_file": str(scenario_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "duration_seconds": reference_config["experiment"]["duration_seconds"],  # identical to the reference's duration
            "seed": args.seed,
        },
        "detector": reference_config["detector"],
        "cost_model": reference_config["cost_model"],
        "replica_sampler": reference_config["replica_sampler"],
        "prometheus": {"base_url": args.prometheus_url},
    }
    CANDIDATE_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    config_path = CANDIDATE_CONFIGS_DIR / f"{args.candidate_id}.yaml"
    config_path.write_text(yaml.safe_dump(candidate_config, sort_keys=False))

    print(f"=== CANDIDATE RUN: {args.candidate_id} (users={CALIBRATED_USERS}, report_complexity={CALIBRATED_REPORT_COMPLEXITY}, seed={args.seed}) ===")
    metadata = run_experiment(config_path, args.host, args.prometheus_url, output_features_dir=CANDIDATE_FEATURES_DIR)

    candidate_raw = pd.read_csv(metadata["timeseries_path"])
    candidate_signature = compute_signature(args.candidate_id, candidate_raw)
    print(f"    -> candidate signature: {candidate_signature}\n")

    tolerances = MatchTolerances()  # unchanged defaults — never loosened
    report = compare_signatures(reference_signature, candidate_signature, tolerances)
    report_path = save_match_report(report, REPO_ROOT / "data" / "experiments")

    print(f"=== MATCH RESULT: {report.match_status} ===")
    print(json.dumps(report.to_dict(), indent=2))
    print(f"\nmatch_report.json -> {report_path}")
    print(f"candidate features -> {metadata['features_path']}")
    print(f"reference features (pre-existing, unmodified) -> data/features/{REFERENCE_EXPERIMENT_ID}.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
