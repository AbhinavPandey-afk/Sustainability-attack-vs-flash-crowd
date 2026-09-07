"""Volumetric anomaly (rolling z-score) baseline — CLAUDE.md section 21.

z = (x - rolling_mean) / rolling_std; alert if abs(z) > threshold
(default 3). Rolling statistics are computed CAUSALLY: at row i, mean/std
come only from the `rolling_window` rows strictly BEFORE i (via
`shift(1)` prior to `.rolling()`) — never row i itself or any future row
(CLAUDE.md principle #11).
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class VolumetricDetectorConfig:
    z_threshold: float = 3.0
    rolling_window: int = 10
    min_periods: int = 3


def compute_z_scores(df: pd.DataFrame, config: VolumetricDetectorConfig = VolumetricDetectorConfig()) -> pd.Series:
    df = df.sort_values("window_end").reset_index(drop=True)
    series = df["request_rate"]
    shifted = series.shift(1)
    rolling_mean = shifted.rolling(window=config.rolling_window, min_periods=config.min_periods).mean()
    rolling_std = shifted.rolling(window=config.rolling_window, min_periods=config.min_periods).std(ddof=0)

    z_values = []
    for value, mean, std in zip(series, rolling_mean, rolling_std):
        if pd.isna(mean) or pd.isna(std):
            z_values.append(0.0)  # not enough prior history yet — no alert, not a false "normal"
        elif std == 0:
            # Zero-variance baseline: any deviation is maximally anomalous
            # rather than an undefined (and previously silently-zeroed) 0/0.
            if value == mean:
                z_values.append(0.0)
            else:
                z_values.append(float("inf") if value > mean else float("-inf"))
        else:
            z_values.append((value - mean) / std)
    return pd.Series(z_values, index=df.index)


def predict(df: pd.DataFrame, config: VolumetricDetectorConfig = VolumetricDetectorConfig()) -> pd.Series:
    return compute_z_scores(df, config).abs() > config.z_threshold


def evaluate(df: pd.DataFrame, config: VolumetricDetectorConfig = VolumetricDetectorConfig()) -> dict:
    """df columns: window_end, request_rate, label (0/1), and optionally
    estimated_cost. Returns CLAUDE.md section 21's classification +
    security + economic measurements.
    """
    df = df.sort_values("window_end").reset_index(drop=True)
    alerts = predict(df, config)
    labels = df["label"].astype(bool)

    tp = int((alerts & labels).sum())
    fn = int((~alerts & labels).sum())
    fp = int((alerts & ~labels).sum())
    tn = int((~alerts & ~labels).sum())

    tpr = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tpr
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    detection_latency = None
    cost_before_detection = None
    if labels.any():
        attack_start = df.loc[labels, "window_end"].min()
        first_alert_times = df.loc[alerts & labels, "window_end"]
        if len(first_alert_times):
            first_alert_time = first_alert_times.min()
            detection_latency = float(first_alert_time - attack_start)
            if "estimated_cost" in df.columns:
                before_mask = (df["window_end"] >= attack_start) & (df["window_end"] < first_alert_time)
                cost_before_detection = float(df.loc[before_mask, "estimated_cost"].sum())

    return {
        "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        "tpr": tpr, "fpr": fpr, "precision": precision, "recall": recall, "f1": f1,
        "detection_latency": detection_latency,
        "cost_before_detection": cost_before_detection,
    }
