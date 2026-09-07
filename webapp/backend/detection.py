"""Derives hypothesis verdicts from the actual results/metrics/*.json
produced by experiments/summarize_results.py. Never hardcodes a verdict —
every SUPPORTED/NOT SUPPORTED/INCONCLUSIVE/INSUFFICIENT DATA label is
computed from the numbers in front of it, and the proof-of-concept data
scale (CLAUDE.md section 5 / docs/experiment_protocol.md §5) always caps
the verdict at INSUFFICIENT DATA regardless of which way the numbers point.
"""
from __future__ import annotations

from config import PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD
from data_access import load_features, load_results_metrics


def _pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100, 1)


def evaluate_h1(summary: dict) -> dict:
    models = summary.get("models", {})
    proposed = models.get("C_proposed_full")
    volume_only = models.get("A_volume_only")
    n_experiments = summary.get("n_experiments", 0)

    evidence: dict = {
        "n_experiments": n_experiments,
        "proposed_recall": proposed.get("recall") if proposed else None,
        "proposed_flash_crowd_fpr": proposed.get("flash_crowd_false_positive_rate") if proposed else None,
        "volume_only_flash_crowd_fpr": volume_only.get("flash_crowd_false_positive_rate") if volume_only else None,
    }

    fpr_reduction = None
    if proposed and volume_only:
        fpr_a = volume_only.get("flash_crowd_false_positive_rate")
        fpr_c = proposed.get("flash_crowd_false_positive_rate")
        if fpr_a not in (None, 0):
            fpr_reduction = (fpr_a - fpr_c) / fpr_a
    evidence["flash_crowd_fpr_reduction_pct"] = _pct(fpr_reduction)

    if n_experiments < PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD or proposed is None or volume_only is None:
        verdict = "INSUFFICIENT DATA"
        reason = (
            f"Only {n_experiments} labeled experiments exist (proof-of-concept scale). "
            "CLAUDE.md's 90% recall / 30% FPR-reduction targets are research targets, not "
            "something a 6-experiment run can establish or refute with statistical confidence."
        )
    else:
        recall_ok = (proposed.get("recall") or 0) >= 0.90
        fpr_ok = fpr_reduction is not None and fpr_reduction >= 0.30
        if recall_ok and fpr_ok:
            verdict = "SUPPORTED"
            reason = "Proposed detector met both the recall and FPR-reduction targets on held-out data."
        else:
            verdict = "NOT SUPPORTED"
            reason = "Proposed detector did not meet one or both targets on held-out data."

    return {
        "id": "H1",
        "text": (
            "Under comparable request-volume conditions, a detector using cost and scaling "
            "behaviour can achieve at least 90% EDoS recall while reducing the false-positive "
            "rate on legitimate flash crowds by at least 30% compared with a volume-only baseline."
        ),
        "verdict": verdict,
        "reason": reason,
        "evidence": evidence,
    }


def evaluate_h0(h1_verdict: str) -> dict:
    if h1_verdict == "SUPPORTED":
        verdict = "REJECTED"
        reason = "H1 was supported by the (proof-of-concept-scale) data, so the null is rejected at this scale."
    elif h1_verdict == "NOT SUPPORTED":
        verdict = "NOT REJECTED"
        reason = "H1 was not supported by the data available, so H0 cannot be rejected."
    else:
        verdict = "INSUFFICIENT DATA"
        reason = "Not enough experiments exist yet to accept or reject the null hypothesis."
    return {
        "id": "H0",
        "text": (
            "Cost and scaling behaviour do not provide a statistically significant improvement "
            "over a volume-only baseline for distinguishing EDoS attacks from legitimate flash crowds."
        ),
        "verdict": verdict,
        "reason": reason,
        "evidence": {},
    }


def evaluate_h2() -> dict:
    rows = []
    for experiment_id in _feature_experiment_ids():
        rows.extend(load_features(experiment_id))

    fc_rows = [r for r in rows if r.get("label") == 0]
    edos_rows = [r for r in rows if r.get("label") == 1]
    n_experiments = len({r.get("experiment_id") for r in rows})

    def _avg(records: list[dict], key: str) -> float | None:
        values = [r[key] for r in records if r.get(key) is not None]
        return sum(values) / len(values) if values else None

    evidence = {
        "n_experiments": n_experiments,
        "fc_mean_cost_per_request": _avg(fc_rows, "cost_per_request"),
        "edos_mean_cost_per_request": _avg(edos_rows, "cost_per_request"),
        "fc_mean_cost_to_traffic_ratio": _avg(fc_rows, "cost_to_traffic_ratio"),
        "edos_mean_cost_to_traffic_ratio": _avg(edos_rows, "cost_to_traffic_ratio"),
        "fc_mean_request_rate": _avg(fc_rows, "request_rate"),
        "edos_mean_request_rate": _avg(edos_rows, "request_rate"),
    }

    if n_experiments < PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD or not fc_rows or not edos_rows:
        verdict = "INSUFFICIENT DATA"
        reason = f"Only {n_experiments} labeled experiments exist — directional only, not statistically meaningful."
    else:
        cpr_higher = (evidence["edos_mean_cost_per_request"] or 0) > (evidence["fc_mean_cost_per_request"] or 0)
        ratio_higher = (evidence["edos_mean_cost_to_traffic_ratio"] or 0) > (evidence["fc_mean_cost_to_traffic_ratio"] or 0)
        verdict = "SUPPORTED" if (cpr_higher and ratio_higher) else "NOT SUPPORTED"
        reason = "Computed directly from feature-window means across all labeled experiments."

    return {
        "id": "H2",
        "text": (
            "EDoS traffic produces a higher cost-per-request and cost-to-traffic ratio than "
            "legitimate flash-crowd traffic at comparable request volumes."
        ),
        "verdict": verdict,
        "reason": reason,
        "evidence": evidence,
    }


def _feature_experiment_ids() -> list[str]:
    from config import DATA_FEATURES

    if not DATA_FEATURES.exists():
        return []
    return sorted(p.stem for p in DATA_FEATURES.glob("*.csv"))


def evaluate_hypotheses() -> dict:
    summary = load_results_metrics("experiment_summary")
    if summary is None:
        insufficient = "INSUFFICIENT DATA"
        return {
            "h1": {"id": "H1", "verdict": insufficient, "reason": "No trained-model results on disk yet.", "evidence": {}},
            "h0": {"id": "H0", "verdict": insufficient, "reason": "No trained-model results on disk yet.", "evidence": {}},
            "h2": {"id": "H2", "verdict": insufficient, "reason": "No feature data on disk yet.", "evidence": {}},
        }
    h1 = evaluate_h1(summary)
    h0 = evaluate_h0(h1["verdict"])
    h2 = evaluate_h2()
    return {"h1": h1, "h0": h0, "h2": h2}
