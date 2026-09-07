import json

from experiments.summarize_results import load_dataset, run
from tests.models._fixtures import ALL_FEATURE_COLUMNS, make_synthetic_dataset


def _write_per_experiment_csvs(df, features_dir):
    features_dir.mkdir(parents=True, exist_ok=True)
    for experiment_id, group in df.groupby("experiment_id"):
        group.to_csv(features_dir / f"{experiment_id}.csv", index=False)


def test_load_dataset_concatenates_all_csvs(tmp_path):
    df = make_synthetic_dataset(n_experiments_per_class=1, rows_per_experiment=3)
    features_dir = tmp_path / "features"
    _write_per_experiment_csvs(df, features_dir)

    loaded = load_dataset(features_dir)
    assert len(loaded) == len(df)


def test_load_dataset_empty_dir_returns_empty_dataframe(tmp_path):
    empty_dir = tmp_path / "features"
    empty_dir.mkdir()
    assert load_dataset(empty_dir).empty


def test_run_end_to_end_on_synthetic_dataset_produces_expected_artifacts(tmp_path):
    """Exercises the full orchestration pipeline (split -> ablation train
    -> RF comparison -> baselines -> SHAP -> figures/tables/metrics)
    without needing a live cluster, using the same synthetic dataset the
    models/ unit tests use."""
    df = make_synthetic_dataset(n_experiments_per_class=3, rows_per_experiment=8)
    features_dir = tmp_path / "features"
    _write_per_experiment_csvs(df, features_dir)

    results_dir = tmp_path / "results"
    exit_code = run(features_dir, results_dir, seed=1)

    assert exit_code == 0
    assert (results_dir / "tables" / "ablation_results.csv").exists()
    assert (results_dir / "tables" / "model_comparison.csv").exists()
    assert (results_dir / "tables" / "baseline_results.csv").exists()
    assert (results_dir / "tables" / "feature_statistics.csv").exists()
    assert (results_dir / "figures" / "confusion_matrix.png").exists()
    assert (results_dir / "figures" / "shap_summary.png").exists()
    assert (results_dir / "metrics" / "experiment_summary.json").exists()

    summary = json.loads((results_dir / "metrics" / "experiment_summary.json").read_text())
    assert summary["n_experiments"] == 6
    assert "C_proposed_full" in summary["models"]
    assert summary["models"]["C_proposed_full"]["accuracy"] > 0.7  # data built to be easily separable


def test_run_evaluates_held_out_mixed_and_interleaved_csvs_without_polluting_main_split(tmp_path):
    """E3/E4 (MIX_001/INTERLEAVED_001) must be evaluated against the
    already-trained model but never enter the main train/val/test split —
    docs/experiment_protocol.md section 8."""
    df = make_synthetic_dataset(n_experiments_per_class=3, rows_per_experiment=8)
    features_dir = tmp_path / "features"
    _write_per_experiment_csvs(df, features_dir)

    held_out_dir = features_dir / "held_out"
    held_out_dir.mkdir(parents=True)
    mix_df = make_synthetic_dataset(n_experiments_per_class=1, rows_per_experiment=1, seed=7)
    mix_df = mix_df[mix_df["label"] == 1].copy()  # E3: attack present throughout
    mix_df["experiment_id"] = "MIX_001"
    mix_df[["window_end", "window_seconds", "label", "experiment_id", "estimated_cost", *ALL_FEATURE_COLUMNS]].to_csv(
        held_out_dir / "MIX_001.csv", index=False
    )

    results_dir = tmp_path / "results"
    exit_code = run(features_dir, results_dir, seed=1)
    assert exit_code == 0

    # held-out CSVs must never appear in the main dataset split.
    summary = json.loads((results_dir / "metrics" / "experiment_summary.json").read_text())
    all_split_experiments = (
        summary["train_experiments"] + summary["val_experiments"] + summary["test_experiments"]
    )
    assert "MIX_001" not in all_split_experiments
    assert summary["n_experiments"] == 6

    mixed_path = results_dir / "metrics" / "mixed_interleaved_evaluation.json"
    assert mixed_path.exists()
    mixed_eval = json.loads(mixed_path.read_text())
    assert "MIX_001" in mixed_eval
    assert mixed_eval["MIX_001"]["cascade_lightgbm"]["n_windows"] == 1
    assert "rate_limiter" in mixed_eval["MIX_001"]
    assert "volumetric_detector" in mixed_eval["MIX_001"]


def test_run_writes_empty_mixed_interleaved_evaluation_when_no_held_out_data(tmp_path):
    df = make_synthetic_dataset(n_experiments_per_class=3, rows_per_experiment=8)
    features_dir = tmp_path / "features"
    _write_per_experiment_csvs(df, features_dir)

    results_dir = tmp_path / "results"
    exit_code = run(features_dir, results_dir, seed=1)
    assert exit_code == 0

    mixed_eval = json.loads((results_dir / "metrics" / "mixed_interleaved_evaluation.json").read_text())
    assert mixed_eval == {}


def test_run_with_no_csvs_returns_nonzero_and_writes_no_output(tmp_path):
    features_dir = tmp_path / "features"
    features_dir.mkdir()
    results_dir = tmp_path / "results"
    exit_code = run(features_dir, results_dir, seed=1)
    assert exit_code == 1
    assert not (results_dir / "metrics" / "experiment_summary.json").exists()
