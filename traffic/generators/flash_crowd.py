"""Legitimate flash-crowd (and 'normal' baseline) traffic generator.

Simulates realistic browsing: diverse endpoints, session continuity (via
the HttpUser's persistent cookie-carrying client), and conversion via
/api/checkout. Used for both the 'flash_crowd' and 'normal' scenario types
— they share this behavioural shape and differ only in scenario config
(user count, spawn rate, think time). See CLAUDE.md section 11.

HARD-NEGATIVE CAPABILITY (docs/research_gap_audit.md Part 6, E4 "Hard-
negative Flash Crowd" / P0 fix): this generator can now also issue
legitimate requests to the expensive /api/generate-report endpoint, via a
`generate_report` weight — defaulting to 0 (unused) so the existing
flash_crowd.yaml / normal.yaml / flash_crowd_viral.yaml configs are
unchanged and remain "pure" legitimate browsing with no expensive-
endpoint traffic at all. A separate scenario config
(traffic/scenarios/flash_crowd_hard_negative.yaml) sets a small non-zero
weight instead, so "any request to /api/generate-report" stops being a
guaranteed EDoS signal while label=0 (legitimate flash crowd) is
unchanged — see that file's comment for the rationale. Configuration
over generator duplication, per the project's existing pattern for
scenario variants (e.g. viral_shape.py reusing this same generator).

WEIGHTING BUG FOUND VIA LIVE VALIDATION: `.tasks` is built via
`weighted_task_list()` (see traffic/generators/__init__.py), not a
`{task: weight}` dict — assigning a dict directly here was found, via a
real cluster run, to be silently collapsed to uniform (unweighted)
probability by this Locust version's `Environment._filter_tasks_by_tags`.
This means every historical flash-crowd run's home/search/checkout mix
(e.g. the configured 3:5:1 weights) was ALSO silently uniform, not
weighted, before this fix. See that helper's docstring for the full
explanation and evidence.
"""
import random

from locust import HttpUser, between

from . import weighted_task_list


def build_user_class(scenario: dict, behavior: dict) -> type:
    weights = behavior.get("weights", {})
    search_terms = behavior.get("search_terms", ["default"])
    think_min = behavior.get("think_time_min", 1.0)
    think_max = behavior.get("think_time_max", 3.0)
    report_complexity = behavior.get("report_complexity", 20)
    scenario_name = scenario["name"]

    class FlashCrowdUser(HttpUser):
        def on_start(self):
            self.client.headers.update({"X-Scenario": scenario_name})

        def home(self):
            self.client.get("/api/home", name="/api/home")

        def search(self):
            q = random.choice(search_terms)
            self.client.get("/api/search", params={"q": q}, name="/api/search")

        def checkout(self):
            self.client.post("/api/checkout", name="/api/checkout")

        def generate_report(self):
            self.client.post(
                "/api/generate-report",
                json={"complexity": report_complexity},
                name="/api/generate-report",
            )

    FlashCrowdUser.wait_time = between(think_min, think_max)
    candidate_tasks = {
        FlashCrowdUser.home: weights.get("home", 0),
        FlashCrowdUser.search: weights.get("search", 0),
        FlashCrowdUser.checkout: weights.get("checkout", 0),
        FlashCrowdUser.generate_report: weights.get("generate_report", 0),
    }
    FlashCrowdUser.tasks = weighted_task_list(candidate_tasks)
    return FlashCrowdUser
