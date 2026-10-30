import { useEffect, useMemo, useState } from 'react'
import { api } from '../api'
import { ComparisonTable } from '../components/ComparisonTable'
import type { ComparisonRowSpec } from '../components/ComparisonTable'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { fmtNum, fmtPct } from '../format'
import { CHART_EDOS, CHART_FC } from '../theme'
import { computeComparisonMetrics, cumulativeCostSeries } from '../summary'
import type { ComparisonMetrics } from '../summary'
import type {
  DetectionSummary,
  ExperimentConfig,
  ExperimentResult,
  HistoryEntry,
  MatchReport,
  PredictionResponse,
} from '../types'

// This page reads only already-collected, previously-run experiment
// artifacts through the existing read-only APIs (api.history/result/config/
// predict/matchReport/detectionSummary) — see webapp/backend/data_access.py.
// It never starts a Locust/Kubernetes/Prometheus run. The live simulator
// backend (scenario_builder.build_unified_config, /api/simulator/run/*)
// is untouched and still available for development use.

type Mode = 'standard' | 'matched' | 'stealth'

const MODE_LABELS: Record<Mode, string> = {
  standard: 'Standard',
  matched: 'Matched Infrastructure',
  stealth: 'Stealth EDoS',
}

const DEFAULT_FC_ID = 'FC_HARDNEG_001'
const DEFAULT_EDOS_STANDARD_ID = 'EDOS_001'
const DEFAULT_EDOS_MATCHED_ID = 'EDOS_MATCHED_E6_001'
const DEFAULT_EDOS_STEALTH_ID = 'EDOS_STEALTH_001'

const FC_SCENARIO_TYPES = new Set(['flash_crowd', 'flash_crowd_cohort_mixed'])

const isEdos = (e: HistoryEntry) => e.scenario_type === 'edos'
const isFlashCrowd = (e: HistoryEntry) => !!e.scenario_type && FC_SCENARIO_TYPES.has(e.scenario_type)
const isStealth = (e: HistoryEntry) => e.experiment_id.startsWith('EDOS_STEALTH')
const isMatchedCandidate = (e: HistoryEntry) => e.experiment_id.startsWith('EDOS_MATCHED')

function prettyFeatureName(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const O1_ROWS: ComparisonRowSpec[] = [
  { key: 'requestRate', label: 'Request Rate (req/s)', format: 'num', digits: 2 },
  { key: 'peakReplicas', label: 'Peak Replicas', format: 'num', digits: 0 },
  { key: 'meanReplicas', label: 'Mean Replicas', format: 'num', digits: 2 },
  { key: 'costPerRequest', label: 'Cost / Request', format: 'num', digits: 5 },
  { key: 'estimatedCost', label: 'Total Cost (units)', format: 'num', digits: 4 },
]

const O1_MATCH_AXES: (keyof ComparisonMetrics)[] = ['meanReplicas', 'peakReplicas', 'estimatedCost']

const O2_ROWS: { key: keyof ComparisonMetrics; label: string }[] = [
  { key: 'expensiveEndpointRatio', label: 'Expensive Endpoint Ratio' },
  { key: 'reportGenerationRatio', label: 'Report Generation Ratio' },
  { key: 'searchRatio', label: 'Search Ratio' },
  { key: 'cheapEndpointRatio', label: 'Cheap Endpoint Ratio' },
  { key: 'endpointDiversity', label: 'Endpoint Diversity' },
  { key: 'uniqueClientRatio', label: 'Unique Client Ratio (proxy)' },
  { key: 'conversionRate', label: 'Conversion Rate' },
]

const O2_EXPLAIN: Partial<Record<keyof ComparisonMetrics, (edos: number, fc: number) => string>> = {
  expensiveEndpointRatio: (e, f) =>
    `EDoS traffic is concentrated on the expensive report-generation endpoint (${fmtPct(e)} of requests) versus the flash crowd (${fmtPct(f)}).`,
  reportGenerationRatio: () =>
    `Identical to Expensive Endpoint Ratio in this implementation — generate-report is currently the app's only expensive-class endpoint, so these are the same measured signal, not two independent ones.`,
  searchRatio: (e, f) => `Search-endpoint share differs: ${fmtPct(e)} (EDoS) vs ${fmtPct(f)} (flash crowd).`,
  cheapEndpointRatio: (e, f) => `Cheap-endpoint (home/checkout) share differs: ${fmtPct(e)} (EDoS) vs ${fmtPct(f)} (flash crowd).`,
  endpointDiversity: (e, f) =>
    `Endpoint diversity differs: ${fmtNum(e, 3)} (EDoS) vs ${fmtNum(f, 3)} (flash crowd) — the flash crowd spreads requests across a wider endpoint mix.`,
  uniqueClientRatio: (e, f) => `Unique-client-ratio proxy differs: ${fmtPct(e)} (EDoS) vs ${fmtPct(f)} (flash crowd).`,
  conversionRate: (e, f) => `Conversion rate differs: ${fmtPct(e)} (EDoS) vs ${fmtPct(f)} (flash crowd).`,
}

function classText(label: 0 | 1 | null | undefined): string {
  if (label === 1) return 'EDoS'
  if (label === 0) return 'Legitimate Flash Crowd'
  return 'Unknown'
}

function MetricBar({
  label,
  edos,
  fc,
  digits = 2,
}: {
  label: string
  edos: number | null
  fc: number | null
  digits?: number
}) {
  const max = Math.max(edos ?? 0, fc ?? 0, 0.0001)
  return (
    <div className="metric-bar-row">
      <div className="metric-bar-label">{label}</div>
      <div className="metric-bar-stack">
        <div className="metric-bar-line">
          <div className="metric-bar-track">
            <div className="metric-bar-fill current" style={{ width: `${Math.min(100, ((edos ?? 0) / max) * 100)}%` }} />
          </div>
          <div className="metric-bar-value">{fmtNum(edos, digits)}</div>
        </div>
        <div className="metric-bar-line">
          <div className="metric-bar-track">
            <div className="metric-bar-fill opposite" style={{ width: `${Math.min(100, ((fc ?? 0) / max) * 100)}%` }} />
          </div>
          <div className="metric-bar-value">{fmtNum(fc, digits)}</div>
        </div>
      </div>
    </div>
  )
}

function Picker({
  label,
  options,
  value,
  onChange,
  accent,
}: {
  label: string
  options: HistoryEntry[]
  value: string
  onChange: (id: string) => void
  accent: 'edos' | 'fc'
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-faint)' }}>
      <span>
        {label} <span className={`badge ${accent === 'edos' ? 'badge-edos' : 'badge-fc'}`}>{accent === 'edos' ? 'EDoS' : 'Flash Crowd'}</span>
      </span>
      {options.length === 0 ? (
        <span className="empty-note" style={{ padding: 0 }}>
          No saved experiments of this class available.
        </span>
      ) : (
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          style={{
            background: 'var(--surface-2)',
            color: 'var(--text)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '7px 10px',
            fontFamily: 'var(--mono)',
            fontSize: 13,
            minWidth: 260,
          }}
        >
          {options.map((ex) => (
            <option key={ex.experiment_id} value={ex.experiment_id}>
              {ex.experiment_id} — {ex.metadata.duration_seconds}s, seed {String(ex.metadata.seed)}
            </option>
          ))}
        </select>
      )}
    </label>
  )
}

function ExperimentDetailBlock({ id, entry, config }: { id: string; entry: HistoryEntry | undefined; config: ExperimentConfig | null }) {
  if (!id) return null
  return (
    <div className="card">
      <h4 style={{ fontFamily: 'var(--mono)', marginBottom: 8 }}>{id}</h4>
      <div className="exp-card-meta">
        <span>class {entry?.scenario_label ?? '—'}</span>
        <span>seed {entry ? String(entry.metadata.seed) : '—'}</span>
        <span>duration {entry ? `${entry.metadata.duration_seconds}s` : '—'}</span>
        <span>feature windows {entry ? entry.metadata.n_feature_rows : '—'}</span>
        <span>data source saved experiment artifact (data/experiments/{id})</span>
        {config?.config_path && <span>config {config.config_path}</span>}
        {config?.experiment && 'think_time_min' in config.experiment && (
          <span>think time {String(config.experiment.think_time_min)}-{String(config.experiment.think_time_max)}s</span>
        )}
      </div>
      {config?.scenario_purpose && (
        <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginTop: 10 }}>{config.scenario_purpose}</p>
      )}
    </div>
  )
}

export function AnalysisPage() {
  const [mode, setMode] = useState<Mode>('standard')
  const [history, setHistory] = useState<HistoryEntry[]>([])
  const [idEdos, setIdEdos] = useState('')
  const [idFc, setIdFc] = useState('')
  const [resultEdos, setResultEdos] = useState<ExperimentResult | null>(null)
  const [resultFc, setResultFc] = useState<ExperimentResult | null>(null)
  const [configEdos, setConfigEdos] = useState<ExperimentConfig | null>(null)
  const [configFc, setConfigFc] = useState<ExperimentConfig | null>(null)
  const [predEdos, setPredEdos] = useState<PredictionResponse | null>(null)
  const [predFc, setPredFc] = useState<PredictionResponse | null>(null)
  const [matchReport, setMatchReport] = useState<MatchReport | null>(null)
  const [detection, setDetection] = useState<DetectionSummary | null>(null)

  useEffect(() => {
    api.history().then(setHistory).catch(() => setHistory([]))
    api.detectionSummary().then(setDetection).catch(() => setDetection(null))
  }, [])

  const edosOptions = useMemo(() => history.filter(isEdos), [history])
  const fcOptions = useMemo(() => history.filter(isFlashCrowd), [history])
  const stealthOptions = useMemo(() => edosOptions.filter(isStealth), [edosOptions])
  const matchedOptions = useMemo(() => edosOptions.filter(isMatchedCandidate), [edosOptions])
  const standardOptions = useMemo(() => edosOptions.filter((e) => !isStealth(e) && !isMatchedCandidate(e)), [edosOptions])

  const modeEdosOptions = mode === 'stealth' ? stealthOptions : mode === 'matched' ? matchedOptions : standardOptions

  // Reset to this mode's documented reference pair whenever the mode
  // changes (or history first loads) — never carries a stale selection
  // from a different mode's experiment pool into this one.
  useEffect(() => {
    if (history.length === 0) return
    const pool = mode === 'stealth' ? stealthOptions : mode === 'matched' ? matchedOptions : standardOptions
    const preferredId =
      mode === 'stealth' ? DEFAULT_EDOS_STEALTH_ID : mode === 'matched' ? DEFAULT_EDOS_MATCHED_ID : DEFAULT_EDOS_STANDARD_ID
    setIdEdos(pool.find((e) => e.experiment_id === preferredId)?.experiment_id ?? pool[0]?.experiment_id ?? '')
    setIdFc(fcOptions.find((e) => e.experiment_id === DEFAULT_FC_ID)?.experiment_id ?? fcOptions[0]?.experiment_id ?? '')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, history])

  useEffect(() => {
    if (!idEdos) return
    setResultEdos(null)
    setMatchReport(null)
    api.result(idEdos).then(setResultEdos).catch(() => setResultEdos(null))
    api.config(idEdos).then(setConfigEdos).catch(() => setConfigEdos(null))
    api.predict(idEdos).then(setPredEdos).catch(() => setPredEdos(null))
    api.matchReport(idEdos).then(setMatchReport).catch(() => setMatchReport(null))
  }, [idEdos])

  useEffect(() => {
    if (!idFc) return
    setResultFc(null)
    api.result(idFc).then(setResultFc).catch(() => setResultFc(null))
    api.config(idFc).then(setConfigFc).catch(() => setConfigFc(null))
    api.predict(idFc).then(setPredFc).catch(() => setPredFc(null))
  }, [idFc])

  const entryEdos = history.find((e) => e.experiment_id === idEdos)
  const entryFc = history.find((e) => e.experiment_id === idFc)

  const edosMetrics = computeComparisonMetrics(resultEdos)
  const fcMetrics = computeComparisonMetrics(resultFc)
  const hasBoth = !!resultEdos && !!resultFc && resultEdos.features.length > 0 && resultFc.features.length > 0

  const heuristicDeltas = hasBoth
    ? O1_MATCH_AXES.map((k) => {
        const a = edosMetrics[k]
        const b = fcMetrics[k]
        const pct = a !== null && b !== null && b !== 0 ? (a - b) / b : null
        return { k, pct }
      })
    : null
  const heuristicAllKnown = heuristicDeltas ? heuristicDeltas.every((d) => d.pct !== null) : false
  const heuristicMatched = heuristicDeltas && heuristicAllKnown ? heuristicDeltas.every((d) => Math.abs(d.pct as number) <= 0.25) : null

  const matchReportAppliesToPair = !!(matchReport && matchReport.candidate_experiment_id === idEdos && matchReport.reference_experiment_id === idFc)

  const o1Verdict: 'matched' | 'not_matched' | 'unknown' = matchReportAppliesToPair
    ? matchReport!.match_status === 'MATCHED'
      ? 'matched'
      : 'not_matched'
    : heuristicMatched === true
      ? 'matched'
      : heuristicMatched === false
        ? 'not_matched'
        : 'unknown'

  const o2Diffs = hasBoth
    ? O2_ROWS.map((row) => {
        const a = edosMetrics[row.key]
        const b = fcMetrics[row.key]
        const diff = a !== null && b !== null ? Math.abs(a - b) : null
        return { row, a, b, diff }
      })
        .filter((d) => d.diff !== null)
        .sort((x, y) => (y.diff as number) - (x.diff as number))
    : []
  const o2MaxDiff = o2Diffs[0]?.diff ?? null
  const o2Observed = o2MaxDiff !== null ? o2MaxDiff >= 0.15 : null
  const topDiffs = o2Diffs.slice(0, 3)

  const lightgbmMetrics = detection?.lightgbm_metrics ?? detection?.summary?.models?.C_proposed_full
  const testCount = detection?.summary?.test_experiments?.length

  const isDefaultStandardPair = mode === 'standard' && idEdos === DEFAULT_EDOS_STANDARD_ID && idFc === DEFAULT_FC_ID
  const isDefaultMatchedPair = mode === 'matched' && idEdos === DEFAULT_EDOS_MATCHED_ID && idFc === DEFAULT_FC_ID
  const isStealthMode = mode === 'stealth'

  const rateLimiterThreshold = detection?.summary?.baselines?.rate_limiter
    ? (detection.summary.baselines.rate_limiter as Record<string, unknown>).threshold
    : undefined

  return (
    <div>
      <div className="page-title">
        <h2>EDoS vs Flash Crowd Analysis</h2>
        <span className="badge badge-saved">Saved Experiment Data Only</span>
      </div>
      <p className="page-subtitle">
        Experimental comparison of infrastructure and behavioural signatures. This view compares previously validated
        experiments — <strong>no new traffic is generated and no research data is modified.</strong> O1: construct
        EDoS and legitimate flash-crowd traffic with comparable cost/scaling signatures. O2: identify behavioural
        features that distinguish the two classes despite that similarity.
      </p>

      <div className="tabs">
        {(Object.keys(MODE_LABELS) as Mode[]).map((m) => (
          <button key={m} className={`tab-btn ${mode === m ? 'active' : ''}`} onClick={() => setMode(m)}>
            {MODE_LABELS[m]}
          </button>
        ))}
      </div>

      <div className="card">
        <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
          <Picker label="EDoS / Attack Experiment" options={modeEdosOptions} value={idEdos} onChange={setIdEdos} accent="edos" />
          <Picker label="Legitimate Flash Crowd Experiment" options={fcOptions} value={idFc} onChange={setIdFc} accent="fc" />
        </div>

        {isDefaultStandardPair && (
          <p className="note-inline" style={{ marginTop: 12 }}>
            Default reference pair. FC_HARDNEG_001 is a validated legitimate hard-negative experiment used as the
            flash-crowd reference because it contains some expensive-endpoint activity while remaining a legitimate
            flash-crowd scenario — a harder comparison than an ordinary flash crowd (see
            docs/experiment_protocol.md, category C hard-negative flash crowd).
          </p>
        )}
        {isDefaultMatchedPair && (
          <p className="note-inline" style={{ marginTop: 12 }}>
            Default matched-infrastructure pair from this project's own E6 calibration run: EDOS_MATCHED_E6_001 was
            deliberately tuned to match FC_HARDNEG_001's replica/cost signature (see the stored match_report.json
            below).
          </p>
        )}
        {isStealthMode && (
          <p className="note-inline" style={{ marginTop: 12 }}>
            E5/E7 stealth-EDoS candidates ({stealthOptions.length} available) — low request rate, concentrated on the
            expensive endpoint, designed to stay under conventional volumetric detection.
          </p>
        )}
      </div>

      {!hasBoth && (
        <p className="empty-note">
          {idEdos && idFc ? 'Loading the selected experiments’ saved results…' : 'Waiting for saved experiment data to load…'}
        </p>
      )}

      {hasBoth && (
        <>
          <div className="section">
            <div className="section-title">
              O1 — Infrastructure &amp; Cost Signature{' '}
              <span className={`verdict-pill ${o1Verdict === 'matched' ? 'verdict-yes' : o1Verdict === 'not_matched' ? 'verdict-no' : 'verdict-unknown'}`}>
                {o1Verdict === 'matched' ? 'Comparable' : o1Verdict === 'not_matched' ? 'Not Comparable' : 'Unknown'}
              </span>
            </div>
            <div className="card">
              <ComparisonTable
                rows={O1_ROWS}
                current={edosMetrics}
                opposite={fcMetrics}
                currentLabel={`${idEdos} (EDoS)`}
                oppositeLabel={`${idFc} (Flash Crowd)`}
              />
              <div style={{ marginTop: 18 }}>
                <MetricBar label="Mean Replicas" edos={edosMetrics.meanReplicas} fc={fcMetrics.meanReplicas} digits={2} />
                <MetricBar label="Peak Replicas" edos={edosMetrics.peakReplicas} fc={fcMetrics.peakReplicas} digits={0} />
                <MetricBar label="Total Cost" edos={edosMetrics.estimatedCost} fc={fcMetrics.estimatedCost} digits={4} />
                <MetricBar label="Request Rate (context only)" edos={edosMetrics.requestRate} fc={fcMetrics.requestRate} digits={2} />
              </div>

              {matchReportAppliesToPair ? (
                <div style={{ marginTop: 14 }}>
                  <p className="note-inline">
                    Stored match report for this exact pair (data/experiments/{idEdos}/match_report.json) —
                    status <strong>{matchReport!.match_status}</strong>, ±{matchReport!.tolerances.total_cost_pct}% tolerance,
                    primary match axes: {matchReport!.primary_match_axes.map(prettyFeatureName).join(', ')}.
                  </p>
                  <div className="table-scroll" style={{ marginTop: 8 }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Axis</th>
                          <th className="num">Matched</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(matchReport!.axis_matched).map(([axis, matched]) => (
                          <tr key={axis}>
                            <td>{prettyFeatureName(axis)}</td>
                            <td className="num">{matched ? 'yes' : 'no'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <p className="note-inline" style={{ marginTop: 14 }}>
                  {mode === 'matched'
                    ? 'No stored match_report.json exists for this exact pair — showing the raw metric comparison above only, plus this page’s own ±25% comparability heuristic (mean/peak replicas and cost), not a formally calibrated match.'
                    : 'Comparability verdict above uses this page’s own ±25% heuristic on mean/peak replicas and estimated cost — the same tolerance convention as the project’s calibration matching (data/experiments/EDOS_MATCHED_E6_001/match_report.json), not a stored match report for this specific pair.'}
                </p>
              )}

              {isStealthMode && rateLimiterThreshold !== undefined && (
                <p className="note-inline" style={{ marginTop: 14 }}>
                  Context: the project's calibrated rate-limiter threshold from the main train/test evaluation is{' '}
                  {fmtNum(rateLimiterThreshold as number, 2)} req/s. {idEdos}'s measured request rate is{' '}
                  {fmtNum(edosMetrics.requestRate, 2)} req/s —{' '}
                  {(edosMetrics.requestRate ?? 0) < (rateLimiterThreshold as number)
                    ? 'below that threshold, so a request-rate/rate-limiter baseline alone would not flag this run.'
                    : 'at or above that threshold.'}{' '}
                  A dedicated calibration run specifically against the stealth-EDoS scenario has not been completed in
                  this repository (docs/experiment_protocol.md §16) — this is a factual comparison against the
                  existing global threshold, not a claim that a stealth-specific baseline evaluation exists.
                </p>
              )}

              <p className="note-inline" style={{ marginTop: 14 }}>
                <strong>O1 Interpretation:</strong>{' '}
                {o1Verdict === 'matched'
                  ? `${idEdos} and ${idFc} produced comparable mean/peak replica counts and estimated infrastructure cost. This is an example of overlapping infrastructure signatures.`
                  : o1Verdict === 'not_matched'
                    ? `${idEdos} and ${idFc} do not satisfy the project's comparability criterion on mean/peak replicas and cost, so this pair should not be treated as an O1-matched case.`
                    : 'Not enough data to evaluate comparability for this pair.'}
              </p>
            </div>
          </div>

          <div className="section">
            <div className="section-title">
              O2 — Behavioural Differentiation{' '}
              <span className={`verdict-pill ${o2Observed === true ? 'verdict-yes' : o2Observed === false ? 'verdict-no' : 'verdict-unknown'}`}>
                {o2Observed === true ? 'Difference Observed' : o2Observed === false ? 'No Clear Difference' : 'Unknown'}
              </span>
            </div>
            <div className="card">
              <ComparisonTable
                rows={O2_ROWS.map((r) => ({ key: r.key, label: r.label, format: 'pct' as const }))}
                current={edosMetrics}
                opposite={fcMetrics}
                currentLabel={`${idEdos} (EDoS)`}
                oppositeLabel={`${idFc} (Flash Crowd)`}
                highlightMaxDelta
              />
              <p className="note-inline" style={{ marginTop: 10 }}>
                report_generation_ratio is currently identical to expensive_endpoint_ratio in this implementation
                (generate-report is the app's only expensive-class endpoint) — not two independent signals.
              </p>

              <div style={{ marginTop: 16 }}>
                <div className="note-inline" style={{ marginBottom: 8 }}>
                  Key Behavioural Differences
                </div>
                {topDiffs.length === 0 && <p className="empty-note">No comparable behavioural features available for this pair.</p>}
                {topDiffs.map(({ row, a, b, diff }) => (
                  <p key={String(row.key)} style={{ fontSize: 12.5, color: 'var(--text-dim)', lineHeight: 1.6, marginBottom: 8 }}>
                    <strong>{row.label}</strong> — EDoS {fmtPct(a)}, Flash Crowd {fmtPct(b)} (Δ = {fmtNum(diff, 3)}).{' '}
                    {O2_EXPLAIN[row.key]?.(a ?? 0, b ?? 0) ?? ''}
                  </p>
                ))}
              </div>

              <p className="note-inline" style={{ marginTop: 6 }}>
                <strong>O2 Interpretation:</strong>{' '}
                {o2Observed === true
                  ? 'Although infrastructure behaviour can be similar (see O1 above), this pair exhibits substantially different application-level traffic behaviour. These behavioural features provide additional information for distinguishing the two classes.'
                  : o2Observed === false
                    ? 'No strong behavioural separation is observed in this selected pair.'
                    : 'Not enough data to evaluate behavioural separation for this pair.'}
              </p>
            </div>
          </div>

          <div className="section">
            <div className="section-title">Why Can These Two Look Similar Yet Be Distinguished?</div>
            <div className="card">
              <ol className="why-list">
                <li>
                  <h4>Infrastructure Behaviour</h4>
                  <p>
                    Replica scaling and cost can overlap: mean replicas {fmtNum(edosMetrics.meanReplicas, 2)} (EDoS) vs{' '}
                    {fmtNum(fcMetrics.meanReplicas, 2)} (flash crowd); estimated cost {fmtNum(edosMetrics.estimatedCost, 4)} vs{' '}
                    {fmtNum(fcMetrics.estimatedCost, 4)} units.
                  </p>
                </li>
                <li>
                  <h4>Traffic / Application Behaviour</h4>
                  <p>
                    Endpoint usage and client behaviour differ: expensive-endpoint ratio {fmtPct(edosMetrics.expensiveEndpointRatio)} (EDoS)
                    vs {fmtPct(fcMetrics.expensiveEndpointRatio)} (flash crowd).
                  </p>
                </li>
                <li>
                  <h4>Feature Representation</h4>
                  <p>The detector receives the full measured cost + scaling + application-behaviour + traffic feature vector for each run.</p>
                </li>
                <li>
                  <h4>Classification</h4>
                  <p>
                    The trained CASCADE LightGBM model produces the final class from that vector — see the detector results
                    below.
                  </p>
                </li>
              </ol>
            </div>
          </div>

          <div className="section">
            <div className="section-title">CASCADE Detector</div>
            <div className="card">
              <div className="exp-card-meta" style={{ marginBottom: 12 }}>
                <span>Model: LightGBM</span>
                <span>Feature set: C_proposed_full (Cost + Scaling + Application Behaviour + Traffic)</span>
                {lightgbmMetrics && <span>Test accuracy: {fmtPct(lightgbmMetrics.accuracy)}</span>}
              </div>
              {lightgbmMetrics && (
                <p className="note-inline" style={{ marginBottom: 14 }}>
                  {fmtPct(lightgbmMetrics.accuracy)} accuracy on the project's small held-out experiment-level test
                  split{testCount ? ` (${testCount} test experiments)` : ''} — a proof-of-concept-scale result, not a
                  claim of population-level generalization (see docs/experiment_protocol.md for the full data-scale
                  caveats).
                </p>
              )}
              <div className="two-col">
                <div>
                  <h4 style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>{idEdos}</h4>
                  <p className="exp-card-meta">
                    <span>Actual: {classText(entryEdos?.label)}</span>
                  </p>
                  {predEdos?.available ? (
                    <p className={`kpi-classification ${predEdos.final_predicted_label === 1 ? 'cls-edos' : 'cls-fc'}`}>
                      Predicted: {predEdos.final_predicted_label === 1 ? 'EDoS' : 'Legitimate Flash Crowd'} (P(EDoS) ={' '}
                      {fmtPct(predEdos.final_probability_edos)})
                    </p>
                  ) : (
                    <p className="empty-note">Prediction unavailable{predEdos?.detail ? ` — ${predEdos.detail}` : ''}</p>
                  )}
                </div>
                <div>
                  <h4 style={{ fontFamily: 'var(--mono)', fontSize: 13 }}>{idFc}</h4>
                  <p className="exp-card-meta">
                    <span>Actual: {classText(entryFc?.label)}</span>
                  </p>
                  {predFc?.available ? (
                    <p className={`kpi-classification ${predFc.final_predicted_label === 1 ? 'cls-edos' : 'cls-fc'}`}>
                      Predicted: {predFc.final_predicted_label === 1 ? 'EDoS' : 'Legitimate Flash Crowd'} (P(EDoS) ={' '}
                      {fmtPct(predFc.final_probability_edos)})
                    </p>
                  ) : (
                    <p className="empty-note">Prediction unavailable{predFc?.detail ? ` — ${predFc.detail}` : ''}</p>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div className="section">
            <div className="section-title">Timeline Comparison</div>
            <div className="two-col">
              <TimeSeriesChart
                title={`${idEdos} — Request Rate (req/s)`}
                data={resultEdos!.locust_history}
                series={[{ key: 'Requests/s', label: 'req/s', color: CHART_EDOS }]}
              />
              <TimeSeriesChart
                title={`${idFc} — Request Rate (req/s)`}
                data={resultFc!.locust_history}
                series={[{ key: 'Requests/s', label: 'req/s', color: CHART_FC }]}
              />
              <TimeSeriesChart
                title={`${idEdos} — Replica Count`}
                data={resultEdos!.timeseries}
                series={[{ key: 'replica_count', label: 'replicas', color: CHART_EDOS }]}
              />
              <TimeSeriesChart
                title={`${idFc} — Replica Count`}
                data={resultFc!.timeseries}
                series={[{ key: 'replica_count', label: 'replicas', color: CHART_FC }]}
              />
              <TimeSeriesChart
                title={`${idEdos} — Cumulative Cost (units)`}
                data={cumulativeCostSeries(resultEdos!)}
                series={[{ key: 'cumulative_cost', label: 'cumulative cost', color: CHART_EDOS }]}
                xKey="elapsed_seconds"
              />
              <TimeSeriesChart
                title={`${idFc} — Cumulative Cost (units)`}
                data={cumulativeCostSeries(resultFc!)}
                series={[{ key: 'cumulative_cost', label: 'cumulative cost', color: CHART_FC }]}
                xKey="elapsed_seconds"
              />
            </div>
          </div>

          <div className="section">
            <div className="section-title">Experiment Details</div>
            <details>
              <summary style={{ cursor: 'pointer', color: 'var(--text-dim)', fontSize: 13, marginBottom: 10 }}>
                Show configuration and metadata for both selected experiments
              </summary>
              <div className="two-col" style={{ marginTop: 10 }}>
                <ExperimentDetailBlock id={idEdos} entry={entryEdos} config={configEdos} />
                <ExperimentDetailBlock id={idFc} entry={entryFc} config={configFc} />
              </div>
            </details>
          </div>

          <div className="section">
            <div className="section-title">Research Objectives</div>
            <div className="card">
              <div className="grid grid-2">
                <div>
                  <div className="note-inline" style={{ marginBottom: 4 }}>
                    O1 — Comparable cost/scaling signature
                  </div>
                  <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginBottom: 8 }}>
                    Construct attack and legitimate traffic with comparable cost/scaling signatures.
                  </p>
                  <span className={`verdict-pill ${o1Verdict === 'matched' ? 'verdict-yes' : o1Verdict === 'not_matched' ? 'verdict-no' : 'verdict-unknown'}`}>
                    {o1Verdict === 'matched' ? 'Demonstrated by Selected Pair' : o1Verdict === 'not_matched' ? 'Not Demonstrated by Selected Pair' : 'Unknown'}
                  </span>
                </div>
                <div>
                  <div className="note-inline" style={{ marginBottom: 4 }}>
                    O2 — Behavioural differentiation
                  </div>
                  <p style={{ fontSize: 12.5, color: 'var(--text-dim)', marginBottom: 8 }}>
                    Identify behavioural features that distinguish the two classes despite infrastructure similarity.
                  </p>
                  <span className={`verdict-pill ${o2Observed === true ? 'verdict-yes' : o2Observed === false ? 'verdict-no' : 'verdict-unknown'}`}>
                    {o2Observed === true ? 'Behavioural Difference Observed' : o2Observed === false ? 'No Clear Difference in Selected Pair' : 'Unknown'}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      <p className="footer-note" style={{ marginTop: 40 }}>
        Research note: This dashboard visualizes previously collected experimental results. It does not generate new
        traffic, modify the training dataset, or retrain the detector.
      </p>
    </div>
  )
}
