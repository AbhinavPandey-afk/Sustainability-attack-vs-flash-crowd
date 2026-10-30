import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fmtNum } from '../format'
import { CHART_AXIS_LINE, CHART_AXIS_TEXT, CHART_AXIS_TEXT_STRONG, CHART_GRID, CHART_PRIMARY, CHART_TOOLTIP_BG, CHART_TOOLTIP_BORDER } from '../theme'
import type { ShapFeatureRow } from '../types'

/** Global ranked SHAP feature importance from /api/detection/shap — real
 * mean_abs_shap values from the trained model's explainer output, read
 * directly off results/tables/feature_statistics.csv. Never re-ranked or
 * invented on the frontend. */
export function GlobalShapChart({ rows }: { rows: ShapFeatureRow[] }) {
  const data = rows.filter((r) => r.mean_abs_shap !== null).slice(0, 15)
  if (data.length === 0) return <p className="empty-note">No SHAP importances available yet.</p>

  return (
    <div className="chart-card">
      <div className="chart-title">Global Feature Importance (mean |SHAP|)</div>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 30)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} horizontal={false} />
          <XAxis type="number" tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }} stroke={CHART_AXIS_LINE} />
          <YAxis type="category" dataKey="feature" width={190} tick={{ fill: CHART_AXIS_TEXT_STRONG, fontSize: 11.5 }} stroke={CHART_AXIS_LINE} />
          <Tooltip
            contentStyle={{ background: CHART_TOOLTIP_BG, border: `1px solid ${CHART_TOOLTIP_BORDER}`, borderRadius: 6, fontSize: 12 }}
            formatter={(v) => fmtNum(v as number, 4)}
          />
          <Bar dataKey="mean_abs_shap" fill={CHART_PRIMARY} radius={4} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
