import type { ExperimentResult } from './types'

export interface ExperimentSummaryStats {
  totalRequests: number | null
  peakRps: number | null
  maxReplicas: number | null
  totalCost: number | null
  costPerRequest: number | null
  expensiveEndpointRatio: number | null
}

/** Derived, on-the-fly from a result's real features/timeseries/locust_history —
 * nothing here is a separate measurement, just simple aggregates of what the
 * backend already returned. */
export function computeSummaryStats(result: ExperimentResult): ExperimentSummaryStats {
  const lastLocust = result.locust_history[result.locust_history.length - 1]
  const totalRequests = lastLocust ? Number(lastLocust['Total Request Count']) || null : null

  const peakRps = result.locust_history.length
    ? Math.max(...result.locust_history.map((r) => Number(r['Requests/s']) || 0))
    : null

  const maxReplicas = result.timeseries.length
    ? Math.max(...result.timeseries.map((r) => Number(r.replica_count) || 0))
    : null

  const totalCost = result.features.length
    ? result.features.reduce((sum, f) => sum + (Number(f.estimated_cost) || 0), 0)
    : null

  const lastFeature = result.features[result.features.length - 1]
  const costPerRequest = lastFeature?.cost_per_request !== undefined ? Number(lastFeature.cost_per_request) : null
  const expensiveEndpointRatio =
    lastFeature?.expensive_endpoint_ratio !== undefined ? Number(lastFeature.expensive_endpoint_ratio) : null

  return { totalRequests, peakRps, maxReplicas, totalCost, costPerRequest, expensiveEndpointRatio }
}

/** Cumulative cost-so-far at each feature window — shows cost building up
 * over the course of a run, rather than a single end-of-run total. */
export function cumulativeCostSeries(result: ExperimentResult): { elapsed_seconds: number; cumulative_cost: number }[] {
  if (result.features.length === 0) return []
  const start = Number(result.features[0].window_end) - Number(result.features[0].window_seconds)
  let running = 0
  return result.features.map((f) => {
    running += Number(f.estimated_cost) || 0
    return { elapsed_seconds: Number(f.window_end) - start, cumulative_cost: running }
  })
}
