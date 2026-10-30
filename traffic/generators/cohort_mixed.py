"""Second-generation ("Gen2") hard-negative flash crowd: TWO legitimate
(label=0) cohorts running concurrently in one Locust process, at different
population shares and different behaviour weights — approved design
(research-design review session, see docs/experiment_protocol.md's Gen2
section). Both cohorts are `flash_crowd.build_user_class` instances; this
module only composes them, exactly mirroring the population-weighting
mechanism `mixed.py` already uses for FC+EDoS (Locust's per-class `.weight`
class attribute controls what share of `--users N` each class receives).

Unlike `mixed.py`, both classes here are legitimate flash-crowd traffic
(label=0) — a majority "casual browsing" cohort with zero report-viewing
probability (byte-for-byte the existing `flash_crowd.yaml` defaults) and a
minority "engaged/returning-customer" cohort with a real, bounded, non-zero
chance of viewing the (expensive) personalized report, at a configurable
per-cohort report_complexity. The purpose is to raise the AGGREGATE
population-wide expensive_endpoint_ratio (and, via the resulting CPU load,
cost/scaling pressure) further than the first-generation hard-negative
(traffic/scenarios/flash_crowd_hard_negative.yaml) achieved, while keeping
the majority of simulated traffic identical to plain, already-validated
flash-crowd behaviour.

Each cohort gets a distinct `X-Scenario` header value (scenario["name"]
suffixed with the cohort key) so the two cohorts' requests are
independently distinguishable via Prometheus's existing (already-present,
currently-unqueried-by-the-feature-pipeline) `scenario` label — this is
used ONLY for the one-off, post-hoc cohort-verification check this design
requires (docs/experiment_protocol.md's Gen2 Phase 3); it does not change
`feature_engineering/collect_metrics.py`'s queries, which remain
un-grouped `sum(...)` aggregations exactly as before, so the training
feature pipeline is completely unaffected by this addition.
"""
from __future__ import annotations

from . import flash_crowd


def build_user_classes(scenario: dict, config: dict) -> tuple[type, type]:
    majority_cfg = config["majority"]
    minority_cfg = config["minority"]

    majority_scenario = {"name": f"{scenario['name']}_majority"}
    minority_scenario = {"name": f"{scenario['name']}_minority"}

    MajorityCohortUser = flash_crowd.build_user_class(majority_scenario, majority_cfg["behavior"])
    MinorityCohortUser = flash_crowd.build_user_class(minority_scenario, minority_cfg["behavior"])

    # LIVE-DISCOVERED BUG (Gen2 live-validation session): flash_crowd.py's
    # build_user_class() always defines a class literally named
    # `FlashCrowdUser` in its body. Calling it twice here produces two
    # DISTINCT classes sharing that same class name, which this installed
    # Locust version's Environment._validate_user_class_name_uniqueness()
    # rejects with a hard ValueError before any traffic is generated (mixed.py
    # never hit this because it composes flash_crowd.build_user_class with
    # edos.build_user_class -- two generator modules with different internal
    # class names -- not the same generator called twice). Renaming here,
    # after construction, is a cohort_mixed.py-local fix: it does not modify
    # flash_crowd.py or any of its other callers.
    MajorityCohortUser.__name__ = MajorityCohortUser.__qualname__ = "MajorityCohortUser"
    MinorityCohortUser.__name__ = MinorityCohortUser.__qualname__ = "MinorityCohortUser"

    MajorityCohortUser.weight = majority_cfg.get("users", 35)
    MinorityCohortUser.weight = minority_cfg.get("users", 15)

    return MajorityCohortUser, MinorityCohortUser
