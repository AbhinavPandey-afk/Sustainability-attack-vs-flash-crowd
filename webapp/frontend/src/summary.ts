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

export interface EndpointCounts {
  totalRequests: number | null
  cheap: number | null
  medium: number | null
  expensive: number | null
  conversions: number | null
}

/** Real per-endpoint-class request counts for this run, from the delta of
 * the cumulative Prometheus counters sampled at the start/end of the run —
 * same source EndpointDistribution's chart already reads, just surfaced as
 * plain numbers (e.g. "how many expensive report requests actually
 * happened") instead of a chart. */
export function computeEndpointCounts(result: ExperimentResult): EndpointCounts {
  const ts = result.timeseries
  if (ts.length < 2) return { totalRequests: null, cheap: null, medium: null, expensive: null, conversions: null }
  const first = ts[0]
  const last = ts[ts.length - 1]
  const delta = (key: string) => Math.max(0, Number(last[key] ?? 0) - Number(first[key] ?? 0))
  return {
    totalRequests: delta('request_count'),
    cheap: delta('cheap_count'),
    medium: delta('medium_count'),
    expensive: delta('expensive_count'),
    conversions: delta('conversions'),
  }
}

export interface ComparisonMetrics {
  requestRate: number | null
  peakReplicas: number | null
  meanReplicas: number | null
  estimatedCost: number | null
  costPerRequest: number | null
  expensiveEndpointRatio: number | null
  cheapEndpointRatio: number | null
  endpointDiversity: number | null
  searchRatio: number | null
  reportGenerationRatio: number | null
  uniqueClientRatio: number | null
  conversionRate: number | null
}

const EMPTY_COMPARISON_METRICS: ComparisonMetrics = {
  requestRate: null,
  peakReplicas: null,
  meanReplicas: null,
  estimatedCost: null,
  costPerRequest: null,
  expensiveEndpointRatio: null,
  cheapEndpointRatio: null,
  endpointDiversity: null,
  searchRatio: null,
  reportGenerationRatio: null,
  uniqueClientRatio: null,
  conversionRate: null,
}

/** The real feature/timeseries values behind the Simulator page's O1
 * (infrastructure) and O2 (behavioural) comparison sections. Peak/mean
 * replicas are computed from the run's raw timeseries (the whole run),
 * not a single feature window, so a late-run peak isn't missed; every
 * other field is this run's most recent completed feature window, the
 * same convention computeSummaryStats already uses for cost/request. */
export function computeComparisonMetrics(result: ExperimentResult | null): ComparisonMetrics {
  if (!result || result.features.length === 0) return EMPTY_COMPARISON_METRICS
  const stats = computeSummaryStats(result)
  const last = result.features[result.features.length - 1]
  const num = (key: string): number | null => {
    const v = last[key]
    if (v === undefined || v === null) return null
    const n = Number(v)
    return Number.isNaN(n) ? null : n
  }
  const replicaCounts = result.timeseries.map((r) => Number(r.replica_count)).filter((n) => !Number.isNaN(n))
  const meanReplicas = replicaCounts.length ? replicaCounts.reduce((a, b) => a + b, 0) / replicaCounts.length : null

  return {
    requestRate: num('request_rate'),
    peakReplicas: stats.maxReplicas,
    meanReplicas,
    estimatedCost: stats.totalCost,
    costPerRequest: stats.costPerRequest,
    expensiveEndpointRatio: stats.expensiveEndpointRatio,
    cheapEndpointRatio: num('cheap_endpoint_ratio'),
    endpointDiversity: num('endpoint_diversity'),
    searchRatio: num('search_ratio'),
    reportGenerationRatio: num('report_generation_ratio'),
    uniqueClientRatio: num('unique_client_ratio'),
    conversionRate: num('conversion_rate'),
  }
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
