import time
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest
import yaml

import experiments.run_experiment as run_experiment_module
from experiments.run_experiment import check_host_reachable, git_commit

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_check_host_reachable_passes_when_host_responds(monkeypatch):
    monkeypatch.setattr(run_experiment_module.httpx, "get", lambda *a, **k: MagicMock(status_code=200))
    check_host_reachable("http://localhost:8000")  # must not raise


def test_check_host_reachable_raises_clear_error_on_dead_tunnel(monkeypatch):
    """docs/experiment_protocol.md §11.2: a dead kubectl port-forward
    tunnel must fail loudly, immediately, before any traffic is
    generated — not be silently discovered after a whole wasted run."""

    def _raise(*_a, **_k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(run_experiment_module.httpx, "get", _raise)
    with pytest.raises(ConnectionError, match="not reachable"):
        check_host_reachable("http://localhost:8000")


class _OkResetter:
    def __init__(self, **_kwargs):
        pass

    def ensure_isolated(self, *_args, **_kwargs):
        return 1


class _OkPrometheusClient:
    """Always-reachable fake — used by tests that need to get PAST the
    Prometheus preflight to exercise something later in run_experiment()
    (traffic generation, sampler cleanup, etc.) without depending on a
    real, live Prometheus being reachable in whatever environment the
    test suite happens to run in. Each test using this fails/returns
    before collect_app_metrics() would ever be called, so that method is
    deliberately not implemented here — if a future test needs it, add it
    then rather than guessing its shape now."""

    def __init__(self, **_kwargs):
        pass

    def check_reachable(self, timeout_seconds=None):
        pass


class _RealisticStoppableSampler:
    """Mimics ReplicaSampler.sample_for's real loop-and-sleep shape
    (not an instant no-op) so a test can prove the stop_event is
    actually honored promptly, not just that some cleanup code exists."""

    def __init__(self, **_kwargs):
        self.samples = []

    def sample_for(self, duration_seconds, interval_seconds, stop_event=None):
        end = time.time() + duration_seconds
        while time.time() < end:
            if stop_event is not None and stop_event.is_set():
                break
            time.sleep(0.01)
        return self.samples


def test_run_experiment_stops_sampler_thread_promptly_when_traffic_generation_fails(tmp_path, monkeypatch):
    """docs/experiment_protocol.md §12: a failed traffic-generation
    subprocess must not leave the background replica sampler polling
    for the rest of duration_seconds. duration_seconds is deliberately
    large (50s) here — if the stop_event fix regressed, this test would
    take ~50s instead of returning almost immediately.
    """
    config = {
        "experiment": {
            "name": "SAMPLER_CLEANUP_TEST",
            "label": 0,
            "scenario_type": "flash_crowd",
            "scenario_file": "traffic/scenarios/flash_crowd.yaml",
            "duration_seconds": 50,
            "seed": 1,
        },
        "detector": {"window_seconds": [10], "step_seconds": 10},
    }
    config_path = tmp_path / "sampler_cleanup.yaml"
    config_path.write_text(yaml.dump(config))

    monkeypatch.setattr(run_experiment_module, "ReplicaResetter", _OkResetter)
    monkeypatch.setattr(run_experiment_module, "check_host_reachable", lambda host: None)
    monkeypatch.setattr(run_experiment_module, "PrometheusClient", _OkPrometheusClient)
    monkeypatch.setattr(run_experiment_module, "ReplicaSampler", _RealisticStoppableSampler)

    fake_proc = MagicMock()
    fake_proc.poll.return_value = 1  # already exited, with a failure code
    fake_proc.returncode = 1
    monkeypatch.setattr(run_experiment_module.subprocess, "Popen", lambda *a, **k: fake_proc)

    started = time.time()
    with pytest.raises(run_experiment_module.subprocess.CalledProcessError):
        run_experiment_module.run_experiment(config_path, host="http://localhost:8000")
    elapsed = time.time() - started

    assert elapsed < 5.0, f"sampler thread was not stopped promptly (took {elapsed:.1f}s of a 50s duration_seconds)"


def test_git_commit_returns_a_real_commit_hash_or_unknown():
    commit = git_commit()
    assert commit == "unknown" or len(commit) == 40  # full SHA-1 hex length


def test_fc_hardneg_001_config_references_the_hard_negative_scenario_and_label_0():
    """E4 (docs/research_gap_audit.md Part 6): the hard-negative flash-
    crowd experiment config must remain label=0 (legitimate) and must
    point at the hard-negative scenario, not the standard flash_crowd.yaml
    — a deliberate additive config, not a mutation of FC_001-003."""
    config = yaml.safe_load((REPO_ROOT / "experiments/configs/FC_HARDNEG_001.yaml").read_text())
    assert config["experiment"]["label"] == 0
    assert config["experiment"]["scenario_type"] == "flash_crowd"
    assert config["experiment"]["scenario_file"] == "traffic/scenarios/flash_crowd_hard_negative.yaml"

    scenario = yaml.safe_load((REPO_ROOT / config["experiment"]["scenario_file"]).read_text())
    assert scenario["behavior"]["weights"].get("generate_report", 0) > 0


def _reset_fail_config(**reset_overrides):
    config = {
        "experiment": {
            "name": "RESET_FAIL_TEST",
            "label": 0,
            "scenario_type": "flash_crowd",
            "scenario_file": "traffic/scenarios/flash_crowd.yaml",
            "duration_seconds": 10,
            "seed": 1,
        },
        "detector": {"window_seconds": [10], "step_seconds": 10},
        "reset": {"max_attempts": 1, "retry_backoff_seconds": 0.01, **reset_overrides},
    }
    return config


class _FailingResetter:
    """Always fails — every attempt, unconditionally, so tests using
    this can assert exactly `max_attempts` calls were made."""

    calls = 0

    def __init__(self, **_kwargs):
        pass

    def ensure_isolated(self, *_args, **_kwargs):
        type(self).calls += 1
        raise run_experiment_module.ReplicaResetError(f"simulated reset failure (attempt {type(self).calls})")


def test_run_experiment_aborts_before_traffic_generation_when_reset_fails(tmp_path, monkeypatch):
    """P0 methodology fix regression test (docs/research_gap_audit.md
    Part 3): an experiment must never generate traffic if the mandatory
    pre-run replica-isolation step can't confirm minReplicas.
    subprocess.Popen (traffic generation) must never be reached, and a
    ReplicaResetError must propagate rather than being swallowed —
    max_attempts=1 here means no retry loop runs, isolating this test to
    the base "failed reset -> no traffic" invariant.
    """
    config_path = tmp_path / "reset_fail.yaml"
    config_path.write_text(yaml.dump(_reset_fail_config()))

    _FailingResetter.calls = 0
    monkeypatch.setattr(run_experiment_module, "ReplicaResetter", _FailingResetter)
    popen_mock = MagicMock()
    monkeypatch.setattr(run_experiment_module.subprocess, "Popen", popen_mock)

    with pytest.raises(run_experiment_module.ReplicaResetError, match="simulated reset failure"):
        run_experiment_module.run_experiment(config_path, host="http://localhost:8000")

    popen_mock.assert_not_called()
    assert _FailingResetter.calls == 1


def test_run_experiment_retries_reset_and_still_aborts_before_traffic_after_all_attempts_fail(tmp_path, monkeypatch):
    """Phase 3 requirement: retries must happen (each one a real call
    into the isolation procedure, not a cached result) AND traffic must
    still never start once every attempt is exhausted."""
    config_path = tmp_path / "reset_fail_retry.yaml"
    config_path.write_text(yaml.dump(_reset_fail_config(max_attempts=3, retry_backoff_seconds=0.01)))

    _FailingResetter.calls = 0
    monkeypatch.setattr(run_experiment_module, "ReplicaResetter", _FailingResetter)
    popen_mock = MagicMock()
    monkeypatch.setattr(run_experiment_module.subprocess, "Popen", popen_mock)

    with pytest.raises(run_experiment_module.ReplicaResetError, match="failed after 3 attempt"):
        run_experiment_module.run_experiment(config_path, host="http://localhost:8000")

    popen_mock.assert_not_called()
    assert _FailingResetter.calls == 3  # every retry was a real, independent isolation attempt


def test_run_experiment_succeeds_on_a_later_reset_attempt(tmp_path, monkeypatch):
    """Successful reset on retry: the second attempt succeeding must let
    the run proceed past isolation (traffic generation itself is mocked
    out here — this test only proves ensure_isolated_with_retry's
    success path is reached and control returns to run_experiment)."""
    config_path = tmp_path / "reset_flaky.yaml"
    config_path.write_text(yaml.dump(_reset_fail_config(max_attempts=3, retry_backoff_seconds=0.01)))

    class _FlakyThenOkResetter:
        calls = 0

        def __init__(self, **_kwargs):
            pass

        def ensure_isolated(self, *_args, **_kwargs):
            type(self).calls += 1
            if type(self).calls < 2:
                raise run_experiment_module.ReplicaResetError("transient failure")
            return 1

    class _NoOpSampler:
        def __init__(self, **_kwargs):
            self.samples = []

        def sample_for(self, **_kwargs):
            return self.samples

    monkeypatch.setattr(run_experiment_module, "ReplicaResetter", _FlakyThenOkResetter)
    monkeypatch.setattr(run_experiment_module, "check_host_reachable", lambda host: None)
    monkeypatch.setattr(run_experiment_module, "PrometheusClient", _OkPrometheusClient)
    monkeypatch.setattr(run_experiment_module, "ReplicaSampler", _NoOpSampler)
    # Traffic generation itself is out of scope for this test — fail it
    # deliberately right after isolation succeeds, and confirm THAT is
    # the failure we see (proving isolation itself did not raise).
    popen_mock = MagicMock()
    popen_mock.side_effect = RuntimeError("reached traffic generation")
    monkeypatch.setattr(run_experiment_module.subprocess, "Popen", popen_mock)

    with pytest.raises(RuntimeError, match="reached traffic generation"):
        run_experiment_module.run_experiment(config_path, host="http://localhost:8000")

    assert _FlakyThenOkResetter.calls == 2


# --------------------------------------------------------------------- #
# Pre-flight gate ordering (matrix-orchestration-hardening session,
# 2026-09-17): HPA reset -> /healthz -> Prometheus reachability, in that
# order, ALL before any traffic subprocess starts. HPA reset coverage
# already exists above (test_run_experiment_aborts_before_traffic_
# generation_when_reset_fails); these add the two remaining gates.
# --------------------------------------------------------------------- #


def test_run_experiment_aborts_before_traffic_generation_when_healthz_fails(tmp_path, monkeypatch):
    """/healthz failing must abort BEFORE subprocess.Popen is ever
    called — isolation succeeds first (mocked out), then the app-health
    check fails and must be the reason traffic never starts."""
    config_path = tmp_path / "healthz_fail.yaml"
    config_path.write_text(yaml.dump(_reset_fail_config()))

    monkeypatch.setattr(run_experiment_module, "ReplicaResetter", _OkResetter)

    def _raise(*_a, **_k):
        raise ConnectionError("app healthz simulated failure")

    monkeypatch.setattr(run_experiment_module, "check_host_reachable", _raise)
    popen_mock = MagicMock()
    monkeypatch.setattr(run_experiment_module.subprocess, "Popen", popen_mock)

    with pytest.raises(ConnectionError, match="app healthz simulated failure"):
        run_experiment_module.run_experiment(config_path, host="http://localhost:8000")

    popen_mock.assert_not_called()


def test_run_experiment_aborts_before_traffic_generation_when_prometheus_unreachable(tmp_path, monkeypatch):
    """Prometheus preflight (new this session): isolation and /healthz
    both succeed (mocked), but Prometheus is down — traffic must still
    never start, and the failure must be a PrometheusUnreachableError,
    distinguishable from the app's own ConnectionError."""
    from feature_engineering.collect_metrics import PrometheusUnreachableError

    config_path = tmp_path / "prometheus_fail.yaml"
    config_path.write_text(yaml.dump(_reset_fail_config()))

    monkeypatch.setattr(run_experiment_module, "ReplicaResetter", _OkResetter)
    monkeypatch.setattr(run_experiment_module, "check_host_reachable", lambda host: None)

    class _FailingPrometheusClient:
        def __init__(self, **_kwargs):
            pass

        def check_reachable(self, timeout_seconds=None):
            raise PrometheusUnreachableError("simulated: prometheus down right before traffic generation")

    monkeypatch.setattr(run_experiment_module, "PrometheusClient", _FailingPrometheusClient)
    popen_mock = MagicMock()
    monkeypatch.setattr(run_experiment_module.subprocess, "Popen", popen_mock)

    with pytest.raises(PrometheusUnreachableError, match="prometheus down"):
        run_experiment_module.run_experiment(config_path, host="http://localhost:8000")

    popen_mock.assert_not_called()


def test_prometheus_client_check_reachable_passes_when_healthy(monkeypatch):
    from feature_engineering.collect_metrics import PrometheusClient

    monkeypatch.setattr(
        "feature_engineering.collect_metrics.httpx.get", lambda *a, **k: MagicMock(status_code=200)
    )
    PrometheusClient(base_url="http://localhost:9090").check_reachable()  # must not raise


def test_prometheus_client_check_reachable_raises_on_unhealthy_status(monkeypatch):
    from feature_engineering.collect_metrics import PrometheusClient, PrometheusUnreachableError

    monkeypatch.setattr(
        "feature_engineering.collect_metrics.httpx.get", lambda *a, **k: MagicMock(status_code=503)
    )
    with pytest.raises(PrometheusUnreachableError, match="503"):
        PrometheusClient(base_url="http://localhost:9090").check_reachable()


def test_prometheus_client_check_reachable_raises_on_connection_error(monkeypatch):
    import httpx as httpx_module

    from feature_engineering.collect_metrics import PrometheusClient, PrometheusUnreachableError

    def _raise(*_a, **_k):
        raise httpx_module.ConnectError("connection refused")

    monkeypatch.setattr("feature_engineering.collect_metrics.httpx.get", _raise)
    with pytest.raises(PrometheusUnreachableError, match="not reachable"):
        PrometheusClient(base_url="http://localhost:9090").check_reachable()


def test_prometheus_unreachable_error_is_a_connection_error_subclass():
    """Must be a ConnectionError subclass so it is automatically caught
    wherever run_matrix.py's KNOWN_EXPERIMENT_FAILURES already catches
    ConnectionError, without needing a separate tuple entry."""
    from feature_engineering.collect_metrics import PrometheusUnreachableError

    assert issubclass(PrometheusUnreachableError, ConnectionError)
