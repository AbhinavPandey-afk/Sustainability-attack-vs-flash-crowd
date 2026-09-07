"""In-memory lifecycle tracking for a live experiment run.

Wraps the existing experiments/run_experiment.py::run_experiment and
experiments/summarize_results.py::run functions directly (no subprocess,
no reimplementation) in a background thread, with a single global lock so
at most one live run happens at a time — this is a research testbed, not
a multi-tenant service.
"""
from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from config import DATA_FEATURES, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, EXPERIMENTS_CONFIGS, RESULTS_DIR

STATE_READY = "READY"
STATE_STARTING = "STARTING"
STATE_RUNNING = "RUNNING"
STATE_SUMMARIZING = "SUMMARIZING"
STATE_COMPLETED = "COMPLETED"
STATE_FAILED = "FAILED"
STATE_CANCELLED = "CANCELLED"

_TERMINAL_STATES = (STATE_COMPLETED, STATE_FAILED, STATE_CANCELLED)


class RunnerState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: dict | None = None
        self._just_ran: set[str] = set()
        self._cancel_event: threading.Event | None = None

    def is_busy(self) -> bool:
        with self._lock:
            return self._current is not None and self._current["state"] not in _TERMINAL_STATES

    def status(self, experiment_id: str | None = None) -> dict | None:
        with self._lock:
            if self._current is None:
                return None
            if experiment_id is not None and self._current["experiment_id"] != experiment_id:
                return None
            snap = dict(self._current)
        if snap["state"] in (STATE_RUNNING,) and snap.get("started_at"):
            snap["elapsed_seconds"] = round(time.time() - snap["started_at"], 1)
        return snap

    def was_just_run(self, experiment_id: str) -> bool:
        return experiment_id in self._just_ran

    def start(
        self,
        experiment_id: str,
        config_path: Path | None = None,
        output_features_dir: Path | None = None,
        skip_retrain: bool = False,
    ) -> bool:
        """Starts experiment_id. If config_path is given, it's used directly
        (ad-hoc simulator runs — see webapp/backend/scenario_builder.py);
        otherwise experiment_id is resolved as a preset under
        experiments/configs/{id}.yaml, exactly as before."""
        if config_path is None:
            config_path = EXPERIMENTS_CONFIGS / f"{experiment_id}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"No experiment config for {experiment_id}")

        with self._lock:
            if self._current is not None and self._current["state"] not in _TERMINAL_STATES:
                return False
            import yaml

            duration = yaml.safe_load(config_path.read_text())["experiment"]["duration_seconds"]
            cancel_event = threading.Event()
            self._cancel_event = cancel_event
            self._current = {
                "experiment_id": experiment_id,
                "state": STATE_STARTING,
                "duration_seconds": duration,
                "started_at": None,
                "elapsed_seconds": 0.0,
                "error": None,
                "child_pid": None,
            }

        thread = threading.Thread(
            target=self._run,
            args=(experiment_id, config_path, output_features_dir, skip_retrain, cancel_event),
            daemon=True,
        )
        thread.start()
        return True

    def stop(self) -> bool:
        """Requests cancellation of the currently running experiment. Only
        actually interrupts the plain (non-interleaved, non-"mixed") traffic
        subprocess chain — see experiments/run_experiment.py's cancel_event
        handling. Returns False if nothing is running to stop."""
        with self._lock:
            if self._current is None or self._current["state"] not in (STATE_STARTING, STATE_RUNNING):
                return False
            event = self._cancel_event
        if event is not None:
            event.set()
        return True

    def _set(self, **kwargs) -> None:
        with self._lock:
            if self._current is not None:
                self._current.update(kwargs)

    def _on_subprocess_start(self, pid: int) -> None:
        self._set(child_pid=pid)

    def _run(
        self,
        experiment_id: str,
        config_path: Path,
        output_features_dir: Path | None,
        skip_retrain: bool,
        cancel_event: threading.Event,
    ) -> None:
        try:
            import yaml

            config = yaml.safe_load(config_path.read_text())
            held_out_dir = DATA_FEATURES / "held_out"

            self._set(state=STATE_RUNNING, started_at=time.time())

            if "phases" in config:
                # E4 — alternating phases, per-window labels (see
                # docs/experiment_protocol.md section 8). Cancellation isn't
                # wired through this path.
                from experiments.run_interleaved_experiment import run_interleaved_experiment

                run_interleaved_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL)
            elif config["experiment"].get("scenario_type") == "mixed":
                # E3 — simultaneous traffic, kept out of the main train/
                # test split. Cancellation isn't wired through this path.
                from experiments.run_experiment import run_experiment

                run_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, held_out_dir)
            elif config["experiment"].get("scenario_type") == "normal":
                # E0 — normal/non-attack baseline, used only as a visual
                # comparison reference (webapp frontend overlay charts).
                # Kept out of the trained model's train/test split, same
                # isolation pattern as held_out/adhoc; no retrain needed.
                from experiments.run_experiment import run_experiment

                run_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, DATA_FEATURES / "baseline")
                skip_retrain = True
            else:
                from experiments.run_experiment import run_experiment

                run_experiment(
                    config_path,
                    DEFAULT_APP_HOST,
                    DEFAULT_PROMETHEUS_URL,
                    output_features_dir,
                    cancel_event=cancel_event,
                    on_subprocess_start=self._on_subprocess_start,
                )

            if skip_retrain:
                # Ad-hoc simulator runs: features already landed under
                # output_features_dir (kept out of data/features/*.csv), so
                # there is nothing new for the trained model to see —
                # retraining would be wasted work, not a correctness issue,
                # but skipped anyway to keep simulator runs fast.
                self._just_ran.add(experiment_id)
                self._set(state=STATE_COMPLETED)
                return

            self._set(state=STATE_SUMMARIZING)
            from experiments.summarize_results import run as summarize_run

            summarize_run(DATA_FEATURES, RESULTS_DIR, seed=42, held_out_dir=held_out_dir)

            self._just_ran.add(experiment_id)
            self._set(state=STATE_COMPLETED)
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
            from experiments.run_experiment import RunCancelled

            if isinstance(exc, RunCancelled):
                self._set(state=STATE_CANCELLED, error="Cancelled by user")
            else:
                self._set(state=STATE_FAILED, error=f"{exc}\n{traceback.format_exc(limit=3)}")

    def start_sequence(self, experiment_ids: list[str]) -> bool:
        """Runs a list of preset experiment_ids back-to-back (still one
        experiment running at a time — see start()), used by the
        Dashboard's "Run Presentation Demo" button. Retrains once at the
        end of the whole sequence, not after every individual run."""
        with self._lock:
            if self._current is not None and self._current["state"] not in _TERMINAL_STATES:
                return False
            self._current = {
                "experiment_id": experiment_ids[0] if experiment_ids else None,
                "state": STATE_STARTING,
                "duration_seconds": None,
                "started_at": None,
                "elapsed_seconds": 0.0,
                "error": None,
                "child_pid": None,
                "sequence": list(experiment_ids),
                "sequence_index": 0,
                "sequence_total": len(experiment_ids),
            }
            cancel_event = threading.Event()
            self._cancel_event = cancel_event

        thread = threading.Thread(target=self._run_sequence, args=(experiment_ids, cancel_event), daemon=True)
        thread.start()
        return True

    def _run_sequence(self, experiment_ids: list[str], cancel_event: threading.Event) -> None:
        try:
            import yaml

            for i, experiment_id in enumerate(experiment_ids):
                if cancel_event.is_set():
                    self._set(state=STATE_CANCELLED, error="Cancelled by user")
                    return

                config_path = EXPERIMENTS_CONFIGS / f"{experiment_id}.yaml"
                if not config_path.exists():
                    raise FileNotFoundError(f"No experiment config for {experiment_id}")
                config = yaml.safe_load(config_path.read_text())
                duration = config["experiment"]["duration_seconds"]

                self._set(
                    experiment_id=experiment_id,
                    state=STATE_RUNNING,
                    started_at=time.time(),
                    duration_seconds=duration,
                    sequence_index=i,
                )

                held_out_dir = DATA_FEATURES / "held_out"
                if "phases" in config:
                    from experiments.run_interleaved_experiment import run_interleaved_experiment

                    run_interleaved_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL)
                elif config["experiment"].get("scenario_type") == "mixed":
                    from experiments.run_experiment import run_experiment

                    run_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, held_out_dir)
                elif config["experiment"].get("scenario_type") == "normal":
                    from experiments.run_experiment import run_experiment

                    run_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, DATA_FEATURES / "baseline")
                else:
                    from experiments.run_experiment import run_experiment

                    run_experiment(config_path, DEFAULT_APP_HOST, DEFAULT_PROMETHEUS_URL, cancel_event=cancel_event)

                self._just_ran.add(experiment_id)

            self._set(state=STATE_SUMMARIZING)
            from experiments.summarize_results import run as summarize_run

            summarize_run(DATA_FEATURES, RESULTS_DIR, seed=42, held_out_dir=DATA_FEATURES / "held_out")
            self._set(state=STATE_COMPLETED)
        except Exception as exc:  # noqa: BLE001
            from experiments.run_experiment import RunCancelled

            if isinstance(exc, RunCancelled):
                self._set(state=STATE_CANCELLED, error="Cancelled by user")
            else:
                self._set(state=STATE_FAILED, error=f"{exc}\n{traceback.format_exc(limit=3)}")


runner_state = RunnerState()
