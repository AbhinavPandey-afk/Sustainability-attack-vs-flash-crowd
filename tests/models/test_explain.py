from models.explain import compute_shap_values, global_feature_importance
from models.train_lightgbm import train
from tests.models._fixtures import ALL_FEATURE_COLUMNS, make_synthetic_dataset


def test_global_feature_importance_ranks_the_injected_signal_columns_highly():
    df = make_synthetic_dataset()
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    split = len(X) * 7 // 10
    trained = train(X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:], params={"n_estimators": 30})

    importance = global_feature_importance(trained, X.iloc[split:])
    assert list(importance.columns) == ["feature", "mean_abs_shap"]
    assert len(importance) == len(ALL_FEATURE_COLUMNS)

    # The columns deliberately made strongly predictive should clearly
    # beat the pure-noise columns (not asserting an exact rank — SHAP can
    # reorder closely-correlated features).
    top_5 = set(importance.head(5)["feature"])
    assert "expensive_endpoint_ratio" in top_5 or "cost_per_request" in top_5


def test_shap_values_shape_matches_input():
    df = make_synthetic_dataset()
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    trained = train(X, y, X.iloc[0:0], y.iloc[0:0], params={"n_estimators": 10})
    shap_values = compute_shap_values(trained, X)
    assert shap_values.shape == (len(X), len(ALL_FEATURE_COLUMNS))
