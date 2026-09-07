import { Bar, BarChart, CartesianGrid, Cell, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtNum } from '../format'
import type { DetectionExplanation, DetectionExplanationFactor } from '../types'

interface Row {
  feature: string
  contribution: number
  direction: DetectionExplanationFactor['direction']
  this_run_value: number | null
  flash_crowd_mean: number | null
  edos_mean: number | null
  mean_abs_shap: number
}

function ContributionTooltip({ active, payload }: { active?: boolean; payload?: { payload: Row }[] }) {
  if (!active || !payload || payload.length === 0) return null
  const row = payload[0].payload
  return (
    <div style={{ background: '#131a26', border: '1px solid #253145', borderRadius: 6, fontSize: 12, padding: '8px 10px' }}>
      <div style={{ fontFamily: 'var(--mono)', marginBottom: 4 }}>{row.feature}</div>
      <div>SHAP importance: {fmtNum(row.mean_abs_shap, 4)}</div>
      <div>This run: {fmtNum(row.this_run_value, 4)}</div>
      <div>Flash-crowd avg: {fmtNum(row.flash_crowd_mean, 4)}</div>
      <div>EDoS avg: {fmtNum(row.edos_mean, 4)}</div>
      <div style={{ marginTop: 4, color: row.direction === 'closer_to_edos' ? '#fb7185' : '#2dd4bf' }}>
        Pulls toward {row.direction === 'closer_to_edos' ? 'EDoS' : 'Flash Crowd'}
      </div>
    </div>
  )
}

/** Turns the per-run SHAP factor list (real importances + real direction,
 * from /api/analytics/explain) into a diverging bar chart — bars pointing
 * right (red) pulled the classification toward EDoS, bars pointing left
 * (teal) pulled it toward Flash Crowd. Bar length is the feature's real
 * SHAP importance for this model, not a fabricated score. */
export function FeatureContributionChart({ explanation }: { explanation: DetectionExplanation | null }) {
  if (!explanation?.available || !explanation.factors) return null

  const data: Row[] = explanation.factors
    .filter((f) => f.direction !== null)
    .map((f) => ({
      feature: f.feature,
      contribution: f.direction === 'closer_to_edos' ? f.mean_abs_shap : -f.mean_abs_shap,
      direction: f.direction,
      this_run_value: f.this_run_value,
      flash_crowd_mean: f.flash_crowd_mean,
      edos_mean: f.edos_mean,
      mean_abs_shap: f.mean_abs_shap,
    }))
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))

  if (data.length === 0) return null

  const maxAbs = Math.max(...data.map((d) => Math.abs(d.contribution)), 0.0001)

  return (
    <div className="chart-card">
      <div className="chart-title">Which features pulled this run's classification</div>
      <ResponsiveContainer width="100%" height={Math.max(140, data.length * 32)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 20, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1c2636" horizontal={false} />
          <XAxis
            type="number"
            domain={[-maxAbs, maxAbs]}
            ticks={[-maxAbs, -maxAbs / 2, 0, maxAbs / 2, maxAbs]}
            tick={{ fill: '#6b7a90', fontSize: 11 }}
            stroke="#253145"
            tickFormatter={(v: number) => Math.abs(v).toFixed(2)}
          />
          <YAxis type="category" dataKey="feature" width={170} tick={{ fill: '#97a6bb', fontSize: 11.5 }} stroke="#253145" />
          <ReferenceLine x={0} stroke="#3a4a63" />
          <Tooltip content={<ContributionTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
          <Bar dataKey="contribution" radius={4}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.direction === 'closer_to_edos' ? '#fb7185' : '#2dd4bf'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-faint)', marginTop: 6 }}>
        <span style={{ color: '#2dd4bf' }}>← pulls toward Flash Crowd</span>
        <span>bar length = SHAP importance</span>
        <span style={{ color: '#fb7185' }}>pulls toward EDoS →</span>
      </div>
    </div>
  )
}
