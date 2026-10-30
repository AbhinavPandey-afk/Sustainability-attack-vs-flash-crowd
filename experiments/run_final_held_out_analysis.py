#!/usr/bin/env python
"""Final-session supplementary analysis — reuses experiments/summarize_results.py's
already-trained model and existing primitives ONLY (models/feature_sets.py,
models/train_lightgbm.py, models/evaluate.py, models/dataset.py,
baselines/rate_limiter.py, baselines/volumetric_detector.py). Adds no new
methodology; every function called here already exists elsewhere in the
repository.

Must be run AFTER `python experiments/summarize_results.py --seed 42`
(which writes results/models/cascade_lightgbm.joblib and the main
ablation/baseline/SHAP outputs this script builds on).

Produces, in addition to summarize_results.py's own outputs:
  - results/tables/single_family_ablation_results.csv
      cost-only / scaling-only / behavioural-only LightGBM models,
      trained/evaluated on the IDENTICAL experiment-level split
      summarize_results.py used (same seed, same random_split_by_experiment
      call) -- reuses feature_sets.py's pre-existing COST_COLUMNS/
      SCALING_COLUMNS/BEHAVIOUR_COLUMNS constants; no new feature
      definitions.
  - results/tables/duplicate_feature_sensitivity.csv
      C_proposed_full retrained with `report_generation_ratio` (a known
      exact duplicate of `expensive_endpoint_ratio` in this application --
      see docs/feature_dictionary.md) removed, to check the duplicate is
      not silently double-counted as two independent signals.
  - results/metrics/extra_held_out_evaluation.json
      the ALREADY-TRAINED C_proposed_full model evaluated (never retrained)
      against Gen2 (data/features/gen2_pending_review/), E5
      (data/features/e5_pending_review/), and the official matched-E6 pair
      (data/features/matched_e6_pending_review/) -- reuses
      experiments.summarize_results.evaluate_held_out() unchanged, the
      exact function already used for MIX_001/INTERLEAVED_001.
  - Per-window prediction tables (printed, not persisted as new files) for
      every held-out experiment, preserving chronological window order --
      the basis for this session's Gen2/E5/matched-E6/MIX/interleaved
      analysis.

Deliberately does NOT retrain on any held-out data, does NOT modify
Gen1/Gen2/E5/matched-E6 data, and does NOT touch the rate-limiter
threshold, cost model, or HPA configuration.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines import rate_limiter  # noqa: E402
from experiments.summarize_results import evaluate_held_out, load_dataset  # noqa: E402
from models import evaluate as model_evaluate  # noqa: E402
from models import feature_sets, train_lightgbm  # noqa: E402
from models.dataset import assert_no_overlap, random_split_by_experiment  # noqa: E402

RESULTS = REPO_ROOT / "results"
FEATURES_DIR = REPO_ROOT / "data" / "features"


def main() -> int:
    df = load_dataset(FEATURES_DIR)
    window_seconds = df["window_seconds"].max()
    df = df[df["window_seconds"] == window_seconds].reset_index(drop=True)
    # IDENTICAL call (same seed, same fractions) to experiments/summarize_results.py::run() --
    # reproduces the exact same split, never persisted/re-derived differently.
    train_df, val_df, test_df = random_split_by_experiment(df, test_fraction=0.3, val_fraction=0.3, seed=42)
    assert_no_overlap(train_df, val_df, test_df)
    print("TRAIN:", sorted(train_df.experiment_id.unique()))
    print("VAL:  ", sorted(val_df.experiment_id.unique()))
    print("TEST: ", sorted(test_df.experiment_id.unique()))

    lightgbm_trained = joblib.load(RESULTS / "models" / "cascade_lightgbm.joblib")

    # ---- Single-family ablations (existing column-list constants only) ----
    single_family = {
        "cost_only": feature_sets.COST_COLUMNS,
        "scaling_only": feature_sets.SCALING_COLUMNS,
        "behavioural_only": feature_sets.BEHAVIOUR_COLUMNS,
    }
    rows = []
    for name, cols in single_family.items():
        trained = train_lightgbm.train(train_df[cols], train_df["label"], val_df[cols], val_df["label"])
        proba, preds = trained.predict_proba(test_df[cols]), trained.predict(test_df[cols])
        m = model_evaluate.classification_metrics(test_df["label"], preds, proba)
        m["model"] = name
        rows.append(m)
        print(name, m)
    pd.DataFrame(rows).to_csv(RESULTS / "tables" / "single_family_ablation_results.csv", index=False)

    # ---- Duplicate-feature sensitivity (report_generation_ratio == expensive_endpoint_ratio) ----
    c_cols = [c for c in feature_sets.ABLATION_FEATURE_SETS["C_proposed_full"] if c != "report_generation_ratio"]
    trained = train_lightgbm.train(train_df[c_cols], train_df["label"], val_df[c_cols], val_df["label"])
    proba, preds = trained.predict_proba(test_df[c_cols]), trained.predict(test_df[c_cols])
    dup_metrics = model_evaluate.classification_metrics(test_df["label"], preds, proba)
    dup_metrics["model"] = "C_proposed_full_minus_report_generation_ratio"
    print("duplicate-feature sensitivity:", dup_metrics)
    pd.DataFrame([dup_metrics]).to_csv(RESULTS / "tables" / "duplicate_feature_sensitivity.csv", index=False)

    # ---- Gen2 / E5 / matched-E6 held-out evaluation (existing evaluate_held_out(), unmodified) ----
    threshold = rate_limiter.calibrate_threshold(train_df.loc[train_df["label"] == 0, "request_rate"])
    extra_held_out = {
        "gen2": evaluate_held_out(FEATURES_DIR / "gen2_pending_review", lightgbm_trained, threshold),
        "e5": evaluate_held_out(FEATURES_DIR / "e5_pending_review", lightgbm_trained, threshold),
        "matched_e6": evaluate_held_out(FEATURES_DIR / "matched_e6_pending_review", lightgbm_trained, threshold),
    }
    (RESULTS / "metrics" / "extra_held_out_evaluation.json").write_text(json.dumps(extra_held_out, indent=2, default=str))
    print(json.dumps(extra_held_out, indent=2, default=str))

    # ---- Per-window predictions, chronological order preserved ----
    def per_row(path: Path) -> pd.DataFrame:
        d = pd.read_csv(path)
        X = feature_sets.select_features(d, "C_proposed_full")
        out = d[
            ["window_end", "label", "request_rate", "expensive_endpoint_ratio", "mean_replica_count",
             "max_replica_count", "estimated_cost", "cost_per_request", "cost_to_traffic_ratio"]
        ].copy()
        out["prediction"] = lightgbm_trained.predict(X)
        out["proba_edos"] = lightgbm_trained.predict_proba(X)
        out["correct"] = out["label"] == out["prediction"]
        return out

    for eid, path in [
        ("MIX_001", FEATURES_DIR / "held_out" / "MIX_001.csv"),
        ("INTERLEAVED_001", FEATURES_DIR / "held_out" / "INTERLEAVED_001.csv"),
        ("INTERLEAVED_EDOS_FIRST_001", FEATURES_DIR / "held_out" / "INTERLEAVED_EDOS_FIRST_001.csv"),
        ("EDOS_MATCHED_E6_001", FEATURES_DIR / "matched_e6_pending_review" / "EDOS_MATCHED_E6_001.csv"),
        ("FC_HARDNEG_001_reference", FEATURES_DIR / "FC_HARDNEG_001.csv"),
    ]:
        print(f"\n=== {eid} per-window ===")
        print(per_row(path).to_string(index=False))

    for i in range(1, 6):
        print(f"\n=== FC_HARDNEG_GEN2_{i:03d} per-window ===")
        print(per_row(FEATURES_DIR / "gen2_pending_review" / f"FC_HARDNEG_GEN2_{i:03d}.csv").to_string(index=False))
    for i in range(1, 6):
        print(f"\n=== EDOS_STEALTH_{i:03d} per-window ===")
        print(per_row(FEATURES_DIR / "e5_pending_review" / f"EDOS_STEALTH_{i:03d}.csv").to_string(index=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
