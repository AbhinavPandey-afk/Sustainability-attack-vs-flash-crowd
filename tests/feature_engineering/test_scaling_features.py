import pandas as pd
import pytest

from feature_engineering import scaling_features


def test_scale_up_detected():
    rows = [
        {"timestamp": 0, "replica_count": 1, "cpu_utilization_pct": 30.0},
        {"timestamp": 30, "replica_count": 1, "cpu_utilization_pct": 70.0},
        {"timestamp": 60, "replica_count": 4, "cpu_utilization_pct": 90.0},
        {"timestamp": 90, "replica_count": 4, "cpu_utilization_pct": 40.0},
    ]
    result = scaling_features.compute(pd.DataFrame(rows), window_seconds=90, request_count=100, min_replicas=1)
    assert result["current_replica_count"] == 4
    assert result["max_replica_count"] == 4
    assert result["scale_up_events"] == 1
    assert result["scale_down_events"] == 0
    assert result["replica_change_count"] == 1
    assert result["replica_growth_rate"] == pytest.approx((4 - 1) / 90)
    assert result["time_at_elevated_replicas"] == 30


def test_scale_down_detected():
    rows = [
        {"timestamp": 0, "replica_count": 5, "cpu_utilization_pct": 80},
        {"timestamp": 60, "replica_count": 2, "cpu_utilization_pct": 30},
        {"timestamp": 120, "replica_count": 1, "cpu_utilization_pct": 10},
    ]
    result = scaling_features.compute(pd.DataFrame(rows), 120, 50)
    assert result["scale_down_events"] == 2
    assert result["scale_up_events"] == 0


def test_empty_window_returns_zeros():
    empty = pd.DataFrame(columns=["timestamp", "replica_count", "cpu_utilization_pct"])
    assert scaling_features.compute(empty, 60, 10) == scaling_features.EMPTY


def test_replica_to_request_ratio_zero_requests_safe():
    rows = [
        {"timestamp": 0, "replica_count": 2, "cpu_utilization_pct": 50},
        {"timestamp": 60, "replica_count": 2, "cpu_utilization_pct": 50},
    ]
    result = scaling_features.compute(pd.DataFrame(rows), 60, request_count=0)
    assert result["replica_to_request_ratio"] == 0.0
