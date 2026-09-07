import { ExperimentDetail } from '../components/ExperimentDetail'
import type { HistoryEntry } from '../types'

export function LiveMonitorPage({
  runningId,
  history,
  onRunStart,
  onRunFinished,
}: {
  runningId: string | null
  history: HistoryEntry[]
  onRunStart: (id: string) => void
  onRunFinished: () => void
}) {
  const activeId = runningId ?? history[0]?.experiment_id ?? null

  return (
    <div>
      <div className="page-title">
        <h2>Live Monitor</h2>
      </div>
      <p className="page-subtitle">
        The currently running experiment (or the most recently completed one) — request rate, latency, replica
        count, and CPU utilization, from real telemetry.
      </p>
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
  )
}
