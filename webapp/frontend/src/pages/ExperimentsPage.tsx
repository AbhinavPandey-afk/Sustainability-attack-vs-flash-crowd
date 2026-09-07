import { ExperimentCompare } from '../components/ExperimentCompare'
import { ExperimentDetail } from '../components/ExperimentDetail'
import { ExperimentGrid } from '../components/ExperimentGrid'
import type { ExperimentExample } from '../types'

export function ExperimentsPage({
  examples,
  selectedId,
  onSelect,
  runningId,
  onRunStart,
  onRunFinished,
}: {
  examples: ExperimentExample[]
  selectedId: string | null
  onSelect: (id: string) => void
  runningId: string | null
  onRunStart: (id: string) => void
  onRunFinished: () => void
}) {
  return (
    <div>
      <div className="page-title">
        <h2>Experiments</h2>
      </div>
      <p className="page-subtitle">
        Pure flash-crowd, pure EDoS, a viral-arrival-curve flash crowd, simultaneous mixed traffic (E3), and
        alternating interleaved phases (E4). Select one to run it live or open its saved result.
      </p>

      <ExperimentGrid examples={examples} selectedId={selectedId} onSelect={onSelect} runningId={runningId} />

      {selectedId && (
        <div className="section">
          <div className="section-title">Experiment Control &amp; Live View</div>
          <ExperimentDetail
            experimentId={selectedId}
            isRunning={runningId === selectedId}
            onRunStart={onRunStart}
            onRunFinished={onRunFinished}
            disableRun={runningId !== null && runningId !== selectedId}
          />
        </div>
      )}

      <div className="section">
        <div className="section-title">Compare Two Experiments</div>
        <ExperimentCompare examples={examples} />
      </div>
    </div>
  )
}
