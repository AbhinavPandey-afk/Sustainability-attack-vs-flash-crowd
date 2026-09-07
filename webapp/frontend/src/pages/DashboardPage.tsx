import { DemoWalkthrough } from '../components/DemoWalkthrough'
import { StatTile } from '../components/StatTile'
import { fmtNum, fmtPct } from '../format'
import type { HistoryEntry, ResearchQuestion, SystemStatus } from '../types'

export function DashboardPage({
  status,
  research,
  history,
  onRunDemo,
  demoRunning,
}: {
  status: SystemStatus | null
  research: ResearchQuestion | null
  history: HistoryEntry[]
  onRunDemo: () => void
  demoRunning: boolean
}) {
  const latest = history[0] ?? null
  const k = status?.kubernetes

  return (
    <div>
      <div className="page-title">
        <h2>Dashboard</h2>
      </div>
      <p className="page-subtitle">
        {research?.question ??
          'Can cost, scaling and application-behaviour signals distinguish EDoS attacks from legitimate flash crowds when traffic volume alone cannot?'}
      </p>

      <div className="grid grid-4" style={{ marginTop: 20 }}>
        <StatTile
          label="Ready Replicas (live)"
          value={k ? `${fmtNum(k.ready_replicas, 0)} / ${fmtNum(k.max_replicas, 0)}` : '—'}
        />
        <StatTile label="CPU Utilization (live)" value={k ? fmtPct((k.current_cpu_utilization_pct ?? 0) / 100) : '—'} />
        <StatTile
          label="Request Rate (most recent run)"
          value={latest ? fmtNum(latest.summary.request_rate, 1) : '—'}
          unit="req/s"
        />
        <StatTile label="Cost (most recent run)" value={latest ? fmtNum(latest.summary.estimated_cost, 4) : '—'} unit="units" />
        <StatTile
          label="Cost / Request (most recent run)"
          value={latest ? fmtNum(latest.summary.cost_per_request, 5) : '—'}
          unit="units"
        />
        <StatTile
          label="Expensive-Endpoint Ratio (most recent run)"
          value={latest ? fmtPct(latest.summary.expensive_endpoint_ratio) : '—'}
        />
      </div>

      {latest && (
        <p className="note-inline" style={{ marginTop: 10 }}>
          Most recent run:{' '}
          <span className={`badge ${latest.label === 0 ? 'badge-fc' : 'badge-edos'}`}>
            {latest.experiment_id} — {latest.scenario_label}
          </span>{' '}
          (ground-truth label from the experiment config — open it in Experiments or a Simulator page to see the
          live CASCADE prediction for that run).
        </p>
      )}

      <div className="section">
        <div className="section-title">One-Click Presentation Demo</div>
        <div className="card">
          <p style={{ fontSize: 13, color: 'var(--text-dim)', marginBottom: 12 }}>
            Runs a curated sequence of real, live experiments against the cascade cluster — real traffic, real
            autoscaling, real cost accumulation. Takes several minutes; nothing is sped up or simulated.
          </p>
          <button className="primary" onClick={onRunDemo} disabled={demoRunning}>
            {demoRunning ? 'Demo running…' : 'Run Presentation Demo'}
          </button>
        </div>
      </div>

      <div className="section">
        <div className="section-title">How to Demonstrate</div>
        <DemoWalkthrough steps={research?.demo_walkthrough ?? []} />
      </div>
    </div>
  )
}
