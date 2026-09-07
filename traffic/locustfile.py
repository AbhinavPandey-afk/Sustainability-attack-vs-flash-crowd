"""Locust entrypoint. Selects a traffic generator based on the scenario
YAML named by the CASCADE_SCENARIO env var (default: normal.yaml).

Run directly:
    CASCADE_SCENARIO=traffic/scenarios/edos.yaml \
        locust -f traffic/locustfile.py --host http://localhost:8000

Or via the wrapper that also saves telemetry:
    python traffic/run_scenario.py traffic/scenarios/edos.yaml
"""
import os
import sys
from pathlib import Path

import yaml

_TRAFFIC_DIR = Path(__file__).resolve().parent
if str(_TRAFFIC_DIR) not in sys.path:
    sys.path.insert(0, str(_TRAFFIC_DIR))

from generators import edos, flash_crowd, mixed, viral_shape  # noqa: E402

_DEFAULT_SCENARIO = _TRAFFIC_DIR / "scenarios" / "normal.yaml"
_scenario_path = Path(os.environ.get("CASCADE_SCENARIO", _DEFAULT_SCENARIO))

_config = yaml.safe_load(_scenario_path.read_text())
_scenario = _config["scenario"]
_behavior = _config.get("behavior", {})
_locust_cfg = _config.get("locust", {})

_GENERATORS = {
    "normal": flash_crowd.build_user_class,
    "flash_crowd": flash_crowd.build_user_class,
    "edos": edos.build_user_class,
}

if _scenario["type"] == "mixed":
    # E3: expose BOTH User classes at module level — Locust discovers
    # every HttpUser subclass present in the module, not just one.
    FlashCrowdUser, EdosUser = mixed.build_user_classes(_scenario, _config)
else:
    _builder = _GENERATORS.get(_scenario["type"])
    if _builder is None:
        raise ValueError(f"Unknown scenario type: {_scenario['type']!r} in {_scenario_path}")
    # Locust auto-discovers HttpUser subclasses at module level.
    CascadeUser = _builder(_scenario, _behavior)

_arrival_shape_cfg = _locust_cfg.get("arrival_shape")
if _arrival_shape_cfg:
    # Locust auto-discovers a LoadTestShape subclass the same way; when
    # present it takes over user-count/spawn-rate scheduling entirely.
    ViralEventShape = viral_shape.build_shape_class(_scenario, _arrival_shape_cfg)
