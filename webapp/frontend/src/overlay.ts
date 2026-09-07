/** Merges a baseline (e.g. NORMAL_001, "an ordinary day") run's time series
 * with a current run's, bucketed onto a shared elapsed_seconds axis, so a
 * chart can plot both as separate lines over the same timeline. Real data
 * from two independent runs — not synthesized. Gaps (a bucket only one
 * series has a sample for) are left as null; recharts skips them. */
export function overlayByElapsedSeconds(
  baselineRows: Record<string, unknown>[],
  currentRows: Record<string, unknown>[],
  xKey: string,
  valueKey: string,
  bucketSeconds = 5,
): { elapsed_seconds: number; baseline: number | null; current: number | null }[] {
  const bucket = (v: unknown) => Math.round(Number(v) / bucketSeconds) * bucketSeconds
  const map = new Map<number, { elapsed_seconds: number; baseline: number | null; current: number | null }>()

  for (const row of baselineRows) {
    const x = bucket(row[xKey])
    if (Number.isNaN(x)) continue
    const existing = map.get(x) ?? { elapsed_seconds: x, baseline: null, current: null }
    const v = Number(row[valueKey])
    existing.baseline = Number.isNaN(v) ? existing.baseline : v
    map.set(x, existing)
  }
  for (const row of currentRows) {
    const x = bucket(row[xKey])
    if (Number.isNaN(x)) continue
    const existing = map.get(x) ?? { elapsed_seconds: x, baseline: null, current: null }
    const v = Number(row[valueKey])
    existing.current = Number.isNaN(v) ? existing.current : v
    map.set(x, existing)
  }

  return Array.from(map.values()).sort((a, b) => a.elapsed_seconds - b.elapsed_seconds)
}
