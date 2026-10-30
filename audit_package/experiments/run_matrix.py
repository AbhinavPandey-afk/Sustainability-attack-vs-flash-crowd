#!/usr/bin/env python
"""Run every experiment config in a directory sequentially (CLAUDE.md
Phase 10: "Run controlled experiments").

FAILURE ISOLATION (docs/experiment_protocol.md §12): one experiment
failing must not silently terminate the rest of the matrix, and must
also never be silently treated as a successful research sample. Each
config's outcome is recorded (PASS/FAILED) in a matrix-run summary
written under data/experiments/matrix_runs/ — a location deliberately
separate from results/ (the provisional research results) — and the
matrix continues to the next config regardless of one config's outcome,
except for KeyboardInterrupt/SystemExit, which are never caught here.

Usage:
    python experiments/run_matrix.py experiments/configs --host http://localhost:8000
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.run_experiment import run_experiment  # noqa: E402
from feature_engineering.collect_metrics import ReplicaResetError  # noqa: E402

# Exception types run_experiment() is documented to raise for known,
# anticipated infrastructure/runtime failure modes — see
# docs/experiment_protocol.md §11/§12:
#   ReplicaResetError            isolation could not be confirmed after
#                                 every retry (feature_engineering/
#                                 collect_metrics.py)
#   ConnectionError               the app wasn't reachable right before
#                                 traffic generation (check_host_reachable)
#   subprocess.CalledProcessError traffic generation itself failed, e.g.
#                                 a dead port-forward tunnel surfaced via
#                                 Locust's --exit-code-on-error
#   OSError                       e.g. a missing scenario file
#   KeyError                      a malformed config missing a required
#                                 key (experiment.name, experiment.label, …)
#   yaml.YAMLError                an unparsable config file
#
# A failure of one of these types is recorded as FAILED and the matrix
# continues to the next config. Anything else is treated as an
# unexpected programming error: still recorded, still non-fatal to the
# matrix (see run_one_experiment's docstring for why that's safe), but
# never silently indistinguishable from a routine, anticipated failure.
KNOWN_EXPERIMENT_FAILURES = (
    ReplicaResetError,
    ConnectionError,
    subprocess.CalledProcessError,
    OSError,
    KeyError,
    yaml.YAMLError,
)


@dataclass
class MatrixEntryResult:
    """One config's outcome within a matrix run — the auditable record
    Phase 3 of docs/experiment_protocol.md §12 calls for. A FAILED entry
    is never counted as, or convertible into, a valid research sample —
    it carries no features_path/n_feature_rows a downstream training
    script could accidentally glob."""

    name: str
    config_file: str
    status: str  # "PASS" | "FAILED"
    started_at: str
    ended_at: str
    failure_stage: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    traceback: str | None = None
    traffic_started: bool | None = None
    output_directory: str | None = None
    reset_config: dict = field(default_factory=dict)
    n_feature_rows: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _classify_failure_stage(exc: Exception, traffic_started: bool) -> str:
    """Best-effort classification of WHERE in run_experiment()'s pipeline
    a failure happened, from the exception type alone (run_experiment()
    doesn't currently expose an explicit stage marker) — good enough to
    make a failure record immediately useful without re-running anything."""
    if isinstance(exc, ReplicaResetError):
        return "isolation"
    if isinstance(exc, ConnectionError):
        return "pre_flight_host_check"
    if isinstance(exc, subprocess.CalledProcessError):
        return "traffic_generation"
    if isinstance(exc, (KeyError, yaml.YAMLError)):
        return "config_load"
    if isinstance(exc, OSError):
        return "traffic_generation" if traffic_started else "config_load"
    return "post_traffic_processing" if traffic_started else "unexpected_programming_error"


def run_one_experiment(
    config_path: Path, host: str, prometheus_url: str, output_features_dir: Path | None = None
) -> MatrixEntryResult:
    """Runs a single config through run_experiment(), never letting its
    outcome (success OR any anticipated/unanticipated failure) raise out
    of this function — the matrix loop below relies on that to keep
    going. KeyboardInterrupt/SystemExit are the explicit exception: they
    are never caught here, so an operator's Ctrl-C or a process-level
    exit request always stops the matrix immediately, exactly as it
    would for any other script.

    Continuing after an UNEXPECTED (non-KNOWN_EXPERIMENT_FAILURES)
    exception is deliberately not treated as automatically unsafe: this
    experiment's own subprocess/thread state has already been cleaned up
    by run_experiment() itself (see its sampler-thread stop_event
    handling) by the time any exception reaches here, and every
    subsequent config still goes through its OWN independent, from
    -scratch ensure_isolated_with_retry() call — there is no shared
    mutable state one experiment's crash could leave behind that the
    next experiment's isolation step doesn't already re-verify. If that
    ever stops being true (e.g. a future change introduces persistent
    cross-experiment state), this reasoning — not just this code — would
    need to be revisited.
    """
    name = config_path.stem
    started_at = dt.datetime.now(dt.timezone.utc).isoformat()

    traffic_started_flag = {"value": False}

    def _on_subprocess_start(pid: int) -> None:
        traffic_started_flag["value"] = True

    reset_cfg: dict = {}
    try:
        raw_config = yaml.safe_load(config_path.read_text())
        reset_cfg = (raw_config or {}).get("reset", {})
    except yaml.YAMLError:
        pass  # surfaced properly by run_experiment() below; this is just for the record's reset_config field

    try:
        metadata = run_experiment(
            config_path, host, prometheus_url, output_features_dir, on_subprocess_start=_on_subprocess_start
        )
    except KNOWN_EXPERIMENT_FAILURES as exc:
        return MatrixEntryResult(
            name=name,
            config_file=str(config_path),
            status="FAILED",
            started_at=started_at,
            ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            failure_stage=_classify_failure_stage(exc, traffic_started_flag["value"]),
            error_type=type(exc).__name__,
            error_message=str(exc),
            traffic_started=traffic_started_flag["value"],
            output_directory=str(REPO_ROOT / "data" / "raw" / f"{name}.inprogress"),
            reset_config=reset_cfg,
        )
    except Exception as exc:  # noqa: BLE001 - deliberately broad: see docstring above
        return MatrixEntryResult(
            name=name,
            config_file=str(config_path),
            status="FAILED",
            started_at=started_at,
            ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            failure_stage="unexpected_programming_error",
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback=traceback.format_exc(),
            traffic_started=traffic_started_flag["value"],
            output_directory=str(REPO_ROOT / "data" / "raw" / f"{name}.inprogress"),
            reset_config=reset_cfg,
        )

    return MatrixEntryResult(
        name=name,
        config_file=str(config_path),
        status="PASS",
        started_at=started_at,
        ended_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        traffic_started=True,
        output_directory=metadata.get("timeseries_path"),
        reset_config=reset_cfg,
        n_feature_rows=metadata.get("n_feature_rows"),
    )


def write_matrix_summary(entries: list[MatrixEntryResult], summary_dir: Path | None = None) -> Path:
    """Writes a matrix-run summary to data/experiments/matrix_runs/
    (deliberately separate from results/, the provisional research
    results — never overwritten, never mistaken for a research
    artifact) — one timestamped file per matrix run, so a previous run's
    summary is never overwritten either."""
    summary_dir = summary_dir or (REPO_ROOT / "data" / "experiments" / "matrix_runs")
    summary_dir.mkdir(parents=True, exist_ok=True)

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    n_failed = sum(1 for e in entries if e.status == "FAILED")
    summary = {
        "run_id": run_id,
        "status": "COMPLETED_WITH_FAILURES" if n_failed else "COMPLETED",
        "n_experiments": len(entries),
        "n_passed": len(entries) - n_failed,
        "n_failed": n_failed,
        "experiments": [e.to_dict() for e in entries],
    }
    out_path = summary_dir / f"{run_id}.json"
    out_path.write_text(json.dumps(summary, indent=2))
    return out_path


def run_matrix(
    config_dir: Path, host: str, prometheus_url: str, output_features_dir: Path | None = None
) -> list[MatrixEntryResult]:
    configs = sorted(config_dir.glob("*.yaml"))
    results: list[MatrixEntryResult] = []
    for config_path in configs:
        print(f"=== Running {config_path.name} ===")
        entry = run_one_experiment(config_path, host, prometheus_url, output_features_dir)
        results.append(entry)
        if entry.status == "PASS":
            print(f"    -> PASS ({entry.n_feature_rows} feature rows)")
        else:
            print(f"    -> FAILED at stage '{entry.failure_stage}': {entry.error_type}: {entry.error_message}")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config_dir", help="Directory of experiment config YAML files")
    parser.add_argument("--host", required=True)
    parser.add_argument("--prometheus-url", default="http://localhost:9090")
    parser.add_argument(
        "--output-features-dir",
        help="Write every config's features CSV here instead of data/features/ — e.g. to keep a "
        "smoke-test or other non-research matrix run out of the real dataset (mirrors "
        "run_experiment.py's own --output-features-dir).",
    )
    args = parser.parse_args()

    output_features_dir = Path(args.output_features_dir) if args.output_features_dir else None
    config_dir = Path(args.config_dir)
    configs = sorted(config_dir.glob("*.yaml"))
    if not configs:
        print(f"No experiment configs found in {config_dir}")
        return 1

    results = run_matrix(config_dir, args.host, args.prometheus_url, output_features_dir)
    summary_path = write_matrix_summary(results)

    n_failed = sum(1 for r in results if r.status == "FAILED")
    print(f"\nCompleted {len(results)} experiments: {len(results) - n_failed} passed, {n_failed} failed.")
    print(f"Matrix run summary: {summary_path}")
    if n_failed:
        print("FAILED experiments (never counted as valid research samples):")
        for r in results:
            if r.status == "FAILED":
                print(f"  - {r.name}: {r.failure_stage} / {r.error_type}: {r.error_message}")

    return 1 if n_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
