from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest

from feature_engineering.collect_metrics import (
    PrometheusClient,
    ReplicaResetError,
    ReplicaResetter,
    ReplicaSample,
    ReplicaSampler,
    ResetConfig,
    ResetRetryConfig,
    align_raw_dataframe,
    ensure_isolated_with_retry,
)


def test_query_range_parses_prometheus_response():
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "status": "success",
        "data": {"result": [{"values": [[0, "1"], [10, "5"], [20, "12"]]}]},
    }
    fake_response.raise_for_status.return_value = None

    client = PrometheusClient(base_url="http://fake:9090")
    with patch("feature_engineering.collect_metrics.httpx.get", return_value=fake_response) as mock_get:
        df = client.query_range("sum(x)", start=0, end=20, step_seconds=10)

    mock_get.assert_called_once()
    assert list(df["timestamp"]) == [0.0, 10.0, 20.0]
    assert list(df["value"]) == [1.0, 5.0, 12.0]


def test_query_range_empty_result_returns_empty_dataframe():
    fake_response = MagicMock()
    fake_response.json.return_value = {"status": "success", "data": {"result": []}}
    fake_response.raise_for_status.return_value = None

    client = PrometheusClient()
    with patch("feature_engineering.collect_metrics.httpx.get", return_value=fake_response):
        df = client.query_range("sum(x)", 0, 10, 5)
    assert df.empty
    assert list(df.columns) == ["timestamp", "value"]


def test_query_range_raises_on_prometheus_error_status():
    fake_response = MagicMock()
    fake_response.json.return_value = {"status": "error", "error": "bad query"}
    fake_response.raise_for_status.return_value = None

    client = PrometheusClient()
    with patch("feature_engineering.collect_metrics.httpx.get", return_value=fake_response):
        with pytest.raises(RuntimeError, match="Prometheus query failed"):
            client.query_range("sum(x)", 0, 10, 5)


def test_align_raw_dataframe_merges_and_forward_fills():
    app_counters = {
        "request_count": pd.DataFrame({"timestamp": [0, 10, 20], "value": [0, 5, 10]}),
    }
    replica_samples = [
        ReplicaSample(timestamp=0, replica_count=1, cpu_utilization_pct=20.0),
        ReplicaSample(timestamp=20, replica_count=2, cpu_utilization_pct=50.0),
    ]
    merged = align_raw_dataframe(app_counters, replica_samples)
    assert "request_count" in merged.columns
    assert "replica_count" in merged.columns
    assert "cpu_utilization_pct" in merged.columns

    row_10 = merged[merged["timestamp"] == 10].iloc[0]
    assert row_10["replica_count"] == 1  # forward-filled from t=0


def test_align_raw_dataframe_handles_no_replica_samples():
    app_counters = {"request_count": pd.DataFrame({"timestamp": [0, 10], "value": [0, 1]})}
    merged = align_raw_dataframe(app_counters, [])
    assert "request_count" in merged.columns
    assert not merged.empty


def test_query_range_retries_transient_connection_errors_then_succeeds():
    """A `kubectl port-forward` tunnel can drop momentarily mid-experiment
    (observed in practice during a real live run) — the client must
    retry rather than fail the whole experiment on one blip."""
    fake_response = MagicMock()
    fake_response.json.return_value = {"status": "success", "data": {"result": [{"values": [[0, "1"]]}]}}
    fake_response.raise_for_status.return_value = None

    call_count = {"n": 0}

    def flaky_get(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise httpx.ConnectError("connection refused")
        return fake_response

    client = PrometheusClient(base_url="http://fake:9090", max_retries=3, retry_backoff_seconds=0.0)
    with patch("feature_engineering.collect_metrics.httpx.get", side_effect=flaky_get):
        df = client.query_range("sum(x)", 0, 10, 5)

    assert call_count["n"] == 3
    assert list(df["value"]) == [1.0]


def test_query_range_raises_after_exhausting_retries():
    client = PrometheusClient(base_url="http://fake:9090", max_retries=2, retry_backoff_seconds=0.0)
    with patch("feature_engineering.collect_metrics.httpx.get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(httpx.ConnectError):
            client.query_range("sum(x)", 0, 10, 5)


def test_replica_sampler_poll_once_reads_replicas_and_cpu_via_api_client():
    """ReplicaSampler must go through the kubernetes API client, not
    subprocess kubectl calls — see the class docstring for why (spawning
    kubectl.exe concurrently with an open port-forward tunnel was
    observed to break that tunnel on this project's dev setup)."""
    from feature_engineering.collect_metrics import ReplicaSampler

    fake_deployment = MagicMock()
    fake_deployment.status.replicas = 4

    fake_metric = MagicMock()
    fake_metric.type = "Resource"
    fake_metric.resource.name = "cpu"
    fake_metric.resource.current.average_utilization = 75

    fake_hpa = MagicMock()
    fake_hpa.status.current_metrics = [fake_metric]

    fake_apps_api = MagicMock()
    fake_apps_api.read_namespaced_deployment.return_value = fake_deployment
    fake_autoscaling_api = MagicMock()
    fake_autoscaling_api.read_namespaced_horizontal_pod_autoscaler.return_value = fake_hpa

    sampler = ReplicaSampler(namespace="cascade", deployment="cascade-app", hpa="cascade-app")
    sampler._apps_api = fake_apps_api
    sampler._autoscaling_api = fake_autoscaling_api

    sample = sampler.poll_once()

    assert sample.replica_count == 4
    assert sample.cpu_utilization_pct == 75.0
    assert sampler.samples == [sample]
    fake_apps_api.read_namespaced_deployment.assert_called_once_with("cascade-app", "cascade")


def test_sample_for_stops_early_when_stop_event_is_set():
    """docs/experiment_protocol.md §12: a background sampler must be
    stoppable before its full duration elapses, so a failed traffic-
    generation run doesn't leave it polling the Kubernetes API for the
    rest of duration_seconds after the run has already been abandoned."""
    import threading

    from feature_engineering.collect_metrics import ReplicaSampler

    fake_deployment = MagicMock()
    fake_deployment.status.replicas = 1
    fake_hpa = MagicMock()
    fake_hpa.status.current_metrics = []

    sampler = ReplicaSampler()
    sampler._apps_api = MagicMock(read_namespaced_deployment=MagicMock(return_value=fake_deployment))
    sampler._autoscaling_api = MagicMock(read_namespaced_horizontal_pod_autoscaler=MagicMock(return_value=fake_hpa))

    stop_event = threading.Event()
    stop_event.set()  # already set before sample_for even starts polling

    samples = sampler.sample_for(duration_seconds=100.0, interval_seconds=0.01, stop_event=stop_event)

    # Stopped immediately rather than running anywhere near the full
    # 100s duration_seconds.
    assert samples == []


def test_sample_for_without_stop_event_behaves_exactly_as_before():
    """Backward compatibility: existing callers that don't pass
    stop_event (e.g. any future direct use of ReplicaSampler) must be
    unaffected."""
    fake_deployment = MagicMock()
    fake_deployment.status.replicas = 2
    fake_hpa = MagicMock()
    fake_hpa.status.current_metrics = []

    sampler = ReplicaSampler()
    sampler._apps_api = MagicMock(read_namespaced_deployment=MagicMock(return_value=fake_deployment))
    sampler._autoscaling_api = MagicMock(read_namespaced_horizontal_pod_autoscaler=MagicMock(return_value=fake_hpa))

    samples = sampler.sample_for(duration_seconds=0.03, interval_seconds=0.01)

    assert len(samples) >= 1
    assert all(s.replica_count == 2 for s in samples)


# --------------------------------------------------------------------- #
# ReplicaResetter / ResetConfig — P0 methodology fix (mandatory
# experiment isolation, docs/research_gap_audit.md Part 3/7).
# --------------------------------------------------------------------- #


def _fake_deployment(replicas: int):
    deployment = MagicMock()
    deployment.status.replicas = replicas
    return deployment


def _fake_hpa(min_replicas: int):
    hpa = MagicMock()
    hpa.spec.min_replicas = min_replicas
    return hpa


def test_reset_config_from_dict_uses_conservative_defaults_when_missing():
    """timeout_seconds default (330s) is live-validated, not arbitrary:
    it must comfortably exceed Kubernetes' own default 300s HPA
    downscale-stabilization window, since the HPA re-asserts its cached
    recommendation regardless of an explicit scale-down patch (confirmed
    against a real cluster — see ResetConfig's docstring and
    docs/research_gap_audit.md's live validation session)."""
    cfg = ResetConfig.from_dict({})
    assert cfg.enabled is True
    assert cfg.timeout_seconds == 330.0
    assert cfg.timeout_seconds > 300.0
    assert cfg.stabilization_seconds == 30.0
    assert cfg.poll_interval_seconds == 5.0


def test_reset_config_from_dict_reads_explicit_values():
    cfg = ResetConfig.from_dict(
        {
            "reset_to_min_replicas": False,
            "replica_reset_timeout_seconds": 5,
            "replica_stabilization_seconds": 1,
            "replica_poll_interval_seconds": 0.5,
        }
    )
    assert cfg.enabled is False
    assert cfg.timeout_seconds == 5.0
    assert cfg.stabilization_seconds == 1.0
    assert cfg.poll_interval_seconds == 0.5


def test_ensure_isolated_skips_when_explicitly_disabled_and_touches_no_api():
    resetter = ReplicaResetter()
    fake_apps_api = MagicMock()
    resetter._apps_api = fake_apps_api  # would raise if _ensure_clients() were called
    logs = []

    result = resetter.ensure_isolated(ResetConfig(enabled=False), log=logs.append)

    assert result == -1
    assert any("skipped" in line for line in logs)
    fake_apps_api.read_namespaced_deployment.assert_not_called()


def test_ensure_isolated_scales_down_and_confirms_min_replicas_then_stabilizes():
    resetter = ReplicaResetter(namespace="cascade", deployment="cascade-app", hpa="cascade-app")
    fake_apps_api = MagicMock()
    fake_apps_api.read_namespaced_deployment.return_value = _fake_deployment(1)
    fake_autoscaling_api = MagicMock()
    fake_autoscaling_api.read_namespaced_horizontal_pod_autoscaler.return_value = _fake_hpa(1)
    resetter._apps_api = fake_apps_api
    resetter._autoscaling_api = fake_autoscaling_api
    logs = []

    result = resetter.ensure_isolated(
        ResetConfig(timeout_seconds=1.0, stabilization_seconds=0.02, poll_interval_seconds=0.01),
        log=logs.append,
    )

    assert result == 1
    fake_apps_api.patch_namespaced_deployment_scale.assert_called_once_with(
        "cascade-app", "cascade", {"spec": {"replicas": 1}}
    )
    assert any("RESETTING" in line for line in logs)
    assert any("STABILIZED" in line for line in logs)


def test_ensure_isolated_raises_if_min_replicas_never_reached():
    """A deployment stuck above minReplicas (e.g. genuinely still serving
    a previous run's traffic) must FAIL the experiment, never silently
    continue — this is the core safety property of the P0 fix."""
    resetter = ReplicaResetter()
    fake_apps_api = MagicMock()
    fake_apps_api.read_namespaced_deployment.return_value = _fake_deployment(4)
    fake_autoscaling_api = MagicMock()
    fake_autoscaling_api.read_namespaced_horizontal_pod_autoscaler.return_value = _fake_hpa(1)
    resetter._apps_api = fake_apps_api
    resetter._autoscaling_api = fake_autoscaling_api

    with pytest.raises(ReplicaResetError, match="did not reach minReplicas"):
        resetter.ensure_isolated(
            ResetConfig(timeout_seconds=0.03, stabilization_seconds=0.02, poll_interval_seconds=0.01)
        )


def test_ensure_isolated_raises_if_replicas_drift_away_during_stabilization():
    """Reaching minReplicas once is not enough — it must HOLD for the
    full stabilization window, or the reset must fail rather than let a
    briefly-correct-then-drifting deployment through."""
    resetter = ReplicaResetter()
    call_count = {"n": 0}

    def read_deployment(*_args, **_kwargs):
        call_count["n"] += 1
        # First read confirms minReplicas; every read after that drifts
        # away and never recovers.
        return _fake_deployment(1 if call_count["n"] == 1 else 2)

    fake_apps_api = MagicMock()
    fake_apps_api.read_namespaced_deployment.side_effect = read_deployment
    fake_autoscaling_api = MagicMock()
    fake_autoscaling_api.read_namespaced_horizontal_pod_autoscaler.return_value = _fake_hpa(1)
    resetter._apps_api = fake_apps_api
    resetter._autoscaling_api = fake_autoscaling_api

    with pytest.raises(ReplicaResetError, match="left minReplicas"):
        resetter.ensure_isolated(
            ResetConfig(timeout_seconds=0.05, stabilization_seconds=0.02, poll_interval_seconds=0.01)
        )


# --------------------------------------------------------------------- #
# ensure_isolated_with_retry / ResetRetryConfig — experiment-orchestration
# -level retry-with-backoff around ReplicaResetter (docs/experiment_
# protocol.md §11). ReplicaResetter itself is exercised above; these
# tests use a minimal fake resetter (duck-typed: only `.ensure_isolated`
# matters to the wrapper) so retry/backoff/logging logic is tested in
# isolation from the real Kubernetes-facing implementation.
# --------------------------------------------------------------------- #


class _FakeResetter:
    """Records every call and raises/returns according to a scripted
    sequence of outcomes — one entry consumed per ensure_isolated() call."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = 0

    def ensure_isolated(self, config=None, log=print):
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_reset_retry_config_from_dict_uses_defaults_when_missing():
    cfg = ResetRetryConfig.from_dict({})
    assert cfg.max_attempts == 3
    assert cfg.backoff_seconds == 30.0


def test_reset_retry_config_from_dict_reads_explicit_values():
    cfg = ResetRetryConfig.from_dict({"max_attempts": 5, "retry_backoff_seconds": 10})
    assert cfg.max_attempts == 5
    assert cfg.backoff_seconds == 10.0


def test_ensure_isolated_with_retry_succeeds_immediately_without_retry(monkeypatch):
    sleeps = []
    monkeypatch.setattr("feature_engineering.collect_metrics.time.sleep", lambda s: sleeps.append(s))
    resetter = _FakeResetter([1])

    result = ensure_isolated_with_retry(resetter, retry_config=ResetRetryConfig(max_attempts=3, backoff_seconds=99))

    assert result == 1
    assert resetter.calls == 1
    assert sleeps == []  # no backoff needed when the first attempt succeeds


def test_ensure_isolated_with_retry_retries_after_failure_then_succeeds(monkeypatch):
    """Each retry must invoke the real isolation procedure again (here:
    the fake resetter is called a second time, not a cached result)."""
    sleeps = []
    monkeypatch.setattr("feature_engineering.collect_metrics.time.sleep", lambda s: sleeps.append(s))
    resetter = _FakeResetter([ReplicaResetError("attempt 1 failed"), 1])

    result = ensure_isolated_with_retry(resetter, retry_config=ResetRetryConfig(max_attempts=3, backoff_seconds=7))

    assert result == 1
    assert resetter.calls == 2
    assert sleeps == [7]  # exactly one backoff, between attempt 1 and 2


def test_ensure_isolated_with_retry_raises_after_exhausting_all_attempts(monkeypatch):
    monkeypatch.setattr("feature_engineering.collect_metrics.time.sleep", lambda s: None)
    resetter = _FakeResetter(
        [ReplicaResetError("attempt 1"), ReplicaResetError("attempt 2"), ReplicaResetError("attempt 3")]
    )

    with pytest.raises(ReplicaResetError, match="failed after 3 attempt"):
        ensure_isolated_with_retry(resetter, retry_config=ResetRetryConfig(max_attempts=3, backoff_seconds=0.01))

    assert resetter.calls == 3


def test_ensure_isolated_with_retry_logs_each_attempt_clearly(monkeypatch):
    monkeypatch.setattr("feature_engineering.collect_metrics.time.sleep", lambda s: None)
    resetter = _FakeResetter([ReplicaResetError("boom"), 1])
    logs = []

    ensure_isolated_with_retry(resetter, retry_config=ResetRetryConfig(max_attempts=3, backoff_seconds=1), log=logs.append)

    assert any("RESET ATTEMPT 1/3" in line for line in logs)
    assert any("RESET ATTEMPT 1/3 FAILED" in line for line in logs)
    assert any("WAITING" in line and "before retrying" in line for line in logs)
    assert any("RESET ATTEMPT 2/3" in line for line in logs)


def test_ensure_isolated_with_retry_never_returns_after_exhaustion_even_if_caller_ignores_config(monkeypatch):
    """Safety invariant: exhausting every attempt always raises — there
    is no code path that returns a "best effort" result, matching
    ReplicaResetter's own contract."""
    monkeypatch.setattr("feature_engineering.collect_metrics.time.sleep", lambda s: None)
    resetter = _FakeResetter([ReplicaResetError("only attempt")])

    with pytest.raises(ReplicaResetError):
        ensure_isolated_with_retry(resetter, retry_config=ResetRetryConfig(max_attempts=1, backoff_seconds=0.01))

    assert resetter.calls == 1
