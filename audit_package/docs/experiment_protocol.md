# Experiment Protocol

Design decisions affecting research validity (CLAUDE.md section 16), and
an honest account of what has and hasn't been verified at scale.

## 1. Experiment unit and labeling

Each experiment run (`experiments/configs/*.yaml`) is a single continuous
traffic-generation window tagged with exactly one label: `0` (flash crowd
/ normal) or `1` (EDoS). Mixed-scenario experiments (interleaved E3/E4 from
CLAUDE.md section 13) are not yet implemented — every config here is a
pure single-class run. Labels are assigned by the experimenter at config
time, not inferred from traffic content.

## 2. Train/test separation

The split unit is the **experiment run**, never an individual feature
window (`models/dataset.py`). `random_split_by_experiment` additionally
**stratifies by each experiment's label** — with a small number of total
experiments (the realistic scale for local runs; see §5), an unstratified
shuffle can trivially place an entire class into one split, leaving a
classifier with nothing to learn from the other side. This was caught as
a real bug during development (see §6) and is now covered by a regression
test (`tests/models/test_dataset.py::test_random_split_stratifies_by_label_both_classes_in_each_split`).

## 3. Ablation feature sets (ties to CLAUDE.md section 19)

Model B ("volume + resource") is **CPU-only**, not "volume + CPU +
memory" as CLAUDE.md's illustrative example lists. This project's HPA is
CPU-utilization-based only (CLAUDE.md section 9's "use CPU utilization
initially"), and memory utilization is not sampled anywhere in the
pipeline. Substituting a CPU-only proxy for Model B is documented here
explicitly, not silently done — see `models/feature_sets.py`.

## 4. Known measurement limitations

- **`unique_client_ratio` / `requests_per_session`** (behaviour features)
  are proxies built from the `active_sessions` gauge, not true
  client-identity measurements — the app deliberately never tracks client
  IPs or exposes session IDs as Prometheus labels (CLAUDE.md section 7
  forbids unbounded labels). See `docs/feature_dictionary.md`.
- **Scaling feature granularity** depends on `ReplicaSampler`'s polling
  interval (`replica_sampler.interval_seconds` in each experiment config,
  default 5s) — a scale event shorter than that interval could be missed
  entirely between polls.
- **Cost model** uses `cost units`, not a real cloud bill, by design
  (CLAUDE.md section 10).

## 5. Data scale actually run — read this before citing any number

The experiment configs in `experiments/configs/` (`EDOS_001..003`,
`FC_001..003`) use **75-second** runs — proof-of-concept scale, not the
multi-minute-to-hour durations and many repetitions CLAUDE.md sections 13
and 25 call for. Any metrics `experiments/summarize_results.py` produces
from this scale of data are **not** statistically meaningful research
results — the script itself prints an explicit warning when fewer than 3
experiments are found, and the same caution applies at 6. Before drawing
any conclusion about H1/H2 (CLAUDE.md section 2), a much larger matrix —
longer runs, more repetitions per scenario, and the full E0–E7 experiment
set (CLAUDE.md section 13) — is still needed.

## 6. Real bugs found through live verification (not merely assumed-fixed)

Every fix below was found by actually running the pipeline against a live
cluster or a full synthetic integration run, not by static reasoning:

- **LightGBM `min_child_samples` default (20) silently prevented any
  split** on realistically small local datasets (e.g. 16 training rows
  from a 6-experiment split), degenerating to a constant-probability
  model. Lowered the default in `models/train_lightgbm.py`; regression
  test in `tests/models/test_train_lightgbm.py`.
- **Unstratified experiment-level splitting** could place an entire class
  into one split with few experiments (§2 above).
- **`shap`'s lazy `matplotlib`-missing stub broke gevent's global
  object-graph scan** (`isinstance()` on an object whose `__getattribute__`
  always raises) whenever both `shap` and `locust` were imported in the
  same pytest session — fixed by installing `matplotlib` (needed anyway
  for Phase 10's result figures).
- **`tests/feature_engineering/__init__.py` and `tests/traffic/__init__.py`
  collided in import name with the top-level `feature_engineering/` and
  `traffic/` packages**, causing pytest to silently resolve `from
  feature_engineering import X` to the wrong module. Fixed by adding
  `tests/__init__.py` to properly namespace the whole test tree.
- **Kubernetes' own readiness/liveness probes were counted as
  application traffic**, inflating `app_active_sessions` and
  `http_requests_total` — `/healthz` and `/metrics` are now excluded from
  session/traffic instrumentation (`app/src/middleware.py`).

## 7. Open, unresolved issue: automated multi-experiment live runs on this dev machine

`experiments/run_matrix.py`, run unattended against a real k3d cluster on
this project's Windows + Docker Desktop development machine, reliably
hits a connection failure querying Prometheus (`ConnectError: target
machine actively refused it`) right after each ~75s traffic-generation
step completes. This was narrowed down as follows:

- Individual pieces work reliably in isolation: traffic generation
  (verified repeatedly, 0% request failures reaching the app), Prometheus
  queries via `PrometheusClient` (verified with many manual calls,
  including immediately after a failed run), and the full
  feature/model/SHAP/baseline pipeline (verified end-to-end against
  **synthetic** data in `tests/experiments/test_summarize_results.py`,
  and against **real** collected data once, ad hoc, during Phase 6
  verification).
- `PrometheusClient.query_range` was hardened with retries (up to 10
  attempts, 5s apart) — insufficient; the connection stays refused
  through the entire retry window during a live run, then works again
  within roughly a minute once queried manually afterward.
- `ReplicaSampler` was rewritten from `kubectl` subprocess calls to the
  `kubernetes` Python API client (removing concurrent `kubectl.exe`
  subprocess spawning as a possible cause) — this is a genuine
  improvement (no subprocess spawn overhead, one fewer moving part) but
  did **not** resolve this specific failure when retested.
- The failure was not reproduced when running traffic generation alone
  (no concurrent replica sampling), which pointed at *something* related
  to concurrent background activity during the load — but was still
  reproduced after removing the kubectl-subprocess variable, so the
  precise remaining trigger is unconfirmed. Plausible remaining
  candidates: `kubectl port-forward`'s own tunnel behavior under
  sustained concurrent load on Docker Desktop's Windows networking stack,
  or a Python-process-level interaction between the background sampler
  thread, the `subprocess.run()`-launched Locust child process, and the
  parent's own `httpx` client — not conclusively isolated.

**What this means concretely:** `experiments/run_experiment.py` and
`run_matrix.py` are correct and fully unit-tested, and each of their
components has independently-verified live evidence. What is *not*
currently proven is that the full matrix runs unattended start-to-finish
on this specific machine. Workarounds that reduce (but did not, in
testing, fully eliminate) the failure: keep experiment durations short,
re-run a failed experiment individually with fresh `kubectl port-forward`
tunnels, or run from a Linux host / inside the cluster instead of through
Windows port-forwarding. This is recorded here rather than silently
retried into an apparent success, per CLAUDE.md's rule against fabricated
or assumed results.

## 8. E3 (mixed) and E4 (interleaved) — implementation and label semantics

CLAUDE.md section 13 defines E3 ("Flash crowd + EDoS simultaneously") and
E4 ("Interleaved" alternating windows). Update to §1 above: these are now
implemented (`MIX_001`, `INTERLEAVED_001`), but their ground-truth
semantics differ from the pure single-class runs and are documented here.

**E3 / `MIX_001`** runs the flash-crowd and EDoS Locust `HttpUser`
classes concurrently in one process (`traffic/generators/mixed.py`,
`traffic/scenarios/mixed.yaml`), each class's `weight` attribute set to
its original per-scenario user count so a single `--users` invocation
reproduces the original ~50/~8 split. **Label = 1 (attack present) for
every window of the run**, because EDoS traffic is present continuously
alongside legitimate traffic — the question this experiment answers is
"does the detector recognize attack presence amid simultaneous legitimate
load", not "which traffic type is larger in this window". This is a
design choice, not an inferred/measured value.

**E4 / `INTERLEAVED_001`** (`experiments/run_interleaved_experiment.py`)
runs alternating pure-scenario phases back-to-back under one continuous
`ReplicaSampler`/Prometheus observation window, then assigns each output
feature window's label by mapping its `window_end` timestamp to whichever
phase's recorded `[start, end)` wall-clock interval contains it
(`run_interleaved_experiment.label_for_timestamp`). Each phase is
deliberately the same length as the feature window
(`detector.window_seconds`) so windows don't straddle a phase boundary.
The phase→label mapping is **not** inferred from traffic content — it is
recorded from the actual subprocess start/end timestamps and saved
verbatim in `data/experiments/INTERLEAVED_001/metadata.json`'s `phases`
list, so it is independently auditable. As with the existing
`ReplicaSampler` limitation (§4 above), label precision at a phase
boundary is bounded by the ~5s replica-sampler/Prometheus polling
granularity, not exact to the millisecond.

**Both `MIX_001` and `INTERLEAVED_001` are excluded from the main
train/val/test split** — their features are written to
`data/features/held_out/` rather than `data/features/`, so
`experiments/summarize_results.py::load_dataset()`'s glob of
`data/features/*.csv` never sees them, and `models/dataset.py`'s
`random_split_by_experiment` (which assumes one label per experiment via
`.groupby("experiment_id")["label"].first()`) is never exposed to a
mixed-label experiment. Instead, the already-trained `C_proposed_full`
LightGBM model is evaluated directly against each held-out CSV
(`experiments/summarize_results.py::evaluate_held_out`), alongside the
same calibrated rate-limiter/volumetric baselines used for the main test
split, writing `results/metrics/mixed_interleaved_evaluation.json`. At
this data scale (1 window for `MIX_001`, 4 for `INTERLEAVED_001`) this is
illustrative, not statistically meaningful — the same proof-of-concept
caveat as §5 applies, and the JSON's `n_windows` field makes the sample
size explicit rather than implying more confidence than the data supports.

## 9. Viral-event flash-crowd arrival curve

`FC_VIRAL_001` (`traffic/scenarios/flash_crowd_viral.yaml`,
`traffic/generators/viral_shape.py`) replaces the default flash-crowd
scenarios' flat linear Locust ramp with a Locust `LoadTestShape`: a short
constant "trickle" of organic traffic, a logistic (sigmoid) S-curve ramp
up to a peak — the standard model of viral/word-of-mouth adoption
(slow start, accelerating spread, saturating near the peak) — a peak
plateau, then a linear decay. Only the arrival *schedule* differs from
`FC_001-003`; the underlying browsing behaviour (`behavior` block, and
`traffic/generators/flash_crowd.py`'s task logic) is byte-for-byte
identical, so this is purely a traffic-shape addition, not a new
legitimate-traffic behavioural model.

## 10. P0 methodology correction (`docs/research_gap_audit.md`)

A dedicated audit (`docs/research_gap_audit.md`) inspected the real,
already-collected data on disk and found two problems that this section
documents the fix for. **The existing `data/`/`results/` artifacts
described in §5-§8 above are unchanged by this fix and remain
provisional** — they were collected before this correction and should
not be cited as evidence until a clean re-run supersedes them.

### 10.1 HPA scale-down carryover contamination — mandatory experiment isolation

**Finding:** `experiments/run_experiment.py` and `run_matrix.py` never
reset the deployment between runs. Kubernetes' HPA has a default ~300s
scale-down stabilization window, so a run started shortly after a
previous run's scale-up can inherit its replica count for its *entire*
duration. Inspecting the real raw telemetry confirmed this happened:
`FC_002`, `EDOS_002`, `EDOS_003`, and `INTERLEAVED_001` all show
`replica_count` flat at 8 (the configured `maxReplicas`) from their very
first sample — not caused by their own traffic.

**Fix:** `feature_engineering/collect_metrics.py` now provides
`ReplicaResetter`/`ResetConfig`/`ReplicaResetError`. Both
`experiments/run_experiment.py` and `run_interleaved_experiment.py` call
`ReplicaResetter.ensure_isolated(...)` before any traffic is generated
(and before the replica sampler thread starts). It:

1. Reads the HPA's configured `minReplicas` (via the Kubernetes API,
   never assumed).
2. Patches the Deployment's replica count down to `minReplicas`.
3. Polls the observed replica count until it actually equals
   `minReplicas` (never a fixed sleep-and-hope).
4. Holds and re-verifies for a configurable stabilization window,
   restarting the hold if replicas drift away during it.
5. Raises `ReplicaResetError` — propagated, never swallowed — if
   `minReplicas` can't be reached or held within the configured timeout.
   **No traffic is generated in that case.**

Configurable per experiment config via an optional `reset:` block
(defaults apply if omitted — every existing config in
`experiments/configs/*.yaml` is unmodified and picks up the fix
automatically):

```yaml
reset:
  reset_to_min_replicas: true    # default true; false is an explicit opt-out
  replica_reset_timeout_seconds: 330
  replica_stabilization_seconds: 30
  replica_poll_interval_seconds: 5
```

`run_matrix.py` and the dashboard (`webapp/backend/runner.py`) both call
`run_experiment`/`run_interleaved_experiment` directly, so they inherit
this fix without any changes of their own.

**Verified (as of the methodology-correction session that introduced this
fix):** unit/mocked only (`tests/feature_engineering/
test_collect_metrics.py`, `tests/experiments/test_run_experiment.py`) —
no live cluster was available when this fix was implemented.

**UPDATE — live-validated in a follow-up session, see §10.5.** The
`replica_reset_timeout_seconds` default shown above was corrected from an
originally-shipped 120s to 330s based on that live validation; §10.5
explains why in detail.

**Known limitation:** `ensure_isolated()` is a blocking call with no
cancellation hook, unlike traffic generation (which supports
`cancel_event`). A dashboard "Stop" click during the reset/stabilization
wait will not take effect until it completes or times out. Not addressed
here — no dashboard/UI changes were made in this methodology-correction
session.

### 10.2 Deterministic endpoint/behaviour shortcut — traffic generator fix

**Finding:** the real, persisted SHAP output
(`results/tables/feature_statistics.csv`) showed every cost feature and
every scaling feature at exactly `0.0` importance — the model's entire
signal came from `search_ratio`, `cheap_endpoint_ratio`, and
`conversion_rate`. These were not measured behavioural differences:
`traffic/generators/edos.py`'s `EdosUser` had no `home`/`search` task at
all and a `checkout` weight fixed to 0, so these ratios were
*structurally* guaranteed to be exactly 0 for every EDoS window — a
deterministic label shortcut, not signal.

**Fix:**
- `traffic/generators/edos.py`'s `EdosUser` now defines `home`/`search`
  tasks alongside `generate_report`/`checkout`, all gated by configurable
  weights (same pattern as `flash_crowd.py`).
- `traffic/scenarios/edos.yaml`'s default weights changed from
  `{generate_report: 10, checkout: 0}` (home/search absent → 0) to
  `{generate_report: 18, home: 1, search: 1, checkout: 1}` — `generate_
  report` still ~86% dominant, but home/search/checkout are each a real,
  non-zero, ~4.5% chance rather than a structural impossibility.
- `traffic/generators/flash_crowd.py`'s `FlashCrowdUser` gained a
  `generate_report` task, defaulting to weight 0 (every existing
  flash-crowd/normal/viral scenario config is unaffected — they never set
  this key).
- A new scenario, `traffic/scenarios/flash_crowd_hard_negative.yaml`
  (E4, "Hard-negative Flash Crowd" — see §10.3), sets `generate_report: 1`
  against `search: 5` — a legitimate, minority-probability use of the
  same expensive endpoint EDoS targets, so that endpoint alone can no
  longer be a deterministic label proxy either.

**Verified:** unit-tested (`tests/traffic/test_generator_weights.py`,
updated `tests/traffic/test_scenarios.py`) — the weight/task-construction
logic is deterministic and tested directly, not by sampling random
executions. **Not yet verified:** whether cost/scaling features acquire
non-zero SHAP importance once real data is collected under these new
weights — that requires a clean re-run and re-training, explicitly out of
scope for this methodology-correction session.

### 10.3 Hard-negative flash crowd (E4)

`traffic/scenarios/flash_crowd_hard_negative.yaml` — same generator and
behaviour as `flash_crowd.yaml`, `label=0` (unchanged), but with a small
(`generate_report: 1` vs `search: 5`) legitimate chance of viewing the
personalized recommendation report. Exists so "any request to
`/api/generate-report`" cannot be a deterministic EDoS signal, matching
CLAUDE.md's non-negotiable principle #6 (flash crowd is a first-class
negative class) and principle #10 in the audit's terminology ("hard
negative scenarios should be introduced where legitimate traffic also
causes expensive workloads"). No experiment config
(`experiments/configs/*.yaml`) references this scenario yet — adding one
and running it is left to the next (data-collection) session, per this
session's "no full dataset rerun" constraint.

### 10.4 Matched-signature protocol (E3-as-audit-defines-it)

**Terminology note:** CLAUDE.md's own "E3" (§13) means *simultaneous*
flash-crowd + EDoS traffic (`MIX_001`) — already implemented, unrelated
to this section. The audit's Part 6/7 "matched-cost/matched-scaling E3"
is a *different* concept: two **separate** runs (one flash-crowd, one
EDoS) whose aggregate scaling/cost signatures are close. To avoid
conflating the two, this document calls the audit's concept the
**matched-signature pair** and reserves "E3" for the existing
simultaneous-traffic meaning.

**What exists after this session:** `experiments/match_quality.py`
provides the measurement primitives, but **not** a live calibration
search (deliberately deferred — see below):

- `compute_signature(experiment_id, raw_timeseries_df, cost_config)` —
  computes one experiment's aggregate signature (request rate, mean CPU%,
  mean/peak replica count, replica-minutes, total cost, cost/request)
  directly from its `data/raw/<id>/timeseries.csv`, using the exact same
  replica-minute cost formula as `feature_engineering/cost_features.py`.
- `compare_signatures(reference, candidate, tolerances)` — returns a
  `MatchReport` with a percentage delta on every axis
  (`request_rate_delta_pct`, `cpu_delta_pct`, `peak_replica_delta_pct`,
  `mean_replica_delta_pct`, `replica_minutes_delta_pct`,
  `total_cost_delta_pct`, `cost_per_request_delta_pct`) plus a measured
  `match_status`.
- `save_match_report(report, experiments_dir)` — writes
  `data/experiments/<candidate_id>/match_report.json`, alongside that
  experiment's existing `metadata.json`.

**Which axes gate `match_status`:** only `peak_replica_count`,
`mean_replica_count`, and `total_cost` (`PRIMARY_MATCH_AXES`).
`request_rate` is recorded but deliberately **not** gating — EDoS is
*expected* to differ there (lower volume, comparable cost/scaling is the
entire research premise); requiring it to match would contradict the
research question.

**Tolerance rationale (default 25% per axis, ±1 replica absolute for the
two replica-count axes):** derived from this project's own observed
same-scenario run-to-run noise. `FC_001` vs `FC_003` — identical scenario
config, differing only by Locust seed, both clean/uncontaminated runs —
showed ~5-6% deltas on `request_rate`/`estimated_cost`/
`mean_replica_count` from noise alone. 25% is roughly 4-5x that noise
floor: high enough that a "MATCHED" verdict isn't demanding precision the
system's own repeatability can't support, low enough to still mean
something. The ±1 replica absolute tolerance exists because a percentage
delta is unstable at small integers (1 vs 2 replicas = 100% "delta").
These are starting defaults, not final; revisit once a real matched-pair
search has been run and its own achievable precision is known.

**Calibration workflow (designed, NOT implemented/run this session):**

```
1. Run a flash-crowd reference; compute_signature() it.
2. Generate an EDoS candidate (current default parameters);
   compute_signature() it.
3. compare_signatures(reference, candidate).
4. If match_status == "NOT_MATCHED": adjust a configurable EDoS
   parameter (users, report_complexity, or the new endpoint weights) by
   CalibrationConfig's step size, in the direction that reduces the
   dominant primary-axis delta, and go to 2.
5. Stop when MATCHED, or after CalibrationConfig.max_iterations.
6. save_match_report() the final (matched or not) result.
```

`experiments/match_quality.py::CalibrationConfig` exists as the
configuration surface for step 4 (`max_iterations`, `users_step`,
`report_complexity_step`, `target_axes`) — the search loop itself is
intentionally not implemented, per this session's constraint against
running a live calibration search or regenerating any data.

**Verified (at the time §10.1-10.4 were written):** unit-tested only
(`tests/experiments/test_match_quality.py`) — `compute_signature`
against hand-computed values on synthetic data, `compare_signatures`'
matched/not-matched/absolute-tolerance/custom-tolerance behaviour, and
`save_match_report`'s file placement.

**UPDATE — live-validated in a follow-up session, see §10.5-10.6.**

## 10.5 Live validation session — real k3d cluster, three clean small experiments

A follow-up session live-verified §10.1-10.4 against a real k3d cluster
(`cascade`, 1 server + 2 agents, already existing from earlier phases,
restarted via Docker Desktop for this session). This section records
what was actually observed — not what was assumed.

### 10.5.1 HPA reset: works, but the original 120s default was wrong

Real-cluster test (`ReplicaResetter.ensure_isolated` invoked directly,
then through the actual `run_experiment.py` pathway): a deployment
deliberately left at an elevated replica count (residual from the
cluster's own restart, then manually pushed higher) was targeted for
reset to `minReplicas=1`.

**First attempt, with the original 120s default:** `RESETTING` and
`WAITING` fired correctly, replicas briefly reached 1, `VERIFYING`
began — then the HPA controller re-asserted a cached high recommendation
within 5s, `ensure_isolated` correctly logged the drift and restarted the
stabilization hold, repeatedly, for the full 120s, then correctly raised
`ReplicaResetError` rather than reporting a false success. **This proved
the core safety property works** — no traffic was generated, no
contamination occurred — but also proved the 120s default can **never**
realistically win this race: the HPA re-asserts its own desired replica
count on its own sync loop regardless of an explicit scale-down patch,
and that recommendation can itself be "stuck" high for Kubernetes'
default 300s downscale-stabilization window. An assumption in the
original `ResetConfig` docstring ("we're actively scaling down via an
explicit patch... this should normally complete in well under a
minute") was simply wrong, disproven directly by this run.

**Fix applied:** `ResetConfig.timeout_seconds` default raised from 120s
to 330s (300s + margin) in both the dataclass default and the
`from_dict()` fallback (both had to be changed — an easy inconsistency
to miss). **Second attempt, same elevated state, 330s default:** the
exact same drift-and-restart pattern occurred for ~316s, then the
deployment finally held at minReplicas for a full clean 30s window, and
`ensure_isolated` returned success (`STABILIZED`) after 351.6s total.

**A further, minor nuance found and documented (not code-changed):**
that 351.6s exceeds the nominal 330s budget by ~22s. This is because the
overall `timeout_seconds` deadline is only checked when drift is
detected, not during a clean stabilization hold already in progress —
so a hold that begins just before the deadline is allowed to finish. This
never risks a false success (every poll in that hold matched
minReplicas), so it was corrected in the docstring (accurate contract:
timeout bounds drift-tolerance, not the success path's absolute wall-clock
cap) rather than treated as a defect requiring a code change.

**Second live regression, later in the same session:** after a real EDoS
run pushed CPU hard enough to trigger a genuine HPA scale-up to 8
replicas (see §10.5.3), the very next reset attempt still could not reach
minReplicas within the full 330s (last observed: 2 replicas) — a real,
more severe case than the first. The cluster was left to settle
naturally (an additional ~2 minutes, monitored via `kubectl get
deployment`) and the retry then succeeded cleanly on the first attempt.
**Conclusion, stated honestly:** 330s is not a universal upper bound on
how long a real HPA can hold a stale high recommendation after a severe
CPU spike — it is a reasonable default for the common case, not a
guarantee. A production-quality experiment runner should treat a
`ReplicaResetError` as "wait and retry," not "fatal," when running an
unattended matrix. This was not implemented (out of scope: no matrix
orchestration changes this session) but is recorded here as a concrete
requirement for whoever builds that orchestration.

**Live verification level:** real k3d/k3s cluster (`kubectl`-verified
`minReplicas`/`maxReplicas`/deployment name/namespace), real HPA
contention, real `ReplicaResetter` code path (not mocked) — both the
failure mode and the success mode were observed directly, twice each.

## 10.5.2 CRITICAL — task-weighting was silently broken for every multi-weight scenario, in every prior experiment

This is the most significant finding of the live validation session, and
it was NOT anticipated by any part of the P0 methodology-correction plan.

**Discovery:** the first live E4/EDoS validation run
(`VALIDATION_EDOS_001`, weights `generate_report:18, home:1, search:1,
checkout:1`, intended ~86%/4.5%/4.5%/4.5%) produced an observed request
split of ~26%/23%/26%/25% — uniform, not weighted at all. Root-caused to
this installed Locust version's (2.46.4) `Environment.
_filter_tasks_by_tags()`, which runs **unconditionally on every run**
(tag-filtering enabled or not) and does `task_holder.tasks = [task for
task in task_holder.tasks ...]`. Iterating a `{task: weight}` **dict**
yields only its keys, so assigning such a dict directly to `.tasks`
(this project's pattern in `edos.py`/`flash_crowd.py`, used because
weights come from runtime YAML, not a static class body — the pattern
Locust's own docs describe only applies when the dict is declared
*inside* a class body, where the `UserMeta` metaclass flattens it into a
repeated list *before* this filtering step ever runs) gets silently
collapsed to one-of-each, discarding every configured weight.

**This is not new, and it is not specific to this session's changes.**
Cross-checked against `FC_001` (part of the existing provisional
dataset, run months before this session, configured weights `home:3,
search:5, checkout:1`): real observed counts were home=1284, search=1304,
checkout=1268 — uniform (~33% each), not the configured 3:5:1 ratio. This
bug has been silently present since Phase 4, corrupting the intended
browsing-behaviour composition of **every** flash-crowd run in the
provisional dataset (`FC_001-003`, `FC_VIRAL_001`, `NORMAL_001`,
`MIX_001`'s flash-crowd share, `INTERLEAVED_001`'s flash-crowd phases).
The only reason it was never noticed is that `edos.yaml` always had
exactly one non-zero weight (`checkout: 0`), where uniform vs. weighted
selection over a single option is indistinguishable.

**Fix:** `traffic/generators/__init__.py::weighted_task_list()` — builds
`.tasks` as a flat LIST with each task repeated by its configured weight
(exactly what Locust's own metaclass does internally), which survives
`_filter_tasks_by_tags()`'s reassignment unchanged. Applied in both
`edos.py` and `flash_crowd.py` (and therefore `mixed.py`, which calls
into both). Regression tests added, including one that calls Locust's
actual `filter_tasks_by_tags()` directly against a built class
(`tests/traffic/test_generator_weights.py::
test_weighted_task_list_survives_locusts_filter_tasks_by_tags`) — the
most direct test of the real failure mode, not just our own list
construction.

**Live re-verification after the fix**, three separate real experiments:

| Experiment | Endpoint | Configured weight ratio | Observed | 
|---|---|---|---|
| `VALIDATION_EDOS_001` | generate_report | 18/21 = 85.7% | 1107/1300 = 85.2% |
| | home | 1/21 = 4.8% | 68/1300 = 5.2% |
| | search | 1/21 = 4.8% | 72/1300 = 5.5% |
| | checkout | 1/21 = 4.8% | 53/1300 = 4.1% |
| `VALIDATION_FC_001` | home | 3/9 = 33.3% | 1022/3029 = 33.7% |
| | search | 5/9 = 55.6% | 1663/3029 = 54.9% |
| | checkout | 1/9 = 11.1% | 344/3029 = 11.4% |
| `VALIDATION_FC_HARDNEG_001` | home | 3/10 = 30% | 945/3072 = 30.8% |
| | search | 5/10 = 50% | 1520/3072 = 49.5% |
| | checkout | 1/10 = 10% | 298/3072 = 9.7% |
| | generate_report | 1/10 = 10% | 309/3072 = 10.1% |

All observed proportions match configured weights within normal random
variance. **This is the load-bearing evidence for both Deliverable B and
Deliverable C actually working live** — without this fix, neither would
have functioned, despite passing every unit test written for them (the
unit tests checked `.tasks` membership/count directly, which was
correct; they never exercised Locust's own runtime filtering step, which
is exactly where the bug lived).

**Research implication:** every feature computed from `FC_001-003`,
`FC_VIRAL_001`, `NORMAL_001`, and the flash-crowd portions of `MIX_001`/
`INTERLEAVED_001` in the existing provisional dataset reflects **uniform**
home/search/checkout browsing, not the documented, intended 3:5:1 mix —
another reason (independent of §Part 3's HPA-carryover contamination and
§Part 4's EDoS-shortcut findings) that dataset must not be cited as
research evidence and must be regenerated from a clean re-run.

## 10.6 Phase 4/5 checks on the three live validation experiments

Feature CSVs for the three clean runs (`VALIDATION_EDOS_001`,
`VALIDATION_FC_001`, `VALIDATION_FC_HARDNEG_001`) were written to
`data/features/validation_live_gate/` (isolated from the main
`data/features/*.csv` glob `summarize_results.py` trains on) with fresh,
non-colliding experiment IDs — the existing provisional dataset and
`results/models/cascade_lightgbm.joblib` (unchanged mtime, verified) were
never touched.

**Shortcut removal — confirmed with real numbers**, mean values across
each run's 3 feature windows:

| Feature | EDoS | FC | FC hard-negative |
|---|---|---|---|
| `request_rate` | 16.6 | 38.9 | 49.2 |
| `cost_per_request` | 0.00221 | 0.00064 | 0.00071 |
| `cost_to_traffic_ratio` | 0.0442 | 0.0128 | 0.0143 |
| `mean_replica_count` | 2.92 | 1.50 | 2.08 |
| `max_replica_count` | 4.33 | 1.67 | 2.33 |
| `expensive_endpoint_ratio` | 0.574 | 0.000 | 0.068 |
| `cheap_endpoint_ratio` | 0.063 | 0.455 | 0.403 |
| `search_ratio` | 0.030 | 0.545 | 0.497 |
| `conversion_rate` | 0.029 | 0.118 | 0.097 |
| `endpoint_diversity` | 0.299 | 0.626 | 0.783 |

EDoS's `cheap_endpoint_ratio`/`search_ratio`/`conversion_rate` are now
genuinely non-zero (6.3%/3.0%/2.9%) rather than structurally impossible
to be anything but zero — Deliverable B confirmed live. The hard-negative
flash crowd's `expensive_endpoint_ratio` is genuinely non-zero (6.8%)
while remaining clearly a legitimate, minority behaviour — Deliverable C
confirmed live. Crucially, the classes remain clearly distinguishable on
`expensive_endpoint_ratio` (57% vs. 0% vs. 6.8%) — the fix replaced a
deterministic shortcut with a genuine, graded, measured difference, not
with indistinguishable noise. (Note: `expensive_endpoint_ratio`'s 57.4%
window-mean for EDoS is lower than the run's own 85.2% aggregate share
from the table above — window-level composition varied somewhat as HPA
scaled the deployment up mid-run; not investigated further as it does
not affect this session's pass/fail question.)

Also directionally consistent with H2 (not a statistical claim — n=1 run
per class): EDoS's `cost_per_request` (3.4x FC's) and
`cost_to_traffic_ratio` (3.4x FC's) are both higher despite EDoS's
`request_rate` being the *lowest* of the three — the qualitative shape
CLAUDE.md's hypothesis predicts, observed on real, uncontaminated,
correctly-weighted telemetry for the first time this project has
produced.

**Match-quality primitives — confirmed operating on real telemetry**
(`experiments/match_quality.py`, unchanged — no bug found, per Phase 5's
instruction to leave it alone unless a defect surfaced):
`compute_signature()` on `VALIDATION_FC_001`'s and
`VALIDATION_EDOS_001`'s real `timeseries.csv` files produced real,
non-crashing signatures (request_rate 38.9 vs. 16.6, mean CPU% 54.4 vs.
159.9, mean/peak replicas 1.48/2.0 vs. 2.84/8.0, replica-minutes 1.50 vs.
2.90, total cost 1.50 vs. 2.90, cost/request 0.00064 vs. 0.00291).
`compare_signatures()` computed all seven per-axis percentage deltas
correctly and returned `match_status: NOT_MATCHED` (correctly — this
pair was never calibrated to match; no tolerance tuning was performed,
per instructions). `save_match_report()` wrote
`data/experiments/VALIDATION_EDOS_001/match_report.json` alongside that
run's real `metadata.json`, confirmed on disk.

(Mean CPU utilization figures above, e.g. 159.9%, come directly from the
HPA's own `current_metrics.resource.current.average_utilization` field —
values over 100% were observed live and are a Kubernetes/metrics-server
reporting characteristic under a sudden CPU spike relative to the pod's
resource *request* (50m), not a bug in this project's code; recorded
here for anyone surprised by it later.)

## 11. Experiment orchestration reliability (retry + failure-detection fixes)

A follow-up session, after §10.5's live validation, hardened the
orchestration layer against two specific reliability gaps observed
during that validation — in preparation for an eventual unattended full
matrix, not as part of any data collection itself. **No data/results/
models were touched; this section is process-reliability work only.**

### 11.1 Retryable replica reset

**Problem observed in §10.5.1:** a `ReplicaResetError` after the full
330s timeout is a correct, safe outcome (no contamination), but treating
it as fatal for an entire unattended matrix run is unnecessarily brittle
— the very next session's manual retry, after letting the cluster settle
~2 more minutes, succeeded immediately.

**Fix:** `feature_engineering/collect_metrics.py` gained
`ResetRetryConfig` and `ensure_isolated_with_retry()` — an orchestration
-level wrapper around `ReplicaResetter.ensure_isolated()`, called from
both `experiments/run_experiment.py` and `run_interleaved_experiment.py`
(and therefore `run_matrix.py`, which calls those unchanged).
**`ReplicaResetter.ensure_isolated()` itself was NOT modified** — it
remains a single, self-contained attempt, solely responsible for
deciding whether that one attempt succeeded, with its existing safety
contract intact (never returns without a confirmed, held minReplicas
state; always raises `ReplicaResetError`, never swallowed, on failure).
The wrapper only decides whether to call it again:

```yaml
reset:
  max_attempts: 3            # default; bounded, not unlimited
  retry_backoff_seconds: 30  # default, fixed (not exponential)
```

Each retry is a full, independent call into `ensure_isolated()` — never
a cached/assumed result. If every attempt fails, the wrapper raises
`ReplicaResetError` (chained from the last attempt's error); this
propagates out of `run_experiment()`/`run_interleaved_experiment()`
uncaught, so **the safety invariant is unchanged**: failed isolation
(now meaning all `max_attempts` failed) still always means no traffic is
generated. Defaults (3 attempts x 30s) were sized from §10.5.1's
observation, not chosen arbitrarily: they give a comparable total idle
allowance to what actually worked there, without an unbounded retry
count.

**Verified:** unit-tested only, using a duck-typed fake resetter (not
the real Kubernetes-facing `ReplicaResetter`, which already has its own
separate mocked-Kubernetes-client tests) —
`tests/feature_engineering/test_collect_metrics.py` covers immediate
success, retry-then-success, exhaustion-then-raise, per-attempt logging,
and that exhaustion never returns a partial result. Orchestration-level
integration confirmed in `tests/experiments/test_run_experiment.py`:
`subprocess.Popen` (traffic generation) is never reached after all
retries fail, and a later attempt succeeding lets control reach the
traffic-generation code (verified by making the mocked traffic
subprocess call raise a distinguishable error, and asserting that
specific error surfaces rather than a `ReplicaResetError`). **Not
live-verified** — no real cluster retry-then-succeed sequence was
observed in this session (§10.5.1 already provided real evidence that a
retry-after-settling works; this session did not repeat that live).

### 11.2 Port-forward / traffic-failure detection

**Problem observed live in §10.5.1/§10.5.2's validation runs:** a
`kubectl port-forward svc/cascade-app ...` tunnel is bound to whichever
specific pod backs the Service at the moment the tunnel is established
— it does not follow the Service's endpoints if they change. When HPA
scale-down deletes that specific pod (an expected, routine consequence
of any experiment that drives real CPU load), the tunnel breaks
silently. Locust, by default, exits 0 when `--run-time` is reached
regardless of request failures — so a tunnel dying mid-run previously
produced a "successful" (`returncode == 0`) but silently near-empty/
garbage telemetry file, with nothing in the pipeline ever noticing.

**Architectural finding (reported, not worked around):** the entire
port-forward lifecycle is established and held open OUTSIDE this
project's Python code — by whoever runs an experiment, in a separate
terminal, per the commands documented in `README.md`
("Run the application standalone" / experiment sections). No Python
module in this repository spawns, monitors, or manages a
`kubectl port-forward` process. A genuinely robust fix — a self-healing
tunnel-wrapper process that detects a dead tunnel and re-establishes it,
or exposing the Service another way (e.g. NodePort, explicitly ruled out
per this session's instructions) — would require introducing exactly
that new subprocess-lifecycle-management layer: spawning
`kubectl port-forward` from Python, health-checking it, restarting it on
death, and cleaning it up reliably on every exit path (including the
existing Windows process-tree-kill path `_kill_process_tree` already
needed for Locust). That is a real architectural addition, not a small
fix, and was **not implemented this session**, per the explicit
instruction to stop and report rather than introduce a risky redesign.

**What was implemented instead — the smallest change that turns silent
corruption into a loud, already-handled failure:**

1. `traffic/run_scenario.py` now passes Locust's own
   `--exit-code-on-error 1` flag. Locust already tracks every request
   failure; this flag is a native, one-line way to make it exit non-zero
   if any occurred, which `experiments/run_experiment.py`'s existing
   `if proc.returncode != 0: raise subprocess.CalledProcessError(...)`
   check already handles correctly — no other code change was needed for
   this half of the fix. **Trade-off, stated plainly:** this makes a
   *single* transient request failure (unrelated to a dead tunnel) abort
   the whole experiment too, not just a systemic failure. A
   failure-rate-threshold check would avoid that false-positive case but
   requires parsing Locust's own stats post-run — a larger, more bespoke
   addition than this session's scope; not implemented.
2. `experiments/run_experiment.py`/`run_interleaved_experiment.py` gained
   `check_host_reachable(host)`, called immediately after isolation
   succeeds and before traffic generation starts — a single `GET
   /healthz` with a short timeout. This does not make a dead tunnel
   recover; it only fails fast (before spending the whole traffic-
   generation duration) when the tunnel was *already* dead going into
   this run — a cheap, real reliability improvement for the retry-based
   orchestration in §11.1 (a fast, clear failure is retried/reported
   quickly; a failure only discovered after 60+ seconds of wasted, wrong
   telemetry is not).
3. **Prometheus's port-forward was not touched** — the `prometheus`
   Deployment has exactly one replica and no HPA, so its backing pod is
   not churned by scaling the way `cascade-app`'s is; `PrometheusClient`
   already has its own retry-with-backoff for transient connection
   failures (`query_range`'s existing `max_retries`/
   `retry_backoff_seconds`), which is adequate for that component's
   actual failure mode (occasional restart, not routine scale-driven
   pod churn).

**Verified:** unit-tested — `check_host_reachable`'s own success path
(a reachable host, mocked `httpx.get`) and failure path (`httpx.
ConnectError` -> a clear `ConnectionError`) are both directly tested
(`tests/experiments/test_run_experiment.py`), plus the existing mocked
orchestration tests that monkeypatch it out entirely when it's not the
thing under test. `--exit-code-on-error` was verified against the
installed Locust version's own `--help` output (`--exit-code-on-error
<int>` is present) but not exercised against a real dead tunnel this
session (the
live cluster used in §10.5 was not re-used to reproduce the exact
failure and confirm the new non-zero exit code end-to-end).

**Recommended for whoever eventually needs the full self-healing fix:**
a small `PortForwardManager` (or similar) that: spawns
`kubectl port-forward svc/X N:M` via `subprocess.Popen`, health-checks it
on an interval, and restarts it (killing the old process tree first, on
Windows via the same `taskkill /F /T` pattern `_kill_process_tree`
already uses) if a health check fails — scoped narrowly enough to avoid
becoming a general process-supervision framework.

## 12. Matrix-level failure isolation

A follow-up session hardened `experiments/run_matrix.py` itself: before
this fix, one experiment's exhausted failure (from §11's retry
mechanism, or any other exception) propagated straight out of
`run_matrix()`'s `for config_path in configs:` loop, aborting every
remaining config in the matrix. **This is process-reliability work
only — no data/results/models were touched.**

### 12.1 Per-experiment failure isolation

`run_matrix.py` now wraps each config's `run_experiment()` call in
`run_one_experiment()`, which never lets a config's outcome (success or
failure) raise out of it, with one deliberate exception:
`KeyboardInterrupt`/`SystemExit` are never caught — an operator's Ctrl-C
or a process-level exit request always stops the matrix immediately, as
it would for any other script. Every other exception — both the known,
anticipated infrastructure failure modes (`ReplicaResetError`,
`ConnectionError` from `check_host_reachable`,
`subprocess.CalledProcessError` from a failed Locust run, `OSError` from
a missing scenario file, `KeyError`/`yaml.YAMLError` from a malformed
config) and any genuinely unexpected programming error — is caught,
recorded, and the matrix continues to the next config.

**Why continuing after an *unexpected* error is demonstrably safe, not
just convenient:** by the time any exception reaches `run_matrix.py`,
`run_experiment()` has already cleaned up its own subprocess/thread
state (see §12.2), and every subsequent config still goes through its
own independent, from-scratch `ensure_isolated_with_retry()` call —
there is no shared mutable state one experiment's crash leaves behind
that the next experiment's isolation step doesn't already re-verify.
This reasoning is recorded in `run_one_experiment()`'s docstring
precisely so it can be revisited if a future change ever introduces
persistent cross-experiment state.

The known/unexpected distinction is preserved in the record, not
collapsed: an unexpected error gets `failure_stage:
"unexpected_programming_error"` and a full traceback, so it's visibly
different from routine infrastructure flakiness during later
investigation.

### 12.2 Orphaned sampler-thread cleanup (found via code inspection, not live)

Inspecting the actual subprocess/thread lifecycle (per this session's
explicit instruction not to assume cleanup works) surfaced a real gap:
`experiments/run_experiment.py` starts a background thread running
`ReplicaSampler.sample_for(duration_seconds, interval_seconds)` before
generating traffic, but had no way to stop it early. If traffic
generation failed partway through (e.g. `CalledProcessError` from a dead
port-forward tunnel, §11), the exception propagated immediately while
that background thread kept polling the Kubernetes API for the
*remainder* of `duration_seconds` — orphaned, silently, with nothing
waiting on it.

**Fix:** `ReplicaSampler.sample_for()` gained an optional `stop_event:
threading.Event | None = None` parameter (backward compatible — every
existing caller that doesn't pass it is unaffected); its poll loop now
exits early if the event is set. `run_experiment()` creates one
`threading.Event` per run, passes it to the sampler thread, and sets it
(then joins the thread with a bounded timeout) in every failure path —
both the existing cancellation path and a new general `except
Exception` handler around traffic generation. The happy path is
untouched: `stop_event` is never set on success, so the sampler still
runs its full natural `duration_seconds`.

The failed run's staging directory (`data/raw/<id>.inprogress/`) is
deliberately **not** deleted on this new general-failure path (only the
`RunCancelled`/dashboard-Stop path deletes it) — it's the only
diagnostic record of what a failed run actually did, and its
`.inprogress` suffix already excludes it from every glob that reads real
experiment data (`build_features.py`, `summarize_results.py`), so
keeping it around costs nothing and helps investigation.

**Verified:** unit-tested (`ReplicaSampler.sample_for`'s stop_event
behavior and its backward-compatible no-stop_event behavior,
`tests/feature_engineering/test_collect_metrics.py`) and integration
-tested (`run_experiment()` actually invokes the stop_event and returns
promptly instead of hanging for the configured duration on a simulated
traffic failure, `tests/experiments/test_run_experiment.py`). **Not
live-verified** — no real cluster run reproduced a mid-run traffic
failure this session to observe the orphaned thread being avoided in
practice.

### 12.3 Matrix-run summary — kept separate from provisional research results

`run_matrix.py` writes `data/experiments/matrix_runs/<run_id>.json`
(one new timestamped file per matrix run — never overwrites a previous
run's summary) recording, per config: name, config file, PASS/FAILED
status, start/end timestamps, failure stage, exception type/message
(and traceback for unexpected errors), whether traffic had started, the
run's output directory, and its `reset:` config block. This location is
deliberately **not** `results/` (the provisional research results
directory) and not `data/features/`/`data/raw/<id>/` (the actual
experiment data directories) — a failed experiment's record lives
alongside `data/experiments/<id>/metadata.json` conceptually but can
never be mistaken for one (no `metadata.json` is ever written for a
failed run — `run_experiment()` only writes that file after every
prior step, including the "commit point" rename, has already
succeeded).

A failed `MatrixEntryResult` carries no `n_feature_rows` and no path
that any training/dataset-assembly script (`summarize_results.py`)
globs — it is structurally impossible for a failed run to be picked up
as a research sample without a deliberate, separate code change
elsewhere, which this session did not make.

`run_matrix.py`'s process exit code is `1` if any experiment failed
(visible to whatever invokes it — cron, a human, CI) even though the
matrix itself completed every config; `0` only if every config passed.

**Verified:** unit-tested only
(`tests/experiments/test_run_matrix.py` — 14 tests covering all-pass,
one-failure-then-continue, multiple-failures-then-continue,
known-vs-unexpected-error classification, KeyboardInterrupt/SystemExit
propagation without swallowing, and the summary file's PASS/FAILED
distinction and never-overwrite-a-previous-run property). **Not
live-verified** — no real matrix run was executed this session, per
this session's explicit "do not run the full experiment matrix"
instruction; a mocked failure-injection approach was used throughout
instead, as instructed.

### 12.4 `run_interleaved_experiment.py` had the same class of gap — worse

A follow-up session inspected this file specifically (not assumed to be
fixed by §12.2's `run_experiment.py` change) and found a genuinely worse
version of the same problem: its traffic-generation loop (one blocking
`subprocess.run(cmd, check=True)` per phase) had **no exception handling
at all** — not even the cancellation-path cleanup `run_experiment.py`
had before §12.2. A failed phase propagated a `CalledProcessError`
immediately, leaving the background `ReplicaSampler` thread polling the
Kubernetes API for the rest of `total_duration` with zero cleanup of any
kind.

**Fix:** the phase loop is now wrapped in `try/except Exception:`
mirroring `run_experiment.py`'s pattern — `stop_event.set()` and a
bounded `sampler_thread.join()` before re-raising — adapted to this
file's actual phase-loop shape rather than copy-pasted. No cancellation
support was added (this file still has no `cancel_event`/`RunCancelled`
concept — a separate, pre-existing limitation, out of scope here). The
happy path (`sampler_thread.join()` after the loop completes normally)
is unchanged.

**Verified:** unit/integration-tested
(`tests/experiments/test_run_interleaved_experiment.py`) — a simulated
phase-2-of-2 failure with a deliberately large `total_duration` (50s)
returns in well under 5s instead of hanging for the full duration, and a
full happy-path run (both phases succeeding, real minimal Prometheus/
sampler data flowing through feature building) completes normally with
the fix in place, proving no regression. **Not live-verified** this
session — see §13 for what *was* live-verified.

## 13. Live matrix smoke test — real PASS → FAILED → PASS on the actual cluster

A follow-up session ran the real `experiments/run_matrix.py` CLI (not a
mock) against a real k3d cluster, with three deliberately small,
non-research configs (`SMOKE_A_PASS`, `SMOKE_B_FAIL` — a nonexistent
`scenario_file`, `SMOKE_C_PASS`), features routed to an isolated
`data/features/smoke_test_matrix/` directory via a new
`run_matrix.py --output-features-dir` flag (added this session,
mirroring `run_experiment.py`'s existing one, specifically so this test
run could never land in the main dataset directory).

**Real, observed result** (`data/experiments/matrix_runs/
20260917T051516Z.json`, read directly, not inferred from console output):

- `SMOKE_A_PASS`: real `RESETTING → WAITING → VERIFYING` sequence,
  fought 69 rounds of drift against a stale HPA recommendation of 4
  replicas, then `STABILIZED`, then real traffic, then **PASS** (3
  feature rows).
- `SMOKE_B_FAIL`: its own completely independent reset — fought a
  *different* residual value (2 replicas, left over from `SMOKE_A_PASS`'s
  own traffic-driven scale-up) for 64 rounds before stabilizing — proving
  this was a genuine fresh isolation attempt, not reused state. Traffic
  generation then failed immediately and predictably
  (`subprocess.CalledProcessError`, `traffic/run_scenario.py` failing to
  read the nonexistent scenario file) — recorded `failure_stage:
  "traffic_generation"`, `traffic_started: true`. **The matrix
  continued.**
- `SMOKE_C_PASS`: ran immediately after the failure, performed its own
  fresh `RESETTING → WAITING → VERIFYING → STABILIZED` (this time with
  no drift at all), then real traffic, then **PASS** (3 feature rows).

**Data safety, directly verified (not assumed):**
- `results/models/cascade_lightgbm.joblib` and every `results/metrics/
  *.json` file: mtimes unchanged (Sep 1) — confirmed untouched.
- `data/experiments/SMOKE_B_FAIL/` does not exist at all — no
  `metadata.json` was ever written for the failed run (`run_experiment()`
  only writes it after the atomic "commit" rename, which a failed run
  never reaches) — structurally impossible for it to be picked up as a
  research sample.
- `data/raw/SMOKE_B_FAIL.inprogress/` also does not exist — in this
  specific failure mode, the failure happens inside `run_scenario.py`
  before it ever creates its output directory, so there was no partial
  telemetry to preserve as diagnostic output this time (a different
  failure mode, e.g. Locust dying mid-run, would leave a `.inprogress`
  directory behind, per §12.2's design — just not this one).
  `data/raw/SMOKE_A_PASS/` and `data/raw/SMOKE_C_PASS/` exist as normal,
  fully-promoted (non-`.inprogress`) directories.
  `data/features/smoke_test_matrix/` contains exactly
  `SMOKE_A_PASS.csv`/`SMOKE_C_PASS.csv` — no entry for `SMOKE_B_FAIL`,
  and the main `data/features/*.csv` directory contains zero `SMOKE_*`
  files.
- Every pre-existing provisional experiment (`EDOS_001` spot-checked
  directly) is untouched.
- No `webapp/`/dashboard file was modified by this session (the ones
  showing as modified in `git status` are unrelated, pre-existing
  uncommitted work from before this entire methodology-correction
  effort began).

**What this smoke test does NOT newly demonstrate:** the chosen failure
mode (bad scenario file) fails at the *traffic-generation* stage, after
isolation already succeeded — it does not exercise "isolation itself
fails and no traffic starts" live in this session (that specific
property was live-verified in an earlier session's HPA-contention test,
§10.5.1, and is covered by unit tests here). It also doesn't rigorously
stress-test the sampler-thread stop_event's time-saving benefit live,
since `SMOKE_B_FAIL`'s `duration_seconds` (10s) was short enough that
even without the fix, the orphaned thread would have been mostly
harmless — that benefit is demonstrated with a deliberately large
duration in the mocked integration tests (§12.2), not live here.

**Live verification level:** real k3d/k3s cluster, real HPA, real
Prometheus, real traffic (Locust), real `run_matrix.py` CLI process —
not mocked, not a dry run.

---

## 14. FINAL EXPERIMENT MATRIX

Produced by a dedicated research-methodology design session (not a data-
collection session — no experiment was run, no model was trained, no
historical data was regenerated or deleted). The machine-readable
manifest is `experiments/final_matrix.yaml`; this section is its prose
companion. Read `experiments/final_matrix.yaml` for the authoritative,
field-by-field version — this section summarizes it and records the
design decisions/changes made to get there.

### 14.1 Scope and non-claims

`experiments/final_matrix.yaml` is a **design document**, not a results
record. Its own `manifest.status` is `DESIGN_FINALIZED_NOT_EXECUTED` and
it carries an explicit `explicit_non_claims` list (no O1-O4 claimed, no
H1/H0/H2 tested, nothing in it re-runs or supersedes the provisional data
already discussed in §5-§13 above). `tests/experiments/test_final_matrix.py`
enforces several of these properties mechanically (e.g. that no
"contaminated" entry lacks an explanatory note, that every concrete
config/scenario file it references actually exists on disk).

### 14.2 Configuration discrepancies fixed this session

Two stale EDoS weight configurations were found and fixed — both were the
SAME deterministic endpoint-availability shortcut already identified and
fixed in `traffic/scenarios/edos.yaml` by an earlier session
(`docs/research_gap_audit.md` Part 4), just not propagated everywhere:

1. **`traffic/scenarios/mixed.yaml`'s embedded `edos:` block.** Was
   `weights: {generate_report: 10, checkout: 0}` — no `home`/`search` key
   at all, meaning `MIX_001`'s EDoS component had a structurally
   guaranteed zero probability of a home/search/converting request, the
   exact shortcut pattern `edos.yaml` itself was fixed to avoid. Fixed to
   match `edos.yaml`'s current weights exactly
   (`generate_report:18, home:1, search:1, checkout:1`). **Not intended to
   retroactively validate existing `MIX_001` data** — the already-collected
   `data/experiments/MIX_001` / `data/features/held_out/MIX_001.csv` were
   generated under the OLD weights and remain provisional; a clean re-run
   is required before citing `MIX_001` as evidence of the fixed behaviour
   (recorded as `data_status: LIVE_DATA_EXISTS_PRE_FIX_STALE` in
   `final_matrix.yaml`).
2. **`webapp/backend/scenario_builder.py::build_attack_config()`'s
   hardcoded weights dict.** This function is the actual source of every
   `ADHOC_ATTACK_*` config the webapp's Attack Simulator generates — it
   still hardcoded `{"generate_report": 10, "checkout": 0}`, so every
   NEW ad-hoc attack run generated through the dashboard would silently
   keep reproducing the pre-fix shortcut even after `edos.yaml` itself was
   corrected. Fixed to the same weights as `edos.yaml`. The two EXISTING
   historical `ADHOC_ATTACK_*` snapshot files under
   `experiments/configs/generated/` and `traffic/scenarios/generated/`
   were deliberately **left unmodified** — they are timestamped records of
   demo runs that were actually executed under the old weights; editing
   them retroactively would misrepresent what was actually run, and they
   are explicitly out of scope for "final research use" (see
   `final_matrix.yaml`'s `excluded_from_matrix` section). Only the
   generator was fixed, so future ad-hoc runs use the corrected weights.

Configurations deliberately **NOT** changed, because they were not
inconsistent with the current EDoS design: `flash_crowd.yaml`,
`normal.yaml`, `flash_crowd_viral.yaml` (none reference EDoS weights at
all — the "generate_report defaults to 0" behaviour in these is the
INTENDED pure-legitimate-browsing default, not a bug — see §14.5 below for
why that default itself still needs care in matched-pair design);
`webapp/backend/scenario_builder.py::build_flash_crowd_config()` (already
uses a sensible legitimate weight default with no `generate_report` key,
consistent with `flash_crowd.yaml`).

### 14.3 New infrastructure added this session

| Addition | File(s) | Category (final_matrix.yaml) |
|---|---|---|
| Stealth/below-threshold EDoS scenario + config | `traffic/scenarios/edos_stealth.yaml`, `experiments/configs/EDOS_STEALTH_001.yaml` | D |
| EDoS-first interleaved config | `experiments/configs/INTERLEAVED_EDOS_FIRST_001.yaml` | G |
| Matched-signature calibration search loop | `experiments/match_quality.py` (new functions, see §15) | E / F (mechanism only) |

No change was made to `experiments/run_interleaved_experiment.py` for the
EDoS-first config — its phase loop was already fully generic over phase
order (confirmed by direct inspection this session, not assumed from the
prior audit); only a new config was needed.

### 14.4 Categories A-I coverage

See `experiments/final_matrix.yaml` for the authoritative per-entry
detail. Summary:

- **A (legitimate flash crowd):** `FC_001/002/003`, `FC_VIRAL_001` —
  IMPLEMENTED, mixed data cleanliness (FC_002 contaminated).
- **B (standard EDoS):** `EDOS_001/002/003` — IMPLEMENTED, mixed data
  cleanliness (EDOS_002/003 contaminated).
- **C (hard-negative flash crowd):** `FC_HARDNEG_001` — config
  IMPLEMENTED, **no data collected yet** under this exact config (distinct
  from the separate, already-run `VALIDATION_FC_HARDNEG_001`).
- **D (stealth/below-threshold EDoS):** `EDOS_STEALTH_001` — new this
  session, PARTIALLY_IMPLEMENTED; the scenario/config exist and are
  runnable, but the calibrated rate-limiter threshold to compare against
  does not yet exist (**CALIBRATION REQUIRED** — see §16).
- **E / F (matched-signature flash crowd / EDoS):** no concrete
  experiment IDs — described as `MATCHED_SIGNATURE_PAIR_TEMPLATE`,
  PARTIALLY_IMPLEMENTED. The measurement primitives were already
  implemented and live-verified once (uncalibrated); the calibration
  search loop was implemented and unit-tested this session but never run
  against a live cluster (see §15).
- **G (interleaved/simultaneous):** `MIX_001` (simultaneous, data
  pre-fix-stale), `INTERLEAVED_001` (FC-first, contaminated),
  `INTERLEAVED_EDOS_FIRST_001` (EDoS-first, new this session, no data
  yet).
- **H (conventional baselines):** `baselines/rate_limiter.py`,
  `baselines/volumetric_detector.py` — IMPLEMENTED, already confirmed
  fairly evaluated against the same convention as CASCADE
  (`docs/research_gap_audit.md` Part 8).
- **I (normal/background):** `NORMAL_001` — IMPLEMENTED, clean data,
  context-only by design (never a training/test sample).

No experiment was invented merely to make this list look complete —
category D and E/F both explicitly record what is missing (a calibrated
threshold; a completed live calibration run) rather than presenting
infrastructure as validated evidence.

---

## 15. MATCHED-SIGNATURE EXPERIMENT DESIGN

### 15.1 What already existed vs. what this session added

`experiments/match_quality.py` already provided (from the earlier P0
methodology-correction session, `docs/research_gap_audit.md` Part 7):
`ExperimentSignature`, `compute_signature()`, `MatchTolerances`,
`compare_signatures()`, `MatchReport`, `save_match_report()`, and a
`CalibrationConfig` dataclass that was pure configuration with **no**
search loop behind it — confirmed by direct re-reading of the module this
session, not assumed from the prior audit.

This session added the search loop itself:
`CalibrationCandidateParams`, `apply_candidate_params()`,
`next_candidate_params()`, `CalibrationAttempt`, `CalibrationResult`,
`calibrate_matched_pair()`, `save_calibration_report()` — all unit-tested
(`tests/experiments/test_match_quality.py`, 26 tests total for the
module) with a **fake** `run_candidate` callable; no live cluster was
used and no live calibration campaign was executed, per this session's
explicit constraint.

### 15.2 Traffic features vs. scaling/cost signature — explicitly separated

`ExperimentSignature` already separated these correctly (verified, not
just trusted): `request_rate` (a TRAFFIC feature) is recorded and reported
in every comparison, but is **not** one of the three axes that gate
`match_status`. `PRIMARY_MATCH_AXES = ("peak_replica_count",
"mean_replica_count", "total_cost")` is the actual gate — all
SCALING/COST quantities, confirmed unchanged by this session (this
session added the search loop around the existing gate, not a new gate).
`cost_per_request` and `cpu` are recorded (comparison + tolerance) but
also not gating, consistent with the same reasoning: they are useful
context, not the defining condition.

### 15.3 Tolerances — value, rationale, and status

All from the pre-existing `MatchTolerances` dataclass, unchanged this
session (re-verified, not modified, since altering them to make anything
"pass" would violate the explicit "do not choose tolerances because they
make existing experiments pass" instruction):

| Quantity | Tolerance | Type |
|---|---|---|
| `peak_replica_count` | 25% (relative) OR ±1 replica (absolute, whichever is more permissive) | Provisional calibration tolerance |
| `mean_replica_count` | 25% (relative) OR ±1 replica (absolute) | Provisional calibration tolerance |
| `total_cost` | 25% (relative) | Provisional calibration tolerance |
| `request_rate`, `cpu`, `cost_per_request`, `replica_minutes` | 25% (relative) each | Recorded only — not gating |

**Numerical rationale (unchanged from the prior session, re-stated here
for completeness):** derived from this project's own observed
same-scenario run-to-run noise — `FC_001` vs `FC_003` (identical scenario
config, differing only by Locust seed, both clean/uncontaminated runs)
showed ~5-6% deltas on `request_rate`/`estimated_cost`/
`mean_replica_count` from noise alone. 25% is roughly 4-5x that noise
floor.

**Engineering convenience vs. research justification, stated explicitly:**
the 25% figure is a **provisional calibration tolerance**, not a final
hypothesis-testing threshold. It is derived from exactly TWO clean runs
(`FC_001`/`FC_003`) — a defensible starting point, not a statistically
estimated noise floor (that would need the ≥10-repetitions-per-condition
data this manifest's `repetition_policy` calls for, from which a proper
variance estimate — and a tolerance derived from it, e.g. 3-4 standard
deviations of the observed metric — could replace this ad hoc multiplier).
The ±1 replica absolute tolerance is pure engineering necessity (a
percentage is undefined/unstable at small integers, e.g. 1 vs 2 replicas
= 100% "delta") and is not claimed to be anything more than that.
**This session's recommendation:** re-derive the primary-axis tolerances
from real repeated-run variance once ≥10 repetitions of at least one
condition exist, rather than continuing to rely on a 2-run noise estimate
for anything reported as a final result.

### 15.4 A statistically stronger alternative (proposed, not implemented)

A normalized, variance-aware alternative worth adopting once enough
repeated-run data exists: instead of a fixed percentage band, express
each axis's match criterion as a number of **standard deviations of that
axis's own same-scenario repeated-run distribution** (e.g. "matched if
within 2σ of the reference scenario's own observed variance on that
axis"), estimated from the ≥10-repetition data `repetition_policy` calls
for. This would let the tolerance adapt per-axis (cost may naturally vary
more or less than replica count) instead of using one flat 25% for every
quantity, and would let a "MATCHED" verdict carry an actual confidence
level. **Not implemented in this session** — it requires the repeated-run
data that does not yet exist; recorded here as the recommended next step
for `MatchTolerances`, not a silent replacement of the current values.

### 15.5 Calibration search — how it works, and its explicit boundaries

The loop (`calibrate_matched_pair()`) is: run a candidate → measure its
signature → compare to the reference → if matched, stop; if not, adjust
→ repeat, up to `CalibrationConfig.max_iterations` (default 5).

**Tunable parameters — deliberately narrow, and why:** only `users` and
`report_complexity` (an EDoS candidate's user count and per-request
report complexity). These are the two knobs `CalibrationConfig` already
declared step sizes for, and both have an understood, monotonic-ish
relationship to scaling/cost pressure (more users or more complexity →
more CPU → more scale-up pressure → more cost). Think-time, endpoint
weights, and duration were deliberately **excluded** from the tunable
set: think-time and weights would change EDoS's *behavioural* signature
(exactly the axis §14.2/§9 below warns must remain a measured, not
scripted, difference), and duration must stay fixed to the reference
run's duration for a meaningful replica-minute/cost comparison in the
first place, not searched over.

**Bounded, and honestly reports exhaustion:** `next_candidate_params()`
clips `users`/`report_complexity` to a safe range (default `[1, 50]` /
`[1, 100]`) so the search can never silently turn an "EDoS" candidate
into a flash-crowd-sized swarm just to force a numeric match. If clipping
produces no further change, or `max_iterations` is reached, the search
returns `EXHAUSTED_NO_PROGRESS` / `EXHAUSTED_MAX_ITERATIONS` — it never
fabricates a `MATCHED` result (unit-tested directly:
`test_calibrate_matched_pair_never_fabricates_a_match`).

**Independent of the ML model, by construction:** `match_quality.py`
imports nothing from `models/`; the search operates only on
`ExperimentSignature`'s seven pre-declared scaling/cost/traffic
quantities, computed directly from raw telemetry — never on a trained
classifier's predictions, probabilities, or SHAP output. It cannot
optimize toward "what the model finds easy to classify" even
accidentally, because it never sees the model.

**What running this loop for real would require** (not done this
session): a `run_candidate` implementation that (1) calls
`apply_candidate_params()` to build a candidate scenario dict, (2) writes
it to `traffic/scenarios/generated/` and a matching experiment config
(mirroring `webapp/backend/scenario_builder.py`'s existing pattern), (3)
runs it through `experiments/run_experiment.py` against a real cluster,
(4) reads back `data/raw/<id>/timeseries.csv`, and (5) returns
`compute_signature()` of that data. This glue is intentionally not
written as a standalone script in this session — writing it without
running it would be untested and unverifiable; running it would violate
the "do not execute a long/full calibration campaign" constraint.

### 15.6 Persisted calibration report — required fields, all present

`save_calibration_report()` writes
`data/experiments/<candidate_id_prefix>/calibration_report.json`
containing, per the Phase 4 requirement: flash-crowd (reference) and
EDoS (candidate) experiment IDs, request-rate/CPU/mean-replica/
peak-replica/replica-minute/total-cost/cost-per-request comparisons (via
each attempt's embedded `match_report`), the tolerance used for each
quantity, absolute differences (`absolute_differences`, computed
independently of the percentage deltas so they remain meaningful even
when a percentage is undefined), normalized (percentage) differences,
final MATCHED/NOT_MATCHED/EXHAUSTED status, the calibration parameters
tried at every iteration, and seed information (`CalibrationCandidateParams.seed`,
carried through but never itself adjusted by the search).

---

## 16. STEALTH EDoS — CALIBRATION REQUIRED

`traffic/scenarios/edos_stealth.yaml` / `experiments/configs/EDOS_STEALTH_001.yaml`
(new this session) provide a candidate EDoS profile tuned toward a lower
request rate than `edos.yaml` on two independent dimensions: fewer users
(8 → 3) and longer think-time (0.05-0.2s → 0.5-1.5s), while keeping
`report_complexity` and the (already-fixed) endpoint weight distribution
unchanged from `edos.yaml`.

**What this is NOT:** a validated "EDoS successfully evades the
rate-limiter" result. `baselines/rate_limiter.py::calibrate_threshold()`
computes its threshold as a percentile (default 95th, configurable) of
REAL, legitimate (label=0) `request_rate` — the threshold is **not** a
fixed number this project can hardcode, and re-verified this session:
`experiments/summarize_results.py` calls it on
`train_df.loc[train_df["label"]==0, "request_rate"]` from whatever
flash-crowd/normal data is in the training split. **No currently
-collected flash-crowd dataset is simultaneously (a) free of the
HPA-carryover contamination and (b) collected under the corrected
`weighted_task_list()` generator fix** — computing "the threshold" from
today's data would itself be invalid, so this session explicitly declines
to invent or guess a number.

**CALIBRATION REQUIRED, blocking:** before `EDOS_STEALTH_001` (or any
stealth-EDoS claim) can be reported as validated, a clean flash-crowd/
normal baseline dataset must exist, `calibrate_threshold()` must be run
against it to produce a real number, and `EDOS_STEALTH_001` must actually
be run and its observed `request_rate` compared against that number. None
of this is done in this session. `experiments/final_matrix.yaml`'s
`EDOS_STEALTH_001` entry carries this as an explicit
`calibration_required: {blocking: true}` field rather than a silent
assumption.

---

## 17. INTERLEAVED EXPERIMENTS — DIRECTION COVERAGE

Re-inspected `experiments/run_interleaved_experiment.py` directly this
session (not assumed from the prior audit): its phase loop
(`for i, phase in enumerate(phases): ...`) and `label_for_timestamp()`
are both fully generic over the `phases` list's order and length — there
is no code-level assumption about which `scenario_type` comes first.
`docs/research_gap_audit.md`'s Part 6 finding that "EDoS-first
interleaving... is NOT SUPPORTED as a distinct config" was accurate about
the CONFIG, not the runner. This session therefore added exactly one new
config, `experiments/configs/INTERLEAVED_EDOS_FIRST_001.yaml` (phases
EDoS → FC → EDoS → FC, mirroring `INTERLEAVED_001`'s FC → EDoS → FC →
EDoS structure with the opposite starting phase, distinct seed 47), and
made **no change** to `run_interleaved_experiment.py` itself — per the
"do not redesign the interleaved architecture" instruction, none was
needed.

Both directions are now IMPLEMENTED at the config level; neither has been
run (`INTERLEAVED_001` has contaminated data requiring a clean re-run;
`INTERLEAVED_EDOS_FIRST_001` has no data yet at all).

---

## 18. REPETITION / STATISTICAL DESIGN

### 18.1 Repetition recommendation

See `experiments/final_matrix.yaml`'s `repetition_policy` block for the
machine-readable version. Recommendation:

- **Minimum floor per condition: 5.** Below this, no distributional claim
  (mean/std/CI) is meaningful — this is a hard floor for "can we say
  anything statistical at all", not a target.
- **Target for confirmatory claims per condition: 10.** A paired
  non-parametric test (Wilcoxon signed-rank — see §18.3 for why
  non-parametric is the safer default) has limited power below roughly
  8-10 pairs at conventional α=0.05. 10 is the smallest number this
  project considers adequate to report a CASCADE-vs-baseline comparison
  as confirmatory rather than illustrative.
- **Existing project anchor, not a substitute:** `webapp/backend/config.py`'s
  `PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD = 20` is the dashboard's own
  pre-existing bar for TOTAL experiment count before any hypothesis
  verdict leaves `INSUFFICIENT_DATA`. This is a total-dataset-size
  heuristic, not a per-condition power calculation, but a matrix with
  ≥10 repetitions across each of (FC, EDoS, matched-FC, matched-EDoS)
  already clears 20 total experiments before baselines/interleaved/
  stealth conditions are even counted — the two figures are compatible.

**Trade-off, stated explicitly:** at this project's current scale
(~75-90s traffic generation + a mandatory isolation/reset step that can
itself take 30s-330s+ per `docs/experiment_protocol.md` §10.5.1's live
observations), a single experiment realistically costs several minutes
of wall-clock time, not counting Prometheus/feature-extraction overhead.
10 repetitions × 4 primary conditions (FC, EDoS, matched-FC,
matched-EDoS) alone is 40 runs; a full matrix including hard-negative,
stealth, and both interleaved directions at even the 5-repetition floor
adds substantially more. This is a genuine, acknowledged constraint, not
one this session resolves — the recommendation is the target number
research validity requires, with the wall-clock cost stated honestly
rather than quietly using a smaller number for convenience.

### 18.2 What the seed does and does not control

See `experiments/final_matrix.yaml`'s `repetition_policy.what_the_seed_controls`
for the full statement. In brief: the `seed:` field controls Locust's own
random number generator only (search-term choice, exact think-time draw
within its configured range, task-selection order among equal-weight
repeats). It does **not** control, and therefore does not by itself
establish independence with respect to: Kubernetes pod
scheduling/placement, HPA controller sync-loop timing relative to
traffic start, Prometheus scrape-interval alignment, Docker Desktop host
resource contention (directly observed causing variance in
§10.5's live validation), or port-forward timing variance.
`docs/research_gap_audit.md`'s own contamination finding — `FC_002`
inheriting a prior run's replica count despite having its own distinct
seed — is direct, already-collected evidence that seed variation alone
does not achieve run-to-run independence. The mandatory
`ReplicaResetter` isolation step is what makes repeated runs independent
with respect to *starting state*; it does not, and cannot, control the
environmental variability listed above. Repetition (not seed-changing) is
the only way to average over that remaining variability.

### 18.3 Statistical analysis plan (documented, NOT implemented this session)

Per the explicit instruction to document rather than implement:

- **Independent experimental unit:** one complete experiment RUN
  (`experiment_id`), not a feature window — consistent with the existing,
  already-implemented `models/dataset.py` split-by-experiment convention.
  A matched PAIR (one FC run + one calibrated EDoS run) is the unit for
  any matched-signature-specific analysis.
- **Aggregation level:** per-run summary statistics (e.g. mean
  `cost_per_request` across that run's feature windows), not raw
  window-level rows, for any cross-run statistical comparison — window
  -level rows within one run are NOT independent observations of each
  other (temporal/window-level pseudoreplication — see below).
- **Primary metrics:** EDoS recall / TPR, flash-crowd FPR, detection
  latency, cost-before-detection, F1 — matching CLAUDE.md §23/§24's
  existing list; no new metric is proposed here.
- **Confidence interval approach:** for a metric estimated across ≥10
  repeated runs of one condition, a non-parametric bootstrap CI (resample
  runs with replacement, not window-level rows) over the per-run
  statistic — preferred over an assumed-normal CI given the small sample
  sizes this project will realistically have even at the "target" 10
  repetitions.
- **Effect-size approach:** for a paired CASCADE-vs-baseline comparison
  (same matched pairs, two detectors), report both the raw metric
  difference and a standardized effect size (e.g. matched-pairs rank
  -biserial correlation, the natural effect-size companion to a Wilcoxon
  signed-rank test) — not p-value alone.
- **Appropriate statistical comparisons:** a **paired** test, because
  CASCADE and each baseline are evaluated on the IDENTICAL held-out
  windows/runs (already true today — confirmed by re-reading
  `models/evaluate.py`/`baselines/*.py`'s shared `detection_latency`/
  `cost_before_detection` convention this session). Test choice
  (Wilcoxon signed-rank vs. paired t-test) should be decided AFTER
  checking the paired differences' distribution (e.g. a normality check
  or simply inspecting n≤20 paired differences directly, since formal
  normality tests are themselves underpowered at this scale) — Wilcoxon
  is the safer default absent a clear case for normality, not chosen
  reflexively.
- **Handling of failed experiments:** excluded entirely from any
  statistical aggregation, never imputed or treated as a zero/missing
  -data-point substitute — consistent with `run_matrix.py`'s existing
  design (a `FAILED` `MatrixEntryResult` carries no `features_path`/
  `n_feature_rows` and is structurally impossible for a training/analysis
  script to pick up).
- **Handling of contaminated experiments:** excluded from any reported
  statistical result (not merely down-weighted) until re-run cleanly —
  matches this document's own existing convention for `FC_002`/
  `EDOS_002`/`EDOS_003`/`INTERLEAVED_001`.
- **Handling of missing telemetry:** a run with `validation.ok == false`
  (per `feature_engineering/validate_features.py`'s existing report) is
  excluded from statistical aggregation, same as a failed run — never
  silently forward-filled or imputed into a summary statistic.
- **Treatment of matched pairs:** analyzed as PAIRS, not as two
  independent samples — the whole point of matching is to remove
  volume/scaling/cost as a confound, which is only valid if the paired
  structure is preserved in the analysis (an unpaired test across all FC
  runs vs. all EDoS runs would throw away exactly the information
  matching was designed to control for).
- **Treatment of repeated runs:** averaged (or otherwise summarized) to
  ONE value per run before any cross-condition comparison — see
  aggregation level above — never pooled at the window level across runs
  as if each window were an independent repeat of the condition.
- **Prevention of temporal/window-level pseudoreplication:** a single
  experiment run produces multiple overlapping-or-adjacent feature
  windows (`detector.window_seconds`/`step_seconds`) that are NOT
  independent of each other (adjacent windows share most of their
  underlying raw samples by construction). Any statistical test must
  operate on per-RUN summaries (or explicitly model the within-run
  correlation, e.g. a mixed-effects approach) — never treat N windows
  from one run as N independent observations. This is the same principle
  `models/dataset.py`'s existing experiment-level train/test split
  already applies to the ML pipeline; this section extends it explicitly
  to the statistical-comparison layer, which does not yet exist in code.

**Assumptions requiring a check before test selection:** paired-difference
normality (informing t-test vs. Wilcoxon — see above); independence of
runs within a condition (requires the isolation step in §10.1/§11.1 to
have actually succeeded for every run used); homogeneity of variance
across conditions if any test assuming it were ever used (not currently
planned — Wilcoxon does not require it, which is part of why it is the
recommended default).

**Not implemented in this session:** no bootstrap/CI/effect-size code
was written; no statistical test was run; this section is a plan, to be
implemented once ≥5 (floor) or ≥10 (target) clean repetitions of at
least one condition exist.

---

## 19. FEATURE VALIDITY / LEAKAGE AUDIT (re-verified against current source)

Re-read `feature_engineering/behaviour_features.py`,
`traffic/generators/edos.py`, `traffic/generators/flash_crowd.py`, and
every current scenario YAML directly this session (not assumed from
`docs/research_gap_audit.md`, though the conclusions below are largely
consistent with it where the underlying source hadn't changed).

**Safe — no deterministic label dependency found:**
`request_rate`/`request_count`/`peak_request_rate`/etc. (`traffic_features.py`),
all of `cost_features.py`, all of `scaling_features.py` — every one of
these is computed purely from the observed `replica_count`/
`cpu_utilization_pct`/`request_count`/`error_count` time series, with no
dependency on which scenario generated the traffic. Their VALIDITY still
depends on clean (non-contaminated) telemetry — a data-quality problem
(§10 above), not a feature-design leakage problem.

**Needs caution — proxy limitation, not deterministic leakage:**
`unique_client_ratio`/`requests_per_session` (`behaviour_features.py`)
are built from the `active_sessions` gauge as a stand-in for true
client-identity, not verified against real distinct actors (the app
deliberately never tracks client IPs — CLAUDE.md §7). Already documented
in `docs/feature_dictionary.md`; re-confirmed unchanged this session.

**Now genuinely measured, not scripted (fixed by an earlier session, re
-confirmed by this one):** `search_ratio` / `cheap_endpoint_ratio` /
`conversion_rate` on the EDoS side. `edos.yaml`'s current weights
(`generate_report:18, home:1, search:1, checkout:1`) give `EdosUser` a
real, non-zero (~4.5% each) chance of a home/search/checkout request —
confirmed by direct reading of both the scenario YAML and
`traffic/generators/edos.py` this session. These features can now differ
from a true 0 for EDoS windows; whether they remain STATISTICALLY
different from flash-crowd's ~33-55% rates once real (post-fix,
uncontaminated) data is collected is an empirical question this session
does not answer, since no such data has been collected.

**Still a structural (deterministic) zero on the FLASH-CROWD side —
identified fresh this session, not previously stated this precisely:**
`expensive_endpoint_ratio` / `report_generation_ratio` are EXACTLY 0 for
every window of `FC_001/002/003`, `FC_VIRAL_001`, and `NORMAL_001`,
because `flash_crowd.py`'s `weights.get("generate_report", 0)` defaults
to 0 and none of those scenario YAMLs set it — confirmed by reading both
the generator and every default scenario file this session. This is the
MIRROR IMAGE of the already-fixed EDoS-side shortcut: if the DEFAULT
flash-crowd scenarios are the only label=0 data in a training set, a
classifier could trivially learn "expensive_endpoint_ratio > 0 → EDoS"
using a structural boundary, not a measured tendency — indistinguishable
in outcome from the exact bug already fixed on the EDoS side, just
sitting on the other class. **`FC_HARDNEG_001` (category C) exists
precisely to prevent this** — it gives flash-crowd traffic a real,
non-zero (~10%), legitimately-minority chance of the same endpoint.
**The catch, found by this session's analysis (see §15's
`leakage_caution` in `final_matrix.yaml`):** `FC_HARDNEG_001` only
removes this shortcut if its data is actually INCLUDED in the training
set used for any given classifier/evaluation run — a run trained only on
`FC_001-003` (as the current persisted model was) still has the
structural-zero problem on the flash-crowd side, symmetric to the
already-documented EDoS-side finding.

**Does the proposed matched-signature design address this?**
**Partially, and only if used correctly.** Matched-signature calibration
(§15) closes the O1 gap (comparable scaling/cost) but, by explicit
design, never touches endpoint weights — it cannot and does not close
this behavioural-shortcut gap on its own. A matched pair built from
`FC_001`/`FC_003` (default weights) as the reference would still let a
classifier separate on `expensive_endpoint_ratio` even with matched
scaling/cost, defeating the purpose of matching. **Recommendation,
recorded in `final_matrix.yaml`'s `leakage_caution` field:** matched
-signature reference runs should be drawn from `FC_HARDNEG_001`, not the
pure default `flash_crowd.yaml`, specifically so a matched-pair
experiment tests O1 without silently reopening O2. This is a design
recommendation for how the matrix should be USED, not a code change —
`calibrate_matched_pair()` is reference-signature-agnostic and correctly
leaves this choice to the caller.

**Latent, still-unexploited leakage vector (re-confirmed unchanged):**
the Prometheus `scenario` label exists on several metrics
(`app/src/metrics.py`) but `feature_engineering/collect_metrics.py`'s
`APP_METRIC_QUERIES` are all plain `sum(...)` with no `by (` grouping or
`scenario=` filter — re-verified directly by reading every query string
in that dict this session. Not currently exploited; still worth a
regression test asserting no future query introduces it, per the prior
audit's recommendation (not added this session — no code change to
`collect_metrics.py` was made).

**Models were not retrained and no SHAP was re-run this session** — this
section is a source-code-level audit, not a new empirical result.
