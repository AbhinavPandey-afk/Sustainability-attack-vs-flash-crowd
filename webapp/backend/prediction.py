"""Live per-run model inference.

Loads the CASCADE LightGBM model persisted to disk by
experiments/summarize_results.py::run (results/models/cascade_lightgbm.joblib,
written after every real training pass) and scores one experiment's real,
already-computed feature windows. Never available until at least one real
training pass has produced and saved a model, and never available for an
experiment with no feature data — returns {"available": False, ...} in both
cases rather than fabricating a prediction.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from config import RESULTS_DIR
from data_access import load_features

MODEL_PATH = RESULTS_DIR / "models" / "cascade_lightgbm.joblib"


def _load_model():
    if not MODEL_PATH.exists():
        return None
    import joblib

    return joblib.load(MODEL_PATH)


def model_available() -> bool:
    return MODEL_PATH.exists()


def predict_experiment(experiment_id: str) -> dict[str, Any]:
    trained = _load_model()
    if trained is None:
        return {
            "available": False,
            "detail": "No trained/persisted CASCADE model on disk yet — run at least one experiment of each class first.",
        }

    features = load_features(experiment_id)
    if not features:
        return {"available": False, "detail": f"No feature data on disk yet for {experiment_id}."}

    from models.feature_sets import ABLATION_FEATURE_SETS

    feature_columns = ABLATION_FEATURE_SETS["C_proposed_full"]

    df = pd.DataFrame(features)
    missing = [c for c in feature_columns if c not in df.columns]
    if missing:
        return {"available": False, "detail": f"Feature columns missing for this run: {missing}"}

    x = df[feature_columns]
    valid_mask = x.notna().all(axis=1)
    if not valid_mask.any():
        return {"available": False, "detail": "No complete (non-NaN) feature window to score for this run yet."}

    x_valid = x[valid_mask]
    proba = trained.predict_proba(x_valid)
    preds = trained.predict(x_valid)

    windows = []
    for i, idx in enumerate(x_valid.index):
        windows.append(
            {
                "window_end": df.loc[idx, "window_end"] if "window_end" in df.columns else None,
                "probability_edos": float(proba[i]),
                "predicted_label": int(preds[i]),
            }
        )

    final = windows[-1]
    return {
        "available": True,
        "experiment_id": experiment_id,
        "threshold": trained.threshold,
        "windows": windows,
        "final_probability_edos": final["probability_edos"],
        "final_predicted_label": final["predicted_label"],
    }
