"""Random Forest — secondary comparison model (CLAUDE.md section 18):
determines whether observed performance is specific to LightGBM or
inherent to the feature representation itself.
"""
from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier

from .train_lightgbm import TrainedModel, tune_threshold

DEFAULT_PARAMS = {
    "n_estimators": 200,
    "max_depth": None,
    "random_state": 42,
}


def train(X_train, y_train, X_val, y_val, params: dict | None = None) -> TrainedModel:
    merged_params = {**DEFAULT_PARAMS, **(params or {})}
    model = RandomForestClassifier(**merged_params)
    model.fit(X_train, y_train)

    if len(X_val):
        val_proba = model.predict_proba(X_val)[:, 1]
        threshold = tune_threshold(y_val, val_proba)
    else:
        threshold = 0.5

    return TrainedModel(model=model, feature_names=list(X_train.columns), threshold=threshold, params=merged_params)
