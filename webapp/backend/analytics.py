"""New read-only computations over the existing pipeline's on-disk artifacts.

Same convention as data_access.py: every function reads files the existing
CLI pipeline already produces and returns {"available": False, ...} rather
than inventing a value when the underlying data doesn't exist yet. Nothing
here re-implements or duplicates the research pipeline (feature_engineering/,
models/) — it reuses models.feature_sets.ABLATION_FEATURE_SETS for the exact
column set the trained detector uses, and reads results/tables/
feature_statistics.csv for SHAP importances rather than recomputing SHAP.
"""
from __future__ import annotations

import math
from typing import Any

import pandas as pd

from config import DATA_FEATURES, ENDPOINT_COMPUTE_WEIGHTS
from data_access import list_all_experiment_ids, load_features, load_results_table, load_timeseries


def _avg(records: list[dict], key: str) -> float | None:
    values = [
        r[key]
        for r in records
        if r.get(key) is not None and not (isinstance(r[key], float) and math.isnan(r[key]))
    ]
    return sum(values) / len(values) if values else None


# --------------------------------------------------------- cost heatmap --

_ENDPOINT_COUNT_COLUMNS = {"cheap": "cheap_count", "medium": "medium_count", "expensive": "expensive_count"}


def endpoint_cost_heatmap(experiment_id: str | None = None) -> dict[str, Any]:
    """Per-endpoint-class request share and apportioned cost.

    The application does not meter cost per endpoint anywhere in the
    pipeline (app/src/cost.py is purely replica-minutes x rate, with no
    endpoint dimension) — so "apportioned_cost" here is a derived estimate
    (the window's real total measured cost, split by each class's share of
    real request volume), not an independently measured per-endpoint cost.
    Labeled as such in cost_apportionment_note for the frontend to surface.
    """
    experiment_ids = [experiment_id] if experiment_id else list_all_experiment_ids()

    totals = {name: 0.0 for name in _ENDPOINT_COUNT_COLUMNS}
    total_cost = 0.0
    any_data = False

    for exp_id in experiment_ids:
        timeseries = load_timeseries(exp_id)
        if len(timeseries) < 2:
            continue
        first, last = timeseries[0], timeseries[-1]
        for name, key in _ENDPOINT_COUNT_COLUMNS.items():
            totals[name] += max(0.0, float(last.get(key) or 0) - float(first.get(key) or 0))
        total_cost += sum(float(f.get("estimated_cost") or 0) for f in load_features(exp_id))
        any_data = True

    if not any_data:
        return {
            "available": False,
            "detail": f"No timeseries data on disk yet for {experiment_id or 'any experiment'}.",
            "rows": [],
        }

    total_requests = sum(totals.values())
    rows = []
    for name in ("cheap", "medium", "expensive"):
        count = totals[name]
        share = (count / total_requests) if total_requests else None
        apportioned_cost = (total_cost * share) if share is not None else None
        rows.append(
            {
                "endpoint_class": name,
                "request_count": count,
                "request_share": share,
                "apportioned_cost": apportioned_cost,
                "apportioned_cost_per_request": (apportioned_cost / count) if apportioned_cost is not None and count else None,
                "compute_weight_note": ENDPOINT_COMPUTE_WEIGHTS.get(name, {}).get("note"),
            }
        )

    return {
        "available": True,
        "experiment_id": experiment_id,
        "total_requests": total_requests,
        "total_cost": total_cost,
        "rows": rows,
        "cost_apportionment_note": (
            "Cost is not metered per endpoint by the application — this apportions the real, "
            "measured total cost of the selected run(s) across endpoint classes by their share "
            "of real request volume. It is a derived estimate, not an independently measured "
            "per-endpoint cost. 'Relative compute weight' notes are static implementation "
            "constants, not live measurements."
        ),
    }


# --------------------------------------------------------------- PCA -----

def feature_pca(n_components: int = 2) -> dict[str, Any]:
    from sklearn.decomposition import PCA
    from sklearn.preprocessing import StandardScaler

    from models.feature_sets import ABLATION_FEATURE_SETS

    columns = ABLATION_FEATURE_SETS["C_proposed_full"]

    paths = sorted(DATA_FEATURES.glob("*.csv"))  # excludes held_out/ (a subdirectory)
    if not paths:
        return {"available": False, "detail": "No feature data on disk yet.", "points": []}

    frames = []
    for path in paths:
        df = pd.read_csv(path)
        df["experiment_id"] = path.stem
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)

    missing = [c for c in columns if c not in combined.columns]
    if missing:
        return {"available": False, "detail": f"Feature columns missing from disk: {missing}", "points": []}

    subset = combined[[*columns, "experiment_id", "label"]].dropna()
    if len(subset) < n_components + 1:
        return {
            "available": False,
            "detail": f"Only {len(subset)} complete feature rows on disk — need at least {n_components + 1} for PCA.",
            "points": [],
        }

    x = subset[columns].to_numpy(dtype=float)
    scaled = StandardScaler().fit_transform(x)
    pca = PCA(n_components=n_components)
    coords = pca.fit_transform(scaled)

    experiment_ids = subset["experiment_id"].tolist()
    labels = subset["label"].tolist()
    points = [
        {
            "experiment_id": experiment_ids[i],
            "label": int(labels[i]) if labels[i] is not None and not (isinstance(labels[i], float) and math.isnan(labels[i])) else None,
            "pc1": float(coords[i, 0]),
            "pc2": float(coords[i, 1]) if n_components > 1 else None,
        }
        for i in range(len(subset))
    ]

    return {
        "available": True,
        "n_rows": len(subset),
        "n_experiments": subset["experiment_id"].nunique(),
        "explained_variance_ratio": [float(v) for v in pca.explained_variance_ratio_],
        "points": points,
        "is_small_n": len(subset) < 20,
    }


# ------------------------------------------------- detection explanation --

def detection_explanation(experiment_id: str, top_n: int = 8) -> dict[str, Any]:
    """Contributing-factor breakdown for one experiment's most recent
    feature window, driven entirely by real SHAP importances already on
    disk (results/tables/feature_statistics.csv) and real class-conditional
    feature means computed across every saved experiment — never a
    hardcoded "reason" string.
    """
    features = load_features(experiment_id)
    if not features:
        return {"available": False, "detail": f"No feature data on disk for {experiment_id}.", "factors": []}
    this_run = features[-1]

    shap_rows = load_results_table("feature_statistics")
    ranked = sorted(
        (r for r in shap_rows if r.get("mean_abs_shap") is not None),
        key=lambda r: r["mean_abs_shap"],
        reverse=True,
    )[:top_n]
    if not ranked:
        return {"available": False, "detail": "No SHAP feature importances on disk yet — train the detector first.", "factors": []}

    all_rows: list[dict] = []
    for path in sorted(DATA_FEATURES.glob("*.csv")):
        all_rows.extend(pd.read_csv(path).to_dict(orient="records"))
    fc_rows = [r for r in all_rows if r.get("label") == 0]
    edos_rows = [r for r in all_rows if r.get("label") == 1]

    factors = []
    for r in ranked:
        feature = r["feature"]
        this_value = this_run.get(feature)
        fc_mean = _avg(fc_rows, feature)
        edos_mean = _avg(edos_rows, feature)
        direction = None
        if this_value is not None and fc_mean is not None and edos_mean is not None:
            direction = "closer_to_edos" if abs(this_value - edos_mean) < abs(this_value - fc_mean) else "closer_to_flash_crowd"
        factors.append(
            {
                "feature": feature,
                "mean_abs_shap": r["mean_abs_shap"],
                "this_run_value": this_value,
                "flash_crowd_mean": fc_mean,
                "edos_mean": edos_mean,
                "direction": direction,
            }
        )

    return {"available": True, "experiment_id": experiment_id, "factors": factors}
