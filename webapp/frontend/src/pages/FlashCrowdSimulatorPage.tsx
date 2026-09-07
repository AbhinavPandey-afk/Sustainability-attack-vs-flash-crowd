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

export function FlashCrowdSimulatorPage({ status }: { status: SystemStatus | null }) {
  const [users, setUsers] = useState(50)
  const [spawnRate, setSpawnRate] = useState(10)
  const [duration, setDuration] = useState(60)
  const [weightHome, setWeightHome] = useState(3)
  const [weightSearch, setWeightSearch] = useState(5)
  const [weightCheckout, setWeightCheckout] = useState(1)
  const [baseline, setBaseline] = useState<ExperimentResult | null>(null)

  const { experimentId, runStatus, result, explanation, error, isRunning, start, stop } = useSimulatorRun('flash-crowd')

  useEffect(() => {
    api.normalBaseline().then(setBaseline).catch(() => setBaseline(null))
  }, [])

  const clusterUnavailable = status?.application.status === 'UNAVAILABLE' || status?.kubernetes.status === 'UNAVAILABLE'
  const hasBaseline = !!baseline && baseline.timeseries.length > 1

  return (
    <div>
      <div className="page-title">
        <h2>Flash Crowd Simulator</h2>
      </div>
      <p className="page-subtitle">
        Configures and runs a real legitimate demand surge against the live cascade cluster — many simulated
        users browsing home/search/checkout with session continuity. Real traffic, real autoscaling, real cost.
        This run is kept out of the trained detector's train/test split, so running it never perturbs the model's
        reported metrics.
      </p>

      {clusterUnavailable && (
        <p className="empty-note" style={{ color: 'var(--bad)' }}>
          Live application/cluster not reachable — cannot start a real simulation. Check the status pills on the
          Dashboard.
        </p>
      )}

      <div className="card">
        <div className="grid grid-3">
          <NumberField label="Simulated Users" value={users} onChange={setUsers} min={1} max={200} />
          <NumberField label="Spawn Rate (users/s)" value={spawnRate} onChange={setSpawnRate} min={1} max={200} />
          <NumberField label="Duration (s)" value={duration} onChange={setDuration} min={10} max={300} />
        </div>
        <p className="note-inline" style={{ marginTop: 12, marginBottom: 4 }}>
          Endpoint distribution weights (relative — home / search / checkout)
        </p>
        <div className="grid grid-3">
          <NumberField label="Home" value={weightHome} onChange={setWeightHome} min={0} max={100} />
          <NumberField label="Search" value={weightSearch} onChange={setWeightSearch} min={0} max={100} />
          <NumberField label="Checkout (conversion)" value={weightCheckout} onChange={setWeightCheckout} min={0} max={100} />
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button
            className="primary"
            onClick={() =>
              start({
                users,
                spawn_rate: spawnRate,
                duration_seconds: duration,
                weight_home: weightHome,
                weight_search: weightSearch,
                weight_checkout: weightCheckout,
              })
            }
            disabled={isRunning || clusterUnavailable}
          >
            {isRunning ? 'Flash Crowd Running…' : 'Start Flash Crowd'}
          </button>
          {isRunning && <button onClick={stop}>Stop</button>}
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
                  Dashed grey = NORMAL_001, a real "ordinary day" baseline run (no attack, no surge) — solid teal =
                  this flash crowd — compare them directly on the same axes.
                </p>
              )}
              <div className="two-col">
                {hasBaseline ? (
                  <TimeSeriesChart
                    title="Replica Count — flash crowd vs. normal day"
                    data={overlayByElapsedSeconds(baseline!.timeseries, result.timeseries, 'elapsed_seconds', 'replica_count')}
                    series={[
                      { key: 'baseline', label: 'Normal day', color: '#6b7a90', dashed: true },
                      { key: 'current', label: 'This flash crowd', color: '#fbbf24' },
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
                    title="Request Rate — flash crowd vs. normal day"
                    data={overlayByElapsedSeconds(baseline!.locust_history, result.locust_history, 'elapsed_seconds', 'Requests/s')}
                    series={[
                      { key: 'baseline', label: 'Normal day', color: '#6b7a90', dashed: true },
                      { key: 'current', label: 'This flash crowd', color: '#2dd4bf' },
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
                  scenarioType="flash_crowd"
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
