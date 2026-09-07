"""E3 — simultaneous mixed traffic: flash-crowd and EDoS User classes
running concurrently in one Locust process (CLAUDE.md section 13, E3).

Reuses the existing flash_crowd/edos User-class builders unchanged (same
task/behaviour logic as the pure single-class scenarios) and composes
them by giving each class a Locust `weight` so a single `--users N`
invocation distributes N users across both classes proportionally to
their configured counts — e.g. users=58 with weight=50/weight=8
reproduces ~50 flash-crowd users and ~8 EDoS users running at once.
"""
from __future__ import annotations

from . import edos, flash_crowd


def build_user_classes(scenario: dict, config: dict) -> tuple[type, type]:
    fc_cfg = config["flash_crowd"]
    edos_cfg = config["edos"]

    fc_scenario = {"name": "flash_crowd"}
    edos_scenario = {"name": "edos"}

    FlashCrowdUser = flash_crowd.build_user_class(fc_scenario, fc_cfg["behavior"])
    EdosUser = edos.build_user_class(edos_scenario, edos_cfg["behavior"])

    FlashCrowdUser.weight = fc_cfg.get("users", 50)
    EdosUser.weight = edos_cfg.get("users", 8)

    return FlashCrowdUser, EdosUser
