"""Read-only access to the existing pipeline's on-disk artifacts.

Every function here reads files the existing CLI pipeline
(experiments/run_experiment.py, experiments/summarize_results.py) already
produces. Nothing in this module invents or estimates a number — if a file
is missing, callers get None/empty and the frontend must say so.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from config import (
    DATA_EXPERIMENTS,
    DATA_FEATURES,
    DATA_RAW,
    EXPERIMENTS_CONFIGS,
    RESULTS_METRICS,
    RESULTS_TABLES,
    SCENARIO_PURPOSE,
    TRAFFIC_SCENARIOS,
)


def _clean(value: Any) -> Any:
    """Make a value JSON-safe (NaN/inf -> None)."""
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def _records_clean(df: pd.DataFrame) -> list[dict]:
    records = df.to_dict(orient="records")
    return [{k: _clean(v) for k, v in row.items()} for row in records]


def list_experiment_configs() -> list[dict]:
    """Every experiments/configs/*.yaml file, sorted by name."""
    out = []
    for path in sorted(EXPERIMENTS_CONFIGS.glob("*.yaml")):
        config = yaml.safe_load(path.read_text())
        out.append({"path": str(path.relative_to(EXPERIMENTS_CONFIGS.parent.parent)), "config": config})
    return out


def load_experiment_config(experiment_id: str) -> dict | None:
    path = EXPERIMENTS_CONFIGS / f"{experiment_id}.yaml"
    if not path.exists():
        # Ad-hoc simulator runs (webapp/backend/scenario_builder.py) write here.
        path = EXPERIMENTS_CONFIGS / "generated" / f"{experiment_id}.yaml"
    if not path.exists():
        # EDOS_MATCHED_E6_001 (E6, matched-signature calibration candidate)
        # was written under its own pending-review config subdirectory.
        path = EXPERIMENTS_CONFIGS / "matched_e6_pending_review" / f"{experiment_id}.yaml"
    if not path.exists():
        return None
    config = yaml.safe_load(path.read_text())
    scenario_type = config["experiment"]["scenario_type"]
    # Read the scenario file this config actually points to (correct for both
    # presets and ad-hoc-generated configs, which live under
    # traffic/scenarios/generated/ with the run's real parameters), falling
    # back to the type-level default file if that's missing.
    scenario_file = config["experiment"].get("scenario_file")
    scenario_path = (EXPERIMENTS_CONFIGS.parent.parent / scenario_file) if scenario_file else None
    if scenario_path is None or not scenario_path.exists():
        scenario_path = TRAFFIC_SCENARIOS / f"{scenario_type}.yaml"
    scenario = yaml.safe_load(scenario_path.read_text()) if scenario_path.exists() else None
    return {
        "experiment_id": experiment_id,
        "config_path": str(path.relative_to(EXPERIMENTS_CONFIGS.parent.parent)),
        "experiment": config["experiment"],
        "detector": config.get("detector", {}),
        "cost_model": config.get("cost_model", {}),
        "replica_sampler": config.get("replica_sampler", {}),
        "prometheus": config.get("prometheus", {}),
        "scenario_purpose": SCENARIO_PURPOSE.get(scenario_type, ""),
        "scenario": scenario,
        "phases": config.get("phases"),
    }


def load_metadata(experiment_id: str) -> dict | None:
    path = DATA_EXPERIMENTS / experiment_id / "metadata.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def has_saved_result(experiment_id: str) -> bool:
    return (DATA_EXPERIMENTS / experiment_id / "metadata.json").exists()


def load_features(experiment_id: str) -> list[dict]:
    # E3/E4 (MIX_001/INTERLEAVED_001) are deliberately written to
    # data/features/held_out/ instead, kept out of the main train/test
    # split — see docs/experiment_protocol.md section 8. Ad-hoc simulator
    # runs are similarly isolated under data/features/adhoc/ (see
    # webapp/backend/main.py's /api/simulator/* routes) so arbitrary
    # user-chosen simulator parameters never perturb the trained model.
    # e5_pending_review/matched_e6_pending_review/gen2_pending_review hold
    # E7-stealth, E6-matched-signature and Gen2-hard-negative repeatability
    # runs respectively — real measured data, just not yet promoted into
    # the main train/test split (docs/experiment_protocol.md sections 16, 20).
    candidates = [
        DATA_FEATURES / f"{experiment_id}.csv",
        DATA_FEATURES / "held_out" / f"{experiment_id}.csv",
        DATA_FEATURES / "adhoc" / f"{experiment_id}.csv",
        DATA_FEATURES / "baseline" / f"{experiment_id}.csv",
        DATA_FEATURES / "e5_pending_review" / f"{experiment_id}.csv",
        DATA_FEATURES / "matched_e6_pending_review" / f"{experiment_id}.csv",
        DATA_FEATURES / "gen2_pending_review" / f"{experiment_id}.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        return []
    df = pd.read_csv(path)
    return _records_clean(df)


def load_timeseries(experiment_id: str) -> list[dict]:
    path = DATA_RAW / experiment_id / "timeseries.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if df.empty:
        return []
    start = df["timestamp"].min()
    df = df.copy()
    df["elapsed_seconds"] = df["timestamp"] - start
    return _records_clean(df)


def load_locust_history(experiment_id: str) -> list[dict]:
    """Per-~2s Locust stats_history.csv snapshot, if present — used for
    request-rate / latency time series at finer resolution than the
    feature windows.

    An interleaved (E4) experiment has no single stats_history.csv — each
    phase writes its own under data/raw/<id>/phase_<i>_<type>/ — so those
    are concatenated in phase order with elapsed_seconds measured from
    the overall run start, giving one continuous timeline.
    """
    exp_dir = DATA_RAW / experiment_id
    if not exp_dir.exists():
        return []

    direct_matches = list(exp_dir.glob("*_stats_history.csv"))
    if direct_matches:
        frames = [pd.read_csv(direct_matches[0])]
    else:
        phase_dirs = sorted(p for p in exp_dir.iterdir() if p.is_dir() and p.name.startswith("phase_"))
        frames = []
        for phase_dir in phase_dirs:
            matches = list(phase_dir.glob("*_stats_history.csv"))
            if matches:
                frames.append(pd.read_csv(matches[0]))
        if not frames:
            return []

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[combined["Name"] == "Aggregated"].copy()
    if combined.empty:
        return []
    combined = combined.sort_values("Timestamp")
    start = combined["Timestamp"].min()
    combined["elapsed_seconds"] = combined["Timestamp"] - start
    return _records_clean(combined)


def load_match_report(experiment_id: str) -> dict | None:
    """The stored match_report.json for a matched-signature calibration
    candidate (e.g. EDOS_MATCHED_E6_001), written by
    experiments/match_quality.py::save_calibration_report — real measured
    axis-by-axis deltas against a specific reference experiment, never
    recomputed here. None if this experiment was never run through that
    calibration flow."""
    path = DATA_EXPERIMENTS / experiment_id / "match_report.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def list_all_experiment_ids() -> list[str]:
    if not DATA_EXPERIMENTS.exists():
        return []
    return sorted(p.name for p in DATA_EXPERIMENTS.iterdir() if (p / "metadata.json").exists())


def load_results_metrics(name: str) -> dict | None:
    path = RESULTS_METRICS / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_results_table(name: str) -> list[dict]:
    path = RESULTS_TABLES / f"{name}.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    return _records_clean(df)


def figures_available() -> list[str]:
    from config import RESULTS_FIGURES

    if not RESULTS_FIGURES.exists():
        return []
    return sorted(p.name for p in RESULTS_FIGURES.glob("*.png"))
