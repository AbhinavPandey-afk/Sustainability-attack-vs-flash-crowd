#!/usr/bin/env python
"""Assembles all collected experiment features into one labeled dataset,
splits by experiment (never by window — CLAUDE.md principle #12), trains
LightGBM + Random Forest (+ ablation study), evaluates against the rate-
limiter/volumetric baselines, runs SHAP, and writes
results/{tables,metrics,figures} (CLAUDE.md sections 24, 38).

This does NOT fabricate results: everything here operates on whatever
real feature CSVs exist under data/features/ (produced by
experiments/run_experiment.py). Too few/no experiments produces a small
or empty result with an explicit warning, never invented numbers.

Usage:
    python experiments/summarize_results.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import ConfusionMatrixDisplay, PrecisionRecallDisplay, RocCurveDisplay  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from baselines import rate_limiter, volumetric_detector  # noqa: E402
from feature_engineering.validate_features import validate  # noqa: E402
from models import evaluate as model_evaluate  # noqa: E402
from models import explain, feature_sets, train_lightgbm, train_random_forest  # noqa: E402
from models.dataset import assert_no_overlap, random_split_by_experiment  # noqa: E402


def load_dataset(features_dir: Path) -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(features_dir.glob("*.csv"))]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def evaluate_held_out(held_out_dir: Path, lightgbm_trained, threshold: float) -> dict:
    """Evaluates the already-trained C_proposed_full model (and the same
    baselines used for the main test split) on E3/MIX and E4/INTERLEAVED
    feature CSVs kept out of the main train/val/test split — CLAUDE.md
    section 24's "evaluate ... not merely in isolation" requirement.
    Returns {} entries only for files that actually exist; never invents
    a result for a scenario that wasn't actually run.
    """
    baseline_cols = ["window_end", "request_rate", "label", "estimated_cost"]
    results: dict = {}
    if not held_out_dir.exists():
        return results

    for path in sorted(held_out_dir.glob("*.csv")):
        name = path.stem
        df = pd.read_csv(path)
        if df.empty or "label" not in df.columns:
            continue

        X = feature_sets.select_features(df, "C_proposed_full")
        proba = lightgbm_trained.predict_proba(X)
        preds = lightgbm_trained.predict(X)
        cascade_metrics = model_evaluate.classification_metrics(df["label"], preds, proba)
        cascade_metrics["n_windows"] = len(df)
        cascade_metrics["label_distribution"] = df["label"].value_counts().to_dict()

        entry = {"cascade_lightgbm": cascade_metrics}
        if all(c in df.columns for c in baseline_cols):
            entry["rate_limiter"] = rate_limiter.evaluate(df[baseline_cols], threshold)
            entry["volumetric_detector"] = volumetric_detector.evaluate(df[baseline_cols])
        results[name] = entry

    return results


def run(features_dir: Path, results_dir: Path, seed: int, held_out_dir: Path | None = None) -> int:
    (results_dir / "tables").mkdir(parents=True, exist_ok=True)
    (results_dir / "metrics").mkdir(parents=True, exist_ok=True)
    (results_dir / "figures").mkdir(parents=True, exist_ok=True)

    df = load_dataset(features_dir)
    if df.empty:
        print(f"No feature CSVs found in {features_dir} — run experiments/run_experiment.py first.")
        return 1

    report = validate(df)
    if not report.ok:
        print("Dataset validation FAILED:", report.errors)
        return 1

    n_experiments = df["experiment_id"].nunique()
    print(f"Loaded {len(df)} feature rows from {n_experiments} experiments.")
    if n_experiments < 3:
        print(
            "WARNING: fewer than 3 distinct experiments — this is a small-scale "
            "proof-of-concept dataset, not a statistically meaningful research result. "
            "CLAUDE.md sections 13/25 call for a much larger experiment matrix and "
            "repeated runs before drawing research conclusions."
        )

    window_seconds = df["window_seconds"].max()
    df = df[df["window_seconds"] == window_seconds].reset_index(drop=True)

    train_df, val_df, test_df = random_split_by_experiment(df, test_fraction=0.3, val_fraction=0.3, seed=seed)
    assert_no_overlap(train_df, val_df, test_df)

    summary = {
        "n_total_rows": len(df),
        "n_experiments": n_experiments,
        "window_seconds_used": float(window_seconds),
        "train_experiments": sorted(train_df["experiment_id"].unique().tolist()),
        "val_experiments": sorted(val_df["experiment_id"].unique().tolist()),
        "test_experiments": sorted(test_df["experiment_id"].unique().tolist()),
        "models": {},
        "baselines": {},
    }

    if len(train_df) == 0 or len(test_df) == 0:
        print("Not enough experiments to form a non-empty train/test split with this seed/fractions.")
        (results_dir / "metrics" / "experiment_summary.json").write_text(json.dumps(summary, indent=2, default=str))
        return 1

    ablation_results = []
    lightgbm_trained = None
    for model_name in feature_sets.ABLATION_FEATURE_SETS:
        X_train = feature_sets.select_features(train_df, model_name)
        X_val = feature_sets.select_features(val_df, model_name) if len(val_df) else X_train.iloc[0:0]
        X_test = feature_sets.select_features(test_df, model_name)
        y_train = train_df["label"]
        y_val = val_df["label"] if len(val_df) else train_df["label"].iloc[0:0]
        y_test = test_df["label"]

        trained = train_lightgbm.train(X_train, y_train, X_val, y_val)
        if model_name == "C_proposed_full":
            lightgbm_trained = trained

        proba = trained.predict_proba(X_test)
        preds = trained.predict(X_test)
        metrics = model_evaluate.classification_metrics(y_test, preds, proba)
        metrics["model"] = model_name
        ablation_results.append(metrics)
        summary["models"][model_name] = metrics

    pd.DataFrame(ablation_results).to_csv(results_dir / "tables" / "ablation_results.csv", index=False)

    if lightgbm_trained is not None:
        # Persisted so the webapp dashboard (webapp/backend/prediction.py)
        # can score a just-completed run's real feature windows without
        # retraining in-process — CLAUDE.md section 3/O3's "detector should
        # produce classification + confidence" for a live run, not only the
        # aggregate test-split metrics already written above.
        import joblib

        models_dir = results_dir / "models"
        models_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(lightgbm_trained, models_dir / "cascade_lightgbm.joblib")

    X_train_c = feature_sets.select_features(train_df, "C_proposed_full")
    X_val_c = feature_sets.select_features(val_df, "C_proposed_full") if len(val_df) else X_train_c.iloc[0:0]
    X_test_c = feature_sets.select_features(test_df, "C_proposed_full")
    y_val_c = val_df["label"] if len(val_df) else train_df["label"].iloc[0:0]
    rf_trained = train_random_forest.train(X_train_c, train_df["label"], X_val_c, y_val_c)
    rf_proba = rf_trained.predict_proba(X_test_c)
    rf_preds = rf_trained.predict(X_test_c)
    rf_metrics = model_evaluate.classification_metrics(test_df["label"], rf_preds, rf_proba)
    rf_metrics["model"] = "RandomForest_C_proposed_full"

    lgb_c_metrics = next(m for m in ablation_results if m["model"] == "C_proposed_full")
    pd.DataFrame([{**lgb_c_metrics, "model": "LightGBM_C_proposed_full"}, rf_metrics]).to_csv(
        results_dir / "tables" / "model_comparison.csv", index=False
    )

    baseline_cols = ["window_end", "request_rate", "label", "estimated_cost"]
    threshold = rate_limiter.calibrate_threshold(train_df.loc[train_df["label"] == 0, "request_rate"])
    rl_result = rate_limiter.evaluate(test_df[baseline_cols], threshold)
    vd_result = volumetric_detector.evaluate(test_df[baseline_cols])
    summary["baselines"]["rate_limiter"] = rl_result
    summary["baselines"]["volumetric_detector"] = vd_result

    pd.DataFrame(
        [{"detector": "rate_limiter", **rl_result}, {"detector": "volumetric_detector", **vd_result}]
    ).to_csv(results_dir / "tables" / "baseline_results.csv", index=False)

    if lightgbm_trained is not None and len(test_df):
        X_test_full = feature_sets.select_features(test_df, "C_proposed_full")
        y_test_full = test_df["label"]
        proba_full = lightgbm_trained.predict_proba(X_test_full)
        preds_full = lightgbm_trained.predict(X_test_full)

        if len(set(y_test_full)) > 1:
            fig, ax = plt.subplots()
            RocCurveDisplay.from_predictions(y_test_full, proba_full, ax=ax)
            fig.savefig(results_dir / "figures" / "roc_curve.png")
            plt.close(fig)

            fig, ax = plt.subplots()
            PrecisionRecallDisplay.from_predictions(y_test_full, proba_full, ax=ax)
            fig.savefig(results_dir / "figures" / "pr_curve.png")
            plt.close(fig)

        fig, ax = plt.subplots()
        ConfusionMatrixDisplay.from_predictions(y_test_full, preds_full, ax=ax)
        fig.savefig(results_dir / "figures" / "confusion_matrix.png")
        plt.close(fig)

        importance = explain.global_feature_importance(lightgbm_trained, X_test_full)
        importance.to_csv(results_dir / "tables" / "feature_statistics.csv", index=False)

        fig, ax = plt.subplots(figsize=(8, max(4, len(importance) * 0.25)))
        top = importance.head(20).iloc[::-1]
        ax.barh(top["feature"], top["mean_abs_shap"])
        ax.set_xlabel("mean |SHAP value|")
        fig.tight_layout()
        fig.savefig(results_dir / "figures" / "shap_summary.png")
        plt.close(fig)

    held_out_dir = held_out_dir or (features_dir / "held_out")
    mixed_interleaved = {}
    if lightgbm_trained is not None:
        mixed_interleaved = evaluate_held_out(held_out_dir, lightgbm_trained, threshold)
    (results_dir / "metrics" / "mixed_interleaved_evaluation.json").write_text(
        json.dumps(mixed_interleaved, indent=2, default=str)
    )

    (results_dir / "metrics" / "experiment_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (results_dir / "metrics" / "lightgbm_metrics.json").write_text(json.dumps(lgb_c_metrics, indent=2, default=str))
    (results_dir / "metrics" / "baseline_metrics.json").write_text(
        json.dumps(summary["baselines"], indent=2, default=str)
    )

    print(f"\nResults written to {results_dir}")
    print(json.dumps(summary["models"].get("C_proposed_full", {}), indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features-dir", default=str(REPO_ROOT / "data" / "features"))
    parser.add_argument("--results-dir", default=str(REPO_ROOT / "results"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--held-out-dir", help="E3/E4 feature CSVs evaluated but excluded from train/val/test")
    args = parser.parse_args()
    held_out_dir = Path(args.held_out_dir) if args.held_out_dir else None
    return run(Path(args.features_dir), Path(args.results_dir), args.seed, held_out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
