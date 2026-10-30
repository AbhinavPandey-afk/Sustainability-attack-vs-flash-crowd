"""Train/validation/test dataset assembly (CLAUDE.md section 17 / non-
negotiable principle #12).

The split unit is the EXPERIMENT RUN (`experiment_id`), never an
individual feature window/row — adjacent time windows from the same
continuous experiment must never be split across train and test, or the
model would trivially "leak" from near-duplicate neighbouring windows.
"""
from __future__ import annotations

import random

import pandas as pd


def split_by_experiment(
    df: pd.DataFrame,
    train_experiments: list | None = None,
    val_experiments: list | None = None,
    test_experiments: list | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Explicit, named split: the caller decides which experiment_ids go
    to which split. An experiment_id not named in any list is excluded
    from all three (never silently included)."""
    if "experiment_id" not in df.columns:
        raise ValueError("df must have an 'experiment_id' column to split by experiment")

    train_set = set(train_experiments or [])
    val_set = set(val_experiments or [])
    test_set = set(test_experiments or [])

    overlap = (train_set & val_set) | (train_set & test_set) | (val_set & test_set)
    if overlap:
        raise ValueError(f"experiment_ids appear in more than one split: {sorted(overlap)}")

    train_df = df[df["experiment_id"].isin(train_set)].reset_index(drop=True)
    val_df = df[df["experiment_id"].isin(val_set)].reset_index(drop=True)
    test_df = df[df["experiment_id"].isin(test_set)].reset_index(drop=True)
    return train_df, val_df, test_df


def _split_ids(ids: list, test_fraction: float, val_fraction: float, rng: random.Random) -> tuple[list, list, list]:
    ids = sorted(ids)
    rng.shuffle(ids)
    n = len(ids)
    n_test = max(1, round(n * test_fraction)) if n > 1 else 0
    n_val = max(1, round(n * val_fraction)) if n > (1 + n_test) else 0
    test_ids = ids[:n_test]
    val_ids = ids[n_test : n_test + n_val]
    train_ids = ids[n_test + n_val :]
    return train_ids, val_ids, test_ids


def random_split_by_experiment(
    df: pd.DataFrame,
    test_fraction: float = 0.2,
    val_fraction: float = 0.2,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Randomly assigns whole experiments (never individual windows) to
    train/val/test, with a fixed seed for reproducibility (CLAUDE.md
    section 29).

    When a `label` column is present, the split is STRATIFIED by each
    experiment's label: each class's experiments are split separately and
    then combined. Without this, a small number of experiments (a very
    real regime for this project — see CLAUDE.md section 25 on limited
    local runs) can easily place an entire class into just one split,
    leaving a model with nothing to learn from one side of the boundary.
    """
    if "experiment_id" not in df.columns:
        raise ValueError("df must have an 'experiment_id' column to split by experiment")

    rng = random.Random(seed)

    if "label" in df.columns:
        exp_labels = df.groupby("experiment_id")["label"].first()
        train_ids, val_ids, test_ids = [], [], []
        for label_value in sorted(exp_labels.unique()):
            group_ids = exp_labels[exp_labels == label_value].index.tolist()
            group_train, group_val, group_test = _split_ids(group_ids, test_fraction, val_fraction, rng)
            train_ids += group_train
            val_ids += group_val
            test_ids += group_test
    else:
        experiment_ids = df["experiment_id"].unique().tolist()
        train_ids, val_ids, test_ids = _split_ids(experiment_ids, test_fraction, val_fraction, rng)

    return split_by_experiment(df, train_ids, val_ids, test_ids)


def assert_no_overlap(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame) -> None:
    """Raises AssertionError if any experiment_id appears in more than one
    of the three DataFrames. Call this right before training as a final
    guard, independent of how the split was produced."""
    train_ids = set(train_df["experiment_id"]) if "experiment_id" in train_df.columns else set()
    val_ids = set(val_df["experiment_id"]) if "experiment_id" in val_df.columns else set()
    test_ids = set(test_df["experiment_id"]) if "experiment_id" in test_df.columns else set()

    overlap = (train_ids & val_ids) | (train_ids & test_ids) | (val_ids & test_ids)
    if overlap:
        raise AssertionError(f"experiment_id overlap detected across splits: {sorted(overlap)}")
