# CASCADE — Research Matrix Map (REGENERATED — synchronization check)

Supersedes an earlier `RESEARCH_MATRIX_MAP.md` that predated
`experiments/final_matrix.yaml` and the calibration-loop implementation
in `experiments/match_quality.py`. Every status below is re-verified
against the CURRENT working tree this session, not carried over from the
prior document. Where a status genuinely has not changed, it is restated
(not silently dropped); where it HAS changed, that is called out
explicitly.

---

## 0. The authoritative source is now `experiments/final_matrix.yaml`

As of this session, `experiments/final_matrix.yaml` **exists** (it did
not when the prior `RESEARCH_MATRIX_MAP.md` was written) and is the
project's own machine-readable final experiment matrix — covering
categories A-I, every entry's `status`/`data_status`/`objective_mapping`.
This document remains a useful prose companion and audit cross-check,
but `experiments/final_matrix.yaml` (included in this package) is now
the primary source of truth for matrix status; this document has been
re-derived to be consistent with it, not the other way around.

---

## 1. Terminology collision — unchanged, still applies

Same as previously documented: CLAUDE.md §13's E3="simultaneous",
E4="interleaved" vs. `docs/research_gap_audit.md` Part 6's own
E3="matched-signature", E4="hard-negative" numbering collide.
`docs/experiment_protocol.md` §10.4 resolves this by reserving "E3" for
CLAUDE.md's simultaneous-traffic meaning and calling the other concept
the "matched-signature pair" — this document follows that resolution.

---

## 2. Hypotheses (CLAUDE.md §2) — status unchanged, re-affirmed

H1/H0/H2 as before. **Current status: still NOT TESTABLE WITH VALID
EVIDENCE** — this has NOT changed since the prior map, and the new
calibration-loop code added this session does not change it either,
because that code has never been run against a live cluster. Building
the mechanism to test a hypothesis is not the same as having tested it;
`experiments/final_matrix.yaml`'s own `hypotheses.current_status` field
says this explicitly.

---

## 3. O1-O4 status — what has and has not changed

| Objective | Prior map's status | CURRENT status (this session) | What changed |
|---|---|---|---|
| **O1** (comparable cost/scaling signatures) | PARTIALLY IMPLEMENTED, NOT PROVEN — no mechanism *targets* a match | **PARTIALLY IMPLEMENTED, STILL NOT PROVEN** — a calibration SEARCH LOOP now exists (`experiments/match_quality.py::calibrate_matched_pair()`, `next_candidate_params()`, `apply_candidate_params()`), unit-tested, but has **never been executed against a live cluster**. No matched pair has ever actually been produced. | Mechanism completeness improved (measurement-only → measurement+search); empirical status unchanged (still zero real matched pairs) |
| **O2** (behavioural features beyond volume similarity) | PARTIALLY IMPLEMENTED, confounded by scripted shortcut | **Unchanged, PLUS a new finding**: the EDoS-side shortcut fix (`edos.yaml`'s weights) is confirmed still in place; a **mirror-image structural zero on the flash-crowd side** was newly identified this session's predecessor — `expensive_endpoint_ratio`/`report_generation_ratio` are exactly 0 for every default `flash_crowd.yaml`/`normal.yaml`/`FC_VIRAL_001` window (`flash_crowd.py`'s `weights.get("generate_report", 0)` default). `FC_HARDNEG_001` exists to fix this but **has no collected data**, so the fix is not yet realized in any dataset. | New finding carried forward, still unresolved empirically |
| **O3** (detector relies on cost/scaling, not volume) | IMPLEMENTED (mechanically), NOT PROVEN empirically | **Unchanged** — `models/feature_sets.py`'s 5-way ablation still exists and is unmodified this session (re-confirmed: this package's copy is byte-identical to what would be read from the current working tree; no ML code was touched in either session). Still not proven on clean, matched, non-shortcut data. | No change |
| **O4** (latency, cost-before-detection, TPR, FPR, separability) | PARTIALLY IMPLEMENTED — PCA/separability NOT IMPLEMENTED anywhere | **Unchanged** — no separability visualization code was added in either session (out of scope for the prior session's stated task; not part of this synchronization-check task either). Two new interleaved-direction data points (EDoS-first config) exist to support O4 analysis once run, but no data exists yet. | Infrastructure for O4 (EDoS-first interleaved config) added; PCA gap unchanged |

---

## 4. Matrix: CLAUDE.md §13's canonical E0-E7 → CURRENT implementation status

| Scenario | Prior status | CURRENT status | Change |
|---|---|---|---|
| E0 Normal | IMPLEMENTED, clean | **Unchanged** | none |
| E1 Flash crowd only | IMPLEMENTED; FC_002 contaminated | **Unchanged** | none |
| E2 EDoS only | IMPLEMENTED; EDOS_002/003 contaminated | **Unchanged** | none |
| E3 (CLAUDE.md) Simultaneous | IMPLEMENTED; `mixed.yaml`'s embedded EDoS weights found stale | **`mixed.yaml` weights FIXED this session's predecessor** (`generate_report:18,home:1,search:1,checkout:1`, was `10/0`, no home/search). Existing `MIX_001` data predates the fix — `data_status: LIVE_DATA_EXISTS_PRE_FIX_STALE` in `final_matrix.yaml`. | Config fixed; data still stale, unregenerated |
| E4 (CLAUDE.md) Interleaved | IMPLEMENTED (FC-first only); CONTAMINATED | **EDoS-first direction ADDED** (`INTERLEAVED_EDOS_FIRST_001.yaml`, seed 47) — confirmed the runner needed no code change (phase loop already order-generic). FC-first (`INTERLEAVED_001`) still CONTAMINATED; EDoS-first has no data yet. | New config; runner unchanged; no new data collected |
| E5 Volume-matched | NOT SUPPORTED as a dedicated, verified config | **Unchanged — still NOT SUPPORTED as a dedicated config.** (Note: this is distinct from "matched-signature", which targets scaling/cost, not volume — CLAUDE.md's E5 wants volume itself matched, which nothing in this project's design targets, by the research premise itself: EDoS is expected to use LESS volume for comparable impact.) | none |
| E6 Scaling-matched | Measurement tooling only; NO calibration search loop implemented | **CHANGED: the calibration search loop is now IMPLEMENTED** (`calibrate_matched_pair()` and its helpers) and unit-tested (`tests/experiments/test_match_quality.py`, 26 tests). **Still NOT EXECUTED live** — zero real matched pairs exist. `experiments/final_matrix.yaml`'s `MATCHED_SIGNATURE_PAIR_TEMPLATE` entry records this precisely: `status: PARTIALLY_IMPLEMENTED`, `mechanism_status.calibration_search_loop: IMPLEMENTED`, `data_status: NO_DATA`. | **Most significant status change in this map** — mechanism completed, still unvalidated |
| E7 Threshold-evasion | NOT SUPPORTED as a named experiment | **CHANGED: scenario/config infrastructure now exists** (`edos_stealth.yaml` / `EDOS_STEALTH_001.yaml`) but is explicitly marked `CALIBRATION REQUIRED, blocking: true` in `final_matrix.yaml` — the actual rate-limiter threshold to compare against is not known (depends on clean baseline data that doesn't yet exist). **Still NOT VALIDATED.** | Infrastructure added; empirical status unchanged (not evaded, not tested) |

---

## 5. Matrix: `docs/research_gap_audit.md` Part 6's own E-list (differently numbered)

| Audit concept | Prior status | CURRENT status |
|---|---|---|
| Matched-signature pair (audit's "E3") | Measurement tooling only | **Search loop now implemented** (same item as canonical E6 above) — see §4 |
| Hard-negative Flash Crowd (audit's "E4") | IMPLEMENTED, live-validated once (`VALIDATION_FC_HARDNEG_001`) | **Unchanged.** `FC_HARDNEG_001` (the official, non-validation config) still has no collected data — confirmed absent this session. |
| Stealth EDoS (audit's "E5") | NOT SUPPORTED | **Infrastructure now exists, CALIBRATION REQUIRED** — see §4's E7 row |
| Interleaved FC→EDoS→FC (audit's "E6") | IMPLEMENTED, CONTAMINATED | **Unchanged** |
| Interleaved EDoS→FC→EDoS (audit's "E7") | NOT SUPPORTED as a distinct config | **NOW SUPPORTED** — `INTERLEAVED_EDOS_FIRST_001.yaml` |

---

## 6. Per-run table — every entry, current status

| Run | Status (config/code) | Data status | Notes |
|---|---|---|---|
| `NORMAL_001` | IMPLEMENTED | Clean | Unchanged |
| `FC_001` | IMPLEMENTED | Clean | Unchanged |
| `FC_002` | IMPLEMENTED | CONTAMINATED | Unchanged |
| `FC_003` | IMPLEMENTED | Clean | Unchanged |
| `FC_VIRAL_001` | IMPLEMENTED | Clean | Unchanged |
| `FC_HARDNEG_001` | IMPLEMENTED (config) | **NO DATA — confirmed absent this session** | Unchanged from prior map; re-verified directly, not assumed |
| `EDOS_001` | IMPLEMENTED | Clean | Unchanged |
| `EDOS_002` | IMPLEMENTED | CONTAMINATED | Unchanged |
| `EDOS_003` | IMPLEMENTED | CONTAMINATED | Unchanged |
| `EDOS_STEALTH_001` | **NEW — PARTIALLY_IMPLEMENTED** | NO DATA | Config exists; threshold to compare against does not |
| `MATCHED_SIGNATURE_PAIR_TEMPLATE` | **NEW — PARTIALLY_IMPLEMENTED** (mechanism only) | NO DATA | Search loop implemented+tested; never run live |
| `MIX_001` | IMPLEMENTED; **scenario weights fixed this session's predecessor** | **PRE_FIX_STALE** (data predates the weight fix) | Not re-run |
| `INTERLEAVED_001` | IMPLEMENTED | CONTAMINATED | Unchanged |
| `INTERLEAVED_EDOS_FIRST_001` | **NEW — IMPLEMENTED (config only)** | NO DATA | Runner code unchanged; new config only |
| `VALIDATION_EDOS_001` / `VALIDATION_FC_001` / `VALIDATION_FC_HARDNEG_001` | IMPLEMENTED (data exists); source config not locatable | Live-validated | Unchanged |
| `SMOKE_*` / `INTERLEAVED_HAPPY_TEST` | N/A — fixtures, not research data | N/A | Unchanged |
| `ADHOC_ATTACK_*` / `ADHOC_FC_*` (historical files) | Pre-fix weights, left unmodified (historical record) | N/A | Unchanged; **the GENERATOR (`scenario_builder.py`) that produces new ones was fixed**, so future ad-hoc runs differ from these historical snapshots |

---

## 7. Discrepancy re-confirmed from the prior map

`FC_HARDNEG_001`'s config exists but no corresponding
`data/experiments/FC_HARDNEG_001/metadata.json` exists. This was true
when the prior `RESEARCH_MATRIX_MAP.md` was written and remains true now
— checked directly this session via a fresh `find` over
`data/experiments/`, not inferred from any earlier document. No new
discrepancy of this kind was introduced by the intervening work.

---

## 8. Summary — what changed between the two package builds, in one place

1. `experiments/final_matrix.yaml` created (did not exist before).
2. `experiments/match_quality.py` gained a full calibration search loop
   (`CalibrationCandidateParams`, `apply_candidate_params`,
   `next_candidate_params`, `CalibrationAttempt`, `CalibrationResult`,
   `calibrate_matched_pair`, `save_calibration_report`) — all present,
   all unit-tested, **none executed live**.
3. `traffic/scenarios/mixed.yaml`'s embedded EDoS weights fixed (stale →
   consistent with `edos.yaml`).
4. `webapp/backend/scenario_builder.py::build_attack_config()`'s
   hardcoded weights fixed (same fix, at its actual root cause).
5. `traffic/scenarios/edos_stealth.yaml` + `experiments/configs/EDOS_STEALTH_001.yaml`
   created (stealth EDoS infrastructure, calibration-required).
6. `experiments/configs/INTERLEAVED_EDOS_FIRST_001.yaml` created
   (EDoS-first interleaved direction).
7. `docs/experiment_protocol.md` extended with 6 new sections (§14-§19).
8. New test files/tests added: `tests/experiments/test_final_matrix.py`
   (new file), 18 new tests in `tests/experiments/test_match_quality.py`,
   plus additions in `test_run_interleaved_experiment.py` and
   `tests/traffic/test_scenarios.py`.

**What did NOT change:** no experiment was run, no model was trained, no
data under `data/raw/`, `data/features/`, or `results/` was regenerated
or deleted, and none of the underlying contamination/shortcut findings
from `docs/research_gap_audit.md` were resolved by data — only by
INFRASTRUCTURE that, if run, could eventually resolve them.

---

## 9. Bottom line

Nothing in O1-O4/H1/H0/H2's empirical status has changed — this
regenerated map does not claim otherwise. What changed is exclusively
INFRASTRUCTURE READINESS: the matched-signature search loop, stealth-EDoS
scaffolding, and EDoS-first interleaved config all moved from
"not implemented" or "measurement-only" to "implemented and unit-tested,
awaiting a live run." The prior session's own final report already
correctly concluded `FINAL RESEARCH MATRIX READINESS: NOT READY` for
exactly this reason, and that conclusion is unchanged by anything
verified in this synchronization check.
