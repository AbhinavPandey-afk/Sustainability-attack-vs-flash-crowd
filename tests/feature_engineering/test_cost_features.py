import pandas as pd
import pytest

from app.src.cost import CostModelConfig
from feature_engineering import cost_features


def test_matches_hand_computed_cost():
    rows = [
        {"timestamp": 0, "replica_count": 1, "cpu_utilization_pct": 50.0},
        {"timestamp": 60, "replica_count": 1, "cpu_utilization_pct": 50.0},
        {"timestamp": 120, "replica_count": 3, "cpu_utilization_pct": 80.0},
        {"timestamp": 180, "replica_count": 3, "cpu_utilization_pct": 80.0},
    ]
    df = pd.DataFrame(rows)
    config = CostModelConfig(replica_cost_per_minute=2.0)
    result = cost_features.compute(df, window_seconds=180, request_count=90, config=config)
    # intervals: 1repmin + 1repmin + 3repmin = 5 replica-minutes; cost = 5 * 2.0
    assert result["estimated_cost"] == 10.0
    assert result["cost_per_request"] == pytest.approx(10.0 / 90)
    assert result["cost_per_second"] == pytest.approx(10.0 / 180)


def test_zero_requests_handled_safely():
    rows = [
        {"timestamp": 0, "replica_count": 1, "cpu_utilization_pct": 0.0},
        {"timestamp": 60, "replica_count": 1, "cpu_utilization_pct": 0.0},
    ]
    result = cost_features.compute(pd.DataFrame(rows), 60, request_count=0, config=CostModelConfig())
    assert result["cost_per_request"] == 0.0
    assert result["cost_to_traffic_ratio"] == 0.0


def test_single_row_returns_empty():
    df = pd.DataFrame([{"timestamp": 0, "replica_count": 1, "cpu_utilization_pct": 0}])
    result = cost_features.compute(df, 60, 10, CostModelConfig())
    assert result == cost_features.EMPTY


def test_zero_replicas_yield_zero_cost():
    rows = [
        {"timestamp": 0, "replica_count": 0, "cpu_utilization_pct": 0.0},
        {"timestamp": 60, "replica_count": 0, "cpu_utilization_pct": 0.0},
    ]
    result = cost_features.compute(pd.DataFrame(rows), 60, request_count=10, config=CostModelConfig())
    assert result["estimated_cost"] == 0.0
