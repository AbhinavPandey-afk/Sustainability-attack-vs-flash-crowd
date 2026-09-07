#!/usr/bin/env python
"""Run a Locust traffic scenario in headless mode and save telemetry.

Usage:
    python traffic/run_scenario.py traffic/scenarios/flash_crowd.yaml
    python traffic/run_scenario.py traffic/scenarios/edos.yaml --users 20 --run-time 30s

Telemetry (Locust's CSV stats: requests, failures, response-time history)
is written to data/raw/<scenario_name>_<timestamp>/ by default.
"""
import argparse
import datetime as dt
import os
import pathlib
import subprocess
import sys

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("scenario", help="Path to a scenario YAML file")
    parser.add_argument("--host", help="Override the target host from the scenario file")
    parser.add_argument("--users", type=int, help="Override user count")
    parser.add_argument("--spawn-rate", type=float, help="Override spawn rate")
    parser.add_argument("--run-time", help="Override run time, e.g. 60s, 5m")
    parser.add_argument("--output-dir", help="Override the telemetry output directory")
    args = parser.parse_args()

    scenario_path = pathlib.Path(args.scenario).resolve()
    config = yaml.safe_load(scenario_path.read_text())
    name = config["scenario"]["name"]
    locust_cfg = config.get("locust", {})

    host = args.host or locust_cfg.get("host", "http://localhost:8000")
    users = args.users or locust_cfg.get("users", 10)
    spawn_rate = args.spawn_rate or locust_cfg.get("spawn_rate", 1)
    run_time = args.run_time or f"{locust_cfg.get('run_time_seconds', 60)}s"
    has_arrival_shape = bool(locust_cfg.get("arrival_shape"))

    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = (
        pathlib.Path(args.output_dir).resolve()
        if args.output_dir
        else REPO_ROOT / "data" / "raw" / f"{name}_{timestamp}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_prefix = output_dir / name

    cmd = [sys.executable, "-m", "locust", "-f", str(REPO_ROOT / "traffic" / "locustfile.py"), "--host", host]
    if not has_arrival_shape:
        # A LoadTestShape (see traffic/generators/viral_shape.py) takes
        # over user-count/spawn-rate scheduling entirely when present in
        # the locustfile — passing --users/--spawn-rate alongside it would
        # be ignored by Locust but is skipped here for clarity.
        cmd += ["--users", str(users), "--spawn-rate", str(spawn_rate)]
    cmd += ["--run-time", run_time, "--headless", "--csv", str(csv_prefix), "--csv-full-history"]

    env = dict(os.environ)
    env["CASCADE_SCENARIO"] = str(scenario_path)

    print(f"[run_scenario] scenario={name} host={host} users={users} spawn_rate={spawn_rate} run_time={run_time}")
    print(f"[run_scenario] telemetry -> {output_dir}")

    result = subprocess.run(cmd, env=env)
    if result.returncode != 0:
        return result.returncode

    files = sorted(p.name for p in output_dir.glob("*"))
    print(f"[run_scenario] done. Files written: {files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
