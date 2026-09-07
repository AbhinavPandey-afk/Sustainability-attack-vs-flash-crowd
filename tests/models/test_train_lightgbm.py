import numpy as np

from models.train_lightgbm import train, tune_threshold
from tests.models._fixtures import ALL_FEATURE_COLUMNS, make_synthetic_dataset


def test_train_produces_a_usable_model_on_separable_synthetic_data():
    df = make_synthetic_dataset()
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    split = len(X) * 7 // 10
    trained = train(X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:], params={"n_estimators": 20})

    preds = trained.predict(X.iloc[split:])
    accuracy = (preds == y.iloc[split:].values).mean()
    assert accuracy > 0.9  # data was constructed to be easily separable

    assert trained.feature_names == list(X.columns)
    assert 0.0 <= trained.threshold <= 1.0


def test_tune_threshold_picks_a_threshold_that_maximizes_f1_on_perfect_scores():
    y_true = np.array([0, 0, 0, 1, 1, 1])
    proba = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 0.95])
    threshold = tune_threshold(y_true, proba)
    preds = (proba >= threshold).astype(int)
    assert list(preds) == list(y_true)


def test_tune_threshold_does_not_default_blindly_to_point_five():
    y_true = np.array([0] * 5 + [1] * 5)
    proba = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.7, 0.75, 0.8, 0.85, 0.9])
    threshold = tune_threshold(y_true, proba)
    assert 0.05 < threshold <= 0.7


def test_train_learns_something_on_a_very_small_dataset():
    """Regression test: LightGBM's built-in min_child_samples default (20)
    silently prevented ANY split on datasets this small (a realistic
    scale for a handful of short local experiment runs — CLAUDE.md
    section 25), degenerating to a constant-0.5-probability model. Caught
    via experiments/summarize_results.py's end-to-end test on real
    experiment-level splits; this locks the fix in at the unit level."""
    df = make_synthetic_dataset(n_experiments_per_class=1, rows_per_experiment=8)  # 16 rows total
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    trained = train(X, y, X.iloc[0:0], y.iloc[0:0])

    proba = trained.predict_proba(X)
    assert proba.std() > 0.01, "model produced a near-constant probability — it learned nothing"
    preds = trained.predict(X)
    assert (preds == y.values).mean() > 0.8


def test_train_with_empty_validation_set_defaults_threshold_safely():
    df = make_synthetic_dataset()
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    trained = train(X, y, X.iloc[0:0], y.iloc[0:0], params={"n_estimators": 10})
    assert trained.threshold == 0.5
