"""Synthetic EDoS traffic generator: concentrates on the deliberately
expensive /api/generate-report endpoint with minimal think-time and (via
scenario config) few simulated clients relative to flash-crowd scenarios.

Traffic remains entirely local and synthetic, confined to this project's
own test application — see CLAUDE.md section 36 (Safety Constraints).
"""
from locust import HttpUser, between


def build_user_class(scenario: dict, behavior: dict) -> type:
    weights = behavior.get("weights", {})
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

        def checkout(self):
            self.client.post("/api/checkout", name="/api/checkout")

    EdosUser.wait_time = between(think_min, think_max)
    candidate_tasks = {
        EdosUser.generate_report: weights.get("generate_report", 1),
        EdosUser.checkout: weights.get("checkout", 0),
    }
    EdosUser.tasks = {fn: w for fn, w in candidate_tasks.items() if w > 0}
    return EdosUser
