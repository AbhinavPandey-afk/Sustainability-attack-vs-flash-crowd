import { fmtNum, fmtPct } from '../format'
import type { ComparisonMetrics } from '../summary'

export interface ComparisonRowSpec {
  key: keyof ComparisonMetrics
  label: string
  format: 'num' | 'pct'
  digits?: number
}

/** Generic "current run vs. reference run" table over real ComparisonMetrics
 * values — used for the Current-vs-Opposite-Class panel and the O1/O2
 * sections. Highlights the row with the largest relative difference when
 * highlightMaxDelta is set (used by O2 to surface the most differentiating
 * behavioural feature), never invents a row that isn't in `rows`. */
export function ComparisonTable({
  rows,
  current,
  opposite,
  currentLabel,
  oppositeLabel,
  highlightMaxDelta,
}: {
  rows: ComparisonRowSpec[]
  current: ComparisonMetrics
  opposite: ComparisonMetrics | null
  currentLabel: string
  oppositeLabel: string
  highlightMaxDelta?: boolean
}) {
  const withDelta = rows.map((row) => {
    const a = current[row.key]
    const b = opposite?.[row.key] ?? null
    const delta = a !== null && b !== null && b !== 0 ? Math.abs(a - b) : null
    return { row, a, b, delta }
  })
  const maxDelta = highlightMaxDelta ? Math.max(...withDelta.map((r) => r.delta ?? -1)) : null

  const fmt = (row: ComparisonRowSpec, v: number | null) =>
    row.format === 'pct' ? fmtPct(v, row.digits ?? 1) : fmtNum(v, row.digits ?? 2)

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Feature</th>
            <th className="num">{currentLabel}</th>
            <th className="num">{oppositeLabel}</th>
          </tr>
        </thead>
        <tbody>
          {withDelta.map(({ row, a, b, delta }) => (
            <tr key={String(row.key)} style={maxDelta !== null && delta === maxDelta && delta > 0 ? { background: 'var(--surface-2)' } : undefined}>
              <td>{row.label}</td>
              <td className="num">{fmt(row, a)}</td>
              <td className="num">{opposite ? fmt(row, b) : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
