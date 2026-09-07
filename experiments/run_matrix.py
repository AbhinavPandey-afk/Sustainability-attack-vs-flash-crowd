#!/usr/bin/env python
"""Run every experiment config in a directory sequentially (CLAUDE.md
Phase 10: "Run controlled experiments").

Usage:
    python experiments/run_matrix.py experiments/configs --host http://localhost:8000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.run_experiment import run_experiment  # noqa: E402


def run_matrix(config_dir: Path, host: str, prometheus_url: str) -> list:
    configs = sorted(config_dir.glob("*.yaml"))
    results = []
    for config_path in configs:
        print(f"=== Running {config_path.name} ===")
        metadata = run_experiment(config_path, host, prometheus_url)
        results.append(metadata)
        print(f"    -> {metadata['n_feature_rows']} feature rows, valid={metadata['validation']['ok']}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config_dir", help="Directory of experiment config YAML files")
    parser.add_argument("--host", required=True)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    args = parser.parse_args()

    config_dir = Path(args.config_dir)
    configs = sorted(config_dir.glob("*.yaml"))
    if not configs:
        print(f"No experiment configs found in {config_dir}")
        return 1

    results = run_matrix(config_dir, args.host, args.prometheus_url)
    print(f"\nCompleted {len(results)} experiments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
