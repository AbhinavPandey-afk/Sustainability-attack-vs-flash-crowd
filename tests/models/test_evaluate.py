import pandas as pd
import pytest

from models.evaluate import classification_metrics, detection_latency_and_cost


def test_classification_metrics_hand_verified():
    y_true = [0, 0, 1, 1, 1]
    y_pred = [0, 1, 1, 1, 0]  # 1 FP, 1 FN
    metrics = classification_metrics(y_true, y_pred)
    assert metrics["tp"] == 2
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["tn"] == 1
    assert metrics["accuracy"] == pytest.approx(3 / 5)
    assert metrics["precision"] == pytest.approx(2 / 3)
    assert metrics["recall"] == pytest.approx(2 / 3)
    assert metrics["edos_detection_rate"] == metrics["recall"]
    assert metrics["flash_crowd_false_positive_rate"] == pytest.approx(1 / 2)


def test_classification_metrics_roc_auc_present_with_proba_and_both_classes():
    y_true = [0, 0, 1, 1]
    y_pred = [0, 0, 1, 1]
    y_proba = [0.1, 0.2, 0.8, 0.9]
    metrics = classification_metrics(y_true, y_pred, y_proba)
    assert metrics["roc_auc"] == 1.0
    assert metrics["pr_auc"] == 1.0


def test_classification_metrics_roc_auc_none_for_single_class():
    metrics = classification_metrics([1, 1, 1], [1, 1, 1], [0.9, 0.8, 0.7])
    assert metrics["roc_auc"] is None


def test_classification_metrics_zero_division_handled_safely():
    metrics = classification_metrics([0, 0, 0], [0, 0, 0])
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0


def test_detection_latency_and_cost_hand_verified():
    df = pd.DataFrame({
        "window_end": [10, 20, 30, 40],
        "label": [0, 0, 1, 1],
        "estimated_cost": [1.0, 1.0, 2.0, 3.0],
    })
    alerts = pd.Series([False, False, False, True])
    result = detection_latency_and_cost(df, alerts)
    assert result["detection_latency"] == 10.0
    assert result["cost_before_detection"] == 2.0


def test_detection_latency_and_cost_no_attack_windows():
    df = pd.DataFrame({"window_end": [10, 20], "label": [0, 0]})
    result = detection_latency_and_cost(df, pd.Series([False, False]))
    assert result["detection_latency"] is None
    assert result["cost_before_detection"] is None
