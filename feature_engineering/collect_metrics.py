"""Pulls raw telemetry needed by build_features.py from a live Prometheus
instance (app-level counters/gauges, deployed in Phase 3) and from the
Kubernetes API (replica count / HPA CPU% — this project does not run
kube-state-metrics; k3d's bundled metrics-server plus reading the HPA
object directly is enough for this project's scope, per CLAUDE.md's
minimal-complexity rule).

Two independent pieces:
  PrometheusClient  — thin wrapper over the HTTP query_range API.
  ReplicaSampler    — polls the Deployment/HPA objects via the
                       `kubernetes` API client for (replica_count, cpu%)
                       at a fixed interval; run this DURING a traffic-
                       generation run (see experiments/run_experiment.py)
                       to build the replica time series.

align_raw_dataframe() merges both onto a single timestamp grid matching
build_features.py's REQUIRED_RAW_COLUMNS schema.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx
import pandas as pd

# Maps build_features.py's REQUIRED_RAW_COLUMNS (cumulative-counter ones)
# to the PromQL expression that yields them. All are simple sum()s of the
# app's own metrics (app/src/metrics.py) — no per-request/session labels.
APP_METRIC_QUERIES = {
    "request_count": 'sum(http_requests_total{job="cascade-app"})',
    "error_count": 'sum(http_requests_total{job="cascade-app",status_class!="2xx"})',
    "cheap_count": 'sum(app_endpoint_requests_total{job="cascade-app",endpoint_class="cheap"})',
    "medium_count": 'sum(app_endpoint_requests_total{job="cascade-app",endpoint_class="medium"})',
    "expensive_count": 'sum(app_endpoint_requests_total{job="cascade-app",endpoint_class="expensive"})',
    "cache_hits": 'sum(app_cache_hits_total{job="cascade-app"})',
    "cache_misses": 'sum(app_cache_misses_total{job="cascade-app"})',
    "conversions": 'sum(app_conversion_total{job="cascade-app"})',
    "active_sessions": 'sum(app_active_sessions{job="cascade-app"})',
    "session_duration_sum": 'sum(app_session_duration_seconds_sum{job="cascade-app"})',
    "session_duration_count": 'sum(app_session_duration_seconds_count{job="cascade-app"})',
}


@dataclass
class PrometheusClient:
    base_url: str = "http://localhost:9090"
    timeout_seconds: float = 10.0
    max_retries: int = 10
    retry_backoff_seconds: float = 5.0

    def query_range(self, promql: str, start: float, end: float, step_seconds: float) -> pd.DataFrame:
        """Returns a DataFrame [timestamp, value] for a single
        (non-vector-valued, i.e. already sum()-aggregated) PromQL query.

        Retries transient connection failures — observed in practice when
        querying through a long-lived `kubectl port-forward` tunnel during
        a multi-minute experiment run, where the tunnel can drop and
        reconnect on its own (see docs/experiment_protocol.md).
        """
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = httpx.get(
                    f"{self.base_url}/api/v1/query_range",
                    params={"query": promql, "start": start, "end": end, "step": step_seconds},
                    timeout=self.timeout_seconds,
                )
                break
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_seconds)
        else:
            raise last_error
        response.raise_for_status()
        payload = response.json()
        if payload["status"] != "success":
            raise RuntimeError(f"Prometheus query failed: {payload}")

        result = payload["data"]["result"]
        if not result:
            return pd.DataFrame(columns=["timestamp", "value"])

        values = result[0]["values"]
        return pd.DataFrame(values, columns=["timestamp", "value"]).astype(float)

    def collect_app_metrics(self, start: float, end: float, step_seconds: float) -> dict[str, pd.DataFrame]:
        return {name: self.query_range(query, start, end, step_seconds) for name, query in APP_METRIC_QUERIES.items()}


@dataclass
class ReplicaSample:
    timestamp: float
    replica_count: int
    cpu_utilization_pct: float


@dataclass
class ReplicaSampler:
    """Polls a Deployment/HPA pair via the Kubernetes API client at a
    fixed interval.

    Uses the `kubernetes` API client rather than shelling out to
    `kubectl` subprocesses: on this project's Windows/Docker Desktop/k3d
    development setup, spawning `kubectl.exe` subprocesses concurrently
    with an open `kubectl port-forward` tunnel was observed to reliably
    break that tunnel mid-experiment (isolated by testing traffic
    generation with vs. without concurrent kubectl polling — see
    docs/experiment_protocol.md). Going through the API client directly
    avoids spawning any subprocess at all.
    """

    namespace: str = "cascade"
    deployment: str = "cascade-app"
    hpa: str = "cascade-app"
    samples: list = field(default_factory=list)
    _apps_api: object = field(default=None, init=False, repr=False, compare=False)
    _autoscaling_api: object = field(default=None, init=False, repr=False, compare=False)

    def _ensure_clients(self) -> None:
        if self._apps_api is not None:
            return
        from kubernetes import client as k8s_client
        from kubernetes import config as k8s_config

        k8s_config.load_kube_config()
        cfg = k8s_client.Configuration.get_default_copy()
        # Known k3d-on-Windows kubeconfig quirk: the API server host can
        # be "0.0.0.0", which kubectl.exe tolerates but urllib3 cannot
        # connect to directly.
        cfg.host = cfg.host.replace("0.0.0.0", "127.0.0.1")
        k8s_client.Configuration.set_default(cfg)
        self._apps_api = k8s_client.AppsV1Api()
        self._autoscaling_api = k8s_client.AutoscalingV2Api()

    def poll_once(self) -> ReplicaSample:
        self._ensure_clients()

        deployment = self._apps_api.read_namespaced_deployment(self.deployment, self.namespace)
        replica_count = deployment.status.replicas or 0

        hpa = self._autoscaling_api.read_namespaced_horizontal_pod_autoscaler(self.hpa, self.namespace)
        cpu_pct = 0.0
        for metric in hpa.status.current_metrics or []:
            if metric.type == "Resource" and metric.resource and metric.resource.name == "cpu":
                cpu_pct = float(metric.resource.current.average_utilization or 0)

        sample = ReplicaSample(timestamp=time.time(), replica_count=replica_count, cpu_utilization_pct=cpu_pct)
        self.samples.append(sample)
        return sample

    def sample_for(self, duration_seconds: float, interval_seconds: float = 10.0) -> list[ReplicaSample]:
        """Blocks, polling every interval_seconds, for duration_seconds."""
        end = time.time() + duration_seconds
        while time.time() < end:
            self.poll_once()
            time.sleep(interval_seconds)
        return self.samples


def align_raw_dataframe(
    app_counters: dict[str, pd.DataFrame],
    replica_samples: list[ReplicaSample],
) -> pd.DataFrame:
    """Merge Prometheus app-metric series and kubectl replica samples onto
    a single timestamp grid — outer join, forward/backward-filled (all of
    these are either monotonic counters or slow-changing gauges, so
    holding the last known value across a gap is the correct choice) —
    matching build_features.py's REQUIRED_RAW_COLUMNS.
    """
    frames = [df.rename(columns={"value": name}).set_index("timestamp") for name, df in app_counters.items()]

    if replica_samples:
        replica_df = pd.DataFrame(
            [
                {
                    "timestamp": s.timestamp,
                    "replica_count": s.replica_count,
                    "cpu_utilization_pct": s.cpu_utilization_pct,
                }
                for s in replica_samples
            ]
        ).set_index("timestamp")
        frames.append(replica_df)

    merged = pd.concat(frames, axis=1).sort_index()
    merged = merged.ffill().bfill().fillna(0.0)
    return merged.reset_index().rename(columns={"index": "timestamp"})
