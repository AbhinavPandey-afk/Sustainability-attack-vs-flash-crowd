"""Prediction wrapper and temporal smoothing — CLAUDE.md section 22
(detector decision logic).
"""
from __future__ import annotations

import pandas as pd


def predict_proba(trained_model, X: pd.DataFrame):
    return trained_model.predict_proba(X)


def predict(trained_model, X: pd.DataFrame):
    return trained_model.predict(X)


def smoothed_alert(proba_series: pd.Series, threshold: float, k: int, n: int) -> pd.Series:
    """CLAUDE.md section 22: "Alert if EDoS probability > threshold for K
    of the last N windows." Apply only AFTER evaluating the raw classifier
    (section 22: "Do not add smoothing until the raw classifier has been
    evaluated first. Report both where useful.").
    """
    raw_alerts = (proba_series >= threshold).astype(int)
    rolling_count = raw_alerts.rolling(window=n, min_periods=1).sum()
    return rolling_count >= k
