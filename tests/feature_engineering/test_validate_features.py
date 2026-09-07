import math

import pandas as pd

from feature_engineering.validate_features import validate


def _good_df():
    return pd.DataFrame(
        {
            "window_end": [60, 120, 180],
            "window_seconds": [60, 60, 60],
            "label": [0, 0, 1],
            "experiment_id": ["FC_001", "FC_001", "EDOS_001"],
            "request_rate": [1.0, 2.0, 0.5],
        }
    )


def test_valid_dataframe_passes():
    report = validate(_good_df())
    assert report.ok
    assert report.errors == []


def test_empty_dataframe_fails():
    report = validate(pd.DataFrame())
    assert not report.ok
    assert any("empty" in e for e in report.errors)


def test_nan_values_detected():
    df = _good_df()
    df.loc[0, "request_rate"] = math.nan
    report = validate(df)
    assert not report.ok
    assert any("NaN" in e for e in report.errors)


def test_infinite_values_detected():
    df = _good_df()
    df.loc[0, "request_rate"] = float("inf")
    report = validate(df)
    assert not report.ok
    assert any("Infinite" in e for e in report.errors)


def test_invalid_label_values_detected():
    df = _good_df()
    df.loc[0, "label"] = 2
    report = validate(df)
    assert not report.ok
    assert any("labels must be only 0 or 1" in e for e in report.errors)


def test_duplicated_windows_detected():
    df = _good_df()
    df.loc[1, "window_end"] = df.loc[0, "window_end"]  # duplicate within same window_seconds group
    report = validate(df)
    assert not report.ok
    assert any("duplicated observation windows" in e for e in report.errors)


def test_missing_optional_columns_are_reported_as_not_checked_not_errors():
    df = pd.DataFrame({"request_rate": [1.0, 2.0]})
    report = validate(df)
    assert report.ok
    assert any("label" in item for item in report.not_checked)
    assert any("train/test experiment overlap" in item for item in report.not_checked)
