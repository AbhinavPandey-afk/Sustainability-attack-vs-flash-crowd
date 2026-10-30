"""Cost features — CLAUDE.md section 14.2 (core proposed features).

Wraps app/src/cost.py's pure cost-model functions, applied to the
replica_count/cpu_utilization_pct samples within a single feature window.
"""
from __future__ import annotations

import pandas as pd

from app.src.cost import CostModelConfig, ReplicaInterval, compute_cost, total_replica_minutes
from app.src.cost import cost_per_request as _cost_per_request
from app.src.cost import cost_per_second as _cost_per_second
from app.src.cost import cost_to_traffic_ratio as _cost_to_traffic_ratio
from app.src.cost import cpu_seconds_per_request as _cpu_seconds_per_request
from app.src.cost import replica_minutes_per_request as _replica_minutes_per_request

EMPTY = {
    "estimated_cost": 0.0,
    "cost_per_request": 0.0,
    "cost_per_second": 0.0,
    "replica_minutes_per_request": 0.0,
    "cpu_seconds_per_request": 0.0,
    "cost_to_traffic_ratio": 0.0,
}


def _intervals_from_window(window: pd.DataFrame) -> list[ReplicaInterval]:
    rows = list(window[["timestamp", "replica_count", "cpu_utilization_pct"]].itertuples(index=False, name=None))
    intervals = []
    for (t0, replicas, cpu_pct), (t1, _r1, _c1) in zip(rows, rows[1:]):
        intervals.append(
            ReplicaInterval(
                duration_seconds=float(t1 - t0),
                replica_count=int(replicas),
                avg_cpu_utilization=float(cpu_pct) / 100.0,
            )
        )
    return intervals


def compute(window: pd.DataFrame, window_seconds: float, request_count: float, config: CostModelConfig) -> dict:
    if len(window) < 2 or window_seconds <= 0:
        return dict(EMPTY)

    intervals = _intervals_from_window(window)
    estimated_cost = compute_cost(intervals, config)
    replica_minutes = total_replica_minutes(intervals)
    total_cpu_seconds = sum(i.replica_minutes * 60.0 * i.avg_cpu_utilization for i in intervals)
    request_rate = request_count / window_seconds

    return {
        "estimated_cost": estimated_cost,
        "cost_per_request": _cost_per_request(estimated_cost, request_count),
        "cost_per_second": _cost_per_second(estimated_cost, window_seconds),
        "replica_minutes_per_request": _replica_minutes_per_request(replica_minutes, request_count),
        "cpu_seconds_per_request": _cpu_seconds_per_request(total_cpu_seconds, request_count),
        "cost_to_traffic_ratio": _cost_to_traffic_ratio(estimated_cost, request_rate),
    }
