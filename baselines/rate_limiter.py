"""Rate-limiting baseline — CLAUDE.md section 20.

The threshold is calibrated from legitimate (label=0) baseline traffic's
request_rate at a configurable percentile (default 95th) and never from
attack data. An alert fires whenever a window's observed request_rate
exceeds that threshold.

Critical experiment (CLAUDE.md section 20): a low-volume EDoS run whose
request_rate stays under the threshold is EXPECTED to evade this
baseline — this must be measured via evaluate(), not assumed or hidden.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RateLimiterConfig:
    percentile: float = 95.0


def calibrate_threshold(baseline_request_rates, config: RateLimiterConfig = RateLimiterConfig()) -> float:
    """baseline_request_rates: request_rate values from LEGITIMATE traffic
    only. Returns 0.0 if given no data (callers must supply a baseline)."""
    values = np.asarray(list(baseline_request_rates), dtype=float)
    if values.size == 0:
        return 0.0
    return float(np.percentile(values, config.percentile))


def predict(df: pd.DataFrame, threshold: float) -> pd.Series:
    """True where request_rate exceeds the calibrated threshold."""
    return df["request_rate"] > threshold


def evaluate(df: pd.DataFrame, threshold: float) -> dict:
    """df columns: window_end, request_rate, label (0=legit, 1=EDoS), and
    optionally estimated_cost (per-window cost, summed for
    cost_before_detection). Returns CLAUDE.md section 20's measurements.
    """
    df = df.sort_values("window_end").reset_index(drop=True)
    alerts = predict(df, threshold)

    attack_windows = df["label"] == 1
    legit_windows = df["label"] == 0

    attack_detected = bool((alerts & attack_windows).any())
    false_positive_on_flash_crowd = bool((alerts & legit_windows).any())
    false_positive_rate = (
        float((alerts & legit_windows).sum() / legit_windows.sum()) if legit_windows.sum() > 0 else 0.0
    )

    detection_latency = None
    cost_before_detection = None
    if attack_windows.any():
        attack_start = df.loc[attack_windows, "window_end"].min()
        first_alert_times = df.loc[alerts & attack_windows, "window_end"]
        if len(first_alert_times):
            first_alert_time = first_alert_times.min()
            detection_latency = float(first_alert_time - attack_start)
            if "estimated_cost" in df.columns:
                before_mask = (df["window_end"] >= attack_start) & (df["window_end"] < first_alert_time)
                cost_before_detection = float(df.loc[before_mask, "estimated_cost"].sum())

    return {
        "threshold": threshold,
        "attack_detected": attack_detected,
        "false_positive_on_flash_crowd": false_positive_on_flash_crowd,
        "false_positive_rate": false_positive_rate,
        "detection_latency": detection_latency,
        "cost_before_detection": cost_before_detection,
    }
