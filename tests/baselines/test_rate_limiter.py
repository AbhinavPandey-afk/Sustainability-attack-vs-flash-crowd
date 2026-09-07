import pandas as pd
import pytest

from baselines.rate_limiter import RateLimiterConfig, calibrate_threshold, evaluate, predict


def test_calibrate_threshold_empty_data_safe():
    assert calibrate_threshold([]) == 0.0


def test_calibrate_threshold_95th_percentile():
    baseline = list(range(1, 101))  # 1..100
    threshold = calibrate_threshold(baseline, RateLimiterConfig(percentile=95.0))
    assert threshold == pytest.approx(95.05, abs=0.5)


def test_predict_flags_rates_above_threshold():
    df = pd.DataFrame({"request_rate": [1.0, 5.0, 10.0, 50.0]})
    alerts = predict(df, threshold=10.0)
    assert list(alerts) == [False, False, False, True]


def test_high_volume_attack_is_detected():
    """A high-rate EDoS run above the calibrated threshold IS caught."""
    baseline_rates = [5, 5, 6, 5, 6, 5, 5, 6, 5, 5]  # legit traffic, low variance
    threshold = calibrate_threshold(baseline_rates)

    df = pd.DataFrame({
        "window_end": [10, 20, 30, 40],
        "request_rate": [5.0, 5.5, 200.0, 210.0],  # attack starts at window_end=30
        "label": [0, 0, 1, 1],
    })
    result = evaluate(df, threshold)
    assert result["attack_detected"] is True
    assert result["detection_latency"] == 0.0  # detected in the very first attack window


def test_low_volume_edos_evades_rate_limiting():
    """CLAUDE.md section 20's critical experiment: EDoS request_rate below
    the calibrated threshold is EXPECTED to evade this baseline. This test
    documents and locks in that known blind spot rather than hiding it.
    """
    baseline_rates = [5, 6, 5, 6, 7, 5, 6, 5, 6, 7]
    threshold = calibrate_threshold(baseline_rates)  # ~95th percentile of ~5-7

    df = pd.DataFrame({
        "window_end": [10, 20, 30, 40],
        "request_rate": [5.0, 6.0, 4.0, 4.5],  # low-volume EDoS: stays within/below baseline range
        "label": [0, 0, 1, 1],
    })
    result = evaluate(df, threshold)
    assert result["attack_detected"] is False
    assert result["detection_latency"] is None


def test_false_positive_on_flash_crowd_is_measured():
    df = pd.DataFrame({
        "window_end": [10, 20, 30],
        "request_rate": [5.0, 500.0, 5.0],  # legitimate spike above threshold
        "label": [0, 0, 0],
    })
    result = evaluate(df, threshold=100.0)
    assert result["false_positive_on_flash_crowd"] is True
    assert result["false_positive_rate"] == pytest.approx(1 / 3)


def test_cost_before_detection_sums_only_pre_alert_attack_windows():
    df = pd.DataFrame({
        "window_end": [10, 20, 30, 40],
        "request_rate": [5.0, 5.0, 8.0, 200.0],
        "label": [0, 0, 1, 1],
        "estimated_cost": [1.0, 1.0, 2.0, 3.0],
    })
    result = evaluate(df, threshold=100.0)
    # attack starts at window_end=30 (cost=2.0); detected at window_end=40
    assert result["detection_latency"] == 10.0
    assert result["cost_before_detection"] == 2.0
