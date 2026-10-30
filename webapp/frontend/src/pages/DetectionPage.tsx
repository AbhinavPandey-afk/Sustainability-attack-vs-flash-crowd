import { useEffect, useState } from 'react'
import { api } from '../api'
import { ConfusionMatrix } from '../components/ConfusionMatrix'
import { HypothesisCard } from '../components/HypothesisCard'
import { MixedInterleavedEvaluation } from '../components/MixedInterleavedEvaluation'
import { fmtPct } from '../format'
import type { BaselineResultRow, ClassificationMetrics, DetectionSummary, FiguresListResponse, Hypotheses, MixedEvaluationResponse } from '../types'

interface Row {
  name: string
  accuracy: number | null
  precision: number | null
  recall: number | null
  specificity: number | null
  f1: number | null
  fpr: number | null
}

function modelToRow(name: string, m: ClassificationMetrics): Row {
  return {
    name,
    accuracy: m.accuracy,
    precision: m.precision,
    recall: m.recall,
    specificity: m.specificity,
    f1: m.f1,
    fpr: m.flash_crowd_false_positive_rate,
  }
}

function baselineToRow(b: BaselineResultRow): Row {
  return {
    name: b.detector,
    accuracy: null,
    precision: b.precision,
    recall: b.recall ?? b.tpr,
    specificity: null,
    f1: b.f1,
    fpr: b.fpr ?? b.false_positive_rate,
  }
}

const FIGURE_CANDIDATES = [
  { name: 'confusion_matrix.png', title: 'Confusion Matrix' },
  { name: 'roc_curve.png', title: 'ROC Curve' },
  { name: 'pr_curve.png', title: 'Precision-Recall Curve' },
]

export function DetectionPage() {
  const [detection, setDetection] = useState<DetectionSummary | null>(null)
  const [hypotheses, setHypotheses] = useState<Hypotheses | null>(null)
  const [mixedEval, setMixedEval] = useState<MixedEvaluationResponse | null>(null)
  const [figures, setFigures] = useState<FiguresListResponse | null>(null)

  useEffect(() => {
    api.detectionSummary().then(setDetection).catch(() => setDetection(null))
    api.hypotheses().then(setHypotheses).catch(() => setHypotheses(null))
    api.mixedEvaluation().then(setMixedEval).catch(() => setMixedEval(null))
    api.figures().then(setFigures).catch(() => setFigures(null))
  }, [])

  if (!detection) return <p className="empty-note">Loading detector evaluation…</p>

  if (!detection.available) {
    return (
      <div>
        <div className="page-title">
          <h2>Detection</h2>
        </div>
        <p className="empty-note">{detection.detail ?? 'No trained-model results on disk yet.'}</p>
      </div>
    )
  }

  const proposed = detection.summary?.models?.C_proposed_full ?? detection.lightgbm_metrics
  const rows: Row[] = [
    ...(detection.baseline_results ?? []).map(baselineToRow),
    ...(proposed ? [modelToRow('CASCADE (LightGBM, C_proposed_full)', proposed)] : []),
  ]
  const availableFigures = new Set(figures?.figures ?? [])

  return (
    <div>
      <div className="page-title">
        <h2>Detection</h2>
        {detection.is_proof_of_concept && <span className="badge badge-poc">Proof of Concept Scale</span>}
      </div>
      <p className="page-subtitle">
        Volume-only and volumetric-anomaly baselines compared against the proposed CASCADE LightGBM detector
        (cost + scaling + application-behaviour + traffic features), on the project's held-out experiment-level
        test split.
      </p>

      <div className="section">
        <div className="section-title">Baseline vs Proposed Detector</div>
        {rows.length === 0 ? (
          <p className="empty-note">No baseline or model evaluation results on disk yet.</p>
        ) : (
          <div className="card table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Detector</th>
                  <th className="num">Accuracy</th>
                  <th className="num">Precision</th>
                  <th className="num">Recall / EDoS TPR</th>
                  <th className="num">Specificity</th>
                  <th className="num">F1</th>
                  <th className="num">Flash-Crowd FPR</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.name}>
                    <td style={{ fontFamily: 'var(--mono)' }}>{r.name}</td>
                    <td className="num">{fmtPct(r.accuracy)}</td>
                    <td className="num">{fmtPct(r.precision)}</td>
                    <td className="num">{fmtPct(r.recall)}</td>
                    <td className="num">{fmtPct(r.specificity)}</td>
                    <td className="num">{fmtPct(r.f1)}</td>
                    <td className="num">{fmtPct(r.fpr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {detection.summary && (
          <p className="note-inline" style={{ marginTop: 10 }}>
            Evaluated on {detection.summary.test_experiments.length} held-out test experiment
            {detection.summary.test_experiments.length === 1 ? '' : 's'} ({detection.summary.n_total_rows} feature
            windows), {detection.summary.window_seconds_used}s windows — see docs/experiment_protocol.md for the
            full train/val/test split.
          </p>
        )}
      </div>

      <div className="section">
        <div className="section-title">Confusion Matrix — CASCADE (Proposed)</div>
        <div className="card">
          <ConfusionMatrix metrics={proposed} />
          {availableFigures.has('confusion_matrix.png') && (
            <img className="figure-img" style={{ marginTop: 14, maxWidth: 420 }} src={api.figureUrl('confusion_matrix.png')} alt="Confusion matrix" />
          )}
        </div>
      </div>

      <div className="section">
        <div className="section-title">Research Hypotheses</div>
        {hypotheses ? (
          <div className="grid grid-3">
            <HypothesisCard hypothesis={hypotheses.h1} />
            <HypothesisCard hypothesis={hypotheses.h0} />
            <HypothesisCard hypothesis={hypotheses.h2} />
          </div>
        ) : (
          <p className="empty-note">Loading hypothesis evaluation…</p>
        )}
      </div>

      <div className="section">
        <div className="section-title">E3/E4 Held-Out Evaluation — Mixed &amp; Interleaved Traffic</div>
        <MixedInterleavedEvaluation evaluation={mixedEval} />
      </div>

      <div className="section">
        <div className="section-title">Result Figures</div>
        <div className="grid grid-2">
          {FIGURE_CANDIDATES.filter((f) => f.name !== 'confusion_matrix.png').map((f) =>
            availableFigures.has(f.name) ? (
              <div key={f.name} className="card">
                <h4 style={{ fontSize: 13, marginBottom: 8 }}>{f.title}</h4>
                <img className="figure-img" src={api.figureUrl(f.name)} alt={f.title} />
              </div>
            ) : (
              <div key={f.name} className="card">
                <h4 style={{ fontSize: 13, marginBottom: 8 }}>{f.title}</h4>
                <p className="empty-note">Not yet generated — run experiments/summarize_results.py.</p>
              </div>
            ),
          )}
        </div>
      </div>

      <p className="footer-note" style={{ marginTop: 40 }}>
        These metrics are computed on a small, project-scale held-out test split — treat them as proof-of-concept
        evidence, not a claim of population-level generalization.
      </p>
    </div>
  )
}
