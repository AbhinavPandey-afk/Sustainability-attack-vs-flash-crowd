import type { Hypothesis } from '../types'

const VERDICT_CLASS: Record<string, string> = {
  SUPPORTED: 'badge-verdict-SUPPORTED',
  REJECTED: 'badge-verdict-REJECTED',
  'NOT SUPPORTED': 'badge-verdict-NOT-SUPPORTED',
  'NOT REJECTED': 'badge-verdict-NOT-REJECTED',
  INCONCLUSIVE: 'badge-verdict-INCONCLUSIVE',
  'INSUFFICIENT DATA': 'badge-verdict-INSUFFICIENT-DATA',
}

/** Renders one real hypothesis verdict (H1/H0/H2) exactly as computed by
 * webapp/backend/detection.py::evaluate_hypotheses — the verdict, reason,
 * and evidence dict are all read as-is, never re-derived on the frontend. */
export function HypothesisCard({ hypothesis }: { hypothesis: Hypothesis }) {
  const evidenceEntries = Object.entries(hypothesis.evidence ?? {})
  return (
    <div className="card hypothesis-card">
      <div className="hypothesis-head">
        <h4 style={{ fontFamily: 'var(--mono)' }}>{hypothesis.id}</h4>
        <span className={`badge ${VERDICT_CLASS[hypothesis.verdict] ?? 'badge-verdict-INCONCLUSIVE'}`}>{hypothesis.verdict}</span>
      </div>
      <p className="hypothesis-text">{hypothesis.text}</p>
      <p className="hypothesis-reason">{hypothesis.reason}</p>
      {evidenceEntries.length > 0 && (
        <div className="evidence-grid">
          {evidenceEntries.map(([key, value]) => (
            <span key={key} className="evidence-chip">
              {key}: {typeof value === 'number' ? value.toFixed(4) : String(value)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
