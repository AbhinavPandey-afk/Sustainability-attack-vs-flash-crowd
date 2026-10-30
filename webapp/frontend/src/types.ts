// Typed models mirroring webapp/backend responses exactly — every field
// here is read from a real artifact on disk or a live health check.
// Nothing is invented on the frontend.

export type ComponentStatus = 'CONNECTED' | 'DEGRADED' | 'UNAVAILABLE'

export interface StatusComponent {
  component: string
  status: ComponentStatus
  detail: string
  [key: string]: unknown
}

export interface SystemStatus {
  kubernetes: StatusComponent & {
    replicas?: number
    ready_replicas?: number
    current_cpu_utilization_pct?: number | null
    min_replicas?: number
    max_replicas?: number
  }
  application: StatusComponent
  prometheus: StatusComponent
  experiment_runner: StatusComponent & { busy: boolean }
  detector: StatusComponent & { n_experiments?: number }
}

export interface LimitationEntry {
  title: string
  detail: string
}

export interface ResearchQuestion {
  question: string
  known_limitations: LimitationEntry[]
  demo_walkthrough: string[]
  proof_of_concept_threshold: number
}

export type ScenarioType = 'flash_crowd' | 'edos' | 'mixed' | 'interleaved' | 'normal'

export interface ExperimentExample {
  experiment_id: string
  scenario_type: ScenarioType
  scenario_label: string
  label: 0 | 1 | null
  duration_seconds: number
  seed: number | null
  has_saved_result: boolean
  was_just_run_this_session: boolean
}

export interface PhaseScheduleEntry {
  index: number
  scenario_type: string
  scenario_file: string
  label: 0 | 1
  planned_duration_seconds: number
  start: number
  end: number
}

export interface ExperimentConfig {
  experiment_id: string
  config_path: string
  experiment: Record<string, unknown>
  detector: Record<string, unknown>
  cost_model: Record<string, unknown>
  replica_sampler: Record<string, unknown>
  prometheus: Record<string, unknown>
  scenario_purpose: string
  scenario: Record<string, unknown> | null
  phases: { scenario_type: string; scenario_file: string; duration_seconds: number; label: 0 | 1 }[] | null
}

export type RunState = 'READY' | 'STARTING' | 'RUNNING' | 'SUMMARIZING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'

export interface RunStatus {
  experiment_id: string
  state: RunState
  duration_seconds?: number
  started_at?: number | null
  elapsed_seconds?: number
  error?: string | null
  sequence?: string[]
  sequence_index?: number
  sequence_total?: number
}

// One row of feature_engineering output — a single time-window observation.
export type FeatureRow = Record<string, number | string | null>

export type TimeseriesRow = Record<string, number | string | null> & { elapsed_seconds: number }

export type LocustHistoryRow = Record<string, number | string | null> & { elapsed_seconds: number }

export interface ExperimentMetadata {
  experiment_id: string
  timestamp: string
  git_commit: string
  config_file: string
  seed: number | null
  label?: 0 | 1
  duration_seconds: number
  host: string
  n_raw_samples: number
  n_feature_rows: number
  validation: { ok: boolean; errors: string[]; warnings: string[] }
  phases?: PhaseScheduleEntry[]
}

export interface ExperimentResult {
  experiment_id: string
  source: 'just_ran' | 'saved_sample'
  metadata: ExperimentMetadata
  features: FeatureRow[]
  timeseries: TimeseriesRow[]
  locust_history: LocustHistoryRow[]
}

export interface HistoryEntry {
  experiment_id: string
  metadata: ExperimentMetadata
  label: 0 | 1 | null
  scenario_type: ScenarioType | string | null
  scenario_label: string
  summary: {
    request_rate: number | null
    estimated_cost: number | null
    cost_per_request: number | null
    max_replica_count: number | null
    expensive_endpoint_ratio: number | null
  }
}

export interface ClassificationMetrics {
  tp: number
  tn: number
  fp: number
  fn: number
  accuracy: number
  precision: number
  recall: number
  specificity: number
  f1: number
  edos_detection_rate: number
  flash_crowd_false_positive_rate: number
  roc_auc: number
  pr_auc: number
  model: string
}

// results/tables/baseline_results.csv — one row per baseline detector
// (rate_limiter, volumetric_detector), read verbatim off disk.
export interface BaselineResultRow {
  detector: string
  threshold: number | null
  attack_detected: boolean | null
  false_positive_on_flash_crowd: boolean | null
  false_positive_rate: number | null
  detection_latency: number | null
  cost_before_detection: number | null
  tp: number | null
  fn: number | null
  fp: number | null
  tn: number | null
  tpr: number | null
  fpr: number | null
  precision: number | null
  recall: number | null
  f1: number | null
}

export interface DetectionSummary {
  available: boolean
  detail?: string
  summary?: {
    n_total_rows: number
    n_experiments: number
    window_seconds_used: number
    train_experiments: string[]
    val_experiments: string[]
    test_experiments: string[]
    models: Record<string, ClassificationMetrics>
    baselines: {
      rate_limiter: Record<string, unknown>
      volumetric_detector: Record<string, unknown>
    }
  }
  lightgbm_metrics?: ClassificationMetrics
  baseline_metrics?: Record<string, Record<string, unknown>>
  // results/tables/ablation_results.csv and model_comparison.csv share
  // ClassificationMetrics's exact column set — `model` holds the feature-set
  // or model name being compared (e.g. "A_volume_only", "LightGBM_C_proposed_full").
  ablation_results?: ClassificationMetrics[]
  model_comparison?: ClassificationMetrics[]
  baseline_results?: BaselineResultRow[]
  is_proof_of_concept?: boolean
}

export type HypothesisVerdict = 'SUPPORTED' | 'NOT SUPPORTED' | 'INCONCLUSIVE' | 'INSUFFICIENT DATA' | 'REJECTED' | 'NOT REJECTED'

export interface Hypothesis {
  id: string
  text: string
  verdict: HypothesisVerdict
  reason: string
  evidence: Record<string, unknown>
}

export interface Hypotheses {
  h1: Hypothesis
  h0: Hypothesis
  h2: Hypothesis
}

export interface HeldOutEvaluationEntry {
  cascade_lightgbm: ClassificationMetrics & { n_windows: number; label_distribution: Record<string, number> }
  rate_limiter?: Record<string, unknown>
  volumetric_detector?: Record<string, unknown>
}

export interface MixedEvaluationResponse {
  available: boolean
  results: Record<string, HeldOutEvaluationEntry>
}

export interface EndpointCostRow {
  endpoint_class: 'cheap' | 'medium' | 'expensive'
  request_count: number
  request_share: number | null
  apportioned_cost: number | null
  apportioned_cost_per_request: number | null
  compute_weight_note: string | null
}

export interface EndpointHeatmapResponse {
  available: boolean
  detail?: string
  experiment_id?: string | null
  total_requests?: number
  total_cost?: number
  rows: EndpointCostRow[]
  cost_apportionment_note?: string
}

export interface DetectionExplanationFactor {
  feature: string
  mean_abs_shap: number
  this_run_value: number | null
  flash_crowd_mean: number | null
  edos_mean: number | null
  direction: 'closer_to_edos' | 'closer_to_flash_crowd' | null
}

export interface DetectionExplanation {
  available: boolean
  detail?: string
  experiment_id?: string
  factors?: DetectionExplanationFactor[]
}

export interface PredictionWindow {
  window_end: number | null
  probability_edos: number
  predicted_label: 0 | 1
}

export interface LiveImpact {
  kubernetes_available: boolean
  replicas: number | null
  min_replicas: number | null
  max_replicas: number | null
  cpu_utilization_pct: number | null
  prometheus_available: boolean
  request_rate_total: number | null
  request_rate_by_class: Record<string, number | null>
  request_delta_by_class: Record<string, number> | null
  expensive_endpoint_ratio: number | null
  cost_rate_per_minute: number | null
  estimated_cost_session: number
  replica_cost_per_minute: number
}

export interface PredictionResponse {
  available: boolean
  detail?: string
  experiment_id?: string
  threshold?: number
  windows?: PredictionWindow[]
  final_probability_edos?: number
  final_predicted_label?: 0 | 1
}

// The real stored output of experiments/match_quality.py's matched-signature
// calibration flow (data/experiments/<candidate>/match_report.json) — e.g.
// EDOS_MATCHED_E6_001 calibrated against FC_HARDNEG_001. Never recomputed
// on the frontend; read exactly as stored.
export interface FiguresListResponse {
  figures: string[]
}

export interface ShapFeatureRow {
  feature: string
  mean_abs_shap: number | null
  [key: string]: unknown
}

export interface ShapSummaryResponse {
  feature_importance: ShapFeatureRow[]
  summary_figure_available: boolean
  all_zero: boolean
}

export interface PcaPoint {
  experiment_id: string
  label: 0 | 1 | null
  pc1: number
  pc2: number | null
}

export interface PcaResponse {
  available: boolean
  detail?: string
  points: PcaPoint[]
}

export interface MatchReport {
  reference_experiment_id: string
  candidate_experiment_id: string
  tolerances: Record<string, number>
  request_rate_delta_pct: number | null
  cpu_delta_pct: number | null
  peak_replica_delta_pct: number | null
  mean_replica_delta_pct: number | null
  replica_minutes_delta_pct: number | null
  total_cost_delta_pct: number | null
  cost_per_request_delta_pct: number | null
  primary_match_axes: string[]
  axis_matched: Record<string, boolean>
  match_status: 'MATCHED' | 'NOT_MATCHED' | 'EXHAUSTED' | string
}
