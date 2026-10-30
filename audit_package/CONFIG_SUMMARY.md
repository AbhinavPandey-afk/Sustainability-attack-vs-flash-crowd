# CASCADE — Experiment Configuration Summary (REGENERATED — synchronization check)

This document supersedes an earlier `CONFIG_SUMMARY.md` that was found to
be stale relative to the current working tree (it predated
`experiments/final_matrix.yaml`, the calibration-loop additions to
`experiments/match_quality.py`, the stealth-EDoS and EDoS-first-interleaved
configs, and the `mixed.yaml`/`scenario_builder.py` weight fixes). Every
field below is read directly from the source YAML/Python at package
-rebuild time — see `SOURCE_MANIFEST.txt` for the exact hashes this
corresponds to.

---

## Part A — Configs with a committed source YAML (`experiments/configs/`)

### EDOS_001 / EDOS_002 / EDOS_003

| Field | Value |
|---|---|
| Label | `1` (EDoS) |
| Scenario | `traffic/scenarios/edos.yaml` — `users:8, spawn_rate:8`, think time 0.05-0.2s |
| Weights | `generate_report:18, home:1, search:1, checkout:1` (~85.7/4.8/4.8/4.8%) |
| Duration | 75s each |
| Seed | 42 / 43 / 44 |
| Status | `EDOS_001` clean; `EDOS_002`/`EDOS_003` HPA-carryover CONTAMINATED (per `docs/research_gap_audit.md`, re-affirmed in `docs/experiment_protocol.md` §10.1 and `experiments/final_matrix.yaml`) |

### FC_001 / FC_002 / FC_003

| Field | Value |
|---|---|
| Label | `0` (flash crowd) |
| Scenario | `traffic/scenarios/flash_crowd.yaml` — `users:50, spawn_rate:10`, think time 0.3-1.5s |
| Weights | `home:3, search:5, checkout:1` |
| Duration | 75s each |
| Seed | 42 / 43 / 44 |
| Status | `FC_001`/`FC_003` clean; `FC_002` CONTAMINATED |

### FC_HARDNEG_001

| Field | Value |
|---|---|
| Label | `0` (flash crowd, hard-negative) |
| Scenario | `traffic/scenarios/flash_crowd_hard_negative.yaml` — `users:50, spawn_rate:10`, `report_complexity:30` |
| Weights | `home:3, search:5, checkout:1, generate_report:1` (~30/50/10/10%) |
| Duration | 75s |
| Seed | 42 |
| Status | **Config exists; NO run has been persisted to `data/experiments/FC_HARDNEG_001/`** — confirmed absent this session by direct directory check, not assumed. Distinct from `VALIDATION_FC_HARDNEG_001` (a separately-run, config-unlocatable live validation of similar behaviour). |

### FC_VIRAL_001

| Field | Value |
|---|---|
| Label | `0` (flash crowd, viral arrival shape) |
| Scenario | `traffic/scenarios/flash_crowd_viral.yaml` — trickle(5u/10s)→ramp(25s)→peak(50u/30s)→decay(25s to floor 10u), `spawn_rate:15` |
| Weights | `home:3, search:5, checkout:1` (same behaviour as FC_001, different arrival curve) |
| Duration | 90s |
| Seed | 42 |
| Status | Clean |

### INTERLEAVED_001

| Field | Value |
|---|---|
| Label | Per-phase: FC(0)→EDoS(1)→FC(0)→EDoS(1), 20s each, 80s total |
| Run via | `experiments/run_interleaved_experiment.py`, not `run_experiment.py` |
| Seed | 42 |
| Status | CONTAMINATED (replica_count flat at 8 for the entire run, all 4 phases) |

### INTERLEAVED_EDOS_FIRST_001 — **NEW, not in the prior audit_package**

| Field | Value |
|---|---|
| Label | Per-phase: **EDoS(1)→FC(0)→EDoS(1)→FC(0)**, 20s each, 80s total |
| Run via | `experiments/run_interleaved_experiment.py` — **no code change required**; the runner's phase loop was already generic over phase order, confirmed by direct inspection |
| Seed | 47 (distinct from `INTERLEAVED_001`'s 42) |
| Status | Config-only addition. **No data collected yet.** Added to give the interleaved-experiment category both transition directions (FC→EDoS and EDoS→FC), per `docs/experiment_protocol.md` §17. |

### MIX_001

| Field | Value |
|---|---|
| Label | `1` (attack present) for the entire run — simultaneous flash-crowd + EDoS |
| Scenario | `traffic/scenarios/mixed.yaml` — combined `users:58` (50 FC + 8 EDoS), `spawn_rate:18` |
| FC sub-block weights | `home:3, search:5, checkout:1` (unchanged) |
| EDoS sub-block weights | **`generate_report:18, home:1, search:1, checkout:1`** — **FIXED since the prior audit_package.** Previously `generate_report:10, checkout:0` (no home/search key at all) — the same deterministic endpoint-availability shortcut already fixed in `edos.yaml` itself, but not previously propagated to this file's embedded `edos:` block. Verified directly this session: current `traffic/scenarios/mixed.yaml` on disk has the corrected weights. |
| Duration | 75s |
| Seed | 42 |
| Status | Real data exists (`data/experiments/MIX_001`), but **that data was collected under the OLD (pre-fix) weights** — the scenario file has since changed underneath it. `experiments/final_matrix.yaml` records this as `data_status: LIVE_DATA_EXISTS_PRE_FIX_STALE`. A clean re-run under the current weights has NOT been performed. |

### NORMAL_001

| Field | Value |
|---|---|
| Label | `0` (placeholder; never used as training data) |
| Scenario | `traffic/scenarios/normal.yaml` — `users:10, spawn_rate:2`, think time 1.0-4.0s |
| Weights | `home:4, search:4, checkout:1` |
| Duration | 75s |
| Seed | 42 |
| Status | Clean; excluded from every training/PCA/SHAP glob by design |

### EDOS_STEALTH_001 — **NEW, not in the prior audit_package**

| Field | Value |
|---|---|
| Label | `1` (EDoS) |
| Scenario | `traffic/scenarios/edos_stealth.yaml` — `users:3, spawn_rate:3` (vs `edos.yaml`'s 8), think time **0.5-1.5s** (vs `edos.yaml`'s 0.05-0.2s) |
| Weights | `generate_report:18, home:1, search:1, checkout:1` — same distribution as `edos.yaml`; `report_complexity:60` unchanged |
| Duration | 75s |
| Seed | 46 |
| Purpose | Candidate "stealth" EDoS profile: fewer users AND longer think-time (both independently lower request rate) than `edos.yaml`, while keeping per-request cost pressure (`report_complexity`) and the endpoint-weight distribution unchanged. |
| Status | **`CALIBRATION REQUIRED`, blocking.** `baselines/rate_limiter.py::calibrate_threshold()` computes its threshold as a percentile of REAL legitimate `request_rate` from a training split — no currently-collected flash-crowd dataset is simultaneously uncontaminated AND collected under the corrected weighted-task-list generator fix, so the actual numeric threshold this scenario would need to clear is UNKNOWN. This scenario/config is infrastructure to support the experiment, not evidence that stealth EDoS has been validated. No data collected. |

---

## Part B — Generated / ad-hoc configs (`experiments/configs/generated/`, `traffic/scenarios/generated/`)

Runtime-generated by the webapp's Attack/Flash-Crowd Simulator
(`webapp/backend/scenario_builder.py`), not hand-authored research
configs.

### ADHOC_ATTACK_20260901T103629856Z / ADHOC_ATTACK_20260909T064827968Z

| Field | Value |
|---|---|
| Weights (as persisted in these two historical files) | `generate_report:10, checkout:0` — **the pre-fix deterministic-shortcut pattern**, no `home`/`search` key |
| Status | **Deliberately left unmodified this session** (and the prior one) — these are timestamped records of demo runs that were actually executed under the old weights; retroactively editing them would misrepresent history. Out of scope for "final research use". |

### `webapp/backend/scenario_builder.py::build_attack_config()` — the generator itself

**FIXED since the prior audit_package.** This function is the actual
source of every future `ADHOC_ATTACK_*` config. Verified directly this
session: its hardcoded weights dict now reads
`{"generate_report": 18, "home": 1, "search": 1, "checkout": 1}` (was
`{"generate_report": 10, "checkout": 0}`). Any NEW ad-hoc attack run
generated through the dashboard from this point forward will use the
corrected weights; the two existing historical snapshot files above are
unaffected by this fix (they are static files, not regenerated).

### ADHOC_FC_20260901T103733728Z

| Field | Value |
|---|---|
| Weights | `home:3, search:5, checkout:1` — same as `flash_crowd.yaml`'s default, no `generate_report` key |
| Status | Not stale — `build_flash_crowd_config()` was never inconsistent with the current design and was not modified |

---

## Part C — Experiments with real collected data but no locatable source config

**Unchanged since the prior audit_package** — re-verified this session,
not assumed:

### VALIDATION_EDOS_001 / VALIDATION_FC_001 / VALIDATION_FC_HARDNEG_001

`metadata.json`'s `config_file` field still points to a session-local
scratchpad/temp path not present in the repository. Label 1/0/0
respectively, seed 100 (all three), duration 60s each. `VALIDATION_EDOS_001`
additionally has a `match_report.json` (from `experiments/match_quality.py`,
result `NOT_MATCHED`, uncalibrated) — **this file exists in the working
tree but was NOT copied into this package**, since it is not literally
named `metadata.json` and this task's file list specifies exactly
`data/experiments/*/metadata.json`. Flagged here so its absence from the
package is not mistaken for an oversight.

### SMOKE_A_PASS / SMOKE_C_PASS (and the unrecorded SMOKE_B_FAIL)

CI/reliability smoke-test fixtures for `run_matrix.py`'s failure
-isolation logic (`docs/experiment_protocol.md` §13), not research
traffic. `data/experiments/matrix_runs/20260917T051516Z.json` records
`SMOKE_B_FAIL`'s outcome — also **not copied**, same reasoning as
`match_report.json` above (not literally named `metadata.json`).

### INTERLEAVED_HAPPY_TEST

**Not a research experiment** — `metadata.json`'s own `git_commit` field
is literally `"fakecommit"`; this is automated pytest fixture output
from `tests/experiments/test_run_interleaved_experiment.py`, incidentally
written into `data/experiments/`.

---

## Scope note on Part C exclusions (new this session)

The prior audit_package (built under a broader, differently-worded file
request) included `match_report.json` and the `matrix_runs/*.json`
summary as bonus context. **This session's request specifies the file
list precisely** ("Include every: `data/experiments/*/metadata.json`" /
"Do NOT include raw telemetry / features CSV / large generated
datasets"), and `match_report.json` / `matrix_runs/*.json` are neither
`metadata.json` nor explicitly requested — so this rebuild follows the
literal instruction and excludes them, rather than re-including the
prior session's broader interpretation silently. If broader inclusion is
wanted, say so explicitly and this package can be amended.

---

## Notes on cost model (applies to every config above)

Every committed config sets the same `cost_model` block
(`replica_cost_per_minute: 1.0`, `cpu_cost_weight: 0.0`,
`memory_cost_weight: 0.0`) and the same `replica_sampler`/`prometheus`
blocks as documented in the prior audit_package — unchanged this session,
re-verified by reading every config file directly.
