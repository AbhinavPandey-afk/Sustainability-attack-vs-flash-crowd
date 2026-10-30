"""Synthetic EDoS traffic generator: concentrates on the deliberately
expensive /api/generate-report endpoint with minimal think-time and (via
scenario config) few simulated clients relative to flash-crowd scenarios.

Traffic remains entirely local and synthetic, confined to this project's
own test application — see CLAUDE.md section 36 (Safety Constraints).

METHODOLOGY NOTE (docs/research_gap_audit.md Part 4 / P0 fix): this
generator now defines home/search tasks in addition to generate_report/
checkout, all gated by configurable weights exactly like
flash_crowd.py's — home/search/checkout default to weight 0 (unused)
unless the scenario config sets them, but the CAPABILITY is no longer
absent from the code. Earlier versions of this module had no home/search
task at all, which meant search_ratio/cheap_endpoint_ratio were not just
usually-zero but *structurally impossible to be anything else* for EDoS
traffic — a deterministic label shortcut, confirmed by this project's own
SHAP output, rather than a measured behavioural difference. The default
scenario config (traffic/scenarios/edos.yaml) now sets small non-zero
weights for these; see that file's comment for the exact rationale.

WEIGHTING BUG FOUND VIA LIVE VALIDATION: `.tasks` is built via
`weighted_task_list()` (see traffic/generators/__init__.py), not a
`{task: weight}` dict — assigning a dict directly here was found, via a
real cluster run, to be silently collapsed to uniform (unweighted)
probability by this Locust version's `Environment._filter_tasks_by_tags`.
See that helper's docstring for the full explanation and evidence.
"""
import random

from locust import HttpUser, between

from . import weighted_task_list


def build_user_class(scenario: dict, behavior: dict) -> type:
    weights = behavior.get("weights", {})
    search_terms = behavior.get("search_terms", ["default"])
    think_min = behavior.get("think_time_min", 0.05)
    think_max = behavior.get("think_time_max", 0.3)
    complexity = behavior.get("report_complexity", 50)
    scenario_name = scenario["name"]

    class EdosUser(HttpUser):
        def on_start(self):
            self.client.headers.update({"X-Scenario": scenario_name})

        def generate_report(self):
            self.client.post(
                "/api/generate-report",
                json={"complexity": complexity},
                name="/api/generate-report",
            )

        def home(self):
            self.client.get("/api/home", name="/api/home")

        def search(self):
            q = random.choice(search_terms)
            self.client.get("/api/search", params={"q": q}, name="/api/search")

        def checkout(self):
            self.client.post("/api/checkout", name="/api/checkout")

    EdosUser.wait_time = between(think_min, think_max)
    candidate_tasks = {
        EdosUser.generate_report: weights.get("generate_report", 1),
        EdosUser.home: weights.get("home", 0),
        EdosUser.search: weights.get("search", 0),
        EdosUser.checkout: weights.get("checkout", 0),
    }
    EdosUser.tasks = weighted_task_list(candidate_tasks)
    return EdosUser
