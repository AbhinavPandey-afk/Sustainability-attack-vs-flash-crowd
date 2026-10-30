import type {
  DetectionExplanation,
  DetectionSummary,
  EndpointHeatmapResponse,
  ExperimentConfig,
  ExperimentExample,
  ExperimentResult,
  FiguresListResponse,
  HistoryEntry,
  Hypotheses,
  LiveImpact,
  MatchReport,
  MixedEvaluationResponse,
  PcaResponse,
  PredictionResponse,
  ResearchQuestion,
  RunStatus,
  ShapSummaryResponse,
  SystemStatus,
} from './types'

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path)
  if (!res.ok) {
    const body = await res.text().catch(() => '')
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  systemStatus: () => getJson<SystemStatus>('/api/system/status'),
  researchQuestion: () => getJson<ResearchQuestion>('/api/system/research-question'),
  examples: () => getJson<ExperimentExample[]>('/api/experiments/examples'),
  history: () => getJson<HistoryEntry[]>('/api/experiments'),
  config: (id: string) => getJson<ExperimentConfig>(`/api/experiments/${id}/config`),
  result: (id: string) => getJson<ExperimentResult>(`/api/experiments/${id}/result`),
  runStatus: (id: string) => getJson<RunStatus>(`/api/experiments/${id}/run-status`),
  startRun: async (id: string): Promise<{ experiment_id: string; status: string }> => {
    const res = await fetch(`/api/experiments/${id}/run`, { method: 'POST' })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  stopRun: async (id: string): Promise<{ experiment_id: string; stopped: boolean }> => {
    const res = await fetch(`/api/experiments/${id}/stop`, { method: 'POST' })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  startSimulator: async (
    kind: 'attack' | 'flash-crowd',
    params: Record<string, number>,
  ): Promise<{ experiment_id: string; status: string }> => {
    const res = await fetch(`/api/simulator/${kind}/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  stopSimulator: async (kind: 'attack' | 'flash-crowd'): Promise<{ stopped: boolean }> => {
    const res = await fetch(`/api/simulator/${kind}/stop`, { method: 'POST' })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  startUnifiedSimulator: async (params: Record<string, number>): Promise<{ experiment_id: string; status: string }> => {
    const res = await fetch('/api/simulator/run/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  stopUnifiedSimulator: async (): Promise<{ stopped: boolean }> => {
    const res = await fetch('/api/simulator/run/stop', { method: 'POST' })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  predict: (id: string) => getJson<PredictionResponse>(`/api/detection/predict/${id}`),
  detectionSummary: () => getJson<DetectionSummary>('/api/detection/summary'),
  matchReport: async (id: string): Promise<MatchReport | null> => {
    const res = await fetch(`/api/experiments/${id}/match-report`)
    if (res.status === 404) return null
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  storefrontImpact: () => getJson<LiveImpact>('/api/storefront/impact'),
  startDemo: async (): Promise<{ sequence: string[]; status: string }> => {
    const res = await fetch('/api/demo/run', { method: 'POST' })
    if (!res.ok) {
      const body = await res.text().catch(() => '')
      throw new Error(`${res.status} ${res.statusText}: ${body}`)
    }
    return res.json()
  },
  demoStatus: () => getJson<RunStatus>('/api/demo/status'),
  explain: (id: string) => getJson<DetectionExplanation>(`/api/analytics/explain/${id}`),
  normalBaseline: () => getJson<ExperimentResult>('/api/experiments/NORMAL_001/result'),
  exportUrl: (id: string) => `/api/experiments/${id}/export.zip`,
  hypotheses: () => getJson<Hypotheses>('/api/detection/hypotheses'),
  mixedEvaluation: () => getJson<MixedEvaluationResponse>('/api/detection/mixed-evaluation'),
  shap: () => getJson<ShapSummaryResponse>('/api/detection/shap'),
  figures: () => getJson<FiguresListResponse>('/api/results/figures'),
  figureUrl: (name: string) => `/api/results/figures/${name}`,
  endpointHeatmap: (experimentId?: string) =>
    getJson<EndpointHeatmapResponse>(`/api/analytics/endpoint-heatmap${experimentId ? `?experiment_id=${encodeURIComponent(experimentId)}` : ''}`),
  pca: () => getJson<PcaResponse>('/api/analytics/pca'),
}
