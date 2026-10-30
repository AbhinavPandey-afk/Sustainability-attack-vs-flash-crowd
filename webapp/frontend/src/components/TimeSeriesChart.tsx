import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CHART_AXIS_LINE, CHART_AXIS_TEXT, CHART_GRID, CHART_MIXED, CHART_TOOLTIP_BG, CHART_TOOLTIP_BORDER } from '../theme'

interface Series {
  key: string
  label: string
  color: string
  /** Draws this line dashed — used for a baseline/reference series overlaid
   * alongside the current run's (solid) line. */
  dashed?: boolean
}

export function TimeSeriesChart({
  title,
  data,
  series,
  xKey = 'elapsed_seconds',
  yUnit,
  height = 220,
  phaseBoundaries,
}: {
  title: string
  data: Record<string, unknown>[]
  series: Series[]
  xKey?: string
  yUnit?: string
  height?: number
  /** Seconds-since-start of each E4 phase change, for an interleaved
   * (E4) experiment — drawn as vertical reference lines so a phase
   * switch (and its ground-truth label change) is visible on the chart. */
  phaseBoundaries?: number[]
}) {
  if (!data || data.length === 0) {
    return (
      <div className="chart-card">
        <div className="chart-title">{title}</div>
        <p className="empty-note">No data available.</p>
      </div>
    )
  }
  return (
    <div className="chart-card">
      <div className="chart-title">{title}</div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 4, right: 10, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
          <XAxis
            dataKey={xKey}
            tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }}
            tickFormatter={(v: number) => `${Math.round(v)}s`}
            stroke={CHART_AXIS_LINE}
          />
          <YAxis tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }} stroke={CHART_AXIS_LINE} unit={yUnit} width={48} />
          <Tooltip
            contentStyle={{ background: CHART_TOOLTIP_BG, border: `1px solid ${CHART_TOOLTIP_BORDER}`, borderRadius: 6, fontSize: 12 }}
            labelFormatter={(v) => `t = ${Math.round(Number(v))}s`}
          />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {series.map((s) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              dot={false}
              strokeWidth={2}
              strokeDasharray={s.dashed ? '5 4' : undefined}
              connectNulls
              isAnimationActive={false}
            />
          ))}
          {phaseBoundaries?.map((t) => (
            <ReferenceLine key={t} x={t} stroke={CHART_MIXED} strokeDasharray="4 4" strokeOpacity={0.6} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
