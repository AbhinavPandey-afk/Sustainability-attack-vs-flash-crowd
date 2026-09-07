import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import type { DetectionExplanation, ExperimentResult, RunStatus } from '../types'

/** Shared start/poll/stop lifecycle for the Attack Simulator and Flash Crowd
 * Simulator pages — both drive a real, ad-hoc live run through
 * /api/simulator/{kind}/*, never a client-side fake animation. */
export function useSimulatorRun(kind: 'attack' | 'flash-crowd') {
  const [experimentId, setExperimentId] = useState<string | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [result, setResult] = useState<ExperimentResult | null>(null)
  const [explanation, setExplanation] = useState<DetectionExplanation | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  const isRunning = runStatus?.state === 'STARTING' || runStatus?.state === 'RUNNING'

  const start = async (params: Record<string, number>) => {
    setError(null)
    setResult(null)
    setExplanation(null)
    try {
      const { experiment_id } = await api.startSimulator(kind, params)
      setExperimentId(experiment_id)
      setRunStatus({ experiment_id, state: 'STARTING' })
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const stop = async () => {
    try {
      await api.stopSimulator(kind)
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

  return { experimentId, runStatus, result, explanation, error, isRunning, start, stop }
}
