import { ExperimentDetail } from '../components/ExperimentDetail'
import { StatTile } from '../components/StatTile'
import { fmtNum, fmtPct } from '../format'
import type { HistoryEntry, SystemStatus } from '../types'

function SystemStatusStrip({ status }: { status: SystemStatus | null }) {
  const k = status?.kubernetes

  return (
    <div className="section">
      <div className="section-title">Infrastructure Status</div>
      <div className="grid grid-4">
        <StatTile
          label="Kubernetes"
          value={k ? `${fmtNum(k.ready_replicas, 0)} / ${fmtNum(k.max_replicas, 0)}` : '—'}
          unit={k ? 'replicas ready' : undefined}
        />
        <StatTile label="CPU Utilization" value={k ? fmtPct((k.current_cpu_utilization_pct ?? 0) / 100) : '—'} />
        <StatTile label="Prometheus" value={status?.prometheus.status ?? '—'} />
        <StatTile label="Application" value={status?.application.status ?? '—'} />
      </div>
      {!status && <p className="empty-note">Checking live system status…</p>}
    </div>
  )
}

export function LiveMonitorPage({
  status,
  runningId,
  history,
  onRunStart,
  onRunFinished,
}: {
  status: SystemStatus | null
  runningId: string | null
  history: HistoryEntry[]
  onRunStart: (id: string) => void
  onRunFinished: () => void
}) {
  const activeId = runningId ?? history[0]?.experiment_id ?? null

  return (
    <div>
      <div className="page-title">
        <h2>System Monitor</h2>
      </div>
      <p className="page-subtitle">
        Live infrastructure status, plus the currently running experiment (or the most recently completed one) —
        request rate, latency, replica count, and CPU utilization, all from real telemetry.
      </p>

      <SystemStatusStrip status={status} />

      <div className="section">
        <div className="section-title">Experiment Telemetry</div>
        {activeId ? (
          <ExperimentDetail
            experimentId={activeId}
            isRunning={runningId === activeId}
            onRunStart={onRunStart}
            onRunFinished={onRunFinished}
            disableRun={runningId !== null && runningId !== activeId}
          />
        ) : (
          <p className="empty-note">No experiments have been run yet — go to Experiments to start one.</p>
        )}
      </div>
    </div>
  )
}
