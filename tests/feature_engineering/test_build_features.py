import pandas as pd
import pytest

from feature_engineering.build_features import REQUIRED_RAW_COLUMNS, build_features


def _synthetic_raw(n_samples=20, interval=10):
    rows = []
    for i in range(n_samples):
        rows.append({
            "timestamp": i * interval,
            "request_count": i * 5,
            "error_count": i,
            "cheap_count": i * 2,
            "medium_count": i * 2,
            "expensive_count": i,
            "cache_hits": i * 3,
            "cache_misses": i,
            "conversions": i,
            "active_sessions": 10,
            "session_duration_sum": i * 30,
            "session_duration_count": i,
            "replica_count": 1 + (i // 5),
            "cpu_utilization_pct": 40.0 + i,
        })
    return pd.DataFrame(rows)


def test_raises_on_missing_columns():
    with pytest.raises(ValueError, match="missing required columns"):
        build_features(pd.DataFrame({"timestamp": [0, 1]}), window_seconds_list=[60])


def test_empty_raw_returns_empty_dataframe():
    empty = pd.DataFrame(columns=REQUIRED_RAW_COLUMNS)
    result = build_features(empty, window_seconds_list=[60])
    assert result.empty


def test_produces_rows_for_multiple_window_sizes():
    raw = _synthetic_raw(n_samples=30, interval=10)  # covers 0..290s
    result = build_features(raw, window_seconds_list=[60, 120])
    assert set(result["window_seconds"].unique()) == {60, 120}
    assert len(result) > 0


def test_label_and_experiment_id_columns_are_attached():
    raw = _synthetic_raw()
    result = build_features(raw, window_seconds_list=[60], label=1, experiment_id="EDOS_001")
    assert (result["label"] == 1).all()
    assert (result["experiment_id"] == "EDOS_001").all()


def test_no_future_leakage():
    """CLAUDE.md non-negotiable principle #11 (time-series integrity):
    features computed for a window ending at time t must be identical
    whether or not raw data AFTER t exists in the series.
    """
    raw = _synthetic_raw(n_samples=40, interval=10)  # covers 0..390s
    window_seconds = 60

    full_result = build_features(raw, window_seconds_list=[window_seconds])

    truncated = raw[raw["timestamp"] <= 190].reset_index(drop=True)
    truncated_result = build_features(truncated, window_seconds_list=[window_seconds])

    common_ends = set(full_result["window_end"]) & set(truncated_result["window_end"])
    assert common_ends, "test setup produced no overlapping windows"

    full_indexed = full_result.set_index("window_end")
    truncated_indexed = truncated_result.set_index("window_end")

    for window_end in common_ends:
        pd.testing.assert_series_equal(
            full_indexed.loc[window_end].sort_index(),
            truncated_indexed.loc[window_end].sort_index(),
            check_names=False,
        )


def test_windows_do_not_overlap_by_default_step():
    raw = _synthetic_raw(n_samples=30, interval=10)
    result = build_features(raw, window_seconds_list=[60])
    ends = sorted(result["window_end"].tolist())
    diffs = [b - a for a, b in zip(ends, ends[1:])]
    assert all(d == 60 for d in diffs)


def test_custom_step_can_produce_overlapping_windows():
    raw = _synthetic_raw(n_samples=30, interval=10)
    result = build_features(raw, window_seconds_list=[60], step_seconds=10)
    ends = sorted(result["window_end"].unique().tolist())
    diffs = [b - a for a, b in zip(ends, ends[1:])]
    assert all(d == 10 for d in diffs)


def test_combined_relationship_features_present():
    raw = _synthetic_raw()
    result = build_features(raw, window_seconds_list=[60])
    expected = [
        "cost_per_request_over_request_rate",
        "replica_count_over_request_rate",
        "cpu_utilization_over_request_rate",
        "expensive_ratio_times_cost_per_request",
        "replica_growth_rate_over_request_rate",
    ]
    for col in expected:
        assert col in result.columns


def test_no_nan_or_inf_in_output():
    raw = _synthetic_raw(n_samples=30, interval=10)
    result = build_features(raw, window_seconds_list=[30, 60])
    numeric = result.select_dtypes(include="number")
    assert not numeric.isna().any().any()
    assert not (numeric.abs() == float("inf")).any().any()
