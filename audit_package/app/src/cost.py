"""Replica-minute cost model (CLAUDE.md section 10).

An experimental, platform-independent proxy for infrastructure
expenditure — NOT a real cloud bill, and intentionally independent of any
specific cloud provider. Values are in "cost units" by default;
replica_cost_per_minute is not a real-world currency amount unless
explicitly calibrated by the experimenter.

Pure functions only, no FastAPI/runtime dependency, so this module is
reusable by feature engineering and experiment scripts (later phases) as
well as by tests.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModelConfig:
    replica_cost_per_minute: float = 1.0
    cpu_cost_weight: float = 0.0
    memory_cost_weight: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "CostModelConfig":
        return cls(
            replica_cost_per_minute=float(data.get("replica_cost_per_minute", 1.0)),
            cpu_cost_weight=float(data.get("cpu_cost_weight", 0.0)),
            memory_cost_weight=float(data.get("memory_cost_weight", 0.0)),
        )


@dataclass(frozen=True)
class ReplicaInterval:
    """A period during which a given replica count was active.

    avg_cpu_utilization / avg_memory_utilization are fractions (e.g. 0.6
    for 60%) and are only factored into cost when the config's
    cpu_cost_weight / memory_cost_weight are nonzero.
    """

    duration_seconds: float
    replica_count: int
    avg_cpu_utilization: float = 0.0
    avg_memory_utilization: float = 0.0

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60.0

    @property
    def replica_minutes(self) -> float:
        return self.replica_count * self.duration_minutes


def intervals_from_replica_samples(samples: list[tuple[float, int]]) -> list[ReplicaInterval]:
    """Build ReplicaInterval entries from chronological (timestamp,
    replica_count) samples — e.g. from polling `kubectl get deployment` or
    a Prometheus range query. Each sample's replica count is assumed to
    hold until the next sample's timestamp; the final sample contributes
    no interval (nothing follows it to bound its duration).
    """
    intervals: list[ReplicaInterval] = []
    ordered = sorted(samples, key=lambda s: s[0])
    for (t0, count), (t1, _next_count) in zip(ordered, ordered[1:]):
        intervals.append(ReplicaInterval(duration_seconds=t1 - t0, replica_count=count))
    return intervals


def total_replica_minutes(intervals: list[ReplicaInterval]) -> float:
    return sum(interval.replica_minutes for interval in intervals)


def total_duration_seconds(intervals: list[ReplicaInterval]) -> float:
    return sum(interval.duration_seconds for interval in intervals)


def compute_cost(intervals: list[ReplicaInterval], config: CostModelConfig) -> float:
    """Total estimated cost, in cost units.

    Base term: replica-minutes x replica_cost_per_minute.
    Optional terms (added only if the corresponding weight is nonzero):
    replica-minutes x avg_utilization x weight, for CPU and memory.
    """
    cost = 0.0
    for interval in intervals:
        cost += interval.replica_minutes * config.replica_cost_per_minute
        if config.cpu_cost_weight:
            cost += interval.replica_minutes * interval.avg_cpu_utilization * config.cpu_cost_weight
        if config.memory_cost_weight:
            cost += interval.replica_minutes * interval.avg_memory_utilization * config.memory_cost_weight
    return cost


def cost_per_request(total_cost: float, request_count: int) -> float:
    if request_count <= 0:
        return 0.0
    return total_cost / request_count


def cost_per_second(total_cost: float, duration_seconds: float) -> float:
    if duration_seconds <= 0:
        return 0.0
    return total_cost / duration_seconds


def replica_minutes_per_request(replica_minutes_value: float, request_count: int) -> float:
    if request_count <= 0:
        return 0.0
    return replica_minutes_value / request_count


def cpu_seconds_per_request(total_cpu_seconds: float, request_count: int) -> float:
    if request_count <= 0:
        return 0.0
    return total_cpu_seconds / request_count


def cost_to_traffic_ratio(total_cost: float, request_rate: float) -> float:
    """Cost accumulated relative to the average request RATE (not raw
    count) — a high value indicates disproportionate cost for the observed
    traffic intensity, which is the EDoS signature this project studies.
    """
    if request_rate <= 0:
        return 0.0
    return total_cost / request_rate
