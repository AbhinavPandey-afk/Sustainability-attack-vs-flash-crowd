import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  CHART_AXIS_LINE,
  CHART_AXIS_TEXT,
  CHART_AXIS_TEXT_STRONG,
  CHART_ENDPOINT_CHEAP,
  CHART_ENDPOINT_EXPENSIVE,
  CHART_ENDPOINT_MEDIUM,
  CHART_GRID,
  CHART_TOOLTIP_BG,
  CHART_TOOLTIP_BORDER,
} from '../theme'
import type { TimeseriesRow } from '../types'

const COLORS: Record<string, string> = {
  cheap: CHART_ENDPOINT_CHEAP,
  medium: CHART_ENDPOINT_MEDIUM,
  expensive: CHART_ENDPOINT_EXPENSIVE,
}

export function EndpointDistribution({ timeseries }: { timeseries: TimeseriesRow[] }) {
  if (!timeseries || timeseries.length < 2) {
    return (
      <div className="chart-card">
        <div className="chart-title">Endpoint Distribution</div>
        <p className="empty-note">No data available.</p>
      </div>
    )
  }
  const first = timeseries[0]
  const last = timeseries[timeseries.length - 1]
  const delta = (key: string) => Math.max(0, Number(last[key] ?? 0) - Number(first[key] ?? 0))

  const data = [
    { name: 'cheap (home/checkout)', value: delta('cheap_count') },
    { name: 'medium (search)', value: delta('medium_count') },
    { name: 'expensive (generate-report)', value: delta('expensive_count') },
  ]
  const total = data.reduce((sum, d) => sum + d.value, 0)

  return (
    <div className="chart-card">
      <div className="chart-title">Endpoint Distribution ({total.toLocaleString()} requests observed)</div>
      {total === 0 ? (
        <p className="empty-note">No requests observed in the sampled window.</p>
      ) : (
        <ResponsiveContainer width="100%" height={160}>
          <BarChart data={data} layout="vertical" margin={{ left: 10, right: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} horizontal={false} />
            <XAxis type="number" tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }} stroke={CHART_AXIS_LINE} />
            <YAxis type="category" dataKey="name" width={160} tick={{ fill: CHART_AXIS_TEXT_STRONG, fontSize: 11.5 }} stroke={CHART_AXIS_LINE} />
            <Tooltip
              contentStyle={{ background: CHART_TOOLTIP_BG, border: `1px solid ${CHART_TOOLTIP_BORDER}`, borderRadius: 6, fontSize: 12 }}
              formatter={(v) => {
                const n = Number(v)
                return [`${n.toLocaleString()} req (${((n / total) * 100).toFixed(1)}%)`, '']
              }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]}>
              {data.map((_, i) => (
                <Cell key={i} fill={i === 0 ? COLORS.cheap : i === 1 ? COLORS.medium : COLORS.expensive} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
