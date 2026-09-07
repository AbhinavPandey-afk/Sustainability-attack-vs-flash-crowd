import { api } from '../api'
import { fmtNum } from '../format'
import type { HistoryEntry } from '../types'

export function DatasetExportPage({ history }: { history: HistoryEntry[] }) {
  if (history.length === 0) {
    return (
      <div>
        <div className="page-title">
          <h2>Dataset / Export</h2>
        </div>
        <p className="empty-note">No experiments have been run yet.</p>
      </div>
    )
  }

  return (
    <div>
      <div className="page-title">
        <h2>Dataset / Export</h2>
      </div>
      <p className="page-subtitle">
        Download the real metadata, features, config, and raw timeseries/Locust CSVs for any completed run —
        exactly the files this dashboard itself reads, zipped with no transformation.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Experiment</th>
              <th>Scenario</th>
              <th className="num">Requests</th>
              <th className="num">Est. Cost</th>
              <th>Export</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h) => (
              <tr key={h.experiment_id}>
                <td style={{ fontFamily: 'var(--mono)' }}>{h.experiment_id}</td>
                <td>
                  <span className={`badge ${h.label === 0 ? 'badge-fc' : 'badge-edos'}`}>{h.scenario_label}</span>
                </td>
                <td className="num">{h.metadata?.n_raw_samples ?? '—'}</td>
                <td className="num">{fmtNum(h.summary.estimated_cost, 4)}</td>
                <td>
                  <a href={api.exportUrl(h.experiment_id)}>Download .zip</a>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
