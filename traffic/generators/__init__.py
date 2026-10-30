"""Shared helpers for traffic/generators/*.py."""


def weighted_task_list(candidate_tasks: dict) -> list:
    """Builds a Locust `User.tasks` LIST with each task repeated
    proportional to its configured weight, instead of assigning a
    `{task: weight}` dict directly to `.tasks`.

    BUG FOUND VIA LIVE VALIDATION (docs/research_gap_audit.md live
    validation session): this project's installed Locust version's
    `Environment._filter_tasks_by_tags()` runs unconditionally on every
    run (tag-filtering enabled or not) and does
    `task_holder.tasks = [task for task in task_holder.tasks ...]`.
    Iterating a dict yields only its KEYS, so a `{task: weight}` dict
    assigned post-class-creation to `.tasks` (this project's previous
    pattern in edos.py/flash_crowd.py) gets silently collapsed to a list
    of each key exactly ONCE by that reassignment — every configured
    weight is discarded and every remaining task becomes equally likely.
    (Locust's documentation for a `{task: weight}` dict only applies when
    it is declared directly in a User's class body, where the `UserMeta`
    metaclass flattens it into a repeated list BEFORE this filtering step
    ever runs — our dynamically-built classes assign `.tasks` after class
    creation, bypassing that metaclass step entirely.)

    Confirmed empirically against a real cluster: `edos.yaml` weights
    `generate_report:18, home:1, search:1, checkout:1` (intended
    ~86%/4.5%/4.5%/4.5%) produced an observed ~26%/23%/26%/25% split —
    uniform, not weighted. The same bug was already silently present in
    every historical flash-crowd run in this project's provisional
    dataset: `FC_001`'s real home/search/checkout counts (1284/1304/1268)
    are uniform despite configured weights of 3/5/1.

    The fix: pre-flatten the weights into a repeated list ourselves —
    exactly what Locust's own metaclass does for a class-body-declared
    dict (see `get_tasks_from_base_classes` in `locust/user/task.py`) —
    so the result survives `_filter_tasks_by_tags()`'s reassignment
    unchanged (filtering a list of repeats just preserves the repeats).

    Tasks with weight <= 0 are omitted entirely.
    """
    return [task for task, weight in candidate_tasks.items() if weight > 0 for _ in range(int(weight))]
