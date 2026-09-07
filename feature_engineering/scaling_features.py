"""Scaling features — CLAUDE.md section 14.3 (core proposed features).

Computed from the OBSERVED replica_count / cpu_utilization_pct time
series within a window — not from configured HPA targets. CLAUDE.md
section 9: "The detector must use the observed scaling behaviour, not
merely the configured HPA target."
"""
from __future__ import annotations

import pandas as pd

EMPTY = {
    "current_replica_count": 0.0,
    "mean_replica_count": 0.0,
    "max_replica_count": 0.0,
    "replica_growth_rate": 0.0,
    "replica_change_count": 0.0,
    "scale_up_events": 0.0,
    "scale_down_events": 0.0,
    "time_at_elevated_replicas": 0.0,
    "cpu_growth_rate": 0.0,
    "replica_to_request_ratio": 0.0,
}


def compute(window: pd.DataFrame, window_seconds: float, request_count: float, min_replicas: int = 1) -> dict:
    if len(window) < 1:
        return dict(EMPTY)

    replicas = window["replica_count"].reset_index(drop=True)
    cpu = window["cpu_utilization_pct"].reset_index(drop=True)
    timestamps = window["timestamp"].reset_index(drop=True)

    current_replica_count = float(replicas.iloc[-1])
    mean_replica_count = float(replicas.mean())
    max_replica_count = float(replicas.max())

    if window_seconds > 0 and len(replicas) >= 2:
        replica_growth_rate = (float(replicas.iloc[-1]) - float(replicas.iloc[0])) / window_seconds
        cpu_growth_rate = (float(cpu.iloc[-1]) - float(cpu.iloc[0])) / window_seconds
    else:
        replica_growth_rate = 0.0
        cpu_growth_rate = 0.0

    diffs = replicas.diff().dropna()
    replica_change_count = float((diffs != 0).sum())
    scale_up_events = float((diffs > 0).sum())
    scale_down_events = float((diffs < 0).sum())

    time_at_elevated_replicas = 0.0
    for i in range(len(replicas) - 1):
        if replicas.iloc[i] > min_replicas:
            time_at_elevated_replicas += float(timestamps.iloc[i + 1] - timestamps.iloc[i])

    request_rate = request_count / window_seconds if window_seconds > 0 else 0.0
    replica_to_request_ratio = (mean_replica_count / request_rate) if request_rate > 0 else 0.0

    return {
        "current_replica_count": current_replica_count,
        "mean_replica_count": mean_replica_count,
        "max_replica_count": max_replica_count,
        "replica_growth_rate": replica_growth_rate,
        "replica_change_count": replica_change_count,
        "scale_up_events": scale_up_events,
        "scale_down_events": scale_down_events,
        "time_at_elevated_replicas": time_at_elevated_replicas,
        "cpu_growth_rate": cpu_growth_rate,
        "replica_to_request_ratio": replica_to_request_ratio,
    }
