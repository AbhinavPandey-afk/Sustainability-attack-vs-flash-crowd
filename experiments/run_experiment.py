#!/usr/bin/env python
"""Run a single labeled experiment: traffic generation + replica sampling
+ Prometheus collection + feature extraction, saving features and
reproducibility metadata (CLAUDE.md section 29).

Usage:
    python experiments/run_experiment.py experiments/configs/EDOS_001.yaml \
        --host http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.src.cost import CostModelConfig  # noqa: E402
from feature_engineering.build_features import build_features  # noqa: E402
from feature_engineering.collect_metrics import PrometheusClient, ReplicaSampler, align_raw_dataframe  # noqa: E402
from feature_engineering.validate_features import validate  # noqa: E402


class RunCancelled(Exception):
    """Raised when a live run is cancelled mid-flight (dashboard Stop button)."""


def _kill_process_tree(pid: int) -> None:
    """Kills a process and its children. Plain Popen.terminate()/.kill() does
    NOT reach a subprocess's own children on Windows, so the Locust process
    launched by traffic/run_scenario.py would survive a naive terminate()
    call — this kills the whole tree rooted at pid instead."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    else:
        import signal

        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def run_experiment(
    config_path: Path,
    host: str,
    default_prometheus_url: str = "http://localhost:9090",
    output_features_dir: Path | None = None,
    cancel_event: threading.Event | None = None,
    on_subprocess_start: Callable[[int], None] | None = None,
) -> dict:
    config = yaml.safe_load(config_path.read_text())
    exp = config["experiment"]
    experiment_id = exp["name"]
    label = exp["label"]
    duration_seconds = exp["duration_seconds"]

    replica_cfg = config.get("replica_sampler", {})
    sampler = ReplicaSampler(
        namespace=replica_cfg.get("namespace", "cascade"),
        deployment=replica_cfg.get("deployment", "cascade-app"),
        hpa=replica_cfg.get("hpa", "cascade-app"),
    )

    start_time = time.time()
    sampler_thread = threading.Thread(
        target=sampler.sample_for,
        kwargs={"duration_seconds": duration_seconds, "interval_seconds": replica_cfg.get("interval_seconds", 5)},
    )
    sampler_thread.start()

    # Traffic generation writes to a staging directory first, and it is only
    # promoted to the "real" data/raw/<id>/ location once the entire run
    # succeeds (see the "commit" comment below). Without this, a run that
    # generates traffic successfully but then fails during Prometheus
    # collection or feature-building would overwrite a previously-good
    # experiment's raw telemetry with a partial/failed run's data while
    # leaving its metadata.json/features.csv untouched — an inconsistent,
    # silently-wrong "saved result". Observed happening in practice via the
    # dashboard's live-run button hitting the documented Prometheus
    # connection flakiness (docs/experiment_protocol.md section 7).
    final_output_dir = REPO_ROOT / "data" / "raw" / experiment_id
    staging_output_dir = REPO_ROOT / "data" / "raw" / f"{experiment_id}.inprogress"
    if staging_output_dir.exists():
        shutil.rmtree(staging_output_dir)

    scenario_file = REPO_ROOT / exp["scenario_file"]
    cmd = [
        sys.executable, str(REPO_ROOT / "traffic" / "run_scenario.py"), str(scenario_file),
        "--host", host, "--run-time", f"{duration_seconds}s",
        "--output-dir", str(staging_output_dir),
    ]

    popen_kwargs: dict = {}
    if sys.platform == "win32":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["preexec_fn"] = os.setsid  # own process group, so killpg reaches Locust's children too

    try:
        proc = subprocess.Popen(cmd, cwd=REPO_ROOT, **popen_kwargs)
        if on_subprocess_start:
            on_subprocess_start(proc.pid)
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                _kill_process_tree(proc.pid)
                proc.wait(timeout=10)
                raise RunCancelled(f"Cancelled while generating traffic for {config_path.name}")
            time.sleep(0.5)
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    except RunCancelled:
        if staging_output_dir.exists():
            shutil.rmtree(staging_output_dir, ignore_errors=True)
        raise

    sampler_thread.join()
    end_time = time.time()

    prometheus_url = config.get("prometheus", {}).get("base_url", default_prometheus_url)
    prom = PrometheusClient(base_url=prometheus_url)
    app_counters = prom.collect_app_metrics(start=start_time, end=end_time, step_seconds=5)
    raw = align_raw_dataframe(app_counters, sampler.samples)

    raw.to_csv(staging_output_dir / "timeseries.csv", index=False)

    cost_cfg = CostModelConfig.from_dict(config.get("cost_model", {}))
    detector_cfg = config.get("detector", {})
    features = build_features(
        raw,
        window_seconds_list=detector_cfg.get("window_seconds", [60]),
        step_seconds=detector_cfg.get("step_seconds"),
        cost_config=cost_cfg,
        label=label,
        experiment_id=experiment_id,
    )

    report = validate(features)

    features_dir = output_features_dir or (REPO_ROOT / "data" / "features")
    features_path = features_dir / f"{experiment_id}.csv"
    features_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_csv(features_path, index=False)

    # Commit point: every step that can fail (traffic generation, Prometheus
    # collection, feature building/validation) has already succeeded, so it
    # is now safe to replace any previous raw telemetry for this experiment.
    if final_output_dir.exists():
        shutil.rmtree(final_output_dir)
    staging_output_dir.rename(final_output_dir)
    timeseries_path = final_output_dir / "timeseries.csv"

    metadata = {
        "experiment_id": experiment_id,
        "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
        "git_commit": git_commit(),
        "config_file": str(config_path),
        "seed": exp.get("seed"),
        "label": label,
        "duration_seconds": duration_seconds,
        "host": host,
        "n_raw_samples": len(raw),
        "n_feature_rows": len(features),
        "timeseries_path": str(timeseries_path),
        "validation": report.to_dict(),
        "features_path": str(features_path),
    }
    metadata_dir = REPO_ROOT / "data" / "experiments" / experiment_id
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", help="Path to an experiment config YAML")
    parser.add_argument("--host", required=True, help="Reachable URL of the app under test")
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument(
        "--output-features-dir",
        help="Write the features CSV here instead of data/features/ (e.g. to keep E3/E4 runs out of the main train/test split)",
    )
    args = parser.parse_args()

    output_features_dir = Path(args.output_features_dir) if args.output_features_dir else None
    metadata = run_experiment(Path(args.config), args.host, args.prometheus_url, output_features_dir)
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
