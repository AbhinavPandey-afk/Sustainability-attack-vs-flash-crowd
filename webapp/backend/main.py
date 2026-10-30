"""CASCADE dashboard backend.

A thin, read-mostly FastAPI control/observation layer over the existing
research pipeline (app/, traffic/, experiments/, feature_engineering/,
models/, baselines/). It does not reimplement any of that pipeline — it
imports and calls it directly (webapp/backend/runner.py) or reads the
artifacts it already writes to disk (webapp/backend/data_access.py).
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent.parent
for path in (BACKEND_DIR, REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import io  # noqa: E402
import zipfile  # noqa: E402

from fastapi import Body, FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, StreamingResponse  # noqa: E402

import analytics  # noqa: E402
import data_access  # noqa: E402
import live_impact  # noqa: E402
import prediction  # noqa: E402
import scenario_builder  # noqa: E402
import system_status  # noqa: E402
from config import (  # noqa: E402
    DATA_EXPERIMENTS,
    DATA_FEATURES,
    DATA_RAW,
    DEMO_WALKTHROUGH,
    EXPERIMENTS_CONFIGS,
    KNOWN_LIMITATIONS,
    PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD,
    RESULTS_FIGURES,
    SCENARIO_LABEL_NAME,
    SPECIAL_SCENARIO_LABELS,
)
from detection import evaluate_hypotheses  # noqa: E402
from runner import runner_state  # noqa: E402

app = FastAPI(title="CASCADE Dashboard API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        # The app/ storefront demo UI (storefront.py) polls
        # /api/storefront/impact cross-origin from the target application's
        # own origin (DEFAULT_APP_HOST) — not the dashboard's own origin.
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- system --

@app.get("/api/system/status")
def get_system_status():
    return system_status.full_status(runner_state.is_busy())


@app.get("/api/storefront/impact")
def get_storefront_impact():
    """Polled by the app/ storefront demo UI's live impact strip
    (storefront.py / static/store.js) — real replicas/CPU/request-rate
    reads plus a live replica-minute cost accrual, see live_impact.py."""
    return live_impact.get_live_impact()


@app.get("/api/system/research-question")
def get_research_question():
    return {
        "question": (
            "Can cost, scaling and application-behaviour signals distinguish EDoS attacks "
            "from legitimate flash crowds when traffic volume alone cannot?"
        ),
        "known_limitations": KNOWN_LIMITATIONS,
        "demo_walkthrough": DEMO_WALKTHROUGH,
        "proof_of_concept_threshold": PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD,
    }


# ----------------------------------------------------------- experiments --

def _scenario_label(scenario_type: str | None, label: int | None) -> str:
    if scenario_type in SPECIAL_SCENARIO_LABELS:
        return SPECIAL_SCENARIO_LABELS[scenario_type]
    return SCENARIO_LABEL_NAME.get(label, "Unknown")


@app.get("/api/experiments/examples")
def list_examples():
    out = []
    for entry in data_access.list_experiment_configs():
        exp = entry["config"]["experiment"]
        experiment_id = exp["name"]
        scenario_type = exp["scenario_type"]
        label = exp.get("label")
        out.append(
            {
                "experiment_id": experiment_id,
                "scenario_type": scenario_type,
                "scenario_label": _scenario_label(scenario_type, label),
                "label": label,
                "duration_seconds": exp.get("duration_seconds"),
                "seed": exp.get("seed"),
                "has_saved_result": data_access.has_saved_result(experiment_id),
                "was_just_run_this_session": runner_state.was_just_run(experiment_id),
            }
        )
    return out


@app.get("/api/experiments")
def list_history():
    ids = data_access.list_all_experiment_ids()
    out = []
    for experiment_id in ids:
        metadata = data_access.load_metadata(experiment_id)
        config = data_access.load_experiment_config(experiment_id)
        features = data_access.load_features(experiment_id)
        last_row = features[-1] if features else {}
        scenario_type = config["experiment"]["scenario_type"] if config else None
        label = metadata.get("label") if metadata else None
        out.append(
            {
                "experiment_id": experiment_id,
                "metadata": metadata,
                "label": label,
                "scenario_type": scenario_type,
                "scenario_label": _scenario_label(scenario_type, label),
                "summary": {
                    "request_rate": last_row.get("request_rate"),
                    "estimated_cost": last_row.get("estimated_cost"),
                    "cost_per_request": last_row.get("cost_per_request"),
                    "max_replica_count": last_row.get("max_replica_count"),
                    "expensive_endpoint_ratio": last_row.get("expensive_endpoint_ratio"),
                },
            }
        )
    return out


@app.get("/api/experiments/{experiment_id}/config")
def get_config(experiment_id: str):
    config = data_access.load_experiment_config(experiment_id)
    if config is None:
        raise HTTPException(404, f"No config found for {experiment_id}")
    return config


@app.get("/api/experiments/{experiment_id}/result")
def get_result(experiment_id: str):
    metadata = data_access.load_metadata(experiment_id)
    if metadata is None:
        raise HTTPException(404, f"No saved result for {experiment_id} yet")
    return {
        "experiment_id": experiment_id,
        "source": "just_ran" if runner_state.was_just_run(experiment_id) else "saved_sample",
        "metadata": metadata,
        "features": data_access.load_features(experiment_id),
        "timeseries": data_access.load_timeseries(experiment_id),
        "locust_history": data_access.load_locust_history(experiment_id),
    }


@app.get("/api/experiments/{experiment_id}/match-report")
def get_match_report(experiment_id: str):
    """Stored matched-signature calibration report (real measured deltas
    against a reference experiment), if this experiment was produced
    through experiments/match_quality.py's calibration flow — e.g.
    EDOS_MATCHED_E6_001. Never recomputed here."""
    report = data_access.load_match_report(experiment_id)
    if report is None:
        raise HTTPException(404, f"No stored match report for {experiment_id}")
    return report


@app.post("/api/experiments/{experiment_id}/run")
def start_run(experiment_id: str):
    try:
        started = runner_state.start(experiment_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not started:
        raise HTTPException(409, "Another experiment run is already in progress")
    return {"experiment_id": experiment_id, "status": "starting"}


@app.get("/api/experiments/{experiment_id}/run-status")
def get_run_status(experiment_id: str):
    status = runner_state.status(experiment_id)
    if status is None:
        return {"experiment_id": experiment_id, "state": "READY"}
    return status


@app.post("/api/experiments/{experiment_id}/stop")
def stop_run(experiment_id: str):
    stopped = runner_state.stop()
    return {"experiment_id": experiment_id, "stopped": stopped}


# -------------------------------------------------------------- simulator --

# NOTE: these fixed-path routes (/api/simulator/run/start, /api/simulator/run/stop)
# must be registered BEFORE the /api/simulator/{kind}/... routes below —
# FastAPI/Starlette matches routes in registration order, so a parameterized
# path declared first would otherwise greedily match "run" as kind and this
# route would never be reached (a real bug found via live browser testing).

@app.post("/api/simulator/run/start")
def start_unified_simulator(params: dict = Body(default={})):
    """Traffic Classification Simulator (unified): one form, one real
    parameter set — the operator never asserts "this is an attack" or
    "this is a flash crowd". scenario_builder.build_unified_config derives
    only a descriptive bookkeeping label from the configured weights; the
    classification shown to the user always comes from the real trained
    detector (see GET /api/detection/predict/{experiment_id}) scoring this
    run's real measured features. Same isolation as the legacy per-kind
    routes below: features land under data/features/adhoc/, kept out of
    the trained model's train/test split."""
    app_status = system_status.check_app()
    if app_status["status"] == system_status.STATUS_UNAVAILABLE:
        raise HTTPException(503, f"Live application not reachable — cannot start a real simulation ({app_status['detail']}).")

    experiment_id, config_path = scenario_builder.build_unified_config(params or {})

    try:
        started = runner_state.start(
            experiment_id,
            config_path=config_path,
            output_features_dir=DATA_FEATURES / "adhoc",
            skip_retrain=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not started:
        raise HTTPException(409, "Another experiment run is already in progress")
    return {"experiment_id": experiment_id, "status": "starting"}


@app.post("/api/simulator/run/stop")
def stop_unified_simulator():
    stopped = runner_state.stop()
    return {"stopped": stopped}


@app.post("/api/simulator/{kind}/start")
def start_simulator(kind: str, params: dict = Body(default={})):
    """Attack Simulator / Flash Crowd Simulator: builds a real, ad-hoc
    scenario+experiment config from user-supplied parameters and runs it
    through the same live pipeline as any preset experiment (real traffic
    against the real cascade cluster) — never a client-side fake animation.
    Features are written to data/features/adhoc/, kept out of the trained
    model's train/test split (see data_access.load_features)."""
    if kind not in ("attack", "flash-crowd"):
        raise HTTPException(404, f"Unknown simulator kind: {kind!r}")

    app_status = system_status.check_app()
    if app_status["status"] == system_status.STATUS_UNAVAILABLE:
        raise HTTPException(503, f"Live application not reachable — cannot start a real simulation ({app_status['detail']}).")

    builder = scenario_builder.build_attack_config if kind == "attack" else scenario_builder.build_flash_crowd_config
    experiment_id, config_path = builder(params or {})

    try:
        started = runner_state.start(
            experiment_id,
            config_path=config_path,
            output_features_dir=DATA_FEATURES / "adhoc",
            skip_retrain=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    if not started:
        raise HTTPException(409, "Another experiment run is already in progress")
    return {"experiment_id": experiment_id, "status": "starting"}


@app.post("/api/simulator/{kind}/stop")
def stop_simulator(kind: str):
    if kind not in ("attack", "flash-crowd"):
        raise HTTPException(404, f"Unknown simulator kind: {kind!r}")
    stopped = runner_state.stop()
    return {"stopped": stopped}


# ------------------------------------------------------------------ demo --

DEMO_SEQUENCE = ["FC_VIRAL_001", "EDOS_001", "INTERLEAVED_001"]


@app.post("/api/demo/run")
def start_demo(experiment_ids: list[str] | None = Body(default=None)):
    sequence = experiment_ids or DEMO_SEQUENCE
    for experiment_id in sequence:
        if not (EXPERIMENTS_CONFIGS / f"{experiment_id}.yaml").exists():
            raise HTTPException(404, f"No experiment config for {experiment_id}")
    started = runner_state.start_sequence(sequence)
    if not started:
        raise HTTPException(409, "Another experiment run is already in progress")
    return {"sequence": sequence, "status": "starting"}


@app.get("/api/demo/status")
def get_demo_status():
    status = runner_state.status()
    if status is None:
        return {"state": "READY"}
    return status


# ------------------------------------------------------------- detection --

@app.get("/api/detection/summary")
def get_detection_summary():
    summary = data_access.load_results_metrics("experiment_summary")
    lightgbm = data_access.load_results_metrics("lightgbm_metrics")
    baselines = data_access.load_results_metrics("baseline_metrics")
    if summary is None:
        return {
            "available": False,
            "detail": "No trained-model results on disk yet. Run at least one experiment of each class.",
        }
    return {
        "available": True,
        "summary": summary,
        "lightgbm_metrics": lightgbm,
        "baseline_metrics": baselines,
        "ablation_results": data_access.load_results_table("ablation_results"),
        "model_comparison": data_access.load_results_table("model_comparison"),
        "baseline_results": data_access.load_results_table("baseline_results"),
        "is_proof_of_concept": summary.get("n_experiments", 0) < PROOF_OF_CONCEPT_EXPERIMENT_THRESHOLD,
    }


@app.get("/api/detection/hypotheses")
def get_hypotheses():
    return evaluate_hypotheses()


@app.get("/api/detection/mixed-evaluation")
def get_mixed_evaluation():
    """Evaluation of the already-trained detector under E3 (MIX_001,
    attack + legitimate traffic simultaneously) and E4 (INTERLEAVED_001,
    alternating windows) — evaluating with both present, not merely in
    isolation. See experiments/summarize_results.py::evaluate_held_out and
    docs/experiment_protocol.md section 8."""
    evaluation = data_access.load_results_metrics("mixed_interleaved_evaluation")
    return {"available": evaluation is not None and len(evaluation) > 0, "results": evaluation or {}}


@app.get("/api/detection/shap")
def get_shap():
    feature_stats = data_access.load_results_table("feature_statistics")
    ranked = sorted(
        [r for r in feature_stats if r.get("mean_abs_shap") is not None],
        key=lambda r: r["mean_abs_shap"],
        reverse=True,
    )
    figures = data_access.figures_available()
    all_zero = bool(ranked) and all((r.get("mean_abs_shap") or 0) == 0 for r in ranked)
    return {
        "feature_importance": ranked,
        "summary_figure_available": "shap_summary.png" in figures,
        "all_zero": all_zero,
    }


@app.get("/api/results/figures")
def list_figures():
    return {"figures": data_access.figures_available()}


@app.get("/api/results/figures/{name}")
def get_figure(name: str):
    if "/" in name or "\\" in name or not name.endswith(".png"):
        raise HTTPException(404, "Figure not found")
    path = (RESULTS_FIGURES / name).resolve()
    if not path.is_file() or path.parent != RESULTS_FIGURES.resolve():
        raise HTTPException(404, "Figure not found")
    return FileResponse(path, media_type="image/png")


# ------------------------------------------------------------ analytics --

@app.get("/api/analytics/endpoint-heatmap")
def get_endpoint_heatmap(experiment_id: str | None = None):
    return analytics.endpoint_cost_heatmap(experiment_id)


@app.get("/api/analytics/pca")
def get_pca():
    return analytics.feature_pca()


@app.get("/api/analytics/explain/{experiment_id}")
def get_explanation(experiment_id: str):
    return analytics.detection_explanation(experiment_id)


@app.get("/api/detection/predict/{experiment_id}")
def get_prediction(experiment_id: str):
    """Live inference for one completed run, using the persisted CASCADE
    model (results/models/cascade_lightgbm.joblib) — real model, real
    feature windows, never a fabricated confidence score."""
    return prediction.predict_experiment(experiment_id)


# --------------------------------------------------------------- export --

@app.get("/api/experiments/{experiment_id}/export.zip")
def export_experiment(experiment_id: str):
    """Zips the same real on-disk artifacts every other endpoint already
    reads (metadata, features CSV, config, raw timeseries/locust CSVs) —
    no transformation, nothing regenerated."""
    if not data_access.has_saved_result(experiment_id):
        raise HTTPException(404, f"No saved result for {experiment_id}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        metadata_path = DATA_EXPERIMENTS / experiment_id / "metadata.json"
        if metadata_path.exists():
            zf.write(metadata_path, arcname="metadata.json")

        features_path = DATA_FEATURES / f"{experiment_id}.csv"
        if not features_path.exists():
            features_path = DATA_FEATURES / "held_out" / f"{experiment_id}.csv"
        if features_path.exists():
            zf.write(features_path, arcname="features.csv")

        config_path = EXPERIMENTS_CONFIGS / f"{experiment_id}.yaml"
        if config_path.exists():
            zf.write(config_path, arcname="config.yaml")

        raw_dir = DATA_RAW / experiment_id
        if raw_dir.exists():
            for path in raw_dir.rglob("*.csv"):
                zf.write(path, arcname=f"raw/{path.relative_to(raw_dir)}")

    buf.seek(0)
    headers = {"Content-Disposition": f'attachment; filename="{experiment_id}.zip"'}
    return StreamingResponse(buf, media_type="application/zip", headers=headers)
