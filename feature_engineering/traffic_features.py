"""Traffic (volume) features — CLAUDE.md section 14.1.

Baseline/context features, not this project's primary novelty (cost,
scaling, and behaviour are — see cost_features.py, scaling_features.py,
behaviour_features.py). Computed from a causal window of raw
counter/gauge samples; see build_features.py for windowing and the
no-future-leakage guarantee.
"""
from __future__ import annotations

import pandas as pd

EMPTY = {
    "request_rate": 0.0,
    "request_count": 0.0,
    "peak_request_rate": 0.0,
    "request_rate_std": 0.0,
    "request_burstiness": 0.0,
    "response_rate": 0.0,
    "error_rate": 0.0,
}


def compute(window: pd.DataFrame, window_seconds: float) -> dict:
    """window: raw samples with (at least) columns [timestamp,
    request_count, error_count], sorted ascending by timestamp, already
    restricted to the causal window. Needs >=2 rows to form a delta.
    """
    if len(window) < 2 or window_seconds <= 0:
        return dict(EMPTY)

    request_count = max(float(window["request_count"].iloc[-1] - window["request_count"].iloc[0]), 0.0)
    error_count = max(float(window["error_count"].iloc[-1] - window["error_count"].iloc[0]), 0.0)

    dt = window["timestamp"].diff().iloc[1:]
    d_requests = window["request_count"].diff().iloc[1:].clip(lower=0)
    valid = dt > 0
    sub_rates = (d_requests[valid] / dt[valid]) if valid.any() else pd.Series(dtype=float)

    request_rate = request_count / window_seconds
    peak_request_rate = float(sub_rates.max()) if len(sub_rates) else 0.0
    request_rate_std = float(sub_rates.std(ddof=0)) if len(sub_rates) else 0.0
    mean_sub_rate = float(sub_rates.mean()) if len(sub_rates) else 0.0
    request_burstiness = (request_rate_std / mean_sub_rate) if mean_sub_rate > 0 else 0.0

    error_rate = (error_count / request_count) if request_count > 0 else 0.0
    response_rate = max(request_count - error_count, 0.0) / window_seconds

    return {
        "request_rate": request_rate,
        "request_count": request_count,
        "peak_request_rate": peak_request_rate,
        "request_rate_std": request_rate_std,
        "request_burstiness": request_burstiness,
        "response_rate": response_rate,
        "error_rate": error_rate,
    }
