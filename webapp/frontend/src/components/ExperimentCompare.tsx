import { useEffect, useState } from 'react'
import { api } from '../api'
import { fmtNum, fmtPct, fmtRatio } from '../format'
import { computeSummaryStats } from '../summary'
import type { ExperimentExample, ExperimentResult } from '../types'
import { TimeSeriesChart } from './TimeSeriesChart'

function Picker({
  label,
  examples,
  value,
  onChange,
}: {
  label: string
  examples: ExperimentExample[]
  value: string
  onChange: (id: string) => void
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: 'var(--text-faint)' }}>
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: 'var(--surface-2)',
          color: 'var(--text)',
          border: '1px solid var(--border)',
          borderRadius: 6,
          padding: '7px 10px',
          fontFamily: 'var(--mono)',
          fontSize: 13,
        }}
      >
        {examples.map((ex) => (
          <option key={ex.experiment_id} value={ex.experiment_id}>
            {ex.experiment_id} ({ex.scenario_label})
          </option>
        ))}
      </select>
    </label>
  )
}

const ROWS: { key: keyof ReturnType<typeof computeSummaryStats>; label: string; fmt: (v: number | null) => string }[] = [
  { key: 'totalRequests', label: 'Total Requests', fmt: (v) => fmtNum(v, 0) },
  { key: 'peakRps', label: 'Peak Request Rate', fmt: (v) => `${fmtNum(v, 1)} req/s` },
  { key: 'maxReplicas', label: 'Max Replicas', fmt: (v) => fmtNum(v, 0) },
  { key: 'totalCost', label: 'Total Cost (experimental units)', fmt: (v) => fmtNum(v, 4) },
  { key: 'costPerRequest', label: 'Cost / Request', fmt: (v) => fmtNum(v, 5) },
  { key: 'expensiveEndpointRatio', label: 'Expensive-Endpoint Ratio', fmt: (v) => fmtPct(v) },
]

function pickDefault(examples: ExperimentExample[], predicate: (ex: ExperimentExample) => boolean, fallback: string) {
  return examples.find(predicate)?.experiment_id ?? fallback
}

export function ExperimentCompare({ examples }: { examples: ExperimentExample[] }) {
  const [idA, setIdA] = useState('')
  const [idB, setIdB] = useState('')
  const [resultA, setResultA] = useState<ExperimentResult | null>(null)
  const [resultB, setResultB] = useState<ExperimentResult | null>(null)

  useEffect(() => {
    if (examples.length === 0 || idA) return
    setIdA(pickDefault(examples, (ex) => ex.experiment_id === 'FC_VIRAL_001', pickDefault(examples, (ex) => ex.scenario_type === 'flash_crowd', examples[0]?.experiment_id ?? '')))
    setIdB(pickDefault(examples, (ex) => ex.experiment_id === 'EDOS_001', pickDefault(examples, (ex) => ex.scenario_type === 'edos', examples[0]?.experiment_id ?? '')))
  }, [examples, idA])

  useEffect(() => {
    if (!idA) return
    setResultA(null)
    api.result(idA).then(setResultA).catch(() => setResultA(null))
  }, [idA])

  useEffect(() => {
    if (!idB) return
    setResultB(null)
    api.result(idB).then(setResultB).catch(() => setResultB(null))
  }, [idB])

  if (examples.length === 0) return <p className="empty-note">No experiments available yet.</p>

  const statsA = resultA ? computeSummaryStats(resultA) : null
  const statsB = resultB ? computeSummaryStats(resultB) : null

  return (
    <div>
      <div style={{ display: 'flex', gap: 20, marginBottom: 16, flexWrap: 'wrap' }}>
        <Picker label="Experiment A" examples={examples} value={idA} onChange={setIdA} />
        <Picker label="Experiment B" examples={examples} value={idB} onChange={setIdB} />
      </div>

      {statsA && statsB && (
        <div className="card table-scroll">
          <table>
            <thead>
              <tr>
                <th>Metric</th>
                <th className="num">{idA}</th>
                <th className="num">{idB}</th>
                <th className="num">B vs A</th>
              </tr>
            </thead>
            <tbody>
              {ROWS.map((row) => (
                <tr key={row.key}>
                  <td>{row.label}</td>
                  <td className="num">{row.fmt(statsA[row.key])}</td>
                  <td className="num">{row.fmt(statsB[row.key])}</td>
                  <td className="num">{fmtRatio(statsB[row.key], statsA[row.key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {statsA && statsB && statsA.totalCost !== null && statsB.totalCost !== null && statsA.totalRequests !== null && statsB.totalRequests !== null && (
        <p style={{ fontSize: 13, color: 'var(--text-dim)', marginTop: 12, lineHeight: 1.6 }}>
          <strong>{idB}</strong> produced <strong>{fmtRatio(statsB.costPerRequest, statsA.costPerRequest)}</strong>{' '}
          cost per request than <strong>{idA}</strong>, while its total request count was{' '}
          <strong>{fmtRatio(statsB.totalRequests, statsA.totalRequests)}</strong>.
        </p>
      )}

      <div className="two-col" style={{ marginTop: 16 }}>
        <TimeSeriesChart
          title={`${idA || 'A'} — Request Rate (req/s)`}
          data={resultA?.locust_history ?? []}
          series={[{ key: 'Requests/s', label: 'req/s', color: '#2dd4bf' }]}
        />
        <TimeSeriesChart
          title={`${idB || 'B'} — Request Rate (req/s)`}
          data={resultB?.locust_history ?? []}
          series={[{ key: 'Requests/s', label: 'req/s', color: '#fb7185' }]}
        />
      </div>
    </div>
  )
}
