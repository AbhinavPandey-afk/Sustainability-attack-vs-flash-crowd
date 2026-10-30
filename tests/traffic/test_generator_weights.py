"""Deterministic tests for the EDoS/flash-crowd task-weight logic itself
(traffic/generators/edos.py, flash_crowd.py), independent of any scenario
YAML — regression tests for docs/research_gap_audit.md Part 4's finding
that a hard-coded zero-probability endpoint set functioned as a
deterministic label shortcut for the classifier.

These test the weight construction directly (no Locust runtime, no
random execution) so "EDoS/flash-crowd CAN touch endpoint X" is proven by
inspecting `cls.tasks`, not by sampling and hoping.

`cls.tasks` is a LIST with each task repeated proportional to its weight
(see traffic/generators/__init__.py::weighted_task_list), not a
`{task: weight}` dict — a real, live-cluster-discovered bug meant a dict
assigned directly to `.tasks` was silently collapsed to uniform
probability by this Locust version. Tests here check weight via
`list.count(task)`, matching what `weighted_task_list` actually produces.

IMPORTANT: traffic/generators/edos.py and flash_crowd.py import `locust`,
which monkey-patches the stdlib (gevent) at import time. Every other test
file under tests/traffic/ imports these generator modules lazily, inside
each test function, rather than at module level — importing them at
collection time (before pytest has finished collecting/running unrelated
modules, e.g. tests/test_app.py's FastAPI TestClient) was found to hang
the whole test run. These fixtures preserve that lazy-import convention.
"""
import pytest


@pytest.fixture
def edos():
    from traffic.generators import edos as _edos

    return _edos


@pytest.fixture
def flash_crowd():
    from traffic.generators import flash_crowd as _flash_crowd

    return _flash_crowd


def test_edos_can_generate_non_zero_traffic_to_normal_endpoints_when_configured(edos):
    cls = edos.build_user_class(
        {"name": "edos"},
        {"weights": {"generate_report": 18, "home": 1, "search": 1, "checkout": 1}},
    )
    task_names = {fn.__name__ for fn in cls.tasks}
    assert {"generate_report", "home", "search", "checkout"} <= task_names


def test_edos_weighted_task_list_has_exact_repetition_counts_matching_config(edos):
    """Regression test for the live-discovered weighting bug: each task
    must be repeated EXACTLY its configured weight, in a plain list —
    not present via a {task: weight} dict, which this Locust version
    silently flattens to uniform probability (see
    traffic/generators/__init__.py::weighted_task_list)."""
    cls = edos.build_user_class(
        {"name": "edos"},
        {"weights": {"generate_report": 18, "home": 1, "search": 1, "checkout": 1}},
    )
    assert isinstance(cls.tasks, list)
    assert cls.tasks.count(cls.generate_report) == 18
    assert cls.tasks.count(cls.home) == 1
    assert cls.tasks.count(cls.search) == 1
    assert cls.tasks.count(cls.checkout) == 1
    assert len(cls.tasks) == 21


def test_edos_still_generates_the_intended_expensive_workload_and_dominates(edos):
    cls = edos.build_user_class(
        {"name": "edos"},
        {"weights": {"generate_report": 18, "home": 1, "search": 1, "checkout": 1}},
    )
    total = len(cls.tasks)
    assert cls.tasks.count(cls.generate_report) / total > 0.7


def test_edos_endpoint_weights_are_zero_only_when_explicitly_unconfigured(edos):
    """Zero-probability endpoints are still possible — but only because
    the caller's config said so, not because the generator can't do
    otherwise (see the previous two tests)."""
    cls = edos.build_user_class({"name": "edos"}, {"weights": {"generate_report": 10}})
    task_names = {fn.__name__ for fn in cls.tasks}
    assert task_names == {"generate_report"}
    # But the capability exists in the class regardless of what ran:
    assert hasattr(cls, "home")
    assert hasattr(cls, "search")
    assert hasattr(cls, "checkout")


def test_flash_crowd_normal_mode_behaves_as_before(flash_crowd):
    cls = flash_crowd.build_user_class(
        {"name": "flash_crowd"},
        {"weights": {"home": 3, "search": 5, "checkout": 1}},
    )
    task_names = {fn.__name__ for fn in cls.tasks}
    assert task_names == {"home", "search", "checkout"}
    assert "generate_report" not in task_names


def test_flash_crowd_hard_negative_can_generate_expensive_endpoint_requests(flash_crowd):
    cls = flash_crowd.build_user_class(
        {"name": "flash_crowd_hard_negative"},
        {"weights": {"home": 3, "search": 5, "checkout": 1, "generate_report": 1}},
    )
    task_names = {fn.__name__ for fn in cls.tasks}
    assert "generate_report" in task_names
    # Still a legitimate crowd: expensive endpoint is a minority behaviour.
    assert cls.tasks.count(cls.generate_report) < cls.tasks.count(cls.search)


def test_flash_crowd_generate_report_defaults_to_unconfigured(flash_crowd):
    """Omitting `generate_report` from weights (as every existing
    flash-crowd scenario config does) must not silently enable it."""
    cls = flash_crowd.build_user_class(
        {"name": "flash_crowd"},
        {"weights": {"home": 3, "search": 5, "checkout": 1}},
    )
    assert cls.generate_report not in cls.tasks


def test_weighted_task_list_survives_locusts_filter_tasks_by_tags(edos):
    """The actual live-discovered failure mode: Locust's own
    Environment._filter_tasks_by_tags() runs unconditionally on every
    run (no tags needed to trigger it) and reassigns `task_holder.tasks`
    from whatever it iterates over `.tasks`. A {task: weight} dict was
    silently collapsed to one-of-each by this call — proven here by
    calling the exact same Locust function directly against our built
    class and checking the weighted counts survive unchanged."""
    from locust.user.task import filter_tasks_by_tags

    cls = edos.build_user_class(
        {"name": "edos"},
        {"weights": {"generate_report": 18, "home": 1, "search": 1, "checkout": 1}},
    )
    before = list(cls.tasks)
    filter_tasks_by_tags(cls, tags=None, exclude_tags=None)
    assert cls.tasks.count(cls.generate_report) == 18
    assert sorted(t.__name__ for t in cls.tasks) == sorted(t.__name__ for t in before)


def test_scenario_parsing_still_works_for_existing_weight_shapes(edos, flash_crowd):
    """Existing scenario configs that never set home/search/checkout for
    EDoS, or generate_report for flash crowd, must still parse and build
    a valid (non-empty) task set — the new weight keys are additive."""
    edos_cls = edos.build_user_class({"name": "edos"}, {"weights": {"generate_report": 10, "checkout": 0}})
    assert edos_cls.tasks

    fc_cls = flash_crowd.build_user_class(
        {"name": "flash_crowd"}, {"weights": {"home": 3, "search": 5, "checkout": 1}}
    )
    assert fc_cls.tasks
