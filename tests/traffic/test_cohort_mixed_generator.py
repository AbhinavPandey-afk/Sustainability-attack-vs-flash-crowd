"""Unit tests for the Gen2 hard-negative cohort-mixed traffic generator —
traffic/generators/cohort_mixed.py — and its scenario YAML. No live server
or cluster required (mirrors tests/traffic/test_mixed_generator.py's
convention for the structurally-similar E3 "mixed" generator).

Approved research-design review (docs/experiment_protocol.md's Gen2
section): a majority (70%) casual cohort and a minority (30%) "engaged"
cohort, both label=0, run concurrently via Locust's per-class `.weight`
mechanism — the same mechanism traffic/generators/mixed.py already uses
for FC+EDoS, applied here to two flash-crowd cohorts instead.
"""
import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCUSTFILE = REPO_ROOT / "traffic" / "locustfile.py"
SCENARIO_PATH = "traffic/scenarios/flash_crowd_hard_negative_gen2.yaml"


def _load_locustfile(monkeypatch):
    monkeypatch.setenv("CASCADE_SCENARIO", SCENARIO_PATH)
    spec = importlib.util.spec_from_file_location("_cascade_locustfile_cohort_mixed", LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gen2_scenario_yaml_has_both_cohorts():
    config = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    assert config["scenario"]["type"] == "flash_crowd_cohort_mixed"
    assert config["majority"]["users"] > 0
    assert config["minority"]["users"] > 0
    assert config["locust"]["users"] == config["majority"]["users"] + config["minority"]["users"]


def test_gen2_majority_cohort_matches_plain_flash_crowd_defaults():
    """The majority cohort must remain byte-for-byte identical to
    flash_crowd.yaml's own weights/think-time — the design's core
    legitimacy anchor is that most simulated traffic is unchanged from
    already-validated plain flash-crowd behaviour."""
    gen2 = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    plain = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd.yaml").read_text())

    majority_weights = gen2["majority"]["behavior"]["weights"]
    plain_weights = plain["behavior"]["weights"]
    for key in ("home", "search", "checkout"):
        assert majority_weights[key] == plain_weights[key]
    assert majority_weights.get("generate_report", 0) == 0

    assert gen2["majority"]["behavior"]["think_time_min"] == plain["behavior"]["think_time_min"]
    assert gen2["majority"]["behavior"]["think_time_max"] == plain["behavior"]["think_time_max"]


def test_gen2_minority_cohort_report_share_is_bounded_below_edos():
    """The minority cohort's OWN internal report-share must stay clearly
    below EDoS's aggregate (~86%) and below the aggregate ceiling the
    research-design review capped at ~80% for any cohort — this design's
    approved value is 70%."""
    gen2 = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    edos = yaml.safe_load((REPO_ROOT / "traffic/scenarios/edos.yaml").read_text())

    minority_weights = gen2["minority"]["behavior"]["weights"]
    minority_total = sum(w for w in minority_weights.values() if w > 0)
    minority_report_share = minority_weights["generate_report"] / minority_total

    edos_weights = edos["behavior"]["weights"]
    edos_total = sum(w for w in edos_weights.values() if w > 0)
    edos_report_share = edos_weights["generate_report"] / edos_total

    assert 0 < minority_report_share < edos_report_share
    assert minority_weights.get("home", 0) > 0
    assert minority_weights.get("search", 0) > 0
    assert minority_weights.get("checkout", 0) > 0


def test_gen2_minority_think_time_never_borrows_edos_intensity():
    """Both cohorts must keep ordinary flash-crowd think-time — the design
    explicitly never borrows EDoS's near-zero think-time as a legitimacy
    anchor."""
    gen2 = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    edos = yaml.safe_load((REPO_ROOT / "traffic/scenarios/edos.yaml").read_text())

    for cohort in ("majority", "minority"):
        behavior = gen2[cohort]["behavior"]
        assert behavior["think_time_min"] > edos["behavior"]["think_time_min"]
        assert behavior["think_time_max"] > edos["behavior"]["think_time_max"]


def test_gen2_report_complexity_between_gen1_and_edos():
    """Approved design: minority cohort's report_complexity (40) sits
    strictly between Gen1's (30) and EDoS's (60) — a deliberate, stated
    step, not equal to either boundary."""
    gen2 = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    gen1 = yaml.safe_load((REPO_ROOT / "traffic/scenarios/flash_crowd_hard_negative.yaml").read_text())
    edos = yaml.safe_load((REPO_ROOT / "traffic/scenarios/edos.yaml").read_text())

    gen2_complexity = gen2["minority"]["behavior"]["report_complexity"]
    assert gen1["behavior"]["report_complexity"] < gen2_complexity < edos["behavior"]["report_complexity"]


def test_gen2_minority_population_share_is_a_genuine_minority():
    """30% is the approved share — must stay a minority (< 50%) of the
    total population, distinguishing this from simply raising the whole
    population's average behaviour."""
    gen2 = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    total_users = gen2["majority"]["users"] + gen2["minority"]["users"]
    assert gen2["minority"]["users"] / total_users < 0.5
    assert gen2["minority"]["users"] / total_users == 0.30


def test_gen2_expected_aggregate_ratio_exceeds_gen1_ceiling():
    """The exact arithmetic error caught in the prior design review: the
    approved parameterization must produce an aggregate ratio ABOVE Gen1's
    observed ceiling (0.111), not merely reproduce it. This checks the
    CONFIGURED arithmetic only — live telemetry is required to confirm
    the actually-observed ratio (Gen2 Phase 5-7), which this test cannot
    and does not claim to prove."""
    gen2 = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    total_users = gen2["majority"]["users"] + gen2["minority"]["users"]
    minority_share = gen2["minority"]["users"] / total_users

    minority_weights = gen2["minority"]["behavior"]["weights"]
    minority_total = sum(w for w in minority_weights.values() if w > 0)
    minority_report_share = minority_weights["generate_report"] / minority_total

    configured_aggregate_ratio = minority_share * minority_report_share
    GEN1_OBSERVED_CEILING = 0.111
    assert configured_aggregate_ratio > GEN1_OBSERVED_CEILING * 1.5, (
        "Configured aggregate ratio must clear Gen1's observed ceiling with margin, "
        "not merely reproduce Gen1's own band (the exact error this design corrects)."
    )


def test_build_user_classes_returns_two_distinct_label0_classes():
    from traffic.generators.cohort_mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    majority_cls, minority_cls = build_user_classes(config["scenario"], config)
    assert majority_cls is not minority_cls
    assert majority_cls.tasks
    assert minority_cls.tasks


def test_build_user_classes_sets_weight_from_configured_user_counts():
    from traffic.generators.cohort_mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    majority_cls, minority_cls = build_user_classes(config["scenario"], config)
    assert majority_cls.weight == config["majority"]["users"]
    assert minority_cls.weight == config["minority"]["users"]


def test_build_user_classes_produces_distinct_locust_class_names():
    """Regression test for a live-discovered bug (Gen2 live-validation
    session): flash_crowd.build_user_class() always defines a class
    literally named `FlashCrowdUser` in its body. Calling it twice (once
    per cohort) previously produced two classes sharing that same class
    name, which Locust's own Environment._validate_user_class_name_uniqueness()
    rejects with a hard ValueError before any traffic is generated -- a
    real cluster run failed at exactly this point pre-fix. Checked here
    directly against Locust's own Environment construction, not just our
    own class attributes, since that is exactly where the bug lived."""
    from locust.env import Environment

    from traffic.generators.cohort_mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    majority_cls, minority_cls = build_user_classes(config["scenario"], config)

    assert majority_cls.__name__ != minority_cls.__name__
    # The actual failure mode: constructing a real Locust Environment with
    # both classes must not raise.
    env = Environment(user_classes=[majority_cls, minority_cls])
    assert {c.__name__ for c in env.user_classes} == {"MajorityCohortUser", "MinorityCohortUser"}


def test_locustfile_exposes_both_cohort_classes_for_gen2_scenario(monkeypatch):
    module = _load_locustfile(monkeypatch)
    assert hasattr(module, "MajorityCohortUser")
    assert hasattr(module, "MinorityCohortUser")
    assert not hasattr(module, "CascadeUser")
    assert module.MajorityCohortUser.tasks
    assert module.MinorityCohortUser.tasks


class _FakeClient:
    def __init__(self):
        self.headers: dict = {}


def test_gen2_cohorts_tag_requests_with_distinct_scenario_names():
    """Each cohort must be independently attributable via the X-Scenario
    header (-> Prometheus's existing `scenario` label) so Gen2 Phase 3's
    mandatory cohort verification can distinguish majority vs minority
    traffic — this is the ONLY reason cohort-specific scenario names are
    used; feature_engineering/collect_metrics.py's queries remain
    unchanged and never group by this label."""
    from traffic.generators.cohort_mixed import build_user_classes

    config = yaml.safe_load((REPO_ROOT / SCENARIO_PATH).read_text())
    majority_cls, minority_cls = build_user_classes(config["scenario"], config)

    majority_instance = majority_cls.__new__(majority_cls)
    majority_instance.client = _FakeClient()
    majority_cls.on_start(majority_instance)
    assert majority_instance.client.headers.get("X-Scenario") == "flash_crowd_hard_negative_gen2_majority"

    minority_instance = minority_cls.__new__(minority_cls)
    minority_instance.client = _FakeClient()
    minority_cls.on_start(minority_instance)
    assert minority_instance.client.headers.get("X-Scenario") == "flash_crowd_hard_negative_gen2_minority"
