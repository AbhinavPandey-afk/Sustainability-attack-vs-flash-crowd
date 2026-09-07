"""Custom Locust arrival-rate schedule modeling a genuine viral-event
traffic surge, for use with the 'flash_crowd' scenario type.

Locust's default behaviour (a fixed --users/--spawn-rate ramp held flat)
does not reproduce how a real viral event actually arrives: a short
organic trickle, then accelerating word-of-mouth growth that saturates
near a peak (a logistic/S-curve — the standard model of viral adoption),
a sustained peak, and a gradual decline as attention moves on. This
module implements that curve as a Locust LoadTestShape so the existing
flash-crowd User behaviour (traffic/generators/flash_crowd.py) is
reused unchanged — only the *arrival* schedule differs.

Locust auto-discovers a LoadTestShape subclass present in the locustfile
module namespace, the same way it discovers HttpUser subclasses.
"""
from __future__ import annotations

import math


def phase_boundaries(shape_cfg: dict) -> tuple[float, float, float, float]:
    """Returns cumulative end-times (seconds) of each phase: trickle, ramp, peak, decay."""
    trickle = shape_cfg.get("trickle_seconds", 10)
    ramp = shape_cfg.get("ramp_seconds", 25)
    peak = shape_cfg.get("peak_seconds", 30)
    decay = shape_cfg.get("decay_seconds", 25)
    t1 = trickle
    t2 = t1 + ramp
    t3 = t2 + peak
    t4 = t3 + decay
    return t1, t2, t3, t4


def total_duration(shape_cfg: dict) -> float:
    return phase_boundaries(shape_cfg)[3]


def users_at(elapsed: float, shape_cfg: dict) -> float | None:
    """Target concurrent-user count at `elapsed` seconds into the run, or
    None once the run is over (mirrors LoadTestShape.tick()'s stop signal).
    """
    trickle_users = shape_cfg.get("trickle_users", 5)
    peak_users = shape_cfg.get("peak_users", 50)
    decay_floor_users = shape_cfg.get("decay_floor_users", max(1, trickle_users))
    steepness = shape_cfg.get("ramp_steepness", 10.0)

    t1, t2, t3, t4 = phase_boundaries(shape_cfg)

    if elapsed >= t4:
        return None

    if elapsed < t1:
        return float(trickle_users)

    if elapsed < t2:
        # Logistic (sigmoid) S-curve from trickle_users to peak_users over
        # the ramp phase — slow start, accelerating growth, saturating
        # near the peak, matching real viral-adoption curves.
        ramp_seconds = max(t2 - t1, 1e-9)
        progress = (elapsed - t1) / ramp_seconds  # 0..1
        sigmoid = 1.0 / (1.0 + math.exp(-steepness * (progress - 0.5)))
        # Normalize so sigmoid(0)==0 and sigmoid(1)==1 exactly.
        s0 = 1.0 / (1.0 + math.exp(-steepness * (0 - 0.5)))
        s1 = 1.0 / (1.0 + math.exp(-steepness * (1 - 0.5)))
        normalized = (sigmoid - s0) / (s1 - s0)
        return trickle_users + normalized * (peak_users - trickle_users)

    if elapsed < t3:
        return float(peak_users)

    # Decay phase: linear falloff from peak_users toward decay_floor_users.
    decay_seconds = max(t4 - t3, 1e-9)
    progress = (elapsed - t3) / decay_seconds  # 0..1
    return peak_users - progress * (peak_users - decay_floor_users)


def build_shape_class(scenario: dict, shape_cfg: dict) -> type:
    """Builds a Locust LoadTestShape subclass driven by `users_at`."""
    from locust import LoadTestShape

    spawn_rate = shape_cfg.get("spawn_rate", max(shape_cfg.get("peak_users", 50), 1))

    class ViralEventShape(LoadTestShape):
        def tick(self):
            run_time = self.get_run_time()
            target = users_at(run_time, shape_cfg)
            if target is None:
                return None
            return (max(1, round(target)), spawn_rate)

    return ViralEventShape
