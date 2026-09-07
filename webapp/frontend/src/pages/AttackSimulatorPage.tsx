import { useEffect, useState } from 'react'
import { api } from '../api'
import { EndpointDistribution } from '../components/EndpointDistribution'
import { NumberField } from '../components/NumberField'
import { RunNarrative } from '../components/RunNarrative'
import { StatTile } from '../components/StatTile'
import { TimeSeriesChart } from '../components/TimeSeriesChart'
import { fmtNum, fmtPct, fmtSeconds } from '../format'
import { useSimulatorRun } from '../hooks/useSimulatorRun'
import { overlayByElapsedSeconds } from '../overlay'
import { computeSummaryStats, cumulativeCostSeries } from '../summary'
import type { ExperimentResult, SystemStatus } from '../types'

export function AttackSimulatorPage({ status }: { status: SystemStatus | null }) {
  const [users, setUsers] = useState(8)
  const [spawnRate, setSpawnRate] = useState(8)
  const [duration, setDuration] = useState(30)
  const [reportComplexity, setReportComplexity] = useState(60)
  const [baseline, setBaseline] = useState<ExperimentResult | null>(null)

  const { experimentId, runStatus, result, explanation, error, isRunning, start, stop } = useSimulatorRun('attack')

  useEffect(() => {
    api.normalBaseline().then(setBaseline).catch(() => setBaseline(null))
  }, [])

  const clusterUnavailable = status?.application.status === 'UNAVAILABLE' || status?.kubernetes.status === 'UNAVAILABLE'
  const hasBaseline = !!baseline && baseline.timeseries.length > 1

  return (
    <div>
      <div className="page-title">
        <h2>Attack Simulator</h2>
      </div>
      <p className="page-subtitle">
        Configures and runs a real, low-volume EDoS attack against the live cascade cluster — concentrated on the
        deliberately expensive /api/generate-report endpoint. Real traffic, real autoscaling, real cost. This run
        is kept out of the trained detector's train/test split, so running it never perturbs the model's reported
        metrics.
      </p>

      {clusterUnavailable && (
        <p className="empty-note" style={{ color: 'var(--bad)' }}>
          Live application/cluster not reachable — cannot start a real simulation. Check the status pills on the
          Dashboard.
        </p>
      )}

      <div className="card">
        <div className="grid grid-4">
          <NumberField label="Simulated Clients" value={users} onChange={setUsers} min={1} max={200} />
          <NumberField label="Spawn Rate (users/s)" value={spawnRate} onChange={setSpawnRate} min={1} max={200} />
          <NumberField label="Duration (s)" value={duration} onChange={setDuration} min={10} max={300} />
          <NumberField label="Report Complexity (1-100)" value={reportComplexity} onChange={setReportComplexity} min={1} max={100} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button
            className="primary"
            onClick={() =>
              start({ users, spawn_rate: spawnRate, duration_seconds: duration, report_complexity: reportComplexity })
            }
            disabled={isRunning || clusterUnavailable}
          >
            {isRunning ? 'Attack Running…' : 'Start Attack'}
          </button>
          {isRunning && <button onClick={stop}>Stop Attack</button>}
        </div>
        {error && <p style={{ color: 'var(--bad)', fontSize: 12, marginTop: 10 }}>{error}</p>}
        {runStatus && (
          <p className="note-inline" style={{ marginTop: 10 }}>
            {experimentId} — {runStatus.state}
            {runStatus.state === 'RUNNING' &&
              ` (elapsed ${fmtSeconds(runStatus.elapsed_seconds)} / ${runStatus.duration_seconds}s)`}
          </p>
        )}
        {(runStatus?.state === 'FAILED' || runStatus?.state === 'CANCELLED') && runStatus.error && (
          <pre style={{ color: 'var(--bad)', fontSize: 11, whiteSpace: 'pre-wrap', marginTop: 8 }}>{runStatus.error}</pre>
        )}
      </div>

      {result &&
        (() => {
          const stats = computeSummaryStats(result)
          return (
            <div className="section">
              <div className="section-title">Result — {experimentId}</div>
              <div className="grid grid-3" style={{ marginBottom: 12 }}>
                <StatTile label="Total Requests" value={fmtNum(stats.totalRequests, 0)} />
                <StatTile label="Total Cost (this run)" value={fmtNum(stats.totalCost, 4)} unit="units" />
                <StatTile label="Expensive-Endpoint Ratio" value={fmtPct(stats.expensiveEndpointRatio)} />
              </div>

              {hasBaseline && (
                <p className="note-inline" style={{ marginBottom: 10 }}>
                  Dashed grey = NORMAL_001, a real "ordinary day" baseline run (no attack, no surge) — solid red =
                  this attack — compare them directly on the same axes.
                </p>
              )}
              <div className="two-col">
                {hasBaseline ? (
                  <TimeSeriesChart
                    title="Replica Count — attack vs. normal day"
                    data={overlayByElapsedSeconds(baseline!.timeseries, result.timeseries, 'elapsed_seconds', 'replica_count')}
                    series={[
                      { key: 'baseline', label: 'Normal day', color: '#6b7a90', dashed: true },
                      { key: 'current', label: 'This attack', color: '#fbbf24' },
                    ]}
                  />
                ) : (
                  <TimeSeriesChart
                    title="Replica Count"
                    data={result.timeseries}
                    series={[{ key: 'replica_count', label: 'replicas', color: '#fbbf24' }]}
                  />
                )}
                {hasBaseline ? (
                  <TimeSeriesChart
                    title="Request Rate — attack vs. normal day"
                    data={overlayByElapsedSeconds(baseline!.locust_history, result.locust_history, 'elapsed_seconds', 'Requests/s')}
                    series={[
                      { key: 'baseline', label: 'Normal day', color: '#6b7a90', dashed: true },
                      { key: 'current', label: 'This attack', color: '#fb7185' },
                    ]}
                  />
                ) : (
                  <TimeSeriesChart
                    title="Cumulative Cost (experimental cost units)"
                    data={cumulativeCostSeries(result)}
                    series={[{ key: 'cumulative_cost', label: 'cumulative cost', color: '#34d399' }]}
                    xKey="elapsed_seconds"
                  />
                )}
              </div>
              <div style={{ marginTop: 16 }}>
                <EndpointDistribution timeseries={result.timeseries} />
              </div>

              <div className="section">
                <RunNarrative
                  explanation={explanation}
                  scenarioType="edos"
                  experimentId={experimentId ?? undefined}
                  mixedEvaluation={null}
                />
              </div>
            </div>
          )
        })()}
    </div>
  )
}
