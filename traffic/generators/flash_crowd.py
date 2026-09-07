"""Legitimate flash-crowd (and 'normal' baseline) traffic generator.

Simulates realistic browsing: diverse endpoints, session continuity (via
the HttpUser's persistent cookie-carrying client), and conversion via
/api/checkout. Used for both the 'flash_crowd' and 'normal' scenario types
— they share this behavioural shape and differ only in scenario config
(user count, spawn rate, think time). See CLAUDE.md section 11.
"""
import random

from locust import HttpUser, between


def build_user_class(scenario: dict, behavior: dict) -> type:
    weights = behavior.get("weights", {})
    search_terms = behavior.get("search_terms", ["default"])
    think_min = behavior.get("think_time_min", 1.0)
    think_max = behavior.get("think_time_max", 3.0)
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

    FlashCrowdUser.wait_time = between(think_min, think_max)
    candidate_tasks = {
        FlashCrowdUser.home: weights.get("home", 0),
        FlashCrowdUser.search: weights.get("search", 0),
        FlashCrowdUser.checkout: weights.get("checkout", 0),
    }
    FlashCrowdUser.tasks = {fn: w for fn, w in candidate_tasks.items() if w > 0}
    return FlashCrowdUser
