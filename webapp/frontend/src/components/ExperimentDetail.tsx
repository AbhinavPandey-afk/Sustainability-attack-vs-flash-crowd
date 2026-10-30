import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { fmtNum, fmtPct, fmtSeconds } from '../format'
import { overlayByElapsedSeconds } from '../overlay'
import { computeEndpointCounts, computeSummaryStats, cumulativeCostSeries } from '../summary'
import type { DetectionExplanation, ExperimentConfig, ExperimentResult, RunState, RunStatus, ScenarioType } from '../types'
import { EndpointDistribution } from './EndpointDistribution'
import { RunNarrative } from './RunNarrative'
import { StatTile } from './StatTile'
import { TimeSeriesChart } from './TimeSeriesChart'
import { CHART_AMBER, CHART_AXIS_TEXT_STRONG, CHART_EDOS, CHART_ENDPOINT_MEDIUM, CHART_GREEN, CHART_PRIMARY } from '../theme'

const STEPS: RunState[] = ['READY', 'STARTING', 'RUNNING', 'SUMMARIZING', 'COMPLETED']

export function Lifecycle({ state }: { state: RunState }) {
  const terminalOverride = state === 'FAILED' || state === 'CANCELLED'
  const idx = STEPS.indexOf(terminalOverride ? 'COMPLETED' : state)
  return (
    <div className="lifecycle">
      {STEPS.map((step, i) => (
        <span key={step} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            className={`lifecycle-step ${
              terminalOverride && i === STEPS.length - 1 ? 'failed' : i < idx ? 'done' : i === idx ? 'active' : ''
            }`}
          >
            {terminalOverride && i === STEPS.length - 1 ? state : step}
          </span>
          {i < STEPS.length - 1 && <span className="lifecycle-arrow">→</span>}
        </span>
      ))}
    </div>
  )
}

export function ExperimentDetail({
  experimentId,
  isRunning,
  onRunStart,
  onRunFinished,
  disableRun,
}: {
  experimentId: string
  isRunning: boolean
  onRunStart: (id: string) => void
  onRunFinished: () => void
  disableRun: boolean
}) {
  const [config, setConfig] = useState<ExperimentConfig | null>(null)
  const [result, setResult] = useState<ExperimentResult | null>(null)
  const [baseline, setBaseline] = useState<ExperimentResult | null>(null)
  const [explanation, setExplanation] = useState<DetectionExplanation | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    setLoading(true)
    setResult(null)
    setExplanation(null)
    api.config(experimentId).then(setConfig).catch(() => setConfig(null))
    api
      .result(experimentId)
      .then(setResult)
      .catch(() => setResult(null))
      .finally(() => setLoading(false))
    if (experimentId !== 'NORMAL_001') {
      api.normalBaseline().then(setBaseline).catch(() => setBaseline(null))
    }
  }, [experimentId])

  useEffect(() => {
    if (!result) return
    api.explain(experimentId).then(setExplanation).catch(() => setExplanation(null))
  }, [result, experimentId])

  useEffect(() => {
    if (!isRunning) {
      if (pollRef.current) window.clearInterval(pollRef.current)
      return
    }
    const poll = async () => {
      try {
        const status = await api.runStatus(experimentId)
        setRunStatus(status)
        if (status.state === 'COMPLETED' || status.state === 'FAILED' || status.state === 'CANCELLED') {
          if (pollRef.current) window.clearInterval(pollRef.current)
          onRunFinished()
          if (status.state === 'COMPLETED') {
            const fresh = await api.result(experimentId)
            setResult(fresh)
          }
        }
      } catch {
        // transient — next poll tick retries
      }
    }
    poll()
    pollRef.current = window.setInterval(poll, 1500)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [isRunning, experimentId, onRunFinished])

  const handleRun = async () => {
    try {
      await api.startRun(experimentId)
      onRunStart(experimentId)
      setRunStatus({ experiment_id: experimentId, state: 'STARTING' })
    } catch (err) {
      alert(`Could not start run: ${(err as Error).message}`)
    }
  }

  const handleStop = async () => {
    try {
      await api.stopRun(experimentId)
    } catch (err) {
      alert(`Could not stop run: ${(err as Error).message}`)
    }
  }

  if (loading) return <p className="empty-note">Loading {experimentId}…</p>

  const label = config?.experiment?.label as number | undefined
  const scenarioType = config?.experiment?.scenario_type as string | undefined
  const scenarioBadgeText: Record<string, string> = {
    flash_crowd: `Flash Crowd${label !== undefined ? ` (label ${label})` : ''}`,
    edos: `EDoS${label !== undefined ? ` (label ${label})` : ''}`,
    mixed: 'Mixed (E3) — label 1 throughout',
    interleaved: 'Interleaved (E4) — label varies per window',
    normal: 'Normal Baseline (E0) — reference only',
  }
  const scenarioBadgeClass =
    scenarioType === 'flash_crowd'
      ? 'badge-fc'
      : scenarioType === 'edos'
        ? 'badge-edos'
        : scenarioType === 'normal'
          ? 'badge-normal'
          : 'badge-mixed'

  // E4: cumulative phase-duration boundaries, for vertical reference
  // lines on the time-series charts below (see docs/experiment_protocol.md section 8).
  const phaseBoundaries = result?.metadata.phases
    ?.slice(0, -1)
    .reduce<number[]>((acc, p) => [...acc, (acc.at(-1) ?? 0) + p.planned_duration_seconds], [])

  return (
    <div>
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 12 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <h3 style={{ fontFamily: 'var(--mono)' }}>{experimentId}</h3>
              {scenarioType && (
                <span className={`badge ${scenarioBadgeClass}`}>{scenarioBadgeText[scenarioType] ?? scenarioType}</span>
              )}
              {result && (
                <span className={`badge ${result.source === 'just_ran' ? 'badge-live' : 'badge-saved'}`}>
                  {result.source === 'just_ran' ? 'LIVE RESULT (just completed)' : 'SAVED SAMPLE RESULT'}
                </span>
              )}
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="primary" onClick={handleRun} disabled={isRunning || disableRun}>
              {isRunning ? 'Running…' : result ? 'Run Again (Live)' : 'Run Demo (Live)'}
            </button>
            {isRunning && <button onClick={handleStop}>Stop</button>}
          </div>
        </div>

        {result &&
          (() => {
            const counts = computeEndpointCounts(result)
            return (
              <div className="grid grid-5" style={{ marginTop: 14 }}>
                <StatTile label="Total Requests" value={fmtNum(counts.totalRequests, 0)} />
                <StatTile label="Expensive (Report) Requests" value={fmtNum(counts.expensive, 0)} />
                <StatTile label="Search Requests" value={fmtNum(counts.medium, 0)} />
                <StatTile label="Home/Checkout Requests" value={fmtNum(counts.cheap, 0)} />
                <StatTile label="Conversions" value={fmtNum(counts.conversions, 0)} />
              </div>
            )
          })()}

        <p style={{ color: 'var(--text-dim)', fontSize: 13, marginTop: 12, maxWidth: 700 }}>{config?.scenario_purpose}</p>

        {config && (
          <div className="exp-card-meta" style={{ marginTop: 10 }}>
            <span>duration {String(config.experiment.duration_seconds)}s</span>
            <span>seed {String(config.experiment.seed)}</span>
            <span>users {String((config.scenario as Record<string, unknown> | null)?.locust ? (((config.scenario as Record<string, unknown>).locust as Record<string, unknown>).users) : '—')}</span>
            <span>window {JSON.stringify(config.detector.window_seconds)}s</span>
            {config.phases ? (
              <span>{config.phases.length} phases: {config.phases.map((p) => p.scenario_type).join(' → ')}</span>
            ) : (
              <span>scenario file {String(config.experiment.scenario_file)}</span>
            )}
          </div>
        )}

        {(isRunning || runStatus) && (
          <div style={{ marginTop: 14 }}>
            <Lifecycle state={(runStatus?.state as RunState) ?? 'READY'} />
            {runStatus?.state === 'RUNNING' && (
              <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 6 }}>
                Elapsed {fmtSeconds(runStatus.elapsed_seconds)} / {runStatus.duration_seconds}s
              </p>
            )}
            {(runStatus?.state === 'FAILED' || runStatus?.state === 'CANCELLED') && (
              <pre style={{ color: 'var(--bad)', fontSize: 11, whiteSpace: 'pre-wrap', marginTop: 8 }}>{runStatus.error}</pre>
            )}
          </div>
        )}
      </div>

      {!result && !isRunning && (
        <p className="empty-note">No saved result yet for {experimentId} — click "Run Demo (Live)" to generate one.</p>
      )}

      {result &&
        (() => {
          const hasBaseline = experimentId !== 'NORMAL_001' && !!baseline && baseline.timeseries.length > 1
          return (
            <>
              <div className="section">
                <div className="section-title">Live Experiment Impact — Before / During / After</div>
                {phaseBoundaries && phaseBoundaries.length > 0 && (
                  <p style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 10 }}>
                    Dashed lines mark E4 phase changes ({result?.metadata.phases?.map((p) => p.scenario_type).join(' → ')}) — ground truth changes at each one.
                  </p>
                )}
                {hasBaseline && (
                  <p style={{ fontSize: 12, color: 'var(--text-faint)', marginBottom: 10 }}>
                    Dashed grey = NORMAL_001, a real "ordinary day" baseline run (no attack, no surge) — solid = this
                    run — so it's easy to see how much this run actually deviates from normal.
                  </p>
                )}
                <div className="two-col">
                  {hasBaseline ? (
                    <TimeSeriesChart
                      title="Request Rate (Locust, req/s) — vs. normal day"
                      data={overlayByElapsedSeconds(baseline!.locust_history, result.locust_history, 'elapsed_seconds', 'Requests/s')}
                      series={[
                        { key: 'baseline', label: 'Normal day', color: CHART_AXIS_TEXT_STRONG, dashed: true },
                        { key: 'current', label: 'This run', color: CHART_PRIMARY },
                      ]}
                    />
                  ) : (
                    <TimeSeriesChart
                      title="Request Rate (Locust, req/s)"
                      data={result.locust_history}
                      series={[{ key: 'Requests/s', label: 'req/s', color: CHART_PRIMARY }]}
                      phaseBoundaries={phaseBoundaries}
                    />
                  )}
                  <TimeSeriesChart
                    title="Average Latency (ms, cumulative)"
                    data={result.locust_history}
                    series={[{ key: 'Total Average Response Time', label: 'avg ms', color: CHART_ENDPOINT_MEDIUM }]}
                    phaseBoundaries={phaseBoundaries}
                  />
                  {hasBaseline ? (
                    <TimeSeriesChart
                      title="Replica Count — vs. normal day"
                      data={overlayByElapsedSeconds(baseline!.timeseries, result.timeseries, 'elapsed_seconds', 'replica_count')}
                      series={[
                        { key: 'baseline', label: 'Normal day', color: CHART_AXIS_TEXT_STRONG, dashed: true },
                        { key: 'current', label: 'This run', color: CHART_AMBER },
                      ]}
                    />
                  ) : (
                    <TimeSeriesChart
                      title="Replica Count"
                      data={result.timeseries}
                      series={[{ key: 'replica_count', label: 'replicas', color: CHART_AMBER }]}
                      phaseBoundaries={phaseBoundaries}
                    />
                  )}
                  {hasBaseline ? (
                    <TimeSeriesChart
                      title="CPU Utilization (%) — vs. normal day"
                      data={overlayByElapsedSeconds(baseline!.timeseries, result.timeseries, 'elapsed_seconds', 'cpu_utilization_pct')}
                      series={[
                        { key: 'baseline', label: 'Normal day', color: CHART_AXIS_TEXT_STRONG, dashed: true },
                        { key: 'current', label: 'This run', color: CHART_EDOS },
                      ]}
                      yUnit="%"
                    />
                  ) : (
                    <TimeSeriesChart
                      title="CPU Utilization (HPA-reported, % of request)"
                      data={result.timeseries}
                      series={[{ key: 'cpu_utilization_pct', label: 'CPU %', color: CHART_EDOS }]}
                      phaseBoundaries={phaseBoundaries}
                      yUnit="%"
                    />
                  )}
                </div>
              </div>

              <div className="section">
                <RunNarrative
                  explanation={explanation}
                  scenarioType={scenarioType as ScenarioType | undefined}
                  experimentId={experimentId}
                  mixedEvaluation={null}
                />
              </div>

              <div className="section">
                  <div className="section-title">Cost &amp; Endpoint Impact</div>
                {(() => {
                  const stats = computeSummaryStats(result)
                  return (
                    <div className="grid grid-3" style={{ marginBottom: 12 }}>
                      <StatTile label="Total Cost (this run)" value={fmtNum(stats.totalCost, 4)} unit="units" />
                      <StatTile label="Cost / Request" value={fmtNum(stats.costPerRequest, 5)} />
                      <StatTile label="Expensive-Endpoint Ratio" value={fmtPct(stats.expensiveEndpointRatio)} />
                    </div>
                  )
                })()}
                <div className="two-col">
                  <EndpointDistribution timeseries={result.timeseries} />
                  <TimeSeriesChart
                    title="Cumulative Cost Over Time (experimental cost units)"
                    data={cumulativeCostSeries(result)}
                    series={[{ key: 'cumulative_cost', label: 'cumulative cost', color: CHART_GREEN }]}
                    xKey="elapsed_seconds"
                  />
                </div>
              </div>
            </>
          )
        })()}
    </div>
  )
}
