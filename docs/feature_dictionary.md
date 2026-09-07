# Feature Dictionary

Every feature computed by `feature_engineering/` (Phase 6), documented per
CLAUDE.md section 15. All features are computed over a **causal** rolling
window ending at `window_end`: only raw samples with
`window_end - window_seconds < timestamp <= window_end` are used — see
`feature_engineering/build_features.py` and
`tests/feature_engineering/test_build_features.py::test_no_future_leakage`
for the no-leakage guarantee (CLAUDE.md non-negotiable principle #11).

**Collection sources:**
- **Prometheus** — the app's own `/metrics` (CLAUDE.md section 7), scraped
  by the in-cluster Prometheus deployed in Phase 3.
- **kubectl** — `feature_engineering/collect_metrics.py`'s `ReplicaSampler`
  polls `kubectl get deployment` / `kubectl get hpa` directly (this project
  does not run kube-state-metrics; k3d's bundled metrics-server plus HPA
  polling is sufficient for this project's scope).
- **cost model** — `app/src/cost.py` (Phase 5), applied to the window's
  replica/CPU samples.

**Calculation window:** configurable (`window_seconds_list` parameter to
`build_features()`), e.g. `[10, 30, 60]` — not hard-coded to one size.

---

## 1. Traffic Features (`traffic_features.py`)

Baseline/context features — not this project's primary novelty.

| Name | Definition | Unit | Formula |
|---|---|---|---|
| `request_rate` | Mean request throughput over the window | req/s | `request_count / window_seconds` |
| `request_count` | Total requests completed in the window | requests | `http_requests_total` delta over window |
| `peak_request_rate` | Highest per-sub-interval rate observed in the window | req/s | `max(Δrequest_count / Δt)` over consecutive raw samples |
| `request_rate_std` | Standard deviation of per-sub-interval rates | req/s | `std(Δrequest_count / Δt)` |
| `request_burstiness` | Coefficient of variation of per-sub-interval rates | unitless | `request_rate_std / mean(sub_rates)`, 0 if mean is 0 |
| `response_rate` | Successful-response throughput | req/s | `(request_count - error_count) / window_seconds` |
| `error_rate` | Fraction of requests with a non-2xx status | fraction | `error_count / request_count`, 0 if no requests |

**Expected relevance:** Traffic volume alone is explicitly *not* the
proposed detector's primary signal (CLAUDE.md section 44) — a low-volume
EDoS attack can have similar `request_rate` to a light flash crowd.
**Potential leakage:** None identified — derived purely from counters
within the causal window.

---

## 2. Cost Features (`cost_features.py`) — core proposed features

| Name | Definition | Unit | Formula |
|---|---|---|---|
| `estimated_cost` | Modeled infrastructure cost for the window | cost units | `Σ(replica_minutes × replica_cost_per_minute)` + optional CPU/memory-weighted terms (`app/src/cost.py::compute_cost`) |
| `cost_per_request` | Cost per completed request | cost units/request | `estimated_cost / request_count`, 0 if no requests |
| `cost_per_second` | Cost accrual rate | cost units/s | `estimated_cost / window_seconds` |
| `replica_minutes_per_request` | Infrastructure-time consumed per request | replica-minutes/request | `total_replica_minutes / request_count` |
| `cpu_seconds_per_request` | CPU-time consumed per request | cpu-seconds/request | `Σ(replica_minutes × 60 × avg_cpu_utilization) / request_count` |
| `cost_to_traffic_ratio` | Cost relative to traffic *intensity* (rate, not count) | cost units per (req/s) | `estimated_cost / request_rate`, 0 if rate is 0 |

**Expected relevance:** Potentially higher for EDoS because the attack
intentionally causes disproportionate resource consumption per request —
this is the project's central hypothesis (H2, CLAUDE.md section 2).
**Potential leakage:** `cost_per_request` and `cost_to_traffic_ratio`
differ only in denominator (count vs. rate) and are highly correlated by
construction — a model may over-weight one as a proxy for the other.
Documented, not hidden.

---

## 3. Scaling Features (`scaling_features.py`) — core proposed features

Computed from the **observed** replica/CPU time series (CLAUDE.md section 9
— never from the configured HPA target).

| Name | Definition | Unit | Formula |
|---|---|---|---|
| `current_replica_count` | Replica count at window end | replicas | last sample in window |
| `mean_replica_count` | Average replica count over the window | replicas | `mean(replica_count)` |
| `max_replica_count` | Peak replica count over the window | replicas | `max(replica_count)` |
| `replica_growth_rate` | Net change in replica count per second | replicas/s | `(last - first) / window_seconds` |
| `replica_change_count` | Number of sample-to-sample replica count changes | count | count of nonzero consecutive diffs |
| `scale_up_events` | Number of sample-to-sample increases | count | count of positive diffs |
| `scale_down_events` | Number of sample-to-sample decreases | count | count of negative diffs |
| `time_at_elevated_replicas` | Time spent above `min_replicas` | seconds | Σ(Δt where replica_count > min_replicas) |
| `cpu_growth_rate` | Net change in CPU utilization % per second | %/s | `(last_cpu% - first_cpu%) / window_seconds` |
| `replica_to_request_ratio` | Infrastructure footprint per unit traffic | replicas per (req/s) | `mean_replica_count / request_rate`, 0 if rate is 0 |

**Expected relevance:** Core hypothesis — EDoS is expected to trigger
disproportionate scaling relative to its request volume. **Potential
leakage:** None identified beyond sampling granularity (see Limitations).

---

## 4. Application Behaviour Features (`behaviour_features.py`) — core proposed features

| Name | Definition | Unit | Formula |
|---|---|---|---|
| `endpoint_diversity` | Normalized Shannon entropy of traffic across the 3 endpoint classes | [0, 1] | `-Σ(p·ln p) / ln(3)` over class proportions; 0 = concentrated on one class, 1 = evenly spread |
| `unique_endpoint_ratio` | Fraction of the 3 endpoint classes that received any traffic | [0, 1] | `(# classes with count>0) / 3` |
| `expensive_endpoint_ratio` | Share of requests hitting the expensive class | fraction | `expensive_count / request_count` |
| `cheap_endpoint_ratio` | Share of requests hitting the cheap class | fraction | `cheap_count / request_count` |
| `search_ratio` | Share of requests hitting `/api/search` | fraction | `medium_count / request_count` (search is currently the only medium-class endpoint) |
| `report_generation_ratio` | Share of requests hitting `/api/generate-report` | fraction | equals `expensive_endpoint_ratio` (generate-report is currently the only expensive-class endpoint) |
| `requests_per_session` | Request density per concurrent session | requests/session | `request_count / mean(active_sessions)` |
| `session_duration` | Average lifetime of sessions that expired in this window | seconds | `Δapp_session_duration_seconds_sum / Δapp_session_duration_seconds_count` |
| `unique_client_ratio` | Session-based proxy for distinct-actor diversity | fraction | `mean(active_sessions) / request_count` |
| `cache_hit_rate` | Fraction of search requests served from cache | fraction | `cache_hits / (cache_hits + cache_misses)` |
| `cache_miss_rate` | Fraction of search requests not served from cache | fraction | `cache_misses / (cache_hits + cache_misses)` |
| `conversion_rate` | Fraction of requests resulting in a simulated conversion | fraction | `conversions / request_count` |

**Expected relevance:** `expensive_endpoint_ratio` / `report_generation_ratio`
and low `endpoint_diversity` are expected to be strong EDoS indicators
(CLAUDE.md section 11: EDoS "concentrates on expensive endpoints").
**Potential leakage / limitation:** `unique_client_ratio` and
`requests_per_session` are **proxies**, not true client-identity
measurements — the app deliberately does not track client IPs or expose
session IDs as labels (CLAUDE.md section 7 forbids unbounded labels), so
"distinct actors" is approximated via the `active_sessions` gauge. A
scenario with many short-lived sessions and one with few long-lived
sessions could look similar under this proxy. This is a known, documented
limitation, not an unstated assumption.

---

## 5. Combined Relationship Features (`build_features.py`)

CLAUDE.md section 14.5 — "how much infrastructure impact is produced by
how much traffic?" Built directly from the feature groups above.

| Name | Formula |
|---|---|
| `cost_per_request_over_request_rate` | `cost_per_request / request_rate` |
| `replica_count_over_request_rate` | `mean_replica_count / request_rate` (equivalent to `replica_to_request_ratio`) |
| `cpu_utilization_over_request_rate` | `mean(cpu_utilization_pct) / request_rate` |
| `expensive_ratio_times_cost_per_request` | `expensive_endpoint_ratio × cost_per_request` |
| `replica_growth_rate_over_request_rate` | `replica_growth_rate / request_rate` |

All four are 0 when `request_rate` is 0 (safe division, no fabricated
values). **Expected relevance:** these are expected to be the most
discriminative features precisely because they normalize cost/scaling by
traffic, which is the axis volumetric baselines cannot see.

---

## Limitations (apply across all groups)

- **Sampling granularity:** scaling features depend on how frequently
  `ReplicaSampler` polls (`interval_seconds` parameter) — a very short
  scale event between polls could be missed. Document the polling
  interval used for each experiment in its metadata.
- **Single-experiment windows:** `build_features()` operates on one
  continuous raw series (one experiment run). Mixed-scenario experiments
  (E3/E4 interleaved runs) require external per-window labeling, not
  automatic scenario-tag inspection — see `label`/`experiment_id`
  parameters.
- **No cross-window features:** each window is computed independently;
  no feature currently looks back further than its own `window_seconds`.
