import { fmtNum } from '../format'
import type { ClassificationMetrics } from '../types'

/** Real tp/tn/fp/fn from a trained model's ClassificationMetrics, laid out
 * as an actual-vs-predicted 2x2 grid. Never recomputes or estimates these
 * counts — renders exactly what the model evaluation persisted. */
export function ConfusionMatrix({ metrics }: { metrics: ClassificationMetrics | null | undefined }) {
  if (!metrics) return <p className="empty-note">No evaluation metrics available yet.</p>

  const { tp, tn, fp, fn } = metrics
  const total = tp + tn + fp + fn
  if (!total) return <p className="empty-note">Evaluation metrics on disk have zero total observations.</p>

  return (
    <div>
      <div className="confusion-matrix">
        <div className="cm-corner" />
        <div className="cm-axis-label">Predicted Flash Crowd</div>
        <div className="cm-axis-label">Predicted EDoS</div>

        <div className="cm-row-label">Actual Flash Crowd</div>
        <div className="cm-cell cm-correct">
          <div className="cm-value">{fmtNum(tn, 0)}</div>
          <div className="cm-name">True Negative</div>
        </div>
        <div className="cm-cell cm-wrong">
          <div className="cm-value">{fmtNum(fp, 0)}</div>
          <div className="cm-name">False Positive</div>
        </div>

        <div className="cm-row-label">Actual EDoS</div>
        <div className="cm-cell cm-wrong">
          <div className="cm-value">{fmtNum(fn, 0)}</div>
          <div className="cm-name">False Negative</div>
        </div>
        <div className="cm-cell cm-correct">
          <div className="cm-value">{fmtNum(tp, 0)}</div>
          <div className="cm-name">True Positive</div>
        </div>
      </div>
      <p className="note-inline" style={{ marginTop: 10 }}>
        {total} labeled window{total === 1 ? '' : 's'} in this evaluation split — model: {metrics.model}.
      </p>
    </div>
  )
}
