import type { ExperimentExample, ScenarioType } from '../types'

const BADGE_CLASS: Record<ScenarioType, string> = {
  flash_crowd: 'badge-fc',
  edos: 'badge-edos',
  mixed: 'badge-mixed',
  interleaved: 'badge-mixed',
  normal: 'badge-normal',
}

export function ExperimentGrid({
  examples,
  selectedId,
  onSelect,
  runningId,
}: {
  examples: ExperimentExample[]
  selectedId: string | null
  onSelect: (id: string) => void
  runningId: string | null
}) {
  if (examples.length === 0) {
    return <p className="empty-note">No experiment configs found under experiments/configs/.</p>
  }
  return (
    <div className="experiment-grid">
      {examples.map((ex) => (
        <div
          key={ex.experiment_id}
          className={`exp-card-compact type-${ex.scenario_type} ${selectedId === ex.experiment_id ? 'selected' : ''} ${
            runningId === ex.experiment_id ? 'running' : ''
          }`}
          onClick={() => onSelect(ex.experiment_id)}
          title={ex.experiment_id}
        >
          <span className="exp-card-title">{ex.experiment_id}</span>
          <span className={`badge ${BADGE_CLASS[ex.scenario_type]}`}>{ex.scenario_label}</span>
        </div>
      ))}
    </div>
  )
}
