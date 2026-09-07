#!/usr/bin/env python
"""Run an interleaved (E4) experiment: alternating flash-crowd/EDoS
phases back-to-back under one continuous replica-sampling + Prometheus
observation window, producing PER-WINDOW ground-truth labels instead of
one scalar label per experiment (CLAUDE.md section 13, E4).

Reuses the exact same primitives as experiments/run_experiment.py
(ReplicaSampler, PrometheusClient, align_raw_dataframe, build_features,
validate) — this is an orchestration variant, not new pipeline logic.

Usage:
    python experiments/run_interleaved_experiment.py \
        experiments/configs/INTERLEAVED_001.yaml --host http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.src.cost import CostModelConfig  # noqa: E402
from experiments.run_experiment import git_commit  # noqa: E402
from feature_engineering.build_features import build_features  # noqa: E402
from feature_engineering.collect_metrics import PrometheusClient, ReplicaSampler, align_raw_dataframe  # noqa: E402
from feature_engineering.validate_features import validate  # noqa: E402


def label_for_timestamp(timestamp: float, phase_schedule: list[dict]) -> int:
    """Maps a feature window's `window_end` timestamp to the ground-truth
    label of the phase active at that time. Falls back to the nearest
    phase for a timestamp that lands just outside every recorded
    [start, end) interval (clock/subprocess-startup slop at the edges).
    """
    for phase in phase_schedule:
        if phase["start"] <= timestamp <= phase["end"]:
            return phase["label"]
    if timestamp < phase_schedule[0]["start"]:
        return phase_schedule[0]["label"]
    if timestamp > phase_schedule[-1]["end"]:
        return phase_schedule[-1]["label"]

    def distance(phase: dict) -> float:
        return min(abs(timestamp - phase["start"]), abs(timestamp - phase["end"]))

    return min(phase_schedule, key=distance)["label"]


def run_interleaved_experiment(
    config_path: Path,
    host: str,
    default_prometheus_url: str = "http://localhost:9090",
    output_features_dir: Path | None = None,
) -> dict:
    config = yaml.safe_load(config_path.read_text())
    exp = config["experiment"]
    experiment_id = exp["name"]
    phases = config["phases"]
    total_duration = sum(p["duration_seconds"] for p in phases)

    replica_cfg = config.get("replica_sampler", {})
    sampler = ReplicaSampler(
        namespace=replica_cfg.get("namespace", "cascade"),
        deployment=replica_cfg.get("deployment", "cascade-app"),
        hpa=replica_cfg.get("hpa", "cascade-app"),
    )

    overall_start = time.time()
    sampler_thread = threading.Thread(
        target=sampler.sample_for,
        kwargs={"duration_seconds": total_duration, "interval_seconds": replica_cfg.get("interval_seconds", 5)},
    )
    sampler_thread.start()

    # Staged, then promoted atomically on full success — see the matching
    # comment in experiments/run_experiment.py for why.
    final_raw_dir = REPO_ROOT / "data" / "raw" / experiment_id
    staging_raw_dir = REPO_ROOT / "data" / "raw" / f"{experiment_id}.inprogress"
    if staging_raw_dir.exists():
        shutil.rmtree(staging_raw_dir)

    phase_schedule = []
    for i, phase in enumerate(phases):
        scenario_file = REPO_ROOT / phase["scenario_file"]
        phase_output_dir = staging_raw_dir / f"phase_{i}_{phase['scenario_type']}"
        phase_start = time.time()
        cmd = [
            sys.executable, str(REPO_ROOT / "traffic" / "run_scenario.py"), str(scenario_file),
            "--host", host, "--run-time", f"{phase['duration_seconds']}s",
            "--output-dir", str(phase_output_dir),
        ]
        subprocess.run(cmd, cwd=REPO_ROOT, check=True)
        phase_end = time.time()
        phase_schedule.append(
            {
                "index": i,
                "scenario_type": phase["scenario_type"],
                "scenario_file": phase["scenario_file"],
                "label": phase["label"],
                "planned_duration_seconds": phase["duration_seconds"],
                "start": phase_start,
                "end": phase_end,
            }
        )

    sampler_thread.join()
    overall_end = time.time()

    prometheus_url = config.get("prometheus", {}).get("base_url", default_prometheus_url)
    prom = PrometheusClient(base_url=prometheus_url)
    app_counters = prom.collect_app_metrics(start=overall_start, end=overall_end, step_seconds=5)
    raw = align_raw_dataframe(app_counters, sampler.samples)

    staging_raw_dir.mkdir(parents=True, exist_ok=True)
    raw.to_csv(staging_raw_dir / "timeseries.csv", index=False)

    cost_cfg = CostModelConfig.from_dict(config.get("cost_model", {}))
    detector_cfg = config.get("detector", {})
    features = build_features(
        raw,
        window_seconds_list=detector_cfg.get("window_seconds", [20]),
        step_seconds=detector_cfg.get("step_seconds"),
        cost_config=cost_cfg,
        label=None,
        experiment_id=experiment_id,
    )
    if not features.empty:
        features["label"] = features["window_end"].apply(lambda t: label_for_timestamp(t, phase_schedule))

    report = validate(features)

    features_dir = output_features_dir or (REPO_ROOT / "data" / "features" / "held_out")
    features_path = features_dir / f"{experiment_id}.csv"
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(features_path, index=False)

    # Commit point — see experiments/run_experiment.py.
    if final_raw_dir.exists():
        shutil.rmtree(final_raw_dir)
    staging_raw_dir.rename(final_raw_dir)
    timeseries_path = final_raw_dir / "timeseries.csv"

    metadata = {
        "experiment_id": experiment_id,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "config_file": str(config_path),
        "seed": exp.get("seed"),
        "scenario_type": "interleaved",
        "duration_seconds": total_duration,
        "host": host,
        "n_raw_samples": len(raw),
        "n_feature_rows": len(features),
        "timeseries_path": str(timeseries_path),
        "validation": report.to_dict(),
        "features_path": str(features_path),
        "phases": phase_schedule,
    }
    metadata_dir = REPO_ROOT / "data" / "experiments" / experiment_id
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="Path to an interleaved experiment config YAML")
    parser.add_argument("--host", required=True, help="Reachable URL of the app under test")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument("--output-features-dir")
    args = parser.parse_args()

    output_features_dir = Path(args.output_features_dir) if args.output_features_dir else None
    metadata = run_interleaved_experiment(Path(args.config), args.host, args.prometheus_url, output_features_dir)
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
