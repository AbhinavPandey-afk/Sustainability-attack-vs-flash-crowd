"""Named feature subsets for the ablation study (CLAUDE.md section 19):
which feature family actually contributes to the flash-crowd/EDoS
distinction?
"""
from feature_engineering import behaviour_features, cost_features, scaling_features, traffic_features

TRAFFIC_COLUMNS = list(traffic_features.EMPTY.keys())
COST_COLUMNS = list(cost_features.EMPTY.keys())
SCALING_COLUMNS = list(scaling_features.EMPTY.keys())
BEHAVIOUR_COLUMNS = list(behaviour_features.EMPTY.keys())
COMBINED_COLUMNS = [
    "cost_per_request_over_request_rate",
    "replica_count_over_request_rate",
    "cpu_utilization_over_request_rate",
    "expensive_ratio_times_cost_per_request",
    "replica_growth_rate_over_request_rate",
]

# CPU-only "resource" subset for Model B. CLAUDE.md's illustrative example
# lists "Volume + CPU + Memory", but this project's HPA is CPU-utilization
# -based only (CLAUDE.md section 9) and memory utilization is not
# tracked — so Model B here is "Volume + CPU". Documented, not silently
# substituted.
RESOURCE_COLUMNS = ["current_replica_count", "mean_replica_count", "cpu_growth_rate"]

ABLATION_FEATURE_SETS = {
    "A_volume_only": TRAFFIC_COLUMNS,
    "B_volume_plus_resource": TRAFFIC_COLUMNS + RESOURCE_COLUMNS,
    "C_proposed_full": TRAFFIC_COLUMNS + COST_COLUMNS + SCALING_COLUMNS + BEHAVIOUR_COLUMNS + COMBINED_COLUMNS,
    "D_proposed_without_cost": TRAFFIC_COLUMNS + SCALING_COLUMNS + BEHAVIOUR_COLUMNS,
    "E_proposed_without_behaviour": TRAFFIC_COLUMNS + COST_COLUMNS + SCALING_COLUMNS,
}


def select_features(df, model_name: str):
    if model_name not in ABLATION_FEATURE_SETS:
        raise ValueError(f"Unknown ablation model name: {model_name!r}. Known: {sorted(ABLATION_FEATURE_SETS)}")
    columns = ABLATION_FEATURE_SETS[model_name]
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"DataFrame is missing columns required by {model_name}: {sorted(missing)}")
    return df[columns]
