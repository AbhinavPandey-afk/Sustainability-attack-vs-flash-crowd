import pandas as pd
import pytest

from baselines.volumetric_detector import VolumetricDetectorConfig, compute_z_scores, evaluate, predict


def test_z_score_is_causal_not_leaking_future_data():
    """Row i's z-score must be identical whether or not rows AFTER i exist
    in the series (CLAUDE.md principle #11)."""
    rates = [5, 5, 5, 5, 5, 5, 100, 5, 5, 5]
    df_full = pd.DataFrame({"window_end": list(range(10)), "request_rate": rates})
    df_truncated = df_full.iloc[:7].reset_index(drop=True)  # cut off right after the spike at index 6

    config = VolumetricDetectorConfig(rolling_window=5, min_periods=3)
    z_full = compute_z_scores(df_full, config)
    z_truncated = compute_z_scores(df_truncated, config)

    for i in range(7):
        assert z_full.iloc[i] == pytest.approx(z_truncated.iloc[i])


def test_flat_series_has_zero_z_score():
    df = pd.DataFrame({"window_end": range(10), "request_rate": [5.0] * 10})
    z = compute_z_scores(df, VolumetricDetectorConfig(rolling_window=5, min_periods=3))
    assert (z.abs() < 1e-9).all()


def test_sudden_spike_triggers_alert():
    rates = [5, 5, 5, 5, 5, 5, 100]
    df = pd.DataFrame({"window_end": range(7), "request_rate": rates})
    alerts = predict(df, VolumetricDetectorConfig(rolling_window=5, min_periods=3, z_threshold=3.0))
    assert bool(alerts.iloc[-1]) is True
    assert not alerts.iloc[:-1].any()


def test_evaluate_confusion_matrix_and_rates_hand_verified():
    df = pd.DataFrame({
        "window_end": [0, 10, 20, 30, 40, 50, 60],
        "request_rate": [5, 5, 5, 5, 5, 5, 100],  # only the last window spikes
        "label":        [0, 0, 0, 0, 0, 0, 1],
    })
    config = VolumetricDetectorConfig(rolling_window=5, min_periods=3, z_threshold=3.0)
    result = evaluate(df, config)

    assert result["tp"] == 1
    assert result["fn"] == 0
    assert result["fp"] == 0
    assert result["tn"] == 6
    assert result["tpr"] == 1.0
    assert result["fpr"] == 0.0
    assert result["precision"] == 1.0
    assert result["f1"] == 1.0
    assert result["detection_latency"] == 0.0


def test_evaluate_handles_no_attack_windows_safely():
    df = pd.DataFrame({
        "window_end": [0, 10, 20],
        "request_rate": [5.0, 5.0, 5.0],
        "label": [0, 0, 0],
    })
    result = evaluate(df, VolumetricDetectorConfig())
    assert result["detection_latency"] is None
    assert result["cost_before_detection"] is None
    assert result["tpr"] == 0.0


def test_evaluate_handles_no_detection_within_attack_window():
    """A low-volume EDoS run that stays within the baseline's OWN natural
    variance may never trigger the z-score threshold — must be measured
    (FN), not crash. (A perfectly flat/zero-variance baseline would flag
    ANY deviation, correctly — see test_z_score_is_causal_not_leaking_
    future_data's sibling tests — so this uses a baseline with realistic
    jitter for the "blends into noise" premise to actually hold.)"""
    df = pd.DataFrame({
        "window_end": [0, 10, 20, 30, 40, 50, 60, 70],
        "request_rate": [4, 6, 5, 4, 6, 5, 5.2, 5.1],  # attack blends into baseline's own jitter
        "label":        [0, 0, 0, 0, 0, 0, 1, 1],
    })
    result = evaluate(df, VolumetricDetectorConfig(rolling_window=5, min_periods=3, z_threshold=3.0))
    assert result["tp"] == 0
    assert result["fn"] == 2
    assert result["detection_latency"] is None
