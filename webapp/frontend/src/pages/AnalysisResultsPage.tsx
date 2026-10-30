import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis, ZAxis } from 'recharts'
import { api } from '../api'
import { GlobalShapChart } from '../components/GlobalShapChart'
import { fmtNum, fmtPct } from '../format'
import {
  CHART_AXIS_LINE,
  CHART_AXIS_TEXT,
  CHART_AXIS_TEXT_STRONG,
  CHART_EDOS,
  CHART_FC,
  CHART_GRID,
  CHART_SECONDARY,
  CHART_TOOLTIP_BG,
  CHART_TOOLTIP_BORDER,
} from '../theme'
import type { ClassificationMetrics, DetectionSummary, EndpointHeatmapResponse, PcaResponse, ShapSummaryResponse } from '../types'

function AblationChart({ rows }: { rows: ClassificationMetrics[] }) {
  if (rows.length === 0) return <p className="empty-note">No ablation results on disk yet.</p>
  const data = rows.map((r) => ({ name: r.model, f1: r.f1 }))
  return (
    <div className="chart-card">
      <div className="chart-title">Ablation — F1 by Feature Set</div>
      <ResponsiveContainer width="100%" height={Math.max(160, data.length * 34)}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 24, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} horizontal={false} />
          <XAxis type="number" domain={[0, 1]} tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }} stroke={CHART_AXIS_LINE} />
          <YAxis type="category" dataKey="name" width={200} tick={{ fill: CHART_AXIS_TEXT_STRONG, fontSize: 11.5 }} stroke={CHART_AXIS_LINE} />
          <Tooltip
            contentStyle={{ background: CHART_TOOLTIP_BG, border: `1px solid ${CHART_TOOLTIP_BORDER}`, borderRadius: 6, fontSize: 12 }}
            formatter={(v) => fmtPct(v as number)}
          />
          <Bar dataKey="f1" fill={CHART_SECONDARY} radius={4} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function PcaScatter({ pca }: { pca: PcaResponse | null }) {
  if (!pca) return <p className="empty-note">Loading PCA separability…</p>
  if (!pca.available) return <p className="empty-note">{pca.detail ?? 'PCA separability not available yet.'}</p>
  const fc = pca.points.filter((p) => p.label === 0)
  const edos = pca.points.filter((p) => p.label === 1)
  return (
    <div className="chart-card">
      <div className="chart-title">Feature-Space Separability (PCA, real computed coordinates)</div>
      <ResponsiveContainer width="100%" height={320}>
        <ScatterChart margin={{ top: 8, right: 20, bottom: 8, left: 0 }}>
          <CartesianGrid stroke={CHART_GRID} />
          <XAxis type="number" dataKey="pc1" name="PC1" tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }} stroke={CHART_AXIS_LINE} />
          <YAxis type="number" dataKey="pc2" name="PC2" tick={{ fill: CHART_AXIS_TEXT, fontSize: 11 }} stroke={CHART_AXIS_LINE} />
          <ZAxis range={[60, 60]} />
          <Tooltip
            contentStyle={{ background: CHART_TOOLTIP_BG, border: `1px solid ${CHART_TOOLTIP_BORDER}`, borderRadius: 6, fontSize: 12 }}
            formatter={(v) => fmtNum(v as number, 3)}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Scatter name="Flash Crowd" data={fc} fill={CHART_FC} />
          <Scatter name="EDoS" data={edos} fill={CHART_EDOS} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

export function AnalysisResultsPage() {
  const [detection, setDetection] = useState<DetectionSummary | null>(null)
  const [shap, setShap] = useState<ShapSummaryResponse | null>(null)
  const [heatmap, setHeatmap] = useState<EndpointHeatmapResponse | null>(null)
  const [pca, setPca] = useState<PcaResponse | null>(null)

  useEffect(() => {
    api.detectionSummary().then(setDetection).catch(() => setDetection(null))
    api.shap().then(setShap).catch(() => setShap(null))
    api.endpointHeatmap().then(setHeatmap).catch(() => setHeatmap(null))
    api.pca().then(setPca).catch(() => setPca(null))
  }, [])

  return (
    <div>
      <div className="page-title">
        <h2>Analysis</h2>
      </div>
      <p className="page-subtitle">
        Feature Contribution &amp; Ablation — which feature families the detector actually relies on, and how
        separable EDoS and flash-crowd traffic are in feature space.
      </p>

      <div className="section">
        <div className="section-title">SHAP Feature Importance</div>
        {!shap ? (
          <p className="empty-note">Loading SHAP feature importance…</p>
        ) : shap.all_zero || shap.feature_importance.length === 0 ? (
          <p className="empty-note">No non-zero SHAP importances on disk yet — train the model and re-run explainability.</p>
        ) : (
          <GlobalShapChart rows={shap.feature_importance} />
        )}
      </div>

      <div className="section">
        <div className="section-title">Feature Contribution &amp; Ablation</div>
        {!detection ? (
          <p className="empty-note">Loading ablation results…</p>
        ) : (
          <>
            <AblationChart rows={detection.ablation_results ?? []} />
            {(detection.ablation_results?.length ?? 0) > 0 && (
              <div className="card table-scroll" style={{ marginTop: 12 }}>
                <table>
                  <thead>
                    <tr>
                      <th>Feature Set</th>
                      <th className="num">Recall (EDoS)</th>
                      <th className="num">Flash-Crowd FPR</th>
                      <th className="num">F1</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detection.ablation_results!.map((r) => (
                      <tr key={r.model}>
                        <td style={{ fontFamily: 'var(--mono)' }}>{r.model}</td>
                        <td className="num">{fmtPct(r.recall)}</td>
                        <td className="num">{fmtPct(r.flash_crowd_false_positive_rate)}</td>
                        <td className="num">{fmtPct(r.f1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </div>

      <div className="section">
        <div className="section-title">Endpoint Cost Heatmap</div>
        {!heatmap ? (
          <p className="empty-note">Loading endpoint cost apportionment…</p>
        ) : !heatmap.available ? (
          <p className="empty-note">{heatmap.detail ?? 'No endpoint cost data available yet.'}</p>
        ) : (
          <div className="card table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Endpoint Class</th>
                  <th className="num">Requests</th>
                  <th className="num">Request Share</th>
                  <th className="num">Apportioned Cost</th>
                  <th className="num">Cost / Request</th>
                </tr>
              </thead>
              <tbody>
                {heatmap.rows.map((r) => (
                  <tr key={r.endpoint_class}>
                    <td style={{ textTransform: 'capitalize' }}>{r.endpoint_class}</td>
                    <td className="num">{fmtNum(r.request_count, 0)}</td>
                    <td className="num">{fmtPct(r.request_share)}</td>
                    <td className="num">{fmtNum(r.apportioned_cost, 4)}</td>
                    <td className="num">{fmtNum(r.apportioned_cost_per_request, 5)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {heatmap.cost_apportionment_note && <p className="note-inline" style={{ marginTop: 10 }}>{heatmap.cost_apportionment_note}</p>}
          </div>
        )}
      </div>

      <div className="section">
        <div className="section-title">Separability</div>
        <PcaScatter pca={pca} />
      </div>

      <p className="footer-note" style={{ marginTop: 40 }}>
        Every chart and table on this page renders real values already computed by the research pipeline (SHAP,
        ablation, PCA, endpoint cost apportionment) — visual separation here does not by itself prove detection
        quality; see the Detection page for measured classification performance.
      </p>
    </div>
  )
}
