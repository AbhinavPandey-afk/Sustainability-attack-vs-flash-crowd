import pandas as pd
import pytest

from feature_engineering import behaviour_features


def _rows(cheap, medium, expensive, cache_hits, cache_misses, conversions, sessions, dur_sum, dur_count):
    return [
        {
            "timestamp": 0, "cheap_count": 0, "medium_count": 0, "expensive_count": 0,
            "cache_hits": 0, "cache_misses": 0, "conversions": 0, "active_sessions": sessions[0],
            "session_duration_sum": 0, "session_duration_count": 0,
        },
        {
            "timestamp": 60, "cheap_count": cheap, "medium_count": medium, "expensive_count": expensive,
            "cache_hits": cache_hits, "cache_misses": cache_misses, "conversions": conversions,
            "active_sessions": sessions[1], "session_duration_sum": dur_sum, "session_duration_count": dur_count,
        },
    ]


def test_edos_like_concentration_has_zero_diversity():
    rows = _rows(cheap=0, medium=0, expensive=100, cache_hits=0, cache_misses=0, conversions=0,
                 sessions=(5, 5), dur_sum=0, dur_count=0)
    result = behaviour_features.compute(pd.DataFrame(rows), request_count=100)
    assert result["endpoint_diversity"] == 0.0
    assert result["unique_endpoint_ratio"] == pytest.approx(1 / 3)
    assert result["expensive_endpoint_ratio"] == 1.0
    assert result["report_generation_ratio"] == 1.0


def test_flash_crowd_like_spread_has_high_diversity():
    rows = _rows(cheap=40, medium=40, expensive=20, cache_hits=30, cache_misses=10, conversions=5,
                 sessions=(10, 10), dur_sum=0, dur_count=0)
    result = behaviour_features.compute(pd.DataFrame(rows), request_count=100)
    assert result["endpoint_diversity"] > 0.9
    assert result["unique_endpoint_ratio"] == 1.0
    assert result["cache_hit_rate"] == 0.75
    assert result["cache_miss_rate"] == 0.25
    assert result["conversion_rate"] == 0.05


def test_session_duration_from_histogram_deltas():
    rows = _rows(cheap=10, medium=0, expensive=0, cache_hits=0, cache_misses=0, conversions=0,
                 sessions=(3, 3), dur_sum=300, dur_count=10)
    result = behaviour_features.compute(pd.DataFrame(rows), request_count=10)
    assert result["session_duration"] == 30.0


def test_zero_requests_handled_safely():
    rows = _rows(0, 0, 0, 0, 0, 0, sessions=(0, 0), dur_sum=0, dur_count=0)
    result = behaviour_features.compute(pd.DataFrame(rows), request_count=0)
    assert result == behaviour_features.EMPTY


def test_single_row_returns_empty():
    row = [{
        "timestamp": 0, "cheap_count": 0, "medium_count": 0, "expensive_count": 0,
        "cache_hits": 0, "cache_misses": 0, "conversions": 0, "active_sessions": 0,
        "session_duration_sum": 0, "session_duration_count": 0,
    }]
    result = behaviour_features.compute(pd.DataFrame(row), request_count=10)
    assert result == behaviour_features.EMPTY
