export function fmtNum(value: unknown, digits = 2): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return '—'
  const rounded = Number(n.toFixed(digits)) + 0 // collapses -0 to 0
  return rounded.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 })
}

/** A / B as an "Nx higher/lower" phrase, for side-by-side comparisons. */
export function fmtRatio(a: number | null | undefined, b: number | null | undefined): string {
  if (a === null || a === undefined || b === null || b === undefined || b === 0) return '—'
  const ratio = a / b
  if (!Number.isFinite(ratio)) return '—'
  if (ratio >= 1) return `${ratio.toFixed(ratio >= 10 ? 0 : 1)}x higher`
  return `${(1 / ratio).toFixed(1 / ratio >= 10 ? 0 : 1)}x lower`
}

export function fmtPct(value: unknown, digits = 1): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return '—'
  return `${(n * 100).toFixed(digits)}%`
}

export function fmtSeconds(value: unknown): string {
  if (value === null || value === undefined) return '—'
  const n = typeof value === 'number' ? value : Number(value)
  if (Number.isNaN(n)) return '—'
  return `${n.toFixed(1)}s`
}
