export function DemoWalkthrough({ steps }: { steps: string[] }) {
  if (steps.length === 0) return <p className="empty-note">No data available.</p>
  return (
    <div className="card">
      <ol className="walkthrough">
        {steps.map((s, i) => (
          <li key={i}>{s}</li>
        ))}
      </ol>
    </div>
  )
}
