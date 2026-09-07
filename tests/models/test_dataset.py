import pandas as pd
import pytest

from models.dataset import assert_no_overlap, random_split_by_experiment, split_by_experiment


def _df():
    return pd.DataFrame({
        "experiment_id": ["A", "A", "B", "B", "C", "C", "D", "D"],
        "label": [0, 0, 0, 0, 1, 1, 1, 1],
        "value": range(8),
    })


def test_split_by_experiment_explicit():
    train, val, test = split_by_experiment(
        _df(), train_experiments=["A", "B"], val_experiments=["C"], test_experiments=["D"]
    )
    assert set(train["experiment_id"]) == {"A", "B"}
    assert set(val["experiment_id"]) == {"C"}
    assert set(test["experiment_id"]) == {"D"}


def test_split_by_experiment_raises_on_overlap():
    with pytest.raises(ValueError, match="more than one split"):
        split_by_experiment(_df(), train_experiments=["A"], val_experiments=["A"], test_experiments=["D"])


def test_split_by_experiment_requires_experiment_id_column():
    with pytest.raises(ValueError, match="experiment_id"):
        split_by_experiment(pd.DataFrame({"x": [1, 2]}))


def test_random_split_by_experiment_is_reproducible_with_same_seed():
    df = _df()
    split1 = random_split_by_experiment(df, test_fraction=0.25, val_fraction=0.25, seed=7)
    split2 = random_split_by_experiment(df, test_fraction=0.25, val_fraction=0.25, seed=7)
    for a, b in zip(split1, split2):
        assert set(a["experiment_id"]) == set(b["experiment_id"])


def test_random_split_by_experiment_never_splits_an_experiment_across_sets():
    df = _df()
    train, val, test = random_split_by_experiment(df, test_fraction=0.25, val_fraction=0.25, seed=1)
    assert_no_overlap(train, val, test)  # should not raise
    all_ids = set(train["experiment_id"]) | set(val["experiment_id"]) | set(test["experiment_id"])
    assert all_ids == {"A", "B", "C", "D"}


def test_assert_no_overlap_raises_on_manual_overlap():
    train = pd.DataFrame({"experiment_id": ["A", "B"]})
    val = pd.DataFrame({"experiment_id": ["B"]})
    test = pd.DataFrame({"experiment_id": ["C"]})
    with pytest.raises(AssertionError, match="overlap"):
        assert_no_overlap(train, val, test)


def test_random_split_stratifies_by_label_both_classes_in_each_split():
    """Regression test: with a small number of experiments, an
    unstratified shuffle could put an entire class into one split,
    leaving a classifier with nothing to learn from the other side."""
    df = pd.DataFrame({
        "experiment_id": ["EDOS_1", "EDOS_2", "EDOS_3", "FC_1", "FC_2", "FC_3"],
        "label": [1, 1, 1, 0, 0, 0],
    })
    for seed in range(10):  # try several seeds — must hold for all of them
        train, val, test = random_split_by_experiment(df, test_fraction=0.3, val_fraction=0.3, seed=seed)
        for split_df in (train, val, test):
            if len(split_df):
                assert set(split_df["label"].unique()) == {0, 1}, (
                    f"seed={seed} produced a single-class split: {split_df['experiment_id'].tolist()}"
                )


def test_within_experiment_rows_never_split():
    df = _df()
    train, val, test = random_split_by_experiment(df, test_fraction=0.25, val_fraction=0.25, seed=3)
    for experiment_id in df["experiment_id"].unique():
        present_in = [
            name
            for name, split_df in [("train", train), ("val", val), ("test", test)]
            if experiment_id in set(split_df["experiment_id"])
        ]
        assert len(present_in) <= 1
