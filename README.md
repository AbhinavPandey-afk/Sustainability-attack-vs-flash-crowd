# CASCADE — Sustainability Attack vs Flash Crowd

**Cost-Aware Scaling and Application-behaviour Detection Engine**

Distinguishing Economic Denial of Sustainability (EDoS) Attacks from
Legitimate Flash Crowds in Autoscaled Applications.

## Project purpose

Traffic volume alone often cannot distinguish a low-volume EDoS attack from
a legitimate flash crowd. This project builds a reproducible local
Kubernetes research testbed and, in later phases, a cost/scaling/
application-behaviour-aware detector (LightGBM) that learns this
distinction from cost, autoscaling, and application-behaviour signals
rather than request volume alone. See `CLAUDE.md` for the full research
mission, hypotheses, and architecture, and `TASKS.md` for the current
phase's exact scope.

This is a research prototype, not a production security product. All
traffic used in later phases is synthetic and confined to the local
testbed.

## Current architecture (target, full project)

```text
Traffic Generator -> Autoscaled FastAPI App -> Kubernetes HPA -> Prometheus
      -> Feature Engineering (Cost + Scaling + Behaviour) -> LightGBM
      -> EDoS / Flash Crowd
```

Every stage of this pipeline is now implemented and unit-tested (Phases
1–10 below). What is **not** yet done is running it at real research
scale — the live data collected so far is small proof-of-concept volume,
and a full unattended multi-experiment live run has a known unresolved
reliability issue on this specific dev machine. See "Project status"
below and `docs/experiment_protocol.md` for exactly what is and isn't
proven.

## Project status

### Phase 1 — Foundation & Local Kubernetes Testbed
**Status: Implemented and verified** — cluster creation, all kubectl
verification commands, and the smoke test have been run live end-to-end
on a real k3d/k3s cluster, including a full delete/recreate reproducibility
cycle.

- Local k3d/k3s cluster setup, status, and teardown scripts (bash + PowerShell)
- Minimal Kubernetes smoke-test workload (`nginx` Deployment + ClusterIP
  Service in a dedicated `cascade-test` namespace) proving
  Docker → k3d → k3s → Pod → Service → HTTP works
- Prerequisite checks for Docker, k3d, and kubectl
- Static/unit tests for the repository scaffold and manifest validity
- Environment documentation (`docs/environment.md`)

### Phase 2 — FastAPI Application & Metrics
**Status: Implemented and verified** — the app was exercised both via an
in-process test client and as a real Docker container with every endpoint
curled directly; see `app/`.

- FastAPI app (`app/src/`) with cheap (`/api/home`, `/api/checkout`),
  medium (`/api/search`, with a bounded in-memory cache), and expensive
  (`/api/generate-report`, deterministic and CPU-bounded) endpoint classes
- `/metrics` endpoint exposing `http_requests_total`,
  `http_request_duration_seconds`, `app_endpoint_requests_total`,
  `app_endpoint_duration_seconds`, `app_active_sessions`,
  `app_cache_hits_total`, `app_cache_misses_total`, `app_conversion_total`
  — all with bounded labels only (endpoint class, method, status class,
  scenario; never raw query strings or session IDs)
- In-memory session/conversion simulation (`app/src/sessions.py`)
- Dockerfile — builds and runs as a standalone container
- Static tests (`tests/test_app.py`) covering schemas, cache hit/miss,
  deterministic + bounded report generation, and metric exposure

### Phase 3 — Kubernetes Deployment, HPA & Prometheus
**Status: Implemented and verified** — deployed live to the `cascade`
cluster and autoscaling was proven with real load, not assumed: HPA
scaled the app **1 → 4 → 8 replicas** under a sustained CPU burst against
`/api/generate-report`, confirmed via `kubectl describe hpa` events
(`SuccessfulRescale`) and `kubectl get pods`. Prometheus was confirmed
actually scraping the app (`up{job="cascade-app"}`) and returning live
application metric values via PromQL.

- `kubernetes/{namespace,app-deployment,app-service,hpa}.yaml`
- `kubernetes/prometheus/{rbac,config,deployment,service}.yaml` — scrapes
  only the `cascade` namespace via pod annotations, RBAC scoped to a
  namespaced `Role` (no cluster-wide access)
- `scripts/deploy-app.sh` / `.ps1` — builds the image, loads it into k3d
  (no external registry), applies all of the above, waits for rollout
- Relies on k3d's bundled metrics-server (no separate manifests needed —
  confirmed working via real HPA CPU readings, not just "installed")
- Fixed a real bug found during verification: Kubernetes' own
  readiness/liveness probes against `/healthz` (sent without cookies,
  every 5s) were minting a new simulated session each time, inflating
  `app_active_sessions`; `/healthz` and `/metrics` are now excluded from
  session/traffic instrumentation (`app/src/middleware.py`)
- Static tests for all manifests (`tests/environment/test_app_manifests.py`)

### Phase 4 — Traffic Generators (Locust)
**Status: Implemented and verified** — both traffic classes were run live
and produced real saved telemetry (CSV files under `data/raw/`), each
showing the intended behavioural distinction: flash_crowd spread requests
across `/api/home`, `/api/search`, `/api/checkout` (~4ms avg latency);
edos concentrated 100% of requests on `/api/generate-report` with ~67ms
avg latency despite using far fewer simulated users (8 vs 50) — exactly
the "low volume, disproportionate resource cost" signature this project's
hypothesis is about.

- `traffic/locustfile.py` — dispatches to a generator based on a scenario
  YAML's `type` field (`CASCADE_SCENARIO` env var)
- `traffic/generators/flash_crowd.py` — diverse-endpoint browsing with
  session continuity (used by both `normal` and `flash_crowd` scenarios)
- `traffic/generators/edos.py` — concentrated load on the expensive
  endpoint, minimal think-time
- `traffic/scenarios/{normal,flash_crowd,edos}.yaml` — each generator also
  tags its requests with the `X-Scenario` header, so Prometheus metrics
  from Phase 2/3 can already be sliced by scenario
- `traffic/run_scenario.py` — headless runner that saves Locust's CSV
  stats to `data/raw/<scenario>_<timestamp>/`
- Static tests (`tests/traffic/test_scenarios.py`) covering scenario shape
  and generator dispatch — no live server required
- **Known limitation found during verification:** a single
  `kubectl port-forward` tunnel isn't built for real concurrency — testing
  flash_crowd (50 users) through one gave a ~30% connection-failure rate
  that vanished (0% failures) against a directly-reachable instance. For
  real experiments, run traffic generation from inside the cluster or
  against a NodePort/directly-exposed endpoint, not through port-forward.

### Phase 5 — Replica-Minute Cost Model
**Status: Implemented and verified** — `app/src/cost.py`, a pure/
deterministic module (no FastAPI dependency, reusable by later feature
engineering and experiment scripts). Implements `replica_cost_per_minute`
×`active_minutes` accounting plus `cost_per_request`, `cost_per_second`,
`replica_minutes_per_request`, `cpu_seconds_per_request`, and
`cost_to_traffic_ratio`, all with safe zero-division handling. 22 tests in
`tests/test_cost.py`, including a hand-computed end-to-end scenario. Cost
units only — this is explicitly not a real cloud bill (CLAUDE.md section 10).

### Phase 6 — Feature Engineering
**Status: Implemented and verified** — verified both statically (54 tests)
and live: pulled real Prometheus + kubectl telemetry from the deployed
cluster during an actual EDoS traffic run (which caught a genuine 1→4
scale event mid-collection) and ran it through the full pipeline to a
real, non-fabricated feature row.

- `feature_engineering/{traffic,cost,scaling,behaviour}_features.py` —
  all groups from CLAUDE.md section 14, each a pure function over a
  windowed raw-sample DataFrame
- `feature_engineering/build_features.py` — windowing orchestrator with a
  **proven no-future-leakage guarantee**: a dedicated test shows features
  for a window ending at time *t* are byte-identical whether or not the
  raw series contains data after *t* (CLAUDE.md principle #11)
- `feature_engineering/collect_metrics.py` — `PrometheusClient` (range
  queries) + `ReplicaSampler` (polls `kubectl get deployment/hpa`, since
  this project doesn't run kube-state-metrics)
- `feature_engineering/validate_features.py` — NaN/inf/label/duplicate-
  window checks (CLAUDE.md section 34); train/test overlap checking is
  deferred to Phase 8 where dataset splitting exists
- `docs/feature_dictionary.md` — every feature documented (definition,
  unit, formula, expected relevance, potential leakage/limitation)
- Added real instrumentation the feature pipeline needed but didn't have:
  `app_session_duration_seconds` histogram in the app (Phase 2/3 work),
  since `session_duration` can't be honestly computed from a live gauge
  alone
- **Found and fixed a real test-infra bug:** `tests/feature_engineering/`
  and `tests/traffic/` had `__init__.py`s whose package name collided
  with the top-level `feature_engineering/`/`traffic/` source packages,
  causing pytest to silently import the wrong module. Fixed by adding
  `tests/__init__.py` to properly namespace the whole test tree.

### Phase 7 — Baselines (Rate Limiter & Volumetric Anomaly Detector)
**Status: Implemented and verified** (unit-tested with hand-verified
confusion matrices; a real edge case was caught and fixed — see below).

- `baselines/rate_limiter.py` — threshold calibrated from legitimate
  traffic's request_rate at a configurable percentile. A dedicated test
  (`test_low_volume_edos_evades_rate_limiting`) demonstrates and locks in
  CLAUDE.md section 20's critical experiment: a low-volume EDoS run below
  the threshold evades this baseline, as expected — not hidden.
- `baselines/volumetric_detector.py` — causal rolling z-score
  (`shift(1)` before `.rolling()`, so row *i*'s score never sees row *i*
  or later — proven by a no-future-leakage test).
- **Bug found and fixed:** the original z-score formula silently zeroed
  out any deviation when the trailing baseline window had exactly zero
  variance (`std=0` → `0/0` guarded to `0.0`), which would let an attack
  evade detection specifically when legitimate traffic was *perfectly*
  flat — the opposite of what should happen. Fixed so a zero-variance
  baseline now flags any deviation as maximally anomalous.

### Phase 8 — LightGBM, Random Forest & Ablation Study
**Status: Implemented; verified two ways — full synthetic end-to-end
integration test, and individually-proven live components** (see Phase 10
for why the full live matrix isn't proven end-to-end on this machine).

- `models/train_lightgbm.py` — primary model; threshold tuned by F1 grid
  search on the **validation** set only (never test, never a blind 0.5 —
  CLAUDE.md section 16)
- `models/train_random_forest.py` — secondary comparison model (CLAUDE.md
  section 18)
- `models/feature_sets.py` — the 5-way ablation study (CLAUDE.md section
  19): Models A–E by feature group; Model B is documented as CPU-only,
  not "CPU + memory" (memory isn't tracked anywhere in this pipeline —
  see `docs/experiment_protocol.md`)
- `models/dataset.py` — train/val/test split by **experiment**, never by
  window (CLAUDE.md principle #12), **stratified by label**
- `models/evaluate.py` — classification + security + economic metrics,
  same convention as the baselines for apples-to-apples comparison
- **Two real bugs found via live/integration testing, not by inspection:**
  1. LightGBM's default `min_child_samples=20` silently prevented *any*
     split on realistically small local datasets (16 training rows),
     degenerating to a constant-0.5-probability model that predicted one
     class for every input. Lowered the default; regression test added.
  2. Unstratified experiment-level splitting could place an entire class
     into one split with only a few experiments — exactly what happened
     on the first real attempt. Fixed with per-class stratified splitting.

### Phase 9 — SHAP Explainability
**Status: Implemented and verified** — `models/explain.py`, `TreeExplainer`
over the trained LightGBM model; rankings are always derived from actual
SHAP values, never hard-coded (CLAUDE.md section 27). Verified via a
synthetic dataset where the deliberately-predictive columns
(`expensive_endpoint_ratio`, `cost_per_request`) rank at the top.

### Phase 10 — Experiment Orchestration
**Status: Code implemented and tested; full live matrix not proven
unattended on this dev machine — see below.**

- `experiments/run_experiment.py` — one labeled run: traffic generation +
  concurrent replica sampling + Prometheus collection + feature
  extraction + reproducibility metadata (git commit, config, seed —
  CLAUDE.md section 29), saved to `data/features/` and
  `data/experiments/<id>/metadata.json`
- `experiments/run_matrix.py` — runs every config in a directory
  sequentially
- `experiments/summarize_results.py` — assembles all collected features,
  splits by experiment, trains the ablation study + Random Forest
  comparison, evaluates against both baselines, runs SHAP, writes
  `results/{tables,metrics,figures}` — **verified end-to-end** via
  `tests/experiments/test_summarize_results.py` on a synthetic dataset
  (real code path, all real computation, synthetic input data)
- `experiments/configs/{EDOS,FC}_00{1,2,3}.yaml` — 6 small (75s)
  proof-of-concept experiment configs

**What is and isn't proven at this point:**
- ✅ Traffic generation against the live cluster: proven repeatedly (0%
  request failures reaching the app across many real runs)
- ✅ Prometheus + replica-count collection: proven via manual live
  queries and one full ad hoc live run in Phase 6
- ✅ The full model/baseline/SHAP/results pipeline: proven end-to-end
  against a synthetic dataset that exercises every real function
- ❌ **Running the full 6-experiment matrix unattended, live,
  start-to-finish**: reliably hit a Prometheus connection failure right
  after each 75s traffic run on this specific Windows + Docker Desktop +
  k3d development machine. Extensively debugged (retry logic added,
  replica polling rewritten from `kubectl` subprocesses to the
  `kubernetes` API client to remove a plausible cause) but not fully
  resolved — documented honestly in `docs/experiment_protocol.md` §7
  rather than papered over or claimed fixed without evidence.

Planned for future phases (**not implemented yet**):
- The full E0–E7 experiment matrix at real scale (CLAUDE.md section 13)
- Statistical evaluation across repeated runs (CLAUDE.md section 25)
- Interleaved/mixed-scenario experiments

Do not interpret anything above as a claim that H1/H2 (CLAUDE.md section
2) have been validated — the data volume collected so far is proof-of-
concept scale only; see `docs/experiment_protocol.md` §5.

## Local prerequisites

- [Docker](https://www.docker.com/) (daemon running)
- [k3d](https://k3d.io/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

Verify:

```bash
docker --version && docker info
k3d version
kubectl version --client
```

## Cluster setup

```bash
./scripts/setup-cluster.sh      # bash
.\scripts\setup-cluster.ps1     # PowerShell
```

Creates (or reuses) a local k3d cluster named `cascade` with 1 server node
and 2 agent nodes by default (configurable via `.env`, see `.env.example`).

## Verification commands

```bash
kubectl get nodes
kubectl get pods -A
kubectl get svc -A

./scripts/cluster-status.sh     # bash
.\scripts\cluster-status.ps1    # PowerShell
```

## Run the smoke test

```bash
./scripts/smoke-test.sh         # bash
.\scripts\smoke-test.ps1        # PowerShell
```

Deploys a minimal nginx workload into the `cascade-test` namespace and
verifies internal HTTP connectivity. Prints `RESULT: PASS` or `RESULT: FAIL`.

## Tear down

```bash
./scripts/delete-cluster.sh     # bash
.\scripts\delete-cluster.ps1    # PowerShell
```

Deletes only the `cascade` k3d cluster; no other clusters or Docker
resources are affected.

## Deploy the application to Kubernetes (Phase 3)

```bash
./scripts/deploy-app.sh      # bash
.\scripts\deploy-app.ps1     # PowerShell
```

Builds the app image, loads it into the `cascade` k3d cluster with
`k3d image import` (no external registry is used), and applies the
Deployment, Service, HPA, and Prometheus. Verify:

```bash
kubectl -n cascade get pods,svc,hpa
kubectl -n cascade port-forward svc/cascade-app 8000:80    # then curl localhost:8000/...
kubectl -n cascade port-forward svc/prometheus 9090:9090   # then open localhost:9090
```

## Run the application standalone (outside Kubernetes)

Locally:

```bash
pip install -r app/requirements.txt
uvicorn app.src.main:app --reload --port 8000
```

In Docker:

```bash
docker build -t cascade-app ./app
docker run --rm -p 8000:8000 cascade-app
```

Then:

```bash
curl http://localhost:8000/api/home
curl "http://localhost:8000/api/search?q=example"
curl -X POST http://localhost:8000/api/generate-report -H "Content-Type: application/json" -d '{"complexity": 5}'
curl -X POST http://localhost:8000/api/checkout
curl http://localhost:8000/metrics
curl http://localhost:8000/healthz
```

## Web UI: dashboard & storefront demo

Two human-facing layers sit on top of the pipeline above. Neither
reimplements pipeline logic or fabricates a number — both either call the
real pipeline code in-process or read/poll real live state.

### Dashboard (`webapp/`)

A read-mostly React + FastAPI control/observation layer over
`app/`, `traffic/`, `experiments/`, `feature_engineering/`, `models/`, and
`baselines/` — it imports and calls that pipeline directly
(`webapp/backend/runner.py`) or reads the artifacts it already writes to
disk (`webapp/backend/data_access.py`). Every status shown is a live check
or a read of a real artifact (`system_status.py`), never a hardcoded value.

Run the backend:

```bash
pip install -r webapp/backend/requirements.txt
cd webapp/backend
uvicorn main:app --port 8500
```

Run the frontend (dev server; proxies `/api/*` to the backend above — see
`webapp/frontend/vite.config.ts`):

```bash
cd webapp/frontend
npm install
npm run dev
```

Then open `http://localhost:5173`. Pages:

- **Dashboard** — live system status (Kubernetes/HPA/Prometheus/app
  reachability), the research question and H1/H0/H2 hypotheses, and the
  current SUPPORTED / NOT SUPPORTED / INCONCLUSIVE / INSUFFICIENT DATA
  verdict (`detection.py`) — always capped at INSUFFICIENT DATA below the
  proof-of-concept data-scale threshold, regardless of which way the
  numbers point.
- **Experiments** — every recorded run (presets and ad-hoc), with per-run
  time series, cost/scaling/behaviour charts, per-endpoint request counts
  (cheap/medium/expensive/conversions — real deltas of the Prometheus
  counters sampled at run start/end, see `webapp/frontend/src/summary.ts`'s
  `computeEndpointCounts`), and SHAP/feature-contribution breakdowns where
  a trained model exists.
- **Attack Simulator** / **Flash Crowd Simulator** — start a real,
  parameterized live run (`scenario_builder.py` builds an ad-hoc
  scenario+config pair, `runner.py` runs it through the same
  `experiments/run_experiment.py` path as a preset) against the target
  app — not a canned/precomputed demo.
- **Live Monitor** — polls the currently-running experiment's progress.
- **Dataset Export** — downloads the collected feature dataset as a zip.
- **Architecture** — the real implemented pipeline, diagrammed.

### Storefront demo UI

A human-facing "dummy shop" skin over the same endpoints above
(`app/src/storefront.py`), for live demos where a visible target makes
flash-crowd/EDoS traffic legible — every click calls the real `/api/*`
endpoints, so it produces the same instrumented traffic as Locust or the
dashboard's simulators, not a client-side fake. Its own page/asset
requests are excluded from traffic metrics (see `middleware.py`); only the
API calls it triggers count.

With the app running on port 8000 and the dashboard backend running on
port 8500 (see above), open:

```text
http://localhost:8000/shop
```

Below the header is a "Live traffic & autoscaling" panel driven entirely by
real signals polled from the dashboard backend's `/api/storefront/impact`
endpoint (`webapp/backend/live_impact.py`) — no simulated numbers:

- **Replica pods** — one box per replica (from the live Kubernetes/HPA
  state), so scale-up/scale-down is visible as it happens. Requires the app
  actually deployed via `kubernetes/` (k3d) with Prometheus scraping it —
  outside a cluster this shows "no cluster connected" rather than faking it.
- **Per-endpoint request-rate meters** (cheap/medium/expensive) and a
  **live request feed** built from real per-poll deltas of
  `app_endpoint_requests_total`, so you can see exactly which endpoint
  traffic is landing on.
- A descriptive **pattern banner** (quiet / broad surge / concentrated on
  the expensive endpoint) — a simple threshold on the live
  `expensive_endpoint_ratio` for this page only, *not* the trained CASCADE
  model's verdict (that lives in the dashboard's Detection page).
- **"Simulate flash crowd" / "Simulate EDoS attack" buttons** that start a
  real live run through the same Attack/Flash Crowd Simulator the dashboard
  uses (`POST /api/simulator/{kind}/start` on `webapp/backend`) — so an
  attack demoed here is genuine, instrumented traffic against this app, not
  a client-side animation.

## Generate traffic (Phase 4)

Against a running app (standalone, port-forwarded, or otherwise reachable):

```bash
pip install -r traffic/requirements.txt
python traffic/run_scenario.py traffic/scenarios/flash_crowd.yaml --host http://localhost:8000
python traffic/run_scenario.py traffic/scenarios/edos.yaml --host http://localhost:8000
python traffic/run_scenario.py traffic/scenarios/normal.yaml --host http://localhost:8000
```

Telemetry (Locust's CSV stats) is saved to `data/raw/<scenario>_<timestamp>/`.
Override `--users`, `--spawn-rate`, `--run-time` to deviate from the
scenario file's defaults.

## Run experiments & train the detector (Phases 8–10)

```bash
pip install -r models/requirements.txt

# One labeled experiment: traffic + replica sampling + Prometheus
# collection + feature extraction. Needs --host / --prometheus-url
# reachable (e.g. via kubectl port-forward — see docs/experiment_protocol.md
# §7 for a known reliability caveat with long unattended live runs).
python experiments/run_experiment.py experiments/configs/EDOS_001.yaml \
    --host http://localhost:8000 --prometheus-url http://localhost:9090

# Run every config in experiments/configs/ sequentially:
python experiments/run_matrix.py experiments/configs \
    --host http://localhost:8000 --prometheus-url http://localhost:9090

# Once data/features/*.csv exist, train + evaluate + explain:
python experiments/summarize_results.py
```

`summarize_results.py` writes `results/tables/*.csv`,
`results/metrics/*.json`, and `results/figures/*.png` (ROC/PR curves,
confusion matrix, SHAP summary) — see CLAUDE.md section 38. It refuses to
run on zero data and prints an explicit warning below 3 experiments; it
never fabricates numbers.

## Tests

Static/unit tests (no cluster, no Docker required — covers the
Kubernetes scaffold, the FastAPI application, traffic generators, feature
engineering, baselines, models, and experiment orchestration):

```bash
pip install -r requirements-dev.txt -r app/requirements.txt \
    -r traffic/requirements.txt -r feature_engineering/requirements.txt \
    -r models/requirements.txt
python -m pytest
```

Live-cluster tests (require a running `cascade` cluster with the smoke
test applied):

```bash
python -m pytest -m live tests/environment/test_live_cluster.py
```

## Documentation

- `CLAUDE.md` — full research vision, architecture, and constraints
- `TASKS.md` — current phase scope and acceptance criteria
- `docs/environment.md` — environment setup, verification, and
  troubleshooting for Phase 1
- `docs/feature_dictionary.md` — every feature's definition, unit,
  formula, expected relevance, and known limitations
- `docs/experiment_protocol.md` — train/test separation, ablation-set
  design decisions, data scale actually run so far, and real bugs found
  through live verification

## Safety

This project is a controlled research testbed. All Kubernetes workloads in
this phase are local, internal-only (ClusterIP), and non-destructive. All
EDoS/flash-crowd traffic — including runs started from the dashboard's
Attack/Flash Crowd Simulator pages or the storefront's own "Simulate"
buttons — targets only `DEFAULT_APP_HOST` (`http://localhost:8000` by
default) and is duration-bounded (10–300s, clamped server-side in
`scenario_builder.py`); none of it is capable of reaching a third-party
host (see `CLAUDE.md` §36).
