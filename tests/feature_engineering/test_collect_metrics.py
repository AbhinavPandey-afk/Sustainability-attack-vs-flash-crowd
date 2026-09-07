from unittest.mock import MagicMock, patch

import httpx
import pandas as pd
import pytest

from feature_engineering.collect_metrics import PrometheusClient, ReplicaSample, align_raw_dataframe


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
