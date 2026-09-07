"""Feature pipeline orchestrator — combines traffic/cost/scaling/behaviour
features over configurable rolling windows (CLAUDE.md section 14).

Time-series integrity (CLAUDE.md non-negotiable principle #11): a feature
row for window-end time t is computed ONLY from raw samples with
timestamp in (t - window_seconds, t] — never from samples after t.
tests/feature_engineering/test_build_features.py::test_no_future_leakage
proves this directly (features computed on a truncated series match
features computed on the full series, for windows ending before the
truncation point).
"""
from __future__ import annotations

import pandas as pd

from app.src.cost import CostModelConfig

from . import behaviour_features, cost_features, scaling_features, traffic_features

REQUIRED_RAW_COLUMNS = [
    "timestamp",
    "request_count",
    "error_count",
    "cheap_count",
    "medium_count",
    "expensive_count",
    "cache_hits",
    "cache_misses",
    "conversions",
    "active_sessions",
    "session_duration_sum",
    "session_duration_count",
    "replica_count",
    "cpu_utilization_pct",
]


def _window_slice(raw: pd.DataFrame, window_end: float, window_seconds: float) -> pd.DataFrame:
    window_start = window_end - window_seconds
    return raw[(raw["timestamp"] > window_start) & (raw["timestamp"] <= window_end)]


def _combined_features(row: dict, window: pd.DataFrame) -> dict:
    """CLAUDE.md section 14.5 — relationship features built from the
    outputs already computed by the four feature groups above."""
    request_rate = row["request_rate"]
    mean_cpu_pct = float(window["cpu_utilization_pct"].mean()) if len(window) else 0.0
    return {
        "cost_per_request_over_request_rate": (row["cost_per_request"] / request_rate) if request_rate > 0 else 0.0,
        "replica_count_over_request_rate": (row["mean_replica_count"] / request_rate) if request_rate > 0 else 0.0,
        "cpu_utilization_over_request_rate": (mean_cpu_pct / request_rate) if request_rate > 0 else 0.0,
        "expensive_ratio_times_cost_per_request": row["expensive_endpoint_ratio"] * row["cost_per_request"],
        "replica_growth_rate_over_request_rate": (
            row["replica_growth_rate"] / request_rate if request_rate > 0 else 0.0
        ),
    }


def build_features(
    raw: pd.DataFrame,
    window_seconds_list: list[float],
    step_seconds: float | None = None,
    cost_config: CostModelConfig | None = None,
    min_replicas: int = 1,
    label: int | None = None,
    experiment_id: str | None = None,
) -> pd.DataFrame:
    """Compute one feature row per (window_end, window_size) combination.

    window_end times start at raw['timestamp'].min() + window_seconds (so
    every window is fully backed by data — no partial/leaky windows at the
    start of the series) and advance by `step_seconds` (default: the
    window size itself, i.e. non-overlapping windows) up to
    raw['timestamp'].max().

    `label` (0=flash_crowd, 1=EDoS) and `experiment_id` are optional —
    pass them when building a labeled training/eval dataset (Phase 8);
    omit for exploratory/unlabeled use.
    """
    missing = set(REQUIRED_RAW_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"raw DataFrame is missing required columns: {sorted(missing)}")

    if raw.empty:
        return pd.DataFrame()

    raw = raw.sort_values("timestamp").reset_index(drop=True)
    cost_config = cost_config or CostModelConfig()

    t_min, t_max = float(raw["timestamp"].min()), float(raw["timestamp"].max())
    rows = []

    for window_seconds in window_seconds_list:
        step = step_seconds or window_seconds
        window_end = t_min + window_seconds
        while window_end <= t_max:
            window = _window_slice(raw, window_end, window_seconds)
            if len(window) >= 2:
                request_count = max(
                    float(window["request_count"].iloc[-1] - window["request_count"].iloc[0]), 0.0
                )

                row: dict = {"window_end": window_end, "window_seconds": window_seconds}
                if experiment_id is not None:
                    row["experiment_id"] = experiment_id
                if label is not None:
                    row["label"] = label

                row.update(traffic_features.compute(window, window_seconds))
                row.update(cost_features.compute(window, window_seconds, request_count, cost_config))
                row.update(scaling_features.compute(window, window_seconds, request_count, min_replicas))
                row.update(behaviour_features.compute(window, request_count))
                row.update(_combined_features(row, window))

                rows.append(row)

            window_end += step

    return pd.DataFrame(rows)
