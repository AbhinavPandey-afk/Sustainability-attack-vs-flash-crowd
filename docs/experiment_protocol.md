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
