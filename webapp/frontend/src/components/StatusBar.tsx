import type { SystemStatus } from '../types'

export function StatusBar({ status }: { status: SystemStatus | null }) {
  if (!status) {
    return (
      <div className="status-row">
        <span className="empty-note">Checking system status…</span>
      </div>
    )
  }
  const components = [status.kubernetes, status.application, status.prometheus, status.experiment_runner, status.detector]
  return (
    <div className="status-row">
      {components.map((c) => (
        <span key={c.component} className={`status-pill status-${c.status}`} title={c.detail}>
          <span className="status-dot" />
          {c.component}
        </span>
      ))}
    </div>
  )
}
