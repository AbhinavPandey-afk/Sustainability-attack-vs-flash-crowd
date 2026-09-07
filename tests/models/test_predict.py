import pandas as pd

from models.predict import smoothed_alert


def test_smoothed_alert_requires_k_of_last_n():
    proba = pd.Series([0.9, 0.1, 0.9, 0.9, 0.9])
    result = smoothed_alert(proba, threshold=0.5, k=2, n=3)
    assert list(result) == [False, False, True, True, True]


def test_smoothed_alert_k_equals_1_matches_raw_alerts_within_trailing_window():
    proba = pd.Series([0.9, 0.1, 0.1])
    result = smoothed_alert(proba, threshold=0.5, k=1, n=3)
    assert list(result) == [True, True, True]


def test_smoothed_alert_k_equals_n_requires_every_window_in_range():
    proba = pd.Series([0.9, 0.9, 0.9, 0.1, 0.9])
    result = smoothed_alert(proba, threshold=0.5, k=3, n=3)
    assert list(result) == [False, False, True, False, False]
