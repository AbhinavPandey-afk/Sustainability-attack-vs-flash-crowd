import pandas as pd
import pytest

from models.feature_sets import ABLATION_FEATURE_SETS, select_features


def test_all_ablation_sets_are_nonempty():
    for name, columns in ABLATION_FEATURE_SETS.items():
        assert columns, f"{name} has no columns"


def test_model_c_is_superset_of_d_and_e():
    c = set(ABLATION_FEATURE_SETS["C_proposed_full"])
    d = set(ABLATION_FEATURE_SETS["D_proposed_without_cost"])
    e = set(ABLATION_FEATURE_SETS["E_proposed_without_behaviour"])
    assert d <= c
    assert e <= c


def test_model_a_is_subset_of_every_other_model():
    a = set(ABLATION_FEATURE_SETS["A_volume_only"])
    for name, columns in ABLATION_FEATURE_SETS.items():
        assert a <= set(columns), f"Model A's volume features missing from {name}"


def test_select_features_returns_only_requested_columns():
    df = pd.DataFrame({col: [1, 2] for col in ABLATION_FEATURE_SETS["A_volume_only"]})
    df["extra_column_not_in_any_set"] = [9, 9]
    result = select_features(df, "A_volume_only")
    assert list(result.columns) == ABLATION_FEATURE_SETS["A_volume_only"]


def test_select_features_raises_on_missing_columns():
    df = pd.DataFrame({"request_rate": [1, 2]})
    with pytest.raises(ValueError, match="missing columns"):
        select_features(df, "C_proposed_full")


def test_select_features_raises_on_unknown_model_name():
    df = pd.DataFrame({"request_rate": [1, 2]})
    with pytest.raises(ValueError, match="Unknown ablation model"):
        select_features(df, "not_a_real_model")
