# CASCADE Research Gap Audit

**Scope:** P19 — Distinguishing EDoS Attacks from Legitimate Flash Crowds in
Autoscaled Applications. This is a read-only audit of the repository as it
exists on disk (code, tests, and the real artifacts under `data/` and
`results/`), not a review of documentation claims in isolation. Every
finding below is backed by either reading the implementation or running
the actual numbers currently on disk; no result is assumed from prose
elsewhere in the repo.

**Labels used throughout:** IMPLEMENTED · TESTED · LIVE VERIFIED ·
PARTIALLY IMPLEMENTED · PLANNED · NOT PROVEN. "LIVE VERIFIED" means real
data collected from an actual running app/cluster exists on disk for that
claim (`data/raw/*`, `data/experiments/*/metadata.json` with a real host
and timestamp) — not merely that the code path is unit-tested.

---

## 1. Executive Summary

CASCADE's engineering is unusually disciplined for a project at this
scale: causal (no-future-leakage) feature windows, experiment-level
(not window-level) train/test splitting stratified by label, threshold
tuning restricted to validation, a persisted SHAP artifact instead of a
hard-coded ranking, and an honest `docs/experiment_protocol.md` that
already documents several real bugs found via live testing. The
pipeline — traffic generation → HPA → Prometheus → feature engineering →
LightGBM/Random Forest → baselines → SHAP — is genuinely IMPLEMENTED and
mostly TESTED, and important pieces are LIVE VERIFIED (real Kubernetes
deployment, real HPA scaling 1→8, real Prometheus telemetry, real cost
accrual).

However, this audit finds **two independent, evidence-based reasons the
current dataset cannot yet honestly support H1/H2**, neither previously
documented in the repo:

1. **HPA scale-down carryover contamination.** Sequential live experiment
   runs are not reset between runs, and the HPA's default 5-minute
   scale-down stabilization window means a run started shortly after a
   previous run can inherit its replica count. Inspecting the actual raw
   telemetry (`data/raw/*/timeseries.csv`) shows this happened: `FC_002`,
   `EDOS_002`, `EDOS_003`, and `INTERLEAVED_001` all show `replica_count`
   **flat at 8 for every single sample in the run**, including from the
   very first sample — meaning the deployment was already at maximum
   scale before that run's own traffic could have caused it. This is not
   a hypothesis; it is directly visible in the CSVs (§Part 3, §Part 7).
2. **The currently-persisted model is not actually using cost or scaling
   features.** `results/tables/feature_statistics.csv` — the real SHAP
   output from the real trained model on disk — shows **every single
   cost feature and every single scaling feature at exactly `0.0`
   importance**. The entire signal comes from four features:
   `search_ratio` (0.49), `cheap_endpoint_ratio` (0.38), `conversion_rate`
   (0.38), `cpu_growth_rate` (0.34). The first three are not emergent
   behavioural signal — they are deterministic artifacts of the Locust
   task-weight configuration: the `EdosUser` class has **zero** tasks for
   `/api/home`, `/api/search`, or a converting `/api/checkout` (weights
   fixed to 0 in `traffic/scenarios/edos.yaml`), so these ratios are
   trivially 0 for every EDoS window and non-zero for every flash-crowd
   window, by construction, independent of any comparable-cost/comparable
   -scaling condition (§Part 3, §Part 4).

Both findings mean: **the current trained model's apparent "perfect"
test-set separation (accuracy 1.0, FPR 0.0) is not evidence that cost or
scaling behaviour distinguishes EDoS from flash crowds** — it is
evidence that (a) two of the four experiments in the val/test split have
corrupted scaling telemetry, and (b) the model that succeeds is
succeeding via a fixed-endpoint-availability shortcut, not the
hypothesized economic signal. `webapp/backend/detection.py` already caps
every hypothesis verdict at `INSUFFICIENT DATA` below 20 experiments, so
the dashboard does not currently overclaim — but this audit's findings
go further than sample size: **even with more data at the current
traffic-generator design, the feature-family attribution would need to
change before a cost/scaling claim could be made honestly.**

None of this means the architecture is wrong — the instrumentation,
splitting, and evaluation code are sound and mostly reusable as-is. It
means the **experiment protocol** (independent live runs) and the
**traffic generator design** (giving EDoS a non-zero chance of touching
cheap endpoints/converting, so behaviour differences become a measured
outcome rather than a scripted guarantee) need to change before O1/O2/O3
can be considered demonstrated, and before O4's numbers can be trusted.

---

## 2. Current Architecture

Real, on-disk structure (not the aspirational CLAUDE.md tree):

```
app/            FastAPI app: cheap/medium/expensive endpoints, cost.py,
                sessions.py, metrics.py, middleware.py, storefront demo UI
kubernetes/     namespace, deployment, service, HPA (CPU util, min1/max8),
                Prometheus (deployment/service/config/rbac), smoke-test/
traffic/        locustfile.py + generators (flash_crowd, edos, mixed,
                viral_shape) + scenarios/*.yaml + run_scenario.py
feature_engineering/  collect_metrics.py (Prometheus + K8s API sampler),
                traffic/cost/scaling/behaviour_features.py, build_features.py,
                validate_features.py
models/         dataset.py (experiment-level split), feature_sets.py
                (5-way ablation), train_lightgbm.py, train_random_forest.py,
                evaluate.py, explain.py (SHAP), predict.py
baselines/      rate_limiter.py (percentile), volumetric_detector.py (z-score)
experiments/    run_experiment.py, run_interleaved_experiment.py,
                run_matrix.py, summarize_results.py, configs/*.yaml
webapp/         React + FastAPI dashboard (live status, experiments,
                simulators, SHAP, mixed/interleaved eval) + storefront demo
data/, results/ real collected telemetry/features and real trained
                model + metrics + figures (see Part 3 for caveats)
```

**Documentation drift found:** `TASKS.md` still describes only Phase 1
("Foundation & Local Kubernetes Testbed") and has not been updated since;
the actual repo implements through Phase 10 per `README.md`. Separately,
`README.md`'s Phase 10 section still lists "Interleaved/mixed-scenario
experiments" under "Planned... not implemented yet", but
`docs/experiment_protocol.md` §8 and the real `data/experiments/MIX_001`
and `INTERLEAVED_001` artifacts show these **are** implemented and have
real (if proof-of-concept-scale) data. This is a rare case of
under-claiming rather than over-claiming, but it is still a
documentation/reality mismatch worth fixing.

---

## 3. O1–O4 Status

### O1 — Construct EDoS and flash-crowd traffic with comparable cost/scaling signatures
**Status:** PARTIALLY IMPLEMENTED, NOT PROVEN at the level required.
**Implemented:** `traffic/scenarios/edos.yaml` (8 users, 0.05–0.2s think
time, 100% weight on `/api/generate-report`) and `flash_crowd.yaml` (50
users, 0.3–1.5s think time, weighted across home/search/checkout) are
tuned so their *configured* request rates land in the same rough order of
magnitude (CLAUDE.md §12's intent). A viral-arrival-shape flash crowd
(`FC_VIRAL_001`) and a concurrent E3 (`MIX_001`) and alternating E4
(`INTERLEAVED_001`) scenario exist and have real collected data.
**Evidence:** Real feature CSVs exist for all of the above
(`data/features/*.csv`, `data/features/held_out/*.csv`).
**Missing:** No mechanism that *targets* a matched cost/scaling condition
— comparability is a fixed, static config choice, not something tuned or
verified per run. And critically, the "comparable scaling" actually
observed in `FC_002`/`EDOS_002`/`EDOS_003` is **not genuine** — it is HPA
carryover contamination (§Part 3), so O1 has not actually been
demonstrated with valid data yet; only `FC_001`/`EDOS_001` (isolated,
clean runs) constitute real evidence, and there scaling is *not* well
matched (FC_001 mean replicas 1.5 vs EDOS_001 mean replicas 4.17 despite
FC_001 having the *higher* request rate — itself an interesting, valid,
if very small-n, data point in the hypothesis's favor).
**Required experiment:** Re-run the matrix with a guaranteed reset (scale
deployment to `minReplicas` and confirm before starting traffic) between
every run, and explicitly search/tune EDoS and flash-crowd user
counts/complexity to converge on matched replica-count and matched
cost, per experiment, with the match quality itself recorded.
**Required evidence:** A results table showing, per matched pair, request
rate delta%, peak-replica delta%, and cost delta%, all small, with
scaling/cost telemetry known to be clean (fresh from `minReplicas`).

### O2 — Identify behavioural features that distinguish the classes despite that similarity
**Status:** PARTIALLY IMPLEMENTED, confounded.
**Implemented:** `behaviour_features.py` computes all CLAUDE.md-listed
features (endpoint diversity, ratios, session proxies, cache/conversion
rates); `docs/feature_dictionary.md` documents formulas and known
limitations honestly.
**Evidence:** `results/tables/feature_statistics.csv` shows real,
non-zero SHAP importance for `search_ratio`, `cheap_endpoint_ratio`,
`conversion_rate` — behavioural features genuinely do separate the
classes in the current data.
**Missing:** As detailed in Part 4, this separation is currently a
**scripted guarantee**, not a discovered behavioural difference: the
`EdosUser` Locust class has literally zero probability of generating a
`/api/home`, `/api/search`, or converting request. A model cannot fail to
find this signal; it isn't testing anything about EDoS's real-world
behaviour. `expensive_endpoint_ratio`/`report_generation_ratio` — the
features CLAUDE.md and `docs/feature_dictionary.md` actually expect to be
most relevant — show **zero** SHAP importance in the current model,
likely because the flat-8-replica contaminated experiments and the
already-perfect separation from the shortcut features leave LightGBM no
reason to also split on them.
**Required experiment:** Give the EDoS traffic generator a small,
configurable, non-zero probability of touching cheap/medium endpoints
(and flash-crowd traffic a configurable "hard negative" mode that
sometimes hits the expensive endpoint — E4 in Part 6), so that endpoint
ratios become a *measured tendency* instead of a *guaranteed 0 or
non-0*, and re-run SHAP.
**Required evidence:** Feature importance computed on that re-designed
traffic showing which features remain predictive once the trivial
zero/non-zero shortcut is removed.

### O3 — Detector using cost-per-request and scaling-behaviour features, not primarily volume
**Status:** IMPLEMENTED (mechanically), NOT PROVEN (empirically) that it
actually relies on those features.
**Implemented:** `models/feature_sets.py`'s 5-way ablation (A–E) exists
exactly as specified; `C_proposed_full` includes cost + scaling +
behaviour + traffic + combined-relationship features; `train_lightgbm.py`
tunes its threshold on validation only, never test.
**Evidence:** `results/tables/ablation_results.csv` /
`results/metrics/experiment_summary.json` show `A_volume_only` and
`E_proposed_without_behaviour` at 0.5 accuracy (chance) while
`C_proposed_full` and `D_proposed_without_cost` reach 1.0 — superficially
matching the hypothesis's shape (behaviour matters, cost doesn't add much
on top of it). **But** per the SHAP evidence in Part 1/4, `C_proposed_full`
gets its 1.0 not from cost or scaling columns (0.0 importance each) but
from the same behavioural shortcut columns available to `D` — so this
ablation result is currently better explained as "removing volume-only
columns exposes the endpoint-availability shortcut" than "cost/scaling
matter." The ablation code is sound; the *conclusion* it currently
supports is not the one intended.
**Missing:** Evidence that cost/scaling features carry information beyond
the behavioural shortcut, on a dataset free of HPA-carryover
contamination.
**Required experiment:** Re-run ablation on a fresh, uncontaminated,
harder dataset (Part 4's O2 fix applied) and check whether `E_proposed
_without_behaviour` (traffic + cost + scaling only, no endpoint ratios)
now scores meaningfully above chance — that is the real test of O3.
**Required evidence:** `E_proposed_without_behaviour`'s recall/FPR on
that dataset.

### O4 — Evaluate latency, cost-before-detection, TPR, flash-crowd FPR, separability
**Status:** PARTIALLY IMPLEMENTED.
**Implemented:** `baselines/rate_limiter.py` and `volumetric_detector.py`
both compute `detection_latency` and `cost_before_detection` using the
identical convention as `models/evaluate.py::detection_latency_and_cost`,
so CASCADE and both baselines are evaluated on equal terms — this is
correctly built for a fair comparison whenever real data exists.
**Evidence:** `results/metrics/baseline_metrics.json` /
`experiment_summary.json` — real numbers exist, but `detection_latency`
and `cost_before_detection` both show `null` in the current run (the
6-window test set never actually included a positive detection-latency
scenario worth measuring at this scale).
**Missing:** Separability analysis (CLAUDE.md §26 — PCA/2D visualization
of the two classes) does not exist anywhere in the codebase (`grep` for
"pca"/"separab" across the repo returns nothing) — NOT IMPLEMENTED, not
merely unproven.
**Required experiment:** A genuine E5/E6/E7-style matrix (Part 6) at
larger scale, run cleanly (Part 3 fix), so latency/cost-before-detection
have an actual attack window to measure against.
**Required evidence:** Non-null latency/cost-before-detection numbers
across multiple repeated runs with confidence intervals (Part 9), plus a
PCA or equivalent 2D plot (new code, currently absent).

---

## 4. Feature Audit

Classification, causal availability, and leakage assessment for every
feature family. "Causally available at detection time" = computable from
data no newer than the window being classified (all features here are,
by `build_features.py`'s window-slicing design — verified by
`tests/feature_engineering/test_build_features.py::test_no_future_leakage`).

### A. Traffic (`traffic_features.py`)
`request_rate`, `request_count`, `peak_request_rate`, `request_rate_std`,
`request_burstiness`, `response_rate`, `error_rate`.
- Measured: yes, directly from `http_requests_total` deltas.
- Causal: yes.
- Label leakage: none.
- Future leakage: none (window-bounded).
- Trivially reveals scenario: **no** — by design these are the *least*
  discriminative features (`A_volume_only` scores 0.5/chance in the real
  run), which is the intended baseline-comparison role.

### B. Economic/Cost (`cost_features.py`)
`estimated_cost`, `cost_per_request`, `cost_per_second`,
`replica_minutes_per_request`, `cpu_seconds_per_request`,
`cost_to_traffic_ratio`.
- Measured: yes, from `app/src/cost.py`'s replica-minute model applied to
  the window's replica/CPU samples.
- Causal: yes.
- Label leakage: none — computed purely from cost-model math over
  observed replicas, no scenario awareness.
- Future leakage: none.
- Reveals scenario trivially: **currently no** (0.0 SHAP importance) —
  but this is itself a finding: given CLAUDE.md's stated hypothesis that
  cost should be a **core** signal, its complete absence from the
  model's real learned importance is unexpected and traceable to the
  contamination in Part 3 (many experiments artificially pinned at max
  replicas, flattening cost variance) rather than to cost genuinely
  being uninformative.
- **Documented correlation risk** (already noted in
  `docs/feature_dictionary.md`): `cost_per_request` and
  `cost_to_traffic_ratio` are highly correlated by construction
  (same numerator, count vs. rate denominator) — not a leakage bug, but
  worth knowing before over-interpreting either one's individual SHAP
  weight in a future, cleaner run.

### C. Scaling (`scaling_features.py`)
`current_replica_count`, `mean_replica_count`, `max_replica_count`,
`replica_growth_rate`, `replica_change_count`, `scale_up_events`,
`scale_down_events`, `time_at_elevated_replicas`, `cpu_growth_rate`,
`replica_to_request_ratio`.
- Measured: yes, from the **observed** Kubernetes API replica/HPA
  samples (never the configured target) — correctly matches CLAUDE.md §9.
- Causal: yes.
- Label leakage: none directly.
- Future leakage: none.
- **Critical finding — confounded by experiment sequencing, not by
  design:** `current_replica_count`/`mean_replica_count`/`max_replica_
  count` are flat at 8 for 3 of 6 single-class experiments and for
  `INTERLEAVED_001` entirely (see Part 3/7) because of HPA-carryover
  between back-to-back live runs, **not** because those scenarios
  actually caused that scaling. This is real, present-in-the-data
  contamination, distinct from a leakage bug in the code — the *feature
  computation* is correct; the *raw telemetry it's computed from* is
  contaminated for those specific runs.
- `cpu_growth_rate` is the one scaling-family feature with non-zero real
  SHAP importance (0.336) — worth investigating further once the
  contaminated experiments are excluded/re-run, since it may be a
  genuine signal or may also be an artifact of some runs starting from a
  non-baseline CPU state.

### D. Application Behaviour (`behaviour_features.py`)
`endpoint_diversity`, `unique_endpoint_ratio`, `expensive_endpoint_ratio`,
`cheap_endpoint_ratio`, `search_ratio`, `report_generation_ratio`,
`requests_per_session`, `session_duration`, `unique_client_ratio`,
`cache_hit_rate`, `cache_miss_rate`, `conversion_rate`.
- Measured: yes, from `app_endpoint_requests_total`/session
  gauges/histograms.
- Causal: yes.
- Label leakage: **effectively yes, by construction, for three of these
  twelve features** — see the shortcut-learning finding below.
- Future leakage: none.
- **Shortcut-learning finding (this audit's central Part 4 result):**
  `search_ratio`, `cheap_endpoint_ratio`, and `conversion_rate` are not
  emergent behavioural signals under the current traffic generators —
  they are **deterministic** consequences of Locust task weights fixed
  to exactly 0 for the EdosUser class (`traffic/scenarios/edos.yaml`:
  `weights: {generate_report: 10, checkout: 0}`, and `EdosUser` in
  `traffic/generators/edos.py` defines no `home`/`search` task at all).
  This is precisely the "EDoS always uses endpoint X" / trivial-shortcut
  pattern the audit brief warned about, just discovered in the *inverse*
  direction ("flash crowd always uses endpoints EDoS structurally
  cannot"). The real trained model's SHAP output confirms the model
  found and is using exactly this shortcut: these three features plus
  `cpu_growth_rate` are the *only* four features with non-zero
  importance out of 39 candidate columns.
- `unique_client_ratio`/`requests_per_session`: already self-documented
  as session-gauge proxies, not true client-identity measurements — a
  known, honestly-labeled limitation, not a new finding.

### E. Combined Relationship Features (`build_features.py::_combined_features`)
All five (`cost_per_request_over_request_rate`,
`replica_count_over_request_rate`, `cpu_utilization_over_request_rate`,
`expensive_ratio_times_cost_per_request`,
`replica_growth_rate_over_request_rate`) show **0.0** SHAP importance in
the current model — consistent with the cost/scaling contamination
above, since each of these five is built directly from a cost or scaling
input.

### `scenario` Prometheus label — latent, currently-unused leakage vector
`app/src/metrics.py` defines a `scenario` label (populated from the
Locust-set `X-Scenario` HTTP header, read in `app/src/middleware.py`) on
`http_requests_total`, `http_request_duration_seconds`,
`app_endpoint_requests_total`, `app_endpoint_duration_seconds`, and
`app_conversion_total`. **Currently this label is not exploited**:
`feature_engineering/collect_metrics.py`'s `APP_METRIC_QUERIES` are all
plain `sum(...)` aggregations with no `by (scenario)` grouping and no
`scenario="..."` filter, so the raw feature pipeline never sees it. This
is NOT a current leakage bug, but it is a live ground-truth channel
sitting directly in the metrics the pipeline scrapes — anyone extending
`collect_metrics.py` to group by scenario (a natural-looking debugging
step) would silently leak the label into every raw column. Worth
tightening (e.g., stripping the label at the PromQL/collection layer, or
at minimum a code comment/test asserting no query groups by it) before
the collection code is touched again.

---

## 5. Data Leakage Audit

| Vector | Status | Evidence |
|---|---|---|
| **Label leakage** (label used as a feature) | NOT FOUND in code | `feature_sets.py::select_features` only ever returns named feature columns, never `label`/`experiment_id`; `models/dataset.py` splits on `experiment_id` explicitly kept out of `X`. |
| **Effective label leakage via scripted behaviour** | **FOUND** | See Part 4 — `search_ratio`/`cheap_endpoint_ratio`/`conversion_rate` are deterministic per traffic-generator design, functioning as a near-perfect label proxy independent of any genuine economic/scaling condition. |
| **Future leakage** (window sees data after `window_end`) | NOT FOUND | `build_features.py::_window_slice` strictly bounds `(window_end - window_seconds, window_end]`; proven directly by `tests/feature_engineering/test_build_features.py::test_no_future_leakage`. |
| **Window leakage** (windows within one experiment split across train/test) | NOT FOUND | Split unit is the whole experiment (`models/dataset.py`), never an individual window; `assert_no_overlap` is a final guard called before training. |
| **Train/test experiment leakage** | NOT FOUND, but **stratification only defends against class imbalance, not against contamination correlated with run *order*** — see below. |
| **Duplicate experiment leakage** | NOT FOUND | Each experiment CSV is a distinct file keyed by `experiment_id`; no evidence of the same raw run being fed into the dataset twice. |
| **Scenario-specific feature leakage (the `scenario` Prometheus label)** | Latent, not currently exploited — see Part 4. |
| **Cross-experiment contamination via shared live infrastructure state** | **FOUND — not one of the six vectors the brief listed by name, but a closely related and more consequential one for this project specifically.** Sequential live runs on the same Kubernetes Deployment/HPA are not statistically independent observations when run within the HPA's ~5-minute scale-down stabilization window, and the current runner code (`run_experiment.py`, `run_matrix.py`) has no reset/wait step. `random_split_by_experiment`'s stratification-by-label defends against an entire *class* landing in one split; it does nothing to prevent a *specific contaminated experiment* from landing in train, val, or test — and in the actual persisted split, contaminated experiments landed in **both** val (`EDOS_003`, `FC_002`) and test (`EDOS_002`). |

**Threshold selection:** Confirmed test-blind. `train_lightgbm.py::train`
tunes via `tune_threshold(y_val, val_proba, ...)` — validation labels
only; `experiments/summarize_results.py::run` never calls
`tune_threshold` against `y_test`. Same for `train_random_forest.py`.

---

## 6. Experiment Design Audit

| Experiment | Support | Notes |
|---|---|---|
| **E0 Normal** | SUPPORTED | `NORMAL_001` config + real data exist; correctly excluded from train/test (`data/features/baseline/`). |
| **E1 Standard Flash Crowd** | SUPPORTED | `FC_001/002/003` + `FC_VIRAL_001` (viral arrival shape). Real data for all four. |
| **E2 Low-volume EDoS** | PARTIALLY SUPPORTED | `EDOS_001/002/003` exist and are genuinely low-*user-count* (8 vs 50), but nothing enforces "low-volume" relative to a calibrated detection threshold — see E5/stealth below. |
| **E3 Matched-cost/matched-scaling FC vs EDoS** | **NOT SUPPORTED as a controlled experiment.** No dedicated config or tooling constructs or verifies a matched pair; the closest thing on disk (`FC_002`/`EDOS_002` landing at the same replica count) is the HPA-carryover artifact from Part 3, not a designed match. See Part 7. |
| **E4 Hard-negative Flash Crowd** (legitimate users also hit expensive endpoints) | **NOT SUPPORTED.** `traffic/generators/flash_crowd.py`'s `FlashCrowdUser` has no task that calls `/api/generate-report` at all — flash-crowd traffic structurally cannot produce this scenario today. |
| **E5 Stealth EDoS** (below rate-limit/volumetric threshold) | NOT SUPPORTED as a named experiment, though the baseline code (`rate_limiter.py`) is capable of measuring it once such a config exists. No `experiments/configs/*` currently targets "EDoS rate below the calibrated 95th-percentile threshold" explicitly. |
| **E6 Interleaved FC→EDoS→FC** | SUPPORTED at the code/config level (`INTERLEAVED_001`, phases 0/2 = flash_crowd) — **but the actual collected data for this exact run is contaminated** (flat replica=8 for the entire run, all four phases, per Part 3), so the *result* is currently unusable as evidence even though the *mechanism* works. |
| **E7 Interleaved EDoS→FC→EDoS** | NOT SUPPORTED as a distinct config — `INTERLEAVED_001`'s phase order is FC→EDoS→FC→EDoS, not EDoS-first/EDoS-last. `run_interleaved_experiment.py` appears general enough to support an EDoS-first ordering via a new config, but no such config exists yet. |

**MIX_001 (E3-as-CLAUDE.md-defines-it, i.e. simultaneous, not
matched-signature)** exists and is implemented correctly per
`docs/experiment_protocol.md` §8, with defensible (documented)
label=1-throughout semantics — this is a different "E3" than the one this
audit's Part 6 template calls "matched-cost/matched-scaling"; the naming
collision between CLAUDE.md's E3 (simultaneous) and this audit prompt's
E3 (matched-signature) is worth resolving in future docs so the two
concepts aren't conflated.

---

## 7. Matched-Signature Research Gap

This is the project's most important open methodological gap.

**Can the project currently construct a pair where Flash Crowd → high
scaling → high cost and EDoS → lower volume → comparable scaling →
comparable cost?**

**No — not as a controlled, verified construction.** What exists:

- Static scenario YAMLs with fixed user counts (`edos.yaml`: 8 users,
  `flash_crowd.yaml`: 50 users) chosen once, by hand, to be in the same
  rough order of magnitude of *configured* request volume. There is no
  code that measures the resulting request rate/CPU/replica/cost after a
  run and iterates the scenario parameters toward a target match.
- No similarity metric is computed or stored anywhere (`grep` for
  "similarity"/"matched" across the repo returns nothing beyond this new
  audit doc). CLAUDE.md's own instruction ("We need to measure the
  similarity rather than merely claim it") is not yet acted on in code.
- The one place two experiments *did* land on the same replica count
  (`FC_002` and `EDOS_002`/`EDOS_003`, all pinned at max=8) is not a
  genuine match — Part 3's raw-telemetry inspection shows all three were
  flat at 8 from their very first sample, i.e., inherited from
  whichever run immediately preceded them, not caused by their own
  traffic.

**Matching on each specific axis, today:**

| Axis | Can currently match/measure? |
|---|---|
| request rate | Measured, yes (`request_rate`). Matching: manual/coincidental only. |
| CPU | Measured (`cpu_utilization_pct` sampled). Matching: no. |
| peak replicas | Measured (`max_replica_count`). Matching: no; also currently unreliable due to carryover (Part 3). |
| average replicas | Measured (`mean_replica_count`). Same caveat. |
| replica-minutes | Computable (`app/src/cost.py`) from clean data. Matching: no. |
| total cost | Computable (`estimated_cost`). Matching: no. |
| cost/request | Computable (`cost_per_request`). Matching: no. |

**What would need to be implemented (not implementing here per
instructions):** (1) a fixed inter-run reset/wait step (scale to
`minReplicas`, poll until confirmed, only then start traffic) so every
run's scaling telemetry is causally its own; (2) a small
search/calibration loop that adjusts EDoS `users`/`report_complexity`
and/or flash-crowd `users`/think-time until a chosen target metric
(replica count, or cost) falls within a configurable tolerance of a
flash-crowd reference run; (3) a persisted "match quality" record (e.g.
`data/experiments/<id>/match_report.json`) with the deltas, so the
matched condition is demonstrated with numbers, not asserted in a
comment.

---

## 8. Baseline Audit

**Implementation quality:** Both baselines are correctly implemented and
share the exact same `detection_latency`/`cost_before_detection`
convention as `models/evaluate.py`, so CASCADE and the baselines are
genuinely evaluated on identical terms — this part of CLAUDE.md §24 is
correctly honored.

- `rate_limiter.py`: threshold calibrated from **label=0 (legitimate)
  training data only** (`rate_limiter.calibrate_threshold(train_df.loc
  [train_df["label"]==0, "request_rate"])` in
  `experiments/summarize_results.py`), never from attack or test data —
  correct.
- `volumetric_detector.py`: rolling z-score computed causally (`shift(1)`
  before `.rolling()`), correctly avoiding using the current row's own
  value in its own baseline statistics.

**Can the system currently demonstrate "low-volume EDoS → below
threshold → baseline fails → CASCADE detects via
economic/scaling/behaviour"?**

Not yet, for two reasons:
1. No experiment config currently targets "EDoS request rate below the
   calibrated threshold" as a deliberate condition (E5, Part 6) — the
   current EDoS runs are not verified to be sub-threshold; whether they
   are is incidental to whatever the calibrated threshold happens to be
   for a given split.
2. Even where the current numbers superficially match the narrative
   (`experiment_summary.json`: `rate_limiter.attack_detected: false` on
   the current 2-experiment test split), the two experiments in that
   test split are `EDOS_002` (contaminated) and `FC_003` (clean) — a
   result computed on contaminated data cannot be cited as the required
   evidence, however suggestive it looks.

**Required evidence before this can be claimed:** A clean (post-Part-3-fix),
deliberately-constructed E5 config, evaluated with both baselines and
CASCADE using the exact same held-out data, with the rate-limiter's
non-detection and CASCADE's detection (if it occurs) both shown from
real, uncontaminated numbers.

---

## 9. Statistical / Experimental Rigour

| Requirement | Status |
|---|---|
| Repeated experiments | PARTIALLY — `EDOS_001-003`/`FC_001-003` are nominal repeats (different Locust seed only), but see Part 3: at least 3 of the 6 are not independent measurements of their scenario due to carryover. |
| Multiple seeds | IMPLEMENTED at the config level (`seed: 42/43/44`), but seed only controls Locust's own RNG, not the shared live infrastructure's residual state — doesn't achieve true independence by itself (Part 3). |
| Confidence intervals | NOT IMPLEMENTED anywhere in `models/evaluate.py`, `summarize_results.py`, or the frontend. |
| Mean/std across runs | NOT IMPLEMENTED — no aggregation code computes mean/std of a metric across repeated runs of the same scenario. |
| Experiment-level splitting | IMPLEMENTED and TESTED (`models/dataset.py`, `tests/models/test_dataset.py`). |
| Per-class evaluation | IMPLEMENTED (`classification_metrics` reports TP/TN/FP/FN split by class; `flash_crowd_false_positive_rate` explicitly separated from overall accuracy). |
| Attack TPR / flash-crowd FPR | IMPLEMENTED and reported as named fields (`edos_detection_rate`, `flash_crowd_false_positive_rate`). |
| Detection latency | IMPLEMENTED (code), NOT PROVEN with non-null data yet (current run shows `null` — no positive detection event to time in the tiny test set). |
| Cost before detection | Same as above — implemented, currently null. |
| Feature separability (PCA etc.) | **NOT IMPLEMENTED** anywhere in the repo (Part 3/8). |
| Ablation studies | IMPLEMENTED and produces real numbers (`results/tables/ablation_results.csv`) — but see Part 3 for why the current numbers' *interpretation* is compromised. |
| Paired statistical tests (t-test/Wilcoxon) | NOT IMPLEMENTED. |
| Effect size / p-value / CI reporting | NOT IMPLEMENTED. |

`n_experiments` in every current run is 6–10, versus
`PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD = 20` in
`webapp/backend/config.py` — the dashboard already correctly refuses to
call any hypothesis verdict anything but `INSUFFICIENT DATA` at this
scale (`webapp/backend/detection.py`), which is the right behavior and
should not be changed.

---

## 10. ML Audit

**What is already correct:**
- Validation/test separation: genuinely separated at the experiment
  level (`random_split_by_experiment`), confirmed via
  `assert_no_overlap`.
- Threshold tuning: only ever touches `y_val`/`X_val`
  (`train_lightgbm.py::train`, `train_random_forest.py::train`) —
  test set is never seen before final evaluation, confirmed by reading
  `experiments/summarize_results.py::run`'s call order (train → tune on
  val → evaluate once on test).
- `min_child_samples` default lowered from LightGBM's default of 20 to 5
  with a documented rationale and regression test
  (`tests/models/test_train_lightgbm.py`) — a real bug caught and fixed
  honestly, not silently patched.
- SHAP output is real, computed from the actual persisted model on real
  test data — not hard-coded (verified by reading `models/explain.py`
  and cross-checking `results/tables/feature_statistics.csv` against the
  scenario configs).

**What is methodologically questionable, found by this audit:**
- The model is very likely learning a fixed-endpoint-availability
  shortcut rather than economic/scaling behaviour (Part 4) — this is not
  a bug in the ML code, it's a consequence of the traffic generator's
  design combined with the small, contaminated dataset giving LightGBM
  an easy, perfect split to find and never needing to look further.
- `E_proposed_without_behaviour` (traffic + cost + scaling, no
  behaviour) scoring at chance (0.5 accuracy) in the current run is
  **more consistent with "cost/scaling data is currently uninformative
  because it's contaminated" than with "cost/scaling genuinely doesn't
  help"** — the ablation code can't distinguish these two explanations by
  itself; only clean data can.
- No cross-validation or repeated-split averaging — a single
  seed-42 split determines every reported number; with 6–10 total
  experiments, a different split could plausibly produce very different
  metrics. (`random_split_by_experiment`'s `seed` parameter exists
  precisely to support this, but nothing in `summarize_results.py`
  currently loops over multiple seeds and aggregates.)

**Can feature-family ablations be performed?** Yes, and they already are
(`models/feature_sets.py`, `results/tables/ablation_results.csv`) — the
mechanism works correctly; only the current data quality limits what can
be concluded from it today.

---

## 11. Live Infrastructure Audit

| Component | Status |
|---|---|
| k3d/k3s cluster creation | LIVE VERIFIED (README Phase 1: `kubectl get nodes` output captured historically; scripts exist and are tested for structure, not for a live cluster in *this* audit session — no cluster was running when this audit was performed). |
| HPA | LIVE VERIFIED — real replica time series in `data/raw/*/timeseries.csv` show genuine 1→2, 1→2→3, 3→6→8 ramps for the *uncontaminated* runs (`FC_001`, `FC_VIRAL_001`, `EDOS_001`). |
| Prometheus scraping | LIVE VERIFIED for short (~75–90s) runs; **NOT PROVEN reliable for unattended multi-run sequences** — `docs/experiment_protocol.md` §7 documents an unresolved `ConnectError` after each ~75s run when `run_matrix.py` is used unattended on this Windows+Docker Desktop+k3d setup. This audit did not re-attempt to reproduce or fix it (no live cluster available this session) — status unchanged from what the repo already documents. |
| Cost calculation | LIVE VERIFIED for clean runs; **compromised for contaminated runs** since it's a direct function of the same replica_count telemetry (Part 3). |
| Replica sampler | LIVE VERIFIED, and its subprocess-avoidance rewrite (kubectl → Kubernetes API client) is a genuine, documented improvement — did not fully resolve the Prometheus flakiness, honestly reported as such. |
| Experiment runner (`run_experiment.py`) | TESTED (unit) and LIVE VERIFIED for individual runs; **the missing inter-run reset/cooldown step is a new finding from this audit**, not previously flagged — see Part 3/7. |
| Traffic generator | LIVE VERIFIED — "0% request failures reaching the app across many real runs" per README, consistent with what this audit observed in the raw stats CSVs. |

**What breaks during unattended experiments:** per existing docs, a
Prometheus connection failure after each ~75s traffic step when running
`run_matrix.py` unattended. **What this audit additionally identifies:**
even when Prometheus *doesn't* fail, running experiments back-to-back
(as `run_matrix.py` does by design — no pause between configs) produces
scaling-telemetry contamination via HPA scale-down stabilization
carryover, which is arguably a more serious problem for research
validity than the connection-flakiness issue, since it fails silently
(no error, no warning — just wrong numbers) rather than loudly.

---

## 12. Website / Demonstration Audit

**What exists:**
- **Live dashboard** (`DashboardPage.tsx`): live replica/CPU stat tiles
  from real `system_status.py` checks, most-recent-run cost/cost-per-
  request/expensive-ratio tiles, a "Run Presentation Demo" button that
  triggers real live experiments (not simulated), and a walkthrough
  component.
- **Experiment comparison** (`ExperimentCompare.tsx`): genuine side-by-
  side comparison table (total requests, peak RPS, max replicas, total
  cost, cost/request, expensive-endpoint ratio) with a ratio column and
  two live request-rate charts — defaults to `FC_VIRAL_001` vs
  `EDOS_001`, which (by Part 3's contamination map) happen to be two of
  the *cleanest* experiments on disk, though this default was not chosen
  for that reason.
- **Scaling visualization**: `TimeSeriesChart` renders real replica/CPU
  series per experiment (`ExperimentDetail.tsx`).
- **Cost visualization**: cumulative cost series (`summary.ts`'s
  `cumulativeCostSeries`) plus per-endpoint request-count tiles (newly
  added, reviewed in the prior session).
- **Baseline comparison**: `webapp/backend/main.py` exposes rate-
  limiter/volumetric-detector results; not yet confirmed whether a
  frontend page renders them side-by-side with CASCADE (component search
  did not find a dedicated baseline-vs-CASCADE chart component — only
  the raw JSON is exposed via API and consumed in
  `MixedInterleavedEvaluation.tsx` for the held-out sets).
- **Feature analysis / SHAP**: `FeatureContributionChart.tsx` exists and
  is wired to real per-run SHAP-derived factors
  (`DetectionExplanationFactor` in `types.ts`).
- **Experiment replay**: `ExperimentDetail.tsx` (339 lines) — the most
  developed page, showing time series, endpoint distribution, run
  narrative, and detection explanation for any past run.
- **Storefront demo UI** (`app/src/storefront.py`): a human-facing
  `/shop` page for live audience demos, reviewed and live-verified in the
  prior session — real traffic through real endpoints, not a client-side
  simulation.

**What is missing:**
- **Separability analysis / PCA** (CLAUDE.md §26): not implemented
  anywhere, frontend or backend.
- **A dedicated baseline-vs-CASCADE comparison view** for the *main*
  test split (only the held-out mixed/interleaved evaluation has this;
  the primary rate-limiter/volumetric numbers are exposed via API but
  this audit did not find a page rendering them next to CASCADE's).
- **Any UI indication of the contamination/confounding findings in this
  audit** — reasonable, since this audit is what surfaces them for the
  first time; flagging here only so a future session doesn't need to
  rediscover that the dashboard currently has no way to flag "this run's
  scaling telemetry may be carried over from the previous run."

---

## 13. Research Risks

Ranked by how directly each threatens the ability to honestly answer the
research question:

1. **HPA carryover contamination** (Part 3/7/11) — corrupts scaling/cost
   telemetry for a large fraction (3–4 of ~10) of currently labeled
   experiments, including experiments currently sitting in the
   val/test split of the persisted model.
2. **Behavioural shortcut learning** (Part 4/10) — the model's real,
   measured signal is a scripted endpoint-availability artifact, not the
   hypothesized economic/scaling behaviour; this would persist even if
   Risk 1 were fixed, unless the traffic generators are also changed.
3. **No matched-signature construction or measurement** (Part 7) — the
   project cannot yet demonstrate the central premise of its own
   research question (comparable scaling/cost, different outcome) as a
   *designed and verified* condition; any apparent match seen so far is
   coincidental or contamination-driven.
4. **Sample size** (Part 9) — 6–10 experiments is already
   self-acknowledged as insufficient (`PROOF_OF_CONCEPT_EXPERIMENT_
   THRESHOLD = 20`), correctly gated in the dashboard.
5. **Unresolved Prometheus flakiness during unattended multi-run
   sequences** (Part 11, pre-existing/documented) — blocks easily
   scaling up data collection to address Risk 4 without manual
   babysitting.
6. **No statistical rigor layer** (Part 9) — even with more data, there
   is currently no code to produce confidence intervals or paired
   significance tests, both explicitly required by CLAUDE.md §25.
7. **Latent `scenario` label in raw Prometheus metrics** (Part 4) — not
   currently exploited, but a future change to `collect_metrics.py`
   could introduce real label leakage without anyone intending it.

---

## 14. P0/P1/P2/P3 Roadmap

**P0 — Required for research validity (do these before trusting any
number from this pipeline):**
1. Add a mandatory reset-and-verify step before every experiment run:
   scale `cascade-app` to `minReplicas`, poll until the Kubernetes API
   confirms it, only then start traffic generation. Apply to both
   `run_experiment.py` (single) and `run_matrix.py` (sequential).
2. Re-run the entire experiment matrix from a clean baseline using that
   fixed runner, and re-generate `results/` from scratch — the current
   `results/models/cascade_lightgbm.joblib` and all figures/tables are
   downstream of contaminated data and should not be cited in any
   presentation until superseded.
3. Redesign the EDoS and flash-crowd Locust task weights so neither
   class has a *guaranteed-zero* probability of touching any endpoint
   class — e.g., a small non-zero `home`/`checkout` weight for
   `EdosUser`, and a small, configurable "hard-negative" probability of
   flash-crowd users hitting `/api/generate-report` (this is also E4 in
   Part 6). Re-run SHAP after this change and check whether cost/scaling
   features acquire non-zero importance.
4. Re-run the 5-way ablation on the corrected data and re-evaluate
   whether `E_proposed_without_behaviour` (cost+scaling only) scores
   above chance — this is the actual test of O3/H1, not the current
   numbers.

**P1 — Strongly recommended (needed to make P0's results trustworthy and
citable):**
5. Implement a matched-signature construction/verification step (Part 7)
   — even a simple grid search over EDoS `users`/`report_complexity`
   against a fixed flash-crowd reference, with a persisted match-quality
   report.
6. Add multi-seed / repeated-run aggregation (mean, std, 95% CI) to
   `experiments/summarize_results.py` or a new script, plus a paired
   test (t-test or Wilcoxon depending on distribution) between CASCADE
   and each baseline once enough repeats exist.
7. Add dedicated E5 (stealth, below-calibrated-threshold) and E7
   (EDoS-first interleaving) configs.
8. Resolve or work around the documented Prometheus unattended-run
   flakiness (§Part 11) — needed to collect enough data for P1's
   statistical work without manual intervention per run.
9. Tighten `collect_metrics.py`/`app/src/metrics.py` so the `scenario`
   label can never be accidentally grouped into a feature (e.g., a
   regression test asserting no PromQL query in `APP_METRIC_QUERIES`
   contains `by (` or `scenario=`).

**P2 — Useful enhancements:**
10. Implement PCA/2D separability visualization (CLAUDE.md §26) once a
    clean, larger dataset exists — premature before P0.
11. Add a dedicated baseline-vs-CASCADE comparison page for the main
    (non-held-out) test split, mirroring `MixedInterleavedEvaluation.tsx`.
12. Update `TASKS.md` to reflect actual project phase (or replace it with
    a pointer to `README.md`'s per-phase status, which is already
    accurate and well-maintained).
13. Fix the stale README Phase 10 claim that interleaved/mixed
    experiments are "not implemented yet."

**P3 — Cosmetic/demo improvements:**
14. Surface data-quality/contamination flags in the dashboard (e.g., "this
    run's replica_count was non-baseline at start — scaling features may
    be affected") once P0's reset step exists, as a safeguard against
    the same issue recurring silently in the future.
15. `.gitignore` `experiments/configs/generated/` and
    `traffic/scenarios/generated/` (ad-hoc simulator run artifacts) —
    noted in the prior session's review, unrelated to research validity
    but a minor repo-hygiene gap.

---

## 15. Recommended Next Implementation Phase

Based strictly on the findings above, the next phase should **not** be
"collect more data" or "add more models" — it should be a **methodology
correction phase**, in this order:

1. Implement the reset-and-verify step (P0.1) — this is a small, isolated
   change to `run_experiment.py`/`run_matrix.py` with no research-design
   ambiguity, and it invalidates nothing currently working.
2. Redesign the EDoS/flash-crowd task-weight guarantees (P0.3) — a
   traffic-generator change, testable in isolation via the existing
   `tests/traffic/` suite before any live re-run.
3. Re-run the full matrix cleanly (P0.2) and regenerate every artifact
   under `results/` and `data/`.
4. Re-examine SHAP and the ablation table on the new data (P0.4) — this
   is the first point at which any statement about O1–O3 or H1/H2 can be
   made with the confidence the project's own documentation standards
   demand.

Only after that should effort go toward P1's matched-signature tooling
and statistical rigor layer — building those on top of the current
contaminated/shortcut-driven dataset would produce polished-looking
numbers that mean the same as today's: not what they appear to.
