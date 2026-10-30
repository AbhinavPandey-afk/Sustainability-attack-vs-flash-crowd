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


def _build_k8s_clients():
    """Creates (AppsV1Api, AutoscalingV2Api) clients from the local
    kubeconfig. Shared by ReplicaSampler and ReplicaResetter so the
    k3d-on-Windows connection quirk below is fixed in exactly one place.

    Uses the `kubernetes` API client rather than shelling out to
    `kubectl` subprocesses: on this project's Windows/Docker Desktop/k3d
    development setup, spawning `kubectl.exe` subprocesses concurrently
    with an open `kubectl port-forward` tunnel was observed to reliably
    break that tunnel mid-experiment (isolated by testing traffic
    generation with vs. without concurrent kubectl polling — see
    docs/experiment_protocol.md). Going through the API client directly
    avoids spawning any subprocess at all.
    """
    from kubernetes import client as k8s_client
    from kubernetes import config as k8s_config

    k8s_config.load_kube_config()
    cfg = k8s_client.Configuration.get_default_copy()
    # Known k3d-on-Windows kubeconfig quirk: the API server host can
    # be "0.0.0.0", which kubectl.exe tolerates but urllib3 cannot
    # connect to directly.
    cfg.host = cfg.host.replace("0.0.0.0", "127.0.0.1")
    k8s_client.Configuration.set_default(cfg)
    return k8s_client.AppsV1Api(), k8s_client.AutoscalingV2Api()


@dataclass
class ReplicaSample:
    timestamp: float
    replica_count: int
    cpu_utilization_pct: float


@dataclass
class ReplicaSampler:
    """Polls a Deployment/HPA pair via the Kubernetes API client at a
    fixed interval. See _build_k8s_clients() for why the API client is
    used instead of kubectl subprocesses.
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
        self._apps_api, self._autoscaling_api = _build_k8s_clients()

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

    def sample_for(
        self,
        duration_seconds: float,
        interval_seconds: float = 10.0,
        stop_event: "object | None" = None,
    ) -> list[ReplicaSample]:
        """Blocks, polling every interval_seconds, for duration_seconds —
        or until `stop_event.is_set()` (a `threading.Event`), whichever
        comes first. `stop_event` lets a caller running this in a
        background thread (experiments/run_experiment.py) end the poll
        loop early if the traffic-generation phase it's sampling
        alongside fails partway through, instead of the thread polling
        the Kubernetes API for the rest of `duration_seconds` after the
        run has already been abandoned (a real, live-discovered orphaned
        -thread leak — see docs/experiment_protocol.md §12). Optional and
        defaults to None for backward compatibility with any caller that
        doesn't need early cancellation.
        """
        end = time.time() + duration_seconds
        while time.time() < end:
            if stop_event is not None and stop_event.is_set():
                break
            self.poll_once()
            time.sleep(interval_seconds)
        return self.samples


class ReplicaResetError(RuntimeError):
    """Raised when a deployment could not be scaled to (or held at)
    minReplicas before an experiment was allowed to start — see
    ReplicaResetter.ensure_isolated. Always propagates; never silently
    swallowed. A failed reset must fail the experiment before any traffic
    is generated (docs/research_gap_audit.md Part 3: sequential live runs
    without this check were found, via real collected telemetry, to
    inherit a previous run's replica count for the entire duration of the
    next run — FC_002/EDOS_002/EDOS_003/INTERLEAVED_001 were all flat at
    maxReplicas from their very first sample)."""


@dataclass
class ResetConfig:
    """Controls the mandatory pre-experiment isolation step
    (ReplicaResetter.ensure_isolated). Read from an experiment config's
    optional `reset:` block:

        reset:
          reset_to_min_replicas: true   # default true; false opts out explicitly
          replica_reset_timeout_seconds: 330
          replica_stabilization_seconds: 30
          replica_poll_interval_seconds: 5

    timeout_seconds default corrected from an earlier, INCORRECT 120s
    based on live-cluster evidence (docs/research_gap_audit.md live
    validation session): the HPA controller does not stop managing a
    Deployment's replica count just because ensure_isolated() issued an
    explicit scale-down patch — it re-asserts its own cached
    recommendation on its normal sync loop regardless, and that cached
    recommendation can itself be "stuck" high for up to Kubernetes'
    default 300s downscale stabilization window (the same mechanism
    responsible for the original contamination this fix targets). A
    live test against a real cluster with a genuinely contentious HPA
    confirmed this directly: with the old 120s default, ensure_isolated()
    correctly refused to report false success, but could not win the
    race and raised ReplicaResetError after the full 120s — the
    deployment was still being pulled back to a stale-high replica count
    every ~5s throughout. 330s (300s + a margin for polling/network
    latency) is the smallest default that can reliably outlast that
    worst case; the 30s stabilization hold catches a deployment that
    reaches minReplicas only briefly before bouncing back up.
    """

    enabled: bool = True
    timeout_seconds: float = 330.0
    stabilization_seconds: float = 30.0
    poll_interval_seconds: float = 5.0

    @classmethod
    def from_dict(cls, data: dict) -> "ResetConfig":
        return cls(
            enabled=bool(data.get("reset_to_min_replicas", True)),
            timeout_seconds=float(data.get("replica_reset_timeout_seconds", 330.0)),
            stabilization_seconds=float(data.get("replica_stabilization_seconds", 30.0)),
            poll_interval_seconds=float(data.get("replica_poll_interval_seconds", 5.0)),
        )


@dataclass
class ReplicaResetter:
    """Scales a Deployment down to its HPA's configured minReplicas and
    verifies it actually reaches and HOLDS there before an experiment is
    allowed to start (docs/research_gap_audit.md Part 3/7 fix — see
    ReplicaResetError's docstring for the contamination this prevents).

    Uses the same kubernetes API client approach as ReplicaSampler (never
    kubectl subprocesses) via the shared _build_k8s_clients() helper, and
    the same lazy-client / directly-assignable-for-testing pattern
    (tests set ._apps_api/._autoscaling_api directly, bypassing
    _ensure_clients(), exactly like ReplicaSampler's existing tests).

    Known limitation: ensure_isolated() is a blocking call with no
    cancellation hook, unlike traffic generation in run_experiment.py
    (which supports cancel_event). A dashboard "Stop" click during the
    reset/stabilization wait will not take effect until it completes or
    times out. Not addressed in this change — out of scope for this
    methodology-correction session (no dashboard/UI changes).
    """

    namespace: str = "cascade"
    deployment: str = "cascade-app"
    hpa: str = "cascade-app"
    _apps_api: object = field(default=None, init=False, repr=False, compare=False)
    _autoscaling_api: object = field(default=None, init=False, repr=False, compare=False)

    def _ensure_clients(self) -> None:
        if self._apps_api is not None:
            return
        self._apps_api, self._autoscaling_api = _build_k8s_clients()

    def _read_min_replicas(self) -> int:
        hpa_obj = self._autoscaling_api.read_namespaced_horizontal_pod_autoscaler(self.hpa, self.namespace)
        return int(hpa_obj.spec.min_replicas)

    def _read_replica_count(self) -> int:
        deployment = self._apps_api.read_namespaced_deployment(self.deployment, self.namespace)
        return int(deployment.status.replicas or 0)

    def _scale_to(self, replicas: int) -> None:
        self._apps_api.patch_namespaced_deployment_scale(
            self.deployment, self.namespace, {"spec": {"replicas": replicas}}
        )

    def ensure_isolated(self, config: "ResetConfig | None" = None, log=print) -> int:
        """Blocks until the deployment is confirmed at the HPA's
        minReplicas and has held there for `config.stabilization_seconds`
        without leaving it; returns the minReplicas value reached.

        Raises ReplicaResetError — never returns a "best effort" partial
        result — if a drift away from minReplicas is still occurring once
        `config.timeout_seconds` of wall-clock time has elapsed. Note
        (found via live-cluster validation): `timeout_seconds` bounds how
        long DRIFT/retries are tolerated, not the absolute wall-clock cap
        on a *successful* return — once a clean stabilization hold is
        under way (no drift), it is allowed to finish even if that pushes
        total elapsed time slightly past `timeout_seconds` (by at most
        one `poll_interval_seconds` + `stabilization_seconds`). This
        never risks a false success: every poll during that hold,
        including the last one before the window closes, must have
        matched minReplicas, or the hold restarts instead of completing.

        `config.enabled = False` is a deliberate, explicit opt-out (e.g. a
        test/dev run where isolation doesn't matter) and returns
        immediately without contacting the cluster at all — isolation is
        the default; skipping it is never implicit.
        """
        config = config or ResetConfig()
        if not config.enabled:
            log("RESETTING: skipped (reset.reset_to_min_replicas is false)")
            return -1

        self._ensure_clients()
        min_replicas = self._read_min_replicas()
        deadline = time.monotonic() + config.timeout_seconds

        log(f"RESETTING: scaling {self.deployment} to minReplicas={min_replicas}")
        self._scale_to(min_replicas)

        log("WAITING: polling for observed replica count to reach minReplicas")
        while True:
            current = self._read_replica_count()
            if current == min_replicas:
                break
            if time.monotonic() >= deadline:
                raise ReplicaResetError(
                    f"{self.deployment} did not reach minReplicas={min_replicas} within "
                    f"{config.timeout_seconds}s (last observed: {current} replicas). "
                    "Experiment aborted before traffic generation to avoid running in a "
                    "possibly-contaminated (non-isolated) state."
                )
            time.sleep(config.poll_interval_seconds)

        log(f"VERIFYING: holding at minReplicas={min_replicas} for {config.stabilization_seconds}s")
        stabilization_deadline = time.monotonic() + config.stabilization_seconds
        while time.monotonic() < stabilization_deadline:
            time.sleep(min(config.poll_interval_seconds, max(stabilization_deadline - time.monotonic(), 0.0)))
            current = self._read_replica_count()
            if current != min_replicas:
                if time.monotonic() >= deadline:
                    raise ReplicaResetError(
                        f"{self.deployment} left minReplicas={min_replicas} during the "
                        f"stabilization hold (observed {current} replicas) and the overall "
                        f"reset timeout ({config.timeout_seconds}s) has elapsed. Experiment "
                        "aborted before traffic generation."
                    )
                log(
                    f"WAITING: {self.deployment} left minReplicas (observed {current}) during "
                    "stabilization — restarting the stabilization hold"
                )
                stabilization_deadline = time.monotonic() + config.stabilization_seconds

        log(f"STABILIZED: {self.deployment} held at minReplicas={min_replicas}")
        return min_replicas


@dataclass
class ResetRetryConfig:
    """Controls retry-with-backoff around ReplicaResetter.ensure_isolated
    at the EXPERIMENT ORCHESTRATION level (experiments/run_experiment.py,
    run_interleaved_experiment.py — and therefore run_matrix.py, which
    calls those) — deliberately NOT inside ReplicaResetter itself.
    ReplicaResetter.ensure_isolated remains a single, self-contained
    attempt that alone decides whether that one attempt succeeded, with
    its safety contract unchanged: it never returns without a genuinely
    confirmed, held minReplicas state, and it always raises
    ReplicaResetError on failure. This config only controls whether (and
    how) that whole attempt gets repeated before an experiment aborts.

    Read from an experiment config's `reset:` block, alongside
    ResetConfig's own keys:

        reset:
          max_attempts: 3
          retry_backoff_seconds: 30

    Defaults chosen from live-cluster observation
    (docs/experiment_protocol.md §10.5.1): a reset that exhausted a full
    330s attempt after a severe CPU spike succeeded on a second attempt
    once the cluster was left to settle for roughly two more minutes.
    3 attempts x 30s backoff gives a comparable total idle allowance
    (up to ~2 full extra ResetConfig.timeout_seconds windows) without an
    unbounded or arbitrarily large retry count.
    """

    max_attempts: int = 3
    backoff_seconds: float = 30.0

    @classmethod
    def from_dict(cls, data: dict) -> "ResetRetryConfig":
        return cls(
            max_attempts=int(data.get("max_attempts", 3)),
            backoff_seconds=float(data.get("retry_backoff_seconds", 30.0)),
        )


def ensure_isolated_with_retry(
    resetter: "ReplicaResetter",
    reset_config: "ResetConfig | None" = None,
    retry_config: "ResetRetryConfig | None" = None,
    log=print,
) -> int:
    """Orchestration-level wrapper: calls `resetter.ensure_isolated(...)`
    up to `retry_config.max_attempts` times, with a fixed backoff between
    attempts, before giving up. Each attempt is a full, independent,
    real call into ReplicaResetter — never a cached/assumed result —
    so "each retry invokes the real isolation procedure again" holds by
    construction.

    Never weakens the underlying safety invariant: if every attempt
    raises ReplicaResetError, this function raises ReplicaResetError too
    (chained from the last attempt's error) rather than returning or
    silently continuing — the caller must still never generate traffic
    after this raises.
    """
    reset_config = reset_config or ResetConfig()
    retry_config = retry_config or ResetRetryConfig()

    last_error: ReplicaResetError | None = None
    for attempt in range(1, retry_config.max_attempts + 1):
        log(f"RESET ATTEMPT {attempt}/{retry_config.max_attempts}")
        try:
            return resetter.ensure_isolated(reset_config, log=log)
        except ReplicaResetError as exc:
            last_error = exc
            log(f"RESET ATTEMPT {attempt}/{retry_config.max_attempts} FAILED: {exc}")
            if attempt < retry_config.max_attempts:
                log(f"WAITING {retry_config.backoff_seconds}s before retrying isolation")
                time.sleep(retry_config.backoff_seconds)

    raise ReplicaResetError(
        f"Isolation failed after {retry_config.max_attempts} attempt(s); experiment aborted before "
        f"traffic generation. Last error: {last_error}"
    ) from last_error


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
