import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DetectionExplanation, ExperimentResult, PredictionResponse, RunStatus } from '../types'

/** Start/poll/stop lifecycle for the unified Traffic Classification
 * Simulator. Always drives a real, ad-hoc live run through
 * /api/simulator/run/* (webapp/backend/scenario_builder.py's
 * build_unified_config) — never a client-side fake animation — and, once
 * the run completes, fetches the real trained detector's classification
 * for it (/api/detection/predict/{id}) alongside the existing result/SHAP
 * explanation. The detector call is the only source of the EDoS/Flash
 * Crowd label shown to the user. */
export function useUnifiedSimulatorRun() {
  const [experimentId, setExperimentId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [result, setResult] = useState<ExperimentResult | null>(null)
  const [explanation, setExplanation] = useState<DetectionExplanation | null>(null)
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  const isRunning = runStatus?.state === 'STARTING' || runStatus?.state === 'RUNNING'

  const start = async (params: Record<string, number>) => {
    setError(null)
    setResult(null)
    setExplanation(null)
    setPrediction(null)
    try {
      const { experiment_id } = await api.startUnifiedSimulator(params)
      setExperimentId(experiment_id)
      setRunStatus({ experiment_id, state: 'STARTING' })
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const stop = async () => {
    try {
      await api.stopUnifiedSimulator()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  useEffect(() => {
    if (!experimentId || !isRunning) {
      if (pollRef.current) window.clearInterval(pollRef.current)
      return
    }
    const poll = async () => {
      try {
        const s = await api.runStatus(experimentId)
        setRunStatus(s)
        if (s.state === 'COMPLETED') {
          if (pollRef.current) window.clearInterval(pollRef.current)
          const fresh = await api.result(experimentId)
          setResult(fresh)
          api.explain(experimentId).then(setExplanation).catch(() => setExplanation(null))
          api.predict(experimentId).then(setPrediction).catch(() => setPrediction(null))
        } else if (s.state === 'FAILED' || s.state === 'CANCELLED') {
          if (pollRef.current) window.clearInterval(pollRef.current)
        }
      } catch {
        // transient — next tick retries
      }
    }
    poll()
    pollRef.current = window.setInterval(poll, 1500)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [experimentId, isRunning])

  return { experimentId, runStatus, result, explanation, prediction, error, isRunning, start, stop }
}
