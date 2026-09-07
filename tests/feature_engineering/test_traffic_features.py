import pandas as pd
import pytest

from feature_engineering import traffic_features


def _raw(rows):
    return pd.DataFrame(rows)


def test_single_row_returns_zeros():
    result = traffic_features.compute(_raw([{"timestamp": 0, "request_count": 0, "error_count": 0}]), 60)
    assert result == traffic_features.EMPTY


def test_simple_constant_rate():
    rows = [
        {"timestamp": 0, "request_count": 0, "error_count": 0},
        {"timestamp": 10, "request_count": 10, "error_count": 0},
        {"timestamp": 20, "request_count": 20, "error_count": 0},
        {"timestamp": 30, "request_count": 30, "error_count": 0},
    ]
    result = traffic_features.compute(_raw(rows), window_seconds=30)
    assert result["request_count"] == 30
    assert result["request_rate"] == 1.0
    assert result["peak_request_rate"] == 1.0
    assert result["request_rate_std"] == 0.0
    assert result["request_burstiness"] == 0.0
    assert result["error_rate"] == 0.0
    assert result["response_rate"] == 1.0


def test_bursty_traffic_has_higher_peak_than_average_and_nonzero_burstiness():
    rows = [
        {"timestamp": 0, "request_count": 0, "error_count": 0},
        {"timestamp": 10, "request_count": 1, "error_count": 0},
        {"timestamp": 20, "request_count": 50, "error_count": 0},
        {"timestamp": 30, "request_count": 51, "error_count": 0},
    ]
    result = traffic_features.compute(_raw(rows), window_seconds=30)
    assert result["peak_request_rate"] > result["request_rate"]
    assert result["request_burstiness"] > 0


def test_error_rate_and_response_rate():
    rows = [
        {"timestamp": 0, "request_count": 0, "error_count": 0},
        {"timestamp": 60, "request_count": 100, "error_count": 20},
    ]
    result = traffic_features.compute(_raw(rows), window_seconds=60)
    assert result["error_rate"] == 0.2
    assert result["response_rate"] == pytest.approx(80 / 60)


def test_zero_window_seconds_handled_safely():
    rows = [
        {"timestamp": 0, "request_count": 0, "error_count": 0},
        {"timestamp": 10, "request_count": 5, "error_count": 0},
    ]
    result = traffic_features.compute(_raw(rows), window_seconds=0)
    assert result == traffic_features.EMPTY
