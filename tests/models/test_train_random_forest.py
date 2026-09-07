from models.train_random_forest import train
from tests.models._fixtures import ALL_FEATURE_COLUMNS, make_synthetic_dataset


def test_train_produces_a_usable_model_on_separable_synthetic_data():
    df = make_synthetic_dataset()
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    split = len(X) * 7 // 10
    trained = train(X.iloc[:split], y.iloc[:split], X.iloc[split:], y.iloc[split:], params={"n_estimators": 30})

    preds = trained.predict(X.iloc[split:])
    accuracy = (preds == y.iloc[split:].values).mean()
    assert accuracy > 0.9


def test_train_with_empty_validation_set_defaults_threshold_safely():
    df = make_synthetic_dataset()
    X = df[ALL_FEATURE_COLUMNS]
    y = df["label"]
    trained = train(X, y, X.iloc[0:0], y.iloc[0:0], params={"n_estimators": 10})
    assert trained.threshold == 0.5
