"""Phase 5 tests for the replica-minute cost model (app/src/cost.py).

Pure-function tests, no cluster/app/network required — CLAUDE.md section 33:
"known replica duration -> known cost", "zero requests handled safely",
"zero replicas handled safely".
"""
import pytest

from app.src.cost import (
    CostModelConfig,
    ReplicaInterval,
    compute_cost,
    cost_per_request,
    cost_per_second,
    cost_to_traffic_ratio,
    cpu_seconds_per_request,
    intervals_from_replica_samples,
    replica_minutes_per_request,
    total_duration_seconds,
    total_replica_minutes,
)


def test_known_replica_duration_yields_known_cost():
    config = CostModelConfig(replica_cost_per_minute=2.0)
    intervals = [ReplicaInterval(duration_seconds=600, replica_count=3)]  # 10 min * 3 replicas
    assert compute_cost(intervals, config) == 60.0  # 30 replica-minutes * 2.0


def test_multiple_intervals_sum_correctly():
    config = CostModelConfig(replica_cost_per_minute=1.0)
    intervals = [
        ReplicaInterval(duration_seconds=60, replica_count=1),   # 1 replica-minute
        ReplicaInterval(duration_seconds=120, replica_count=2),  # 4 replica-minutes
    ]
    assert total_replica_minutes(intervals) == 5.0
    assert compute_cost(intervals, config) == 5.0


def test_zero_replicas_handled_safely():
    config = CostModelConfig(replica_cost_per_minute=5.0)
    intervals = [ReplicaInterval(duration_seconds=300, replica_count=0)]
    assert compute_cost(intervals, config) == 0.0


def test_empty_intervals_handled_safely():
    config = CostModelConfig()
    assert compute_cost([], config) == 0.0
    assert total_replica_minutes([]) == 0.0
    assert total_duration_seconds([]) == 0.0


def test_cpu_weighted_cost_adds_when_weight_nonzero():
    config = CostModelConfig(replica_cost_per_minute=1.0, cpu_cost_weight=10.0)
    intervals = [ReplicaInterval(duration_seconds=60, replica_count=1, avg_cpu_utilization=0.5)]
    # base = 1 replica-minute * 1.0 = 1.0; cpu term = 1 * 0.5 * 10.0 = 5.0
    assert compute_cost(intervals, config) == 6.0


def test_cpu_weight_zero_ignores_utilization():
    config = CostModelConfig(replica_cost_per_minute=1.0, cpu_cost_weight=0.0)
    intervals = [ReplicaInterval(duration_seconds=60, replica_count=1, avg_cpu_utilization=0.99)]
    assert compute_cost(intervals, config) == 1.0


def test_memory_weighted_cost_adds_when_weight_nonzero():
    config = CostModelConfig(replica_cost_per_minute=0.0, memory_cost_weight=4.0)
    intervals = [ReplicaInterval(duration_seconds=60, replica_count=2, avg_memory_utilization=0.25)]
    # replica-minutes = 2; mem term = 2 * 0.25 * 4.0 = 2.0
    assert compute_cost(intervals, config) == 2.0


def test_cost_model_config_from_dict_defaults():
    config = CostModelConfig.from_dict({})
    assert config.replica_cost_per_minute == 1.0
    assert config.cpu_cost_weight == 0.0
    assert config.memory_cost_weight == 0.0


def test_cost_model_config_from_dict_overrides():
    config = CostModelConfig.from_dict({"replica_cost_per_minute": 3.5, "cpu_cost_weight": 1.2})
    assert config.replica_cost_per_minute == 3.5
    assert config.cpu_cost_weight == 1.2


def test_cost_per_request_zero_requests_handled_safely():
    assert cost_per_request(total_cost=100.0, request_count=0) == 0.0


def test_cost_per_request_normal():
    assert cost_per_request(total_cost=100.0, request_count=50) == 2.0


def test_cost_per_second_zero_duration_handled_safely():
    assert cost_per_second(total_cost=10.0, duration_seconds=0) == 0.0


def test_replica_minutes_per_request_zero_requests_safe():
    assert replica_minutes_per_request(10.0, 0) == 0.0


def test_replica_minutes_per_request_normal():
    assert replica_minutes_per_request(10.0, 5) == 2.0


def test_cpu_seconds_per_request_zero_requests_safe():
    assert cpu_seconds_per_request(10.0, 0) == 0.0


def test_cost_to_traffic_ratio_zero_rate_safe():
    assert cost_to_traffic_ratio(10.0, 0) == 0.0


def test_cost_to_traffic_ratio_normal():
    assert cost_to_traffic_ratio(100.0, 10.0) == 10.0


def test_intervals_from_replica_samples():
    samples = [(0, 1), (60, 2), (180, 1)]
    intervals = intervals_from_replica_samples(samples)
    assert len(intervals) == 2
    assert intervals[0].duration_seconds == 60 and intervals[0].replica_count == 1
    assert intervals[1].duration_seconds == 120 and intervals[1].replica_count == 2


def test_intervals_from_replica_samples_handles_unsorted_input():
    samples = [(180, 1), (0, 1), (60, 2)]
    intervals = intervals_from_replica_samples(samples)
    assert [i.duration_seconds for i in intervals] == [60, 120]


def test_intervals_from_replica_samples_single_sample_yields_no_intervals():
    assert intervals_from_replica_samples([(0, 1)]) == []


def test_intervals_from_replica_samples_empty():
    assert intervals_from_replica_samples([]) == []


def test_end_to_end_matches_hand_computed_scenario():
    """A small scale-up scenario computed by hand:
    0-2min @ 1 replica, 2-5min @ 3 replicas, 5-6min @ 1 replica.
    replica-minutes = 1*2 + 3*3 + 1*1 = 2 + 9 + 1 = 12
    cost @ 1.5/min = 18.0
    """
    samples = [(0, 1), (120, 3), (300, 1), (360, 1)]
    intervals = intervals_from_replica_samples(samples)
    config = CostModelConfig(replica_cost_per_minute=1.5)

    assert total_replica_minutes(intervals) == 12.0
    assert compute_cost(intervals, config) == 18.0
    assert cost_per_request(18.0, request_count=90) == 0.2
    assert replica_minutes_per_request(12.0, request_count=90) == pytest.approx(12.0 / 90)
