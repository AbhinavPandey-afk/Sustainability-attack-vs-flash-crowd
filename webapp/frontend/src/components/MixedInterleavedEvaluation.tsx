import { fmtPct } from '../format'
import type { MixedEvaluationResponse } from '../types'

const TITLES: Record<string, string> = {
  MIX_001: 'MIX_001 — E3: Flash Crowd + EDoS Simultaneously',
  INTERLEAVED_001: 'INTERLEAVED_001 — E4: Alternating Phases',
}

export function MixedInterleavedEvaluation({ evaluation }: { evaluation: MixedEvaluationResponse | null }) {
  if (!evaluation) return <p className="empty-note">Loading…</p>
  if (!evaluation.available) {
    return (
      <p className="empty-note">
        No E3/E4 evaluation available yet — run MIX_001 and/or INTERLEAVED_001 above, then re-run
        experiments/summarize_results.py (or just run them live from this dashboard).
      </p>
    )
  }

  return (
    <div className="grid grid-2">
      {Object.entries(evaluation.results).map(([name, entry]) => {
        const cascade = entry.cascade_lightgbm
        const rateLimiter = entry.rate_limiter
        const volumetric = entry.volumetric_detector
        return (
          <div key={name} className="card">
            <h4 style={{ fontFamily: 'var(--mono)', fontSize: 14 }}>{TITLES[name] ?? name}</h4>
            <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4 }}>
              {cascade.n_windows} feature window{cascade.n_windows === 1 ? '' : 's'} · label distribution{' '}
              {JSON.stringify(cascade.label_distribution)}
            </p>
            <div className="grid grid-3" style={{ marginTop: 10 }}>
              <div className="stat-tile">
                <div className="stat-label">CASCADE Recall</div>
                <div className="stat-value">{fmtPct(cascade.recall)}</div>
              </div>
              <div className="stat-tile">
                <div className="stat-label">CASCADE Flash-Crowd FPR</div>
                <div className="stat-value">{fmtPct(cascade.flash_crowd_false_positive_rate)}</div>
              </div>
              <div className="stat-tile">
                <div className="stat-label">Volumetric z-score Recall</div>
                <div className="stat-value">{volumetric ? fmtPct(volumetric.tpr as number) : '—'}</div>
              </div>
            </div>
            {rateLimiter && (
              <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 10 }}>
                Rate limiter (same calibrated threshold as the main evaluation): attack detected ={' '}
                {String(rateLimiter.attack_detected)}, threshold = {String(rateLimiter.threshold)} req/s.
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}
