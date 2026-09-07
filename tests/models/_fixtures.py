"""Shared synthetic labeled dataset for models/ tests. Not a test module
itself (no test_ prefix) — imported by the actual test files.

The signal is deliberately strong and clean (EDoS rows get high
expensive_endpoint_ratio/cost_per_request/low request_rate; flash-crowd
rows the reverse) so that "does the training/eval code work correctly"
can be tested independently of "is the signal realistic" — realism is
exercised separately via the live-cluster verification, not unit tests.
"""
import numpy as np
import pandas as pd

from models.feature_sets import ABLATION_FEATURE_SETS

ALL_FEATURE_COLUMNS = sorted({col for cols in ABLATION_FEATURE_SETS.values() for col in cols})


def make_synthetic_dataset(n_experiments_per_class: int = 3, rows_per_experiment: int = 10, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    rows = []
    window_end = 0
    for label, prefix in [(0, "FC"), (1, "EDOS")]:
        for exp_i in range(n_experiments_per_class):
            experiment_id = f"{prefix}_{exp_i:03d}"
            for _ in range(rows_per_experiment):
                window_end += 60
                row = {col: float(rng.normal(loc=1.0, scale=0.2)) for col in ALL_FEATURE_COLUMNS}
                if label == 1:
                    row["expensive_endpoint_ratio"] = float(rng.uniform(0.85, 1.0))
                    row["cost_per_request"] = float(rng.uniform(5.0, 8.0))
                    row["request_rate"] = float(rng.uniform(1.0, 3.0))
                else:
                    row["expensive_endpoint_ratio"] = float(rng.uniform(0.0, 0.15))
                    row["cost_per_request"] = float(rng.uniform(0.1, 0.5))
                    row["request_rate"] = float(rng.uniform(5.0, 20.0))
                row["window_end"] = window_end
                row["window_seconds"] = 60
                row["label"] = label
                row["experiment_id"] = experiment_id
                row["estimated_cost"] = row["cost_per_request"] * max(row["request_rate"], 1.0)
                rows.append(row)
    return pd.DataFrame(rows)
