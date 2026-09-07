"""LightGBM training — CLAUDE.md section 16/17.

The research novelty is the cost/scaling/behaviour feature framework, not
the choice of LightGBM (CLAUDE.md: "Do not call the model novel solely
because it uses LightGBM"). The classification threshold is tuned on the
VALIDATION set only — CLAUDE.md: "Do not automatically assume 0.5 is
optimal. Tune it using the training/validation data only."
"""
from __future__ import annotations

from dataclasses import dataclass, field

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score


@dataclass
class TrainedModel:
    model: object
    feature_names: list
    threshold: float
    params: dict = field(default_factory=dict)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.model.predict_proba(X[self.feature_names])[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X) >= self.threshold).astype(int)


DEFAULT_PARAMS = {
    "n_estimators": 100,
    "max_depth": -1,
    "learning_rate": 0.1,
    "random_state": 42,
    "verbosity": -1,
    # LightGBM's built-in default (min_child_samples=20) can prevent ANY
    # split on the small datasets this project realistically produces from
    # local, short experiment runs (CLAUDE.md section 25) — with e.g. 16
    # training rows total, no split can ever satisfy a 20-sample leaf
    # minimum, silently degenerating to a constant-prediction model.
    # Override via `params` for larger datasets.
    "min_child_samples": 5,
    "min_split_gain": 0.0,
}


def tune_threshold(y_true, proba, thresholds=None) -> float:
    """Grid search over [0.05, 0.95] for the threshold maximizing F1 on
    the given (validation) labels."""
    if thresholds is None:
        thresholds = np.linspace(0.05, 0.95, 19)
    best_threshold, best_f1 = 0.5, -1.0
    for t in thresholds:
        preds = (proba >= t).astype(int)
        score = f1_score(y_true, preds, zero_division=0)
        if score > best_f1:
            best_f1, best_threshold = score, float(t)
    return best_threshold


def train(
    X_train: pd.DataFrame,
    y_train,
    X_val: pd.DataFrame,
    y_val,
    params: dict | None = None,
) -> TrainedModel:
    merged_params = {**DEFAULT_PARAMS, **(params or {})}
    model = lgb.LGBMClassifier(**merged_params)
    model.fit(X_train, y_train)

    if len(X_val):
        val_proba = model.predict_proba(X_val)[:, 1]
        threshold = tune_threshold(y_val, val_proba)
    else:
        threshold = 0.5

    return TrainedModel(model=model, feature_names=list(X_train.columns), threshold=threshold, params=merged_params)
