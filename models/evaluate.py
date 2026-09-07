"""Model evaluation — CLAUDE.md section 23 (classification, security-
specific metrics) and section 24 (uniform comparison against the
baselines in baselines/*.py).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score


def classification_metrics(y_true, y_pred, y_proba=None) -> dict:
    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())

    accuracy = (tp + tn) / len(y_true) if len(y_true) else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0  # TPR / EDoS detection rate
    specificity = tn / (tn + fp) if (tn + fp) > 0 else 0.0  # TNR
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    flash_crowd_fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    metrics = {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "edos_detection_rate": recall,
        "flash_crowd_false_positive_rate": flash_crowd_fpr,
        "roc_auc": None,
        "pr_auc": None,
    }

    if y_proba is not None and len(np.unique(y_true)) > 1:
        metrics["roc_auc"] = float(roc_auc_score(y_true, y_proba))
        metrics["pr_auc"] = float(average_precision_score(y_true, y_proba))

    return metrics


def detection_latency_and_cost(df: pd.DataFrame, alerts: pd.Series) -> dict:
    """df needs window_end, label, optionally estimated_cost — same
    convention as baselines/rate_limiter.py and volumetric_detector.py, so
    CASCADE and the baselines are evaluated identically (CLAUDE.md
    section 24)."""
    df = df.reset_index(drop=True)
    alerts = pd.Series(np.asarray(alerts).astype(bool), index=df.index)
    labels = df["label"].astype(bool)

    detection_latency = None
    cost_before_detection = None
    if labels.any():
        attack_start = df.loc[labels, "window_end"].min()
        first_alert_times = df.loc[alerts & labels, "window_end"]
        if len(first_alert_times):
            first_alert_time = first_alert_times.min()
            detection_latency = float(first_alert_time - attack_start)
            if "estimated_cost" in df.columns:
                mask = (df["window_end"] >= attack_start) & (df["window_end"] < first_alert_time)
                cost_before_detection = float(df.loc[mask, "estimated_cost"].sum())

    return {"detection_latency": detection_latency, "cost_before_detection": cost_before_detection}
