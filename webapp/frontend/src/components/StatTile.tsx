export function StatTile({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="stat-tile">
      <div className="stat-label">{label}</div>
      <div className="stat-value">
        {value}
        {unit && <span className="stat-unit">{unit}</span>}
      </div>
    </div>
  )
}
