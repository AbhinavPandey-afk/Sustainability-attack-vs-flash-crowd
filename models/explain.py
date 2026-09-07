"""SHAP explainability for the final LightGBM model — CLAUDE.md section 27.

Answers: which features actually distinguish EDoS from flash crowds?
Rankings are always derived from the trained model's real SHAP values,
never hard-coded (CLAUDE.md: "Do not hard-code these rankings.").
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shap


def compute_shap_values(trained_model, X: pd.DataFrame) -> np.ndarray:
    explainer = shap.TreeExplainer(trained_model.model)
    shap_values = explainer.shap_values(X[trained_model.feature_names])
    # Some SHAP/model combinations return a list [class0_contribs,
    # class1_contribs] for binary classifiers; others return a single 2D
    # array already for the positive class. Normalize to the latter.
    if isinstance(shap_values, list):
        shap_values = shap_values[1]
    elif isinstance(shap_values, np.ndarray) and shap_values.ndim == 3:
        # (n_samples, n_features, n_classes) — take the positive class.
        shap_values = shap_values[:, :, 1]
    return shap_values


def global_feature_importance(trained_model, X: pd.DataFrame) -> pd.DataFrame:
    shap_values = compute_shap_values(trained_model, X)
    mean_abs = np.abs(shap_values).mean(axis=0)
    return (
        pd.DataFrame({"feature": trained_model.feature_names, "mean_abs_shap": mean_abs})
        .sort_values("mean_abs_shap", ascending=False)
        .reset_index(drop=True)
    )
