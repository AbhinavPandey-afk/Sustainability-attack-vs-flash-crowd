"""Paths and static UI copy for the CASCADE dashboard backend.

This module intentionally holds no experiment data itself — only
filesystem locations (so the backend reads the same files the CLI
pipeline writes) and human-authored descriptive text (purposes, demo
walkthrough) that is not a research measurement and therefore safe to
hardcode.
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_RAW = REPO_ROOT / "data" / "raw"
DATA_FEATURES = REPO_ROOT / "data" / "features"
DATA_EXPERIMENTS = REPO_ROOT / "data" / "experiments"
EXPERIMENTS_CONFIGS = REPO_ROOT / "experiments" / "configs"
TRAFFIC_SCENARIOS = REPO_ROOT / "traffic" / "scenarios"
RESULTS_DIR = REPO_ROOT / "results"
RESULTS_FIGURES = RESULTS_DIR / "figures"
RESULTS_TABLES = RESULTS_DIR / "tables"
RESULTS_METRICS = RESULTS_DIR / "metrics"

DEFAULT_APP_HOST = "http://localhost:8000"
DEFAULT_PROMETHEUS_URL = "http://localhost:9090"

# Matches app/src/cost.py CostModelConfig's default and the cost_model.
# replica_cost_per_minute default used across experiments/configs/*.yaml
# (CLAUDE.md section 10) — kept here (not imported) so the storefront's
# live impact endpoint (live_impact.py) has no import-time coupling to the
# app/ package.
DEFAULT_REPLICA_COST_PER_MINUTE = 1.0

# Below this many labeled experiments, results are proof-of-concept scale,
# not a statistically meaningful research result (docs/experiment_protocol.md §5).
PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD = 20

# Human-authored purpose copy per scenario_type, shown on experiment cards.
# This is UI framing text, not a measurement — every number a user sees
# elsewhere in the dashboard is read live from the actual config/result files.
SCENARIO_PURPOSE = {
    "flash_crowd": (
        "Many simulated users browsing diverse endpoints — home, search, checkout — "
        "with realistic think-time and natural conversion."
    ),
    "edos": (
        "Few simulated clients concentrated almost entirely on the deliberately "
        "expensive generate-report endpoint, minimal think-time, no conversion. "
        "Traffic volume is kept comparable to the flash-crowd scenario."
    ),
    "mixed": (
        "Flash-crowd and EDoS traffic running simultaneously against the same app "
        "instance — attack present throughout the run."
    ),
    "interleaved": (
        "Alternating flash-crowd and EDoS phases under one continuous observation "
        "window, each with its own real ground-truth label."
    ),
    "normal": (
        "Light, diverse baseline browsing with no surge and no attack — an "
        "ordinary-day reference point."
    ),
}

SCENARIO_LABEL_NAME = {0: "Flash Crowd", 1: "EDoS"}
SPECIAL_SCENARIO_LABELS = {"mixed": "Mixed (E3)", "interleaved": "Interleaved (E4)", "normal": "Normal Baseline (E0)"}

# Static, non-measured workload constants mirroring app/src/config.py's
# Settings — NOT a live measurement. Shown only as illustrative "relative
# compute weight" context per endpoint class, since cost/CPU is not metered
# per endpoint anywhere in this pipeline (see analytics.py::endpoint_cost_heatmap).
ENDPOINT_COMPUTE_WEIGHTS = {
    "cheap": {
        "note": "No simulated workload — trivial handler (e.g. /api/home, /api/checkout).",
    },
    "medium": {
        "note": (
            "Simulated search workload of ~20 iterations per request "
            "(app/src/config.py SEARCH_WORKLOAD_ITERATIONS), cache-aware."
        ),
    },
    "expensive": {
        "note": (
            "Simulated report-generation workload of ~2000 iterations per complexity unit "
            "(default complexity 10), hard-capped at 200,000 iterations "
            "(app/src/config.py REPORT_ITERATIONS_PER_COMPLEXITY / REPORT_DEFAULT_COMPLEXITY / "
            "REPORT_MAX_ITERATIONS)."
        ),
    },
}

KNOWN_LIMITATIONS = [
    {
        "title": "Proof-of-concept data scale",
        "detail": (
            "The six experiment configs (FC_001-003, EDOS_001-003) run 75-second "
            "traffic bursts — suitable for demonstrating system behaviour end to "
            "end, not yet a multi-minute, multi-repetition statistical protocol. "
            "Any classification/hypothesis verdict shown here is provisional."
        ),
    },
    {
        "title": "Unattended live-matrix Prometheus connection issue",
        "detail": (
            "docs/experiment_protocol.md documents an intermittent Prometheus "
            "'connection refused' failure when running the full experiment matrix "
            "unattended on this Windows + Docker Desktop development machine, "
            "narrowed to concurrent background activity during traffic generation "
            "but not conclusively isolated. Running experiments individually with "
            "fresh port-forward tunnels (as this dashboard's live-run does) is the "
            "documented workaround."
        ),
    },
    {
        "title": "E3/E4 evaluation is 1-4 windows, not a statistical sample",
        "detail": (
            "MIX_001 (E3, simultaneous) currently has 3 feature windows, all "
            "label=1 by design — its 'flash-crowd false-positive rate' is "
            "therefore trivially 0/0 (no negative-class windows exist to false-"
            "positive on), not evidence the detector generalizes. INTERLEAVED_001 "
            "(E4) has 4 windows, one per phase. Both are illustrative of the "
            "pipeline working end-to-end, not a statistically meaningful claim "
            "about mixed/interleaved-condition performance."
        ),
    },
    {
        "title": "CPU-only 'resource' ablation model",
        "detail": (
            "Model B ('volume + resource') is CPU-only, not CPU+memory, because "
            "the HPA is CPU-utilization-based only and memory is not sampled "
            "anywhere in the pipeline."
        ),
    },
    {
        "title": "Client-identity proxies",
        "detail": (
            "unique_client_ratio and requests_per_session are derived from the "
            "app_active_sessions gauge, not true client-identity measurements — "
            "the app never exposes session IDs or client IPs as Prometheus labels "
            "by design (unbounded labels are avoided)."
        ),
    },
    {
        "title": "Live per-run prediction quality",
        "detail": (
            "The trained LightGBM model is now serialized to disk after every "
            "training pass (results/models/cascade_lightgbm.joblib) and scored "
            "live against a just-completed run's real feature windows "
            "(webapp/backend/prediction.py) — but the model itself is still "
            "trained on proof-of-concept-scale data, so a live prediction's "
            "confidence should be read as 'the inference pipeline works end to "
            "end', not as a statistically validated classification."
        ),
    },
]

DEMO_WALKTHROUGH = [
    "Open the dashboard and read the research question and current system status.",
    "Open Experiments and select a Flash Crowd sample (e.g. FC_001) — run it live or open its saved result.",
    "Select FC_VIRAL_001 to see the viral-event arrival curve (trickle -> S-curve ramp -> peak -> decay), and note the replica count actually scale up during the peak.",
    "Select an EDoS sample (e.g. EDOS_001) and compare its request-rate/replica/cost charts to the flash-crowd runs.",
    "Open 'Compare Two Experiments', pick a Flash Crowd and an EDoS run, and read the cost/request comparison directly.",
    "Open the EDoS vs Flash Crowd Simulator, load a sample (or set your own traffic parameters), and run a real live simulation — the trained CASCADE detector determines EDoS vs Flash Crowd from the measured result, never a manual selection.",
    "Open Detection to see the trained model's actual evaluation metrics, the research hypotheses computed from those metrics, and why traffic volume alone can't separate the two classes.",
    "Open MIX_001 (E3) and INTERLEAVED_001 (E4) in Experiments to see attack and legitimate traffic simultaneously and alternating — then open Detection's mixed/interleaved evaluation to see the same trained model scored on them.",
]
